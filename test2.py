import os
import json
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import shape, Polygon
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

def process_direct_file_access(layer, polygon_input, debug=False):
    """
    Process TIFF files directly from filesystem without going through GeoServer.
    """
    try:
        import glob
        
        # Handle geometry parsing
        if isinstance(polygon_input, str):
            polygon_input = json.loads(polygon_input)
        
        if isinstance(polygon_input, list) and len(polygon_input) >= 2:
            actual_geometry = polygon_input[0]
            polygon_geom = shape(actual_geometry)
        elif isinstance(polygon_input, dict):
            if polygon_input.get("type") == "FeatureCollection":
                if not polygon_input.get("features"):
                    return None
                polygon_geom = shape(polygon_input["features"][0]["geometry"])
            elif polygon_input.get("type") == "Feature":
                polygon_geom = shape(polygon_input["geometry"])
            else:
                polygon_geom = shape(polygon_input)
        else:
            return None
        
        print(f"📍 Direct file access - Clip bounds: {polygon_geom.bounds}")
        
        # Define possible locations for slope TIFF files
        possible_data_dirs = [
            # Actual GeoServer mosaic directory from your setup
            "/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May",
            
            # Common Windows GeoServer paths
            r"C:\Program Files (x86)\GeoServer 2.25.1\data_dir\data\useruploads",
            r"C:\Program Files\GeoServer\data_dir\data\useruploads", 
            r"D:\GeoServer\data_dir\data\useruploads",
            r".\data\useruploads",
            r".\tiffData",
            os.path.join(os.path.dirname(__file__), "tiffData"),
            r"C:\Users\adity\Downloads\tiff\tiffData"
        ]
        
        # Look for TIFF files
        slope_files = []
        for data_dir in possible_data_dirs:
            if os.path.exists(data_dir):
                print(f"🔍 Checking directory: {data_dir}")
                
                patterns = [
                    os.path.join(data_dir, "*.tif"),
                    os.path.join(data_dir, "*.tiff"),
                    os.path.join(data_dir, "*slope*.tif*"),
                    os.path.join(data_dir, f"{layer}*.tif*"),
                ]
                
                for pattern in patterns:
                    files = glob.glob(pattern, recursive=False)
                    slope_files.extend(files)
                    if files and debug:
                        print(f"✅ Found {len(files)} files with pattern: {pattern}")
        
        slope_files = list(set(slope_files))  # Remove duplicates
        print(f"📁 Total TIFF files found: {len(slope_files)}")
        
        if not slope_files:
            print("❌ No TIFF files found for direct access")
            return None
        
        # Process files that overlap with the geometry
        all_stats = {}
        valid_files = []
        
        for tiff_file in slope_files[:5]:  # Limit to first 5 for performance
            try:
                print(f"🔍 Processing: {os.path.basename(tiff_file)}")
                
                with rasterio.open(tiff_file) as src:
                    # Check overlap
                    raster_bounds = src.bounds
                    raster_polygon = shape({
                        "type": "Polygon",
                        "coordinates": [[
                            [raster_bounds.left, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.bottom]
                        ]]
                    })
                    
                    if not polygon_geom.intersects(raster_polygon):
                        continue
                    
                    print(f"✅ File overlaps: {os.path.basename(tiff_file)}")
                    
                    # Transform geometry if needed
                    clip_geom = polygon_geom
                    if src.crs and str(src.crs) != 'EPSG:4326':
                        try:
                            clip_geom_dict = transform_geom('EPSG:4326', src.crs, polygon_geom.__geo_interface__)
                            clip_geom = shape(clip_geom_dict)
                        except:
                            continue
                    
                    # Mask the raster
                    masked_data, _ = mask(src, [clip_geom], crop=True, nodata=src.nodata)
                    
                    # Calculate statistics
                    file_stats = {}
                    for band_idx in range(src.count):
                        band_data = masked_data[band_idx] if len(masked_data.shape) > 2 else masked_data
                        
                        if src.nodata is not None:
                            valid_mask = (band_data != src.nodata) & np.isfinite(band_data)
                        else:
                            valid_mask = np.isfinite(band_data)
                        
                        if valid_mask.any():
                            valid_data = band_data[valid_mask]
                            if len(valid_data) > 0:
                                band_key = f"band_{band_idx + 1}"
                                file_stats[band_key] = {
                                    'min': float(np.min(valid_data)),
                                    'max': float(np.max(valid_data)),
                                    'mean': float(np.mean(valid_data)),
                                    'std': float(np.std(valid_data)),
                                    'count': int(len(valid_data)),
                                    'data_type': str(src.dtypes[band_idx]),
                                    'file': os.path.basename(tiff_file)
                                }
                                print(f"📈 Band {band_idx + 1}: min={file_stats[band_key]['min']:.3f}, max={file_stats[band_key]['max']:.3f}")
                    
                    if file_stats:
                        all_stats[os.path.basename(tiff_file)] = file_stats
                        valid_files.append(tiff_file)
                        
            except Exception as file_error:
                if debug:
                    print(f"❌ Error processing {os.path.basename(tiff_file)}: {file_error}")
                continue
        
        if not all_stats:
            print("❌ No valid data found in direct file access")
            return None
        
        # Combine statistics
        combined_stats = {}
        for file_name, file_stats in all_stats.items():
            for band_key, band_stats in file_stats.items():
                if band_key not in combined_stats:
                    combined_stats[band_key] = {
                        'min': band_stats['min'],
                        'max': band_stats['max'],
                        'mean': band_stats['mean'],
                        'std': band_stats['std'],
                        'count': band_stats['count'],
                        'data_type': band_stats['data_type']
                    }
                else:
                    # Update with better (wider range) values
                    combined_stats[band_key]['min'] = min(combined_stats[band_key]['min'], band_stats['min'])
                    combined_stats[band_key]['max'] = max(combined_stats[band_key]['max'], band_stats['max'])
        
        print(f"📈 Direct file access - Combined statistics: {combined_stats}")
        
        from django.http import JsonResponse
        return JsonResponse({
            'status': 'success',
            'layer': layer,
            'min_max': combined_stats,
            'geometry_type': polygon_geom.geom_type,
            'clip_bounds': list(polygon_geom.bounds),
            'method': 'Direct file access',
            'files_processed': len(valid_files),
            'total_files_found': len(slope_files)
        })
        
    except Exception as e:
        print(f"❌ Direct file access error: {e}")
        return None

@csrf_exempt
def get_raster_stats(request):
    """
    Enhanced function to get original raster statistics from TIFF files.
    Supports direct file access and improved WMS/WCS handling.
    """
    try:
        data = json.loads(request.body)
        
        # Get layer name from frontend
        layer = data.get('layer_name') or data.get('layer')
        
        # Get clipping geometry from frontend
        polygon_input = data.get('polygon') or data.get('geometry') or data.get('vector_geometry')
        
        # Get enhancement flags
        debug = data.get('debug', False)
        prefer_wcs = data.get('prefer_wcs', False)
        use_native_crs = data.get('use_native_crs', False)
        fix_coordinates = data.get('fix_coordinates', True)
        buffer_geometry = data.get('buffer_geometry', False)
        method = data.get('method', 'auto')  # 'direct_file', 'wms', 'wcs', or 'auto'
        use_original_files = data.get('use_original_files', False)
        skip_wms = data.get('skip_wms', False)
        
        if not layer:
            return JsonResponse({'error': 'Layer name is required'}, status=400)
        
        if not polygon_input:
            return JsonResponse({'error': 'Clipping geometry is required'}, status=400)

        print(f"🎯 Enhanced processing for layer: {layer}")
        if debug:
            print(f"🔧 Debug mode: {debug}")
            print(f"🔧 Method: {method}")
            print(f"🔧 Use original files: {use_original_files}")
            print(f"🔧 Skip WMS: {skip_wms}")
        
        # Try direct file access first if requested
        if method == 'direct_file' or use_original_files:
            print("🔍 Attempting direct file access...")
            try:
                direct_result = process_direct_file_access(layer, polygon_input, debug)
                if direct_result:
                    return direct_result
                else:
                    print("⚠️ Direct file access failed, falling back to GeoServer methods")
            except Exception as direct_error:
                print(f"⚠️ Direct file access error: {direct_error}")
                if method == 'direct_file':  # If specifically requested direct file, return error
                    return JsonResponse({'error': f'Direct file access failed: {str(direct_error)}'}, status=500)
        
        # Handle geometry from frontend (GeoJSON format)
        if isinstance(polygon_input, str):
            try:
                polygon_input = json.loads(polygon_input)
            except:
                return JsonResponse({'error': 'Invalid geometry string format'}, status=400)
        
        # Handle Canvas layer geometry format [geometry, bounds]
        if isinstance(polygon_input, list) and len(polygon_input) >= 2:
            actual_geometry = polygon_input[0]
            polygon_geom = shape(actual_geometry)
        # Handle standard GeoJSON formats
        elif isinstance(polygon_input, dict):
            if polygon_input.get("type") == "FeatureCollection":
                if not polygon_input.get("features"):
                    return JsonResponse({'error': 'FeatureCollection is empty'}, status=400)
                polygon_geom = shape(polygon_input["features"][0]["geometry"])
            elif polygon_input.get("type") == "Feature":
                polygon_geom = shape(polygon_input["geometry"])
            else:
                polygon_geom = shape(polygon_input)
        else:
            return JsonResponse({'error': 'Unsupported geometry format'}, status=400)
        
        # Apply buffer if requested
        if buffer_geometry:
            buffer_size = 0.001  # ~100m buffer
            polygon_geom = polygon_geom.buffer(buffer_size)
            print(f"🔧 Applied {buffer_size} degree buffer to geometry")
        
        minx, miny, maxx, maxy = polygon_geom.bounds
        print(f"📍 Clip bounds: {minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f}")
        
        # Try multiple methods to get raw raster data (not WMS scaled values)
        geoserver_base_url = "http://192.168.0.158:8080/geoserver/useruploads"
        buffer = 0.001
        bbox_str = f"{minx-buffer},{miny-buffer},{maxx+buffer},{maxy+buffer}"
        
        # Method 1: Try direct file access via GeoServer's data directory REST API
        rest_url = f"http://192.168.0.158:8080/geoserver/rest/workspaces/useruploads/coveragestores/{layer}/coverages/{layer}.json"
        print(f"🔍 Checking layer metadata: {rest_url}")
        
        try:
            # Get layer metadata to find original file location
            rest_response = requests.get(rest_url, auth=('admin', 'geoserver'), timeout=10)
            if rest_response.status_code == 200:
                metadata = rest_response.json()
                # print(f"📋 Got layer metadata: {json.dumps(metadata, indent=2)}")
                
                # Try to extract file path from metadata
                coverage = metadata.get('coverage', {})
                if 'nativeCRS' in coverage:
                    print(f"🗺️ Native CRS: {coverage['nativeCRS']}")
                if 'nativeBoundingBox' in coverage:
                    bbox = coverage['nativeBoundingBox']
                    print(f"📍 Native bounds: {bbox}")
                
                # Look for file URL in various places
                if 'store' in coverage:
                    store_name = coverage['store']['name']
                    print(f"🗂️ Store name: {store_name}")
                    
                    # Extract just the store name without workspace prefix
                    if ':' in store_name:
                        actual_store_name = store_name.split(':')[1]
                    else:
                        actual_store_name = store_name
                    
                    # Try to get the store info to find file path
                    store_url = f"http://192.168.0.158:8080/geoserver/rest/workspaces/useruploads/coveragestores/{actual_store_name}.json"
                    print(f"🔍 Requesting store data: {store_url}")
                    store_response = requests.get(store_url, auth=('admin', 'geoserver'), timeout=10)
                    print(f"📊 Store response status: {store_response.status_code}")
                    if store_response.status_code != 200:
                        print(f"📊 Store response content: {store_response.text[:500]}...")
                    else:
                        print(f"✅ Store request successful")
                    if store_response.status_code == 200:
                        store_data = store_response.json()
                        print(f"🗂️ Store data: {json.dumps(store_data, indent=2)}")
                        
                        # Extract file path from store
                        store_info = store_data.get('coverageStore', {})
                        if 'url' in store_info:
                            file_url = store_info['url']
                            print(f"📁 Found file URL: {file_url}")
                            
                            # Convert file:// URL to local path
                            if file_url.startswith('file://'):
                                local_path = file_url.replace('file://', '').replace('file:', '')
                            elif file_url.startswith('file:'):
                                local_path = file_url.replace('file:', '')
                            else:
                                local_path = file_url
                            
                            print(f"📁 Raw file path from store: {local_path}")
                            
                            # Handle relative paths from GeoServer data directory
                            if not os.path.isabs(local_path):
                                # This is a relative path from GeoServer's data directory
                                # Try common GeoServer data directory locations
                                geoserver_data_dirs = [
                                    "C:/Program Files/GeoServer 2.26.0/data_dir",
                                    "C:/Program Files/GeoServer/data_dir", 
                                    "C:/GeoServer/data_dir",
                                    "C:/apache-tomcat-9.0.65/webapps/geoserver/data",
                                    "C:/Program Files/Apache Software Foundation/Tomcat 9.0/webapps/geoserver/data",
                                    os.path.join(os.path.expanduser("~"), "geoserver", "data_dir"),
                                    os.path.join(os.path.expanduser("~"), "GeoServer", "data_dir")
                                ]
                                
                                # Add environment variable if set
                                if os.getenv('GEOSERVER_DATA_DIR'):
                                    geoserver_data_dirs.insert(0, os.getenv('GEOSERVER_DATA_DIR'))
                                
                                print(f"🔍 Trying to resolve relative path: {local_path}")
                                for data_dir in geoserver_data_dirs:
                                    full_path = os.path.join(data_dir, local_path)
                                    print(f"   Checking: {full_path}")
                                    if os.path.exists(full_path):
                                        local_path = full_path
                                        print(f"🎯 ✅ RESOLVED to: {local_path}")
                                        break
                                else:
                                    print(f"⚠️ Could not resolve relative path to absolute path")
                                    # Continue with the relative path - might still work if we're in the right directory
                            
                            if os.path.exists(local_path):
                                print(f"🎯 Found original file via REST API: {local_path}")
                                
                                # Try to process original file directly
                                try:
                                        with rasterio.open(local_path) as src:
                                            print(f"📊 ORIGINAL FILE - Bands: {src.count}, Size: {src.width}x{src.height}, CRS: {src.crs}")
                                            print(f"📊 ORIGINAL FILE - Data type: {src.dtypes[0]}, NoData: {src.nodata}")
                                            print(f"📊 ORIGINAL FILE - Bounds: {src.bounds}")
                                            
                                            # Sample some data from original file to verify it's not all zeros
                                            sample_data = src.read(1, window=rasterio.windows.Window(0, 0, min(100, src.width), min(100, src.height)))
                                            print(f"🔍 ORIGINAL FILE - Sample data unique values: {np.unique(sample_data)}")
                                            print(f"🔍 ORIGINAL FILE - Sample data range: {np.min(sample_data)} to {np.max(sample_data)}")
                                            
                                            # Transform polygon to match original file CRS
                                            original_polygon_for_file = polygon_geom
                                            if src.crs != 'EPSG:4326':
                                                print(f"🔄 Transforming polygon from EPSG:4326 to {src.crs}")
                                                transformed_geom = transform_geom('EPSG:4326', src.crs, polygon_geom.__geo_interface__)
                                                original_polygon_for_file = shape(transformed_geom)
                                                print(f"📍 Transformed polygon bounds: {original_polygon_for_file.bounds}")
                                            
                                            # Try clipping with original file
                                            try:
                                                masked_data, mask_transform = mask(src, [original_polygon_for_file], crop=True, nodata=src.nodata)
                                                print(f"✅ Successfully clipped original file: {masked_data.shape}")
                                                
                                                min_max = {}
                                                for i in range(src.count):
                                                    band_data = masked_data[i] if len(masked_data.shape) == 3 else masked_data
                                                    
                                                    # Check if we have actual data
                                                    unique_vals = np.unique(band_data)
                                                    print(f"🔍 Original Band {i+1} unique values: {unique_vals[:10]}...")
                                                    
                                                    if src.nodata is not None:
                                                        valid_mask = band_data != src.nodata
                                                    else:
                                                        valid_mask = ~np.isnan(band_data)
                                                    
                                                    if np.sum(valid_mask) > 0:
                                                        valid_data = band_data[valid_mask]
                                                        band_stats = {
                                                            "min": float(np.min(valid_data)),
                                                            "max": float(np.max(valid_data)),
                                                            "mean": float(np.mean(valid_data)),
                                                            "std": float(np.std(valid_data)),
                                                            "count": int(np.sum(valid_mask)),
                                                            "data_type": str(src.dtypes[i])
                                                        }
                                                        min_max[f"band_{i+1}"] = band_stats
                                                    else:
                                                        # min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region"}
                                                        # min_max[f"band_{i+1}"] = "Null"
                                                        min_max[f"band_{i+1}"] = {
                                                            "min": "Null",
                                                            "max": "Null",
                                                            "mean": "Null",
                                                            "std": "Null",
                                                            "count": "Null",
                                                            "data_type": "Null"
                                                        }
                                                
                                                print(f"📈 ORIGINAL FILE statistics: {min_max}")
                                                
                                                return JsonResponse({
                                                    'status': 'success',
                                                    'layer': layer,
                                                    'min_max': min_max,
                                                    'geometry_type': original_polygon_for_file.geom_type,
                                                    'clip_bounds': list(original_polygon_for_file.bounds),
                                                    'method': 'Direct file access via REST API (original values)',
                                                    'raster_info': {
                                                        'bands': src.count,
                                                        'width': src.width,
                                                        'height': src.height,
                                                        'crs': str(src.crs),
                                                        'data_type': str(src.dtypes[0]),
                                                        'nodata': src.nodata,
                                                        'file_path': local_path
                                                    }
                                                })
                                                
                                            except Exception as mask_error:
                                                print(f"⚠️ Masking original file failed: {mask_error}")
                                                # Continue to other methods
                                        
                                except Exception as file_error:
                                    print(f"❌ Could not read original file: {file_error}")
                            else:
                                print(f"❌ File not found: {local_path}")
                                        
                    # If store data request failed, try to guess file path from layer name
                    else:
                        print(f"⚠️ Store request failed with status: {store_response.status_code}")
                        print(f"🔍 Trying to guess file paths for layer: {layer}")
                        
                        # Debug: Try to find GeoServer installation
                        print(f"🔍 Looking for GeoServer installation indicators...")
                        
                        # Check common GeoServer installation directories
                        geoserver_indicators = [
                            "C:/Program Files/GeoServer 2.26.0",
                            "C:/Program Files/GeoServer",
                            "C:/GeoServer",
                            "C:/apache-tomcat-9.0.65/webapps/geoserver",
                            "C:/Program Files/Apache Software Foundation"
                        ]
                        
                        for indicator in geoserver_indicators:
                            if os.path.exists(indicator):
                                print(f"✅ Found GeoServer indicator: {indicator}")
                                # List contents if it's a directory
                                try:
                                    contents = os.listdir(indicator)
                                    print(f"   Contents: {contents[:5]}...")  # Show first 5 items
                                except:
                                    pass
                            else:
                                print(f"❌ Not found: {indicator}")
                        
                        # Check current user's potential GeoServer directories
                        user_home = os.path.expanduser("~")
                        user_geoserver_paths = [
                            os.path.join(user_home, "geoserver"),
                            os.path.join(user_home, "GeoServer"),
                            os.path.join(user_home, ".geoserver")
                        ]
                        
                        for user_path in user_geoserver_paths:
                            if os.path.exists(user_path):
                                print(f"✅ Found user GeoServer directory: {user_path}")
                            else:
                                print(f"❌ User path not found: {user_path}")
                        
                        # Try common file patterns - expanded list for Windows
                        possible_direct_paths = [
                            # Actual GeoServer data directory from your setup
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/{layer}.tif",
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/{layer}.tiff",
                            
                            # Alternative names based on mosaic patterns
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/slopeAll_1.tif",
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/slopeAll_1.tiff",
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/slopeAll_Data.tif",
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/slopeAll_Data.tiff",
                            
                            # Pattern-based naming (common in mosaics)
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/*.tif",
                            f"/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May/*.tiff",
                            
                            # Common GeoServer installation paths
                            f"C:/Program Files/GeoServer 2.26.0/data_dir/data/useruploads/{layer}.tif",
                            f"C:/Program Files/GeoServer/data_dir/data/useruploads/{layer}.tif",
                            f"C:/GeoServer/data_dir/data/useruploads/{layer}.tif", 
                            f"C:/apache-tomcat-9.0.65/webapps/geoserver/data/useruploads/{layer}.tif",
                            f"C:/Program Files/Apache Software Foundation/Tomcat 9.0/webapps/geoserver/data/useruploads/{layer}.tif",
                            
                            # User directory installations
                            f"C:/Users/{os.getenv('USERNAME', 'user')}/geoserver/data_dir/data/useruploads/{layer}.tif",
                            f"C:/Users/{os.getenv('USERNAME', 'user')}/GeoServer/data_dir/data/useruploads/{layer}.tif",
                            
                            # Alternative file extensions
                            f"C:/Program Files/GeoServer 2.26.0/data_dir/data/useruploads/{layer}.tiff",
                            f"C:/Program Files/GeoServer/data_dir/data/useruploads/{layer}.tiff",
                            
                            # Current working directory
                            f"./{layer}.tif",
                            f"./data/useruploads/{layer}.tif",
                            f"./uploads/{layer}.tif",
                            
                            # Linux paths (in case)
                            f"/var/lib/geoserver_data/data/useruploads/{layer}.tif",
                            f"/opt/geoserver/data_dir/data/useruploads/{layer}.tif",
                            f"/home/geoserver/data_dir/data/useruploads/{layer}.tif"
                        ]
                        
                        print(f"🔍 Checking {len(possible_direct_paths)} possible file locations...")
                        
                        # First, try to scan the actual GeoServer directory for TIFF files
                        mosaic_dir = "/home/vicky/Documents/BAIF_GIS_Delivery/SlopeNew28May"
                        if os.path.exists(mosaic_dir):
                            print(f"✅ Found GeoServer mosaic directory: {mosaic_dir}")
                            try:
                                import glob
                                tiff_files = glob.glob(os.path.join(mosaic_dir, "*.tif")) + glob.glob(os.path.join(mosaic_dir, "*.tiff"))
                                print(f"📁 Found {len(tiff_files)} TIFF files in directory:")
                                for tiff_file in tiff_files[:5]:  # Show first 5
                                    print(f"   - {os.path.basename(tiff_file)}")
                                if len(tiff_files) > 5:
                                    print(f"   ... and {len(tiff_files) - 5} more")
                                
                                # Try each TIFF file in the directory
                                for tiff_path in tiff_files:
                                    print(f"🔍 Trying mosaic file: {tiff_path}")
                                    try:
                                        with rasterio.open(tiff_path) as src:
                                            print(f"📊 MOSAIC FILE - Bands: {src.count}, Size: {src.width}x{src.height}, CRS: {src.crs}")
                                            
                                            # Sample data to verify it's not empty
                                            sample_data = src.read(1, window=rasterio.windows.Window(0, 0, min(100, src.width), min(100, src.height)))
                                            unique_vals = np.unique(sample_data)
                                            print(f"🔍 MOSAIC FILE - Sample unique values: {unique_vals[:10]}...")
                                            print(f"🔍 MOSAIC FILE - Sample range: {np.min(sample_data)} to {np.max(sample_data)}")
                                            
                                            # Transform polygon to match file CRS
                                            mosaic_polygon = polygon_geom
                                            if src.crs != 'EPSG:4326':
                                                print(f"🔄 Transforming polygon from EPSG:4326 to {src.crs}")
                                                transformed_geom = transform_geom('EPSG:4326', src.crs, polygon_geom.__geo_interface__)
                                                mosaic_polygon = shape(transformed_geom)
                                                print(f"📍 Transformed polygon bounds: {mosaic_polygon.bounds}")
                                            
                                            # Check if polygon intersects with this TIFF
                                            tiff_bounds = src.bounds
                                            print(f"📍 TIFF bounds: {tiff_bounds}")
                                            
                                            # Create a polygon from TIFF bounds
                                            tiff_bounds_geom = shape({
                                                "type": "Polygon",
                                                "coordinates": [[
                                                    [tiff_bounds.left, tiff_bounds.bottom],
                                                    [tiff_bounds.right, tiff_bounds.bottom],
                                                    [tiff_bounds.right, tiff_bounds.top],
                                                    [tiff_bounds.left, tiff_bounds.top],
                                                    [tiff_bounds.left, tiff_bounds.bottom]
                                                ]]
                                            })
                                            
                                            if mosaic_polygon.intersects(tiff_bounds_geom):
                                                print(f"✅ Polygon intersects with TIFF: {os.path.basename(tiff_path)}")
                                                
                                                # Try clipping
                                                try:
                                                    masked_data, mask_transform = mask(src, [mosaic_polygon], crop=True, nodata=src.nodata)
                                                    print(f"✅ Successfully clipped mosaic file: {masked_data.shape}")
                                                    
                                                    # Calculate statistics
                                                    min_max = {}
                                                    for i in range(src.count):
                                                        band_data = masked_data[i] if len(masked_data.shape) == 3 else masked_data
                                                        
                                                        if src.nodata is not None:
                                                            valid_mask = band_data != src.nodata
                                                        else:
                                                            valid_mask = ~np.isnan(band_data)
                                                        
                                                        if np.sum(valid_mask) > 0:
                                                            valid_data = band_data[valid_mask]
                                                            band_stats = {
                                                                "min": float(np.min(valid_data)),
                                                                "max": float(np.max(valid_data)),
                                                                "mean": float(np.mean(valid_data)),
                                                                "std": float(np.std(valid_data)),
                                                                "count": int(np.sum(valid_mask)),
                                                                "data_type": str(src.dtypes[i])
                                                            }
                                                            min_max[f"band_{i+1}"] = band_stats
                                                        else:
                                                            min_max[f"band_{i+1}"] = {
                                                                "min": "Null",
                                                                "max": "Null",
                                                                "mean": "Null",
                                                                "std": "Null",
                                                                "count": "Null",
                                                                "data_type": "Null"
                                                            }
                                                    
                                                    print(f"📈 MOSAIC FILE statistics: {min_max}")
                                                    
                                                    return JsonResponse({
                                                        'status': 'success',
                                                        'layer': layer,
                                                        'min_max': min_max,
                                                        'geometry_type': mosaic_polygon.geom_type,
                                                        'clip_bounds': list(mosaic_polygon.bounds),
                                                        'method': f'Direct mosaic file access (file: {os.path.basename(tiff_path)})',
                                                        'raster_info': {
                                                            'bands': src.count,
                                                            'width': src.width,
                                                            'height': src.height,
                                                            'crs': str(src.crs),
                                                            'data_type': str(src.dtypes[0]),
                                                            'nodata': src.nodata,
                                                            'file_path': tiff_path
                                                        }
                                                    })
                                                    
                                                except Exception as mask_error:
                                                    print(f"⚠️ Masking failed for {tiff_path}: {mask_error}")
                                                    continue
                                            else:
                                                print(f"❌ No intersection with {os.path.basename(tiff_path)}")
                                                
                                    except Exception as tiff_error:
                                        print(f"❌ Could not read {tiff_path}: {tiff_error}")
                                        continue
                                        
                            except Exception as scan_error:
                                print(f"⚠️ Error scanning mosaic directory: {scan_error}")
                        else:
                            print(f"❌ Mosaic directory not found: {mosaic_dir}")
                        
                        # Try to find GeoServer data directory from environment variables
                        geoserver_data_dir = os.getenv('GEOSERVER_DATA_DIR')
                        if geoserver_data_dir:
                            print(f"🌍 Found GEOSERVER_DATA_DIR environment variable: {geoserver_data_dir}")
                            env_path = os.path.join(geoserver_data_dir, 'data', 'useruploads', f'{layer}.tif')
                            possible_direct_paths.insert(0, env_path)
                        
                        for i, file_path in enumerate(possible_direct_paths, 1):
                            print(f"📁 {i:2d}. Checking: {file_path}")
                            if os.path.exists(file_path):
                                print(f"🎯 ✅ FOUND original file by guessing: {file_path}")
                                try:
                                    with rasterio.open(file_path) as src:
                                        print(f"📊 ORIGINAL FILE - Bands: {src.count}, Size: {src.width}x{src.height}, CRS: {src.crs}")
                                        print(f"📊 ORIGINAL FILE - Data type: {src.dtypes[0]}, NoData: {src.nodata}")
                                        print(f"📊 ORIGINAL FILE - Bounds: {src.bounds}")
                                        
                                        # Sample some data from original file
                                        sample_data = src.read(1, window=rasterio.windows.Window(0, 0, min(100, src.width), min(100, src.height)))
                                        print(f"🔍 ORIGINAL FILE - Sample data unique values: {np.unique(sample_data)[:10]}...")
                                        print(f"🔍 ORIGINAL FILE - Sample data range: {np.min(sample_data)} to {np.max(sample_data)}")
                                        
                                        # Transform polygon to match original file CRS
                                        original_polygon_for_file = polygon_geom
                                        if src.crs != 'EPSG:4326':
                                            print(f"🔄 Transforming polygon from EPSG:4326 to {src.crs}")
                                            transformed_geom = transform_geom('EPSG:4326', src.crs, polygon_geom.__geo_interface__)
                                            original_polygon_for_file = shape(transformed_geom)
                                            print(f"📍 Transformed polygon bounds: {original_polygon_for_file.bounds}")
                                        
                                        # Try clipping with original file
                                        try:
                                            masked_data, mask_transform = mask(src, [original_polygon_for_file], crop=True, nodata=src.nodata)
                                            print(f"✅ Successfully clipped original file: {masked_data.shape}")
                                            
                                            min_max = {}
                                            for i in range(src.count):
                                                band_data = masked_data[i] if len(masked_data.shape) == 3 else masked_data
                                                
                                                # Check if we have actual data
                                                unique_vals = np.unique(band_data)
                                                print(f"🔍 Original Band {i+1} unique values: {unique_vals[:10]}...")
                                                
                                                if src.nodata is not None:
                                                    valid_mask = band_data != src.nodata
                                                else:
                                                    valid_mask = ~np.isnan(band_data)
                                                
                                                if np.sum(valid_mask) > 0:
                                                    valid_data = band_data[valid_mask]
                                                    band_stats = {
                                                        "min": float(np.min(valid_data)),
                                                        "max": float(np.max(valid_data)),
                                                        "mean": float(np.mean(valid_data)),
                                                        "std": float(np.std(valid_data)),
                                                        "count": int(np.sum(valid_mask)),
                                                        "data_type": str(src.dtypes[i])
                                                    }
                                                    min_max[f"band_{i+1}"] = band_stats
                                                else:
                                                    # min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region"}
                                                    # min_max[f"band_{i+1}"] = "Null"
                                                    min_max[f"band_{i+1}"] = {
                                                        "min": "Null",
                                                        "max": "Null",
                                                        "mean": "Null",
                                                        "std": "Null",
                                                        "count": "Null",
                                                        "data_type": "Null"
                                                    }

                                            print(f"📈 ORIGINAL FILE statistics: {min_max}")
                                            
                                            return JsonResponse({
                                                'status': 'success',
                                                'layer': layer,
                                                'min_max': min_max,
                                                'geometry_type': original_polygon_for_file.geom_type,
                                                'clip_bounds': list(original_polygon_for_file.bounds),
                                                'method': 'Direct file access via path guessing (original values)',
                                                'raster_info': {
                                                    'bands': src.count,
                                                    'width': src.width,
                                                    'height': src.height,
                                                    'crs': str(src.crs),
                                                    'data_type': str(src.dtypes[0]),
                                                    'nodata': src.nodata,
                                                    'file_path': file_path
                                                }
                                            })
                                            
                                        except Exception as mask_error:
                                            print(f"⚠️ Masking original file failed: {mask_error}")
                                            # Continue trying other paths
                                    
                                except Exception as file_error:
                                    print(f"❌ Could not read guessed file: {file_error}")
                                    continue
                                
                                # If we successfully opened the file but masking failed, break to continue with other methods
                                break
                
        except Exception as rest_error:
            print(f"⚠️ REST API failed: {rest_error}")
        
        # Method 2: Try WCS GetCoverage for raw data
        # Use native CRS if we found it in metadata, otherwise default to EPSG:4326
        native_crs = None
        try:
            # Extract CRS from any metadata we might have gotten
            if 'metadata' in locals() and metadata:
                coverage_info = metadata.get('coverage', {})
                srs = coverage_info.get('srs', 'EPSG:4326')
                native_crs = srs
                print(f"🗺️ Using native CRS for WCS: {native_crs}")
        except:
            pass
        
        if not native_crs:
            native_crs = 'EPSG:4326'
        
        # Transform clip bounds to native CRS if needed
        wcs_minx, wcs_miny, wcs_maxx, wcs_maxy = minx, miny, maxx, maxy
        if native_crs != 'EPSG:4326':
            try:
                from pyproj import Transformer
                transformer = Transformer.from_crs('EPSG:4326', native_crs, always_xy=True)
                wcs_minx, wcs_miny = transformer.transform(minx, miny)
                wcs_maxx, wcs_maxy = transformer.transform(maxx, maxy)
                print(f"🔄 Transformed bounds to {native_crs}: {wcs_minx:.2f}, {wcs_miny:.2f}, {wcs_maxx:.2f}, {wcs_maxy:.2f}")
            except Exception as transform_error:
                print(f"⚠️ Could not transform bounds to native CRS: {transform_error}")
                # Continue with EPSG:4326 bounds
        
        if native_crs == 'EPSG:4326':
            wcs_url = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=2.0.1&request=GetCoverage&"
                f"coverageId=useruploads:{layer}&"
                f"subset=Long({wcs_minx-buffer},{wcs_maxx+buffer})&"
                f"subset=Lat({wcs_miny-buffer},{wcs_maxy+buffer})&"
                f"format=image/geotiff&"
                f"outputCRS={native_crs}"
            )
        else:
            # For projected CRS, try different axis naming conventions
            # Some GeoServer versions use different axis names
            wcs_url = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=2.0.1&request=GetCoverage&"
                f"coverageId=useruploads:{layer}&"
                f"subset=E({wcs_minx-buffer},{wcs_maxx+buffer})&"
                f"subset=N({wcs_miny-buffer},{wcs_maxy+buffer})&"
                f"format=image/geotiff&"
                f"outputCRS={native_crs}"
            )
        
        print(f"🌐 Trying WCS for raw data: {wcs_url}")
        
        try:
            response = requests.get(wcs_url, timeout=30)
            print(f"📊 WCS Response status: {response.status_code}")
            print(f"📊 WCS Response headers: {response.headers.get('content-type', 'unknown')}")
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('image/'):
                    print("✅ Got raw data via WCS")
                    raster_data = BytesIO(response.content)
                else:
                    print(f"⚠️ WCS returned non-image content: {content_type}")
                    print(f"📄 WCS Response content preview: {response.text[:500]}...")
                    raise Exception("WCS failed - non-image response")
            else:
                print(f"❌ WCS failed with status {response.status_code}")
                print(f"📄 WCS Error content: {response.text[:500]}...")
                raise Exception(f"WCS failed with status {response.status_code}")
                
        except Exception as wcs_error:
            print(f"⚠️ WCS failed: {wcs_error}")
            
            # Try alternative WCS versions and formats
            print("🔄 Trying WCS version 1.1.1...")
            wcs_url_v11 = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=1.1.1&request=GetCoverage&"
                f"identifier=useruploads:{layer}&"
                f"BoundingBox={wcs_minx-buffer},{wcs_miny-buffer},{wcs_maxx+buffer},{wcs_maxy+buffer},{native_crs}&"
                f"format=image/geotiff&"
                f"GridCS={native_crs}&"
                f"GridType=urn:ogc:def:method:WCS:1.1:2dSimpleGrid"
            )
            
            try:
                response = requests.get(wcs_url_v11, timeout=30)
                print(f"📊 WCS v1.1.1 Response status: {response.status_code}")
                print(f"📊 WCS v1.1.1 Response headers: {response.headers.get('content-type', 'unknown')}")
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    if content_type.startswith('image/'):
                        print("✅ Got raw data via WCS v1.1.1")
                        raster_data = BytesIO(response.content)
                    else:
                        print(f"⚠️ WCS v1.1.1 returned non-image content: {content_type}")
                        print(f"📄 WCS v1.1.1 Response content preview: {response.text[:500]}...")
                        raise Exception("WCS v1.1.1 failed - non-image response")
                else:
                    print(f"❌ WCS v1.1.1 failed with status {response.status_code}")
                    raise Exception(f"WCS v1.1.1 failed with status {response.status_code}")
                    
            except Exception as wcs_v11_error:
                print(f"⚠️ WCS v1.1.1 failed: {wcs_v11_error}")
                
                # Try WCS 1.0.0 as final WCS attempt
                print("🔄 Trying WCS version 1.0.0...")
                wcs_url_v10 = (
                    f"{geoserver_base_url}/wcs?"
                    f"service=WCS&version=1.0.0&request=GetCoverage&"
                    f"coverage=useruploads:{layer}&"
                    f"bbox={wcs_minx-buffer},{wcs_miny-buffer},{wcs_maxx+buffer},{wcs_maxy+buffer}&"
                    f"crs={native_crs}&"
                    f"response_crs={native_crs}&"
                    f"format=GeoTIFF&"
                    f"width=1024&height=1024"
                )
                
                try:
                    response = requests.get(wcs_url_v10, timeout=30)
                    print(f"📊 WCS v1.0.0 Response status: {response.status_code}")
                    print(f"📊 WCS v1.0.0 Response headers: {response.headers.get('content-type', 'unknown')}")
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '')
                        if content_type.startswith('image/') or 'tiff' in content_type.lower():
                            print("✅ Got raw data via WCS v1.0.0")
                            raster_data = BytesIO(response.content)
                        else:
                            print(f"⚠️ WCS v1.0.0 returned non-image content: {content_type}")
                            raise Exception("All WCS versions failed")
                    else:
                        print(f"❌ WCS v1.0.0 failed with status {response.status_code}")
                        raise Exception("All WCS versions failed")
                        
                except Exception as wcs_v10_error:
                    print(f"⚠️ WCS v1.0.0 failed: {wcs_v10_error}")
            
            # Method 3: Try WMS with specific parameters to minimize processing
            print("🔄 Trying multiple WMS approaches...")
            
            # Try 1: Raw WMS without styling
            wms_url_raw = (
                f"{geoserver_base_url}/wms?"
                f"service=WMS&version=1.3.0&request=GetMap&"
                f"layers=useruploads:{layer}&"
                f"bbox={minx-buffer},{miny-buffer},{maxx+buffer},{maxy+buffer}&"
                f"width=1024&height=1024&"
                f"crs=EPSG:4326&"
                f"format=image/geotiff&"
                f"styles="
            )
            
            # Try 2: Same with native CRS if different from 4326
            if native_crs != 'EPSG:4326':
                wms_url_native = (
                    f"{geoserver_base_url}/wms?"
                    f"service=WMS&version=1.3.0&request=GetMap&"
                    f"layers=useruploads:{layer}&"
                    f"bbox={wcs_minx-buffer},{wcs_miny-buffer},{wcs_maxx+buffer},{wcs_maxy+buffer}&"
                    f"width=1024&height=1024&"
                    f"crs={native_crs}&"
                    f"format=image/geotiff&"
                    f"styles="
                )
                wms_urls_to_try = [wms_url_native, wms_url_raw]
            else:
                wms_urls_to_try = [wms_url_raw]
                
                wms_success = False
                for i, wms_url in enumerate(wms_urls_to_try, 1):
                    print(f"🌐 Trying WMS approach {i}: {wms_url}")
                    
                    try:
                        response = requests.get(wms_url, timeout=30)
                        print(f"📊 WMS Response {i} status: {response.status_code}")
                        response.raise_for_status()
                        
                        content_type = response.headers.get('content-type', '')
                        if not content_type.startswith('image/'):
                            error_text = response.text
                            print(f"⚠️ WMS {i} returned non-image: {content_type}")
                            print(f"📄 Error content: {error_text[:300]}...")
                            
                            if 'LayerNotDefined' in error_text:
                                return JsonResponse({
                                    'error': f'Layer "useruploads:{layer}" not found on GeoServer',
                                    'layer': layer
                                }, status=404)
                            continue
                        
                        raster_data = BytesIO(response.content)
                        print(f"✅ Got data via WMS approach {i}")
                        wms_success = True
                        break
                        
                    except requests.exceptions.RequestException as e:
                        print(f"❌ WMS approach {i} failed: {e}")
                        continue
                
                if not wms_success:
                    print(f"❌ All GeoServer methods failed")
                    return JsonResponse({'error': 'Could not access raster data via any GeoServer method'}, status=500)
        
        
        # Process the raster data and calculate statistics
        try:
            with rasterio.open(raster_data) as ds:
                print(f"📊 Raster info: {ds.count} bands, {ds.width}x{ds.height}, CRS: {ds.crs}")
                print(f"📊 Data type: {ds.dtypes[0]}, NoData: {ds.nodata}")
                print(f"📊 Raster bounds: {ds.bounds}")
                
                # Sample some data from the raster to understand what we're working with
                print("🔍 Sampling raster data to check for actual values...")
                sample_window = rasterio.windows.Window(0, 0, min(100, ds.width), min(100, ds.height))
                sample_data = ds.read(1, window=sample_window)
                unique_sample_values = np.unique(sample_data)
                print(f"🔍 Sample data unique values (first 20): {unique_sample_values[:20]}")
                print(f"🔍 Sample data range: {np.min(sample_data)} to {np.max(sample_data)}")
                print(f"🔍 Sample data non-zero count: {np.count_nonzero(sample_data)} / {sample_data.size}")
                
                # Check if the entire raster is just zeros/nodata
                if len(unique_sample_values) == 1 and unique_sample_values[0] == (ds.nodata or 0):
                    print("⚠️ WARNING: Sample data contains only nodata values!")
                    print("💡 This might indicate:")
                    print("   - Wrong area requested (outside raster extent)")
                    print("   - Raster has no data in the sampled region")
                    print("   - WCS request parameters might be incorrect")
                elif len(unique_sample_values) <= 3 and all(v in [0, ds.nodata or 0] for v in unique_sample_values):
                    print("⚠️ WARNING: Sample data contains mostly nodata/zero values")
                else:
                    print(f"✅ Sample data looks good - found {len(unique_sample_values)} unique values")
                
                # Check if this looks like processed/scaled data
                if str(ds.dtypes[0]) == 'uint8' and ds.nodata == 0.0:
                    print("⚠️ WARNING: Data appears to be WMS-processed (uint8, 0-255 range)")
                    print("📊 This may not represent original pixel values")
                    
                    # Try to get actual data range from metadata
                    if 'metadata' in locals() and metadata:
                        coverage = metadata.get('coverage', {})
                        dimensions = coverage.get('dimensions', {})
                        if 'coverageDimension' in dimensions:
                            dim_info = dimensions['coverageDimension']
                            if isinstance(dim_info, dict) and 'range' in dim_info:
                                data_range = dim_info['range']
                                actual_min = data_range.get('min', 'unknown')
                                actual_max = data_range.get('max', 'unknown')
                                print(f"📊 Original data range from metadata: {actual_min} to {actual_max}")
                                
                                # Store this for later use in scaling
                                if actual_min != 'unknown' and actual_max != 'unknown' and actual_min != '-inf' and actual_max != 'inf':
                                    try:
                                        original_min = float(actual_min)
                                        original_max = float(actual_max)
                                        print(f"📊 Will attempt to rescale from 0-255 to {original_min:.2f}-{original_max:.2f}")
                                        has_scaling_info = True
                                        scaling_min = original_min
                                        scaling_max = original_max
                                    except:
                                        has_scaling_info = False
                                else:
                                    has_scaling_info = False
                            else:
                                has_scaling_info = False
                        else:
                            has_scaling_info = False
                    else:
                        has_scaling_info = False
                else:
                    has_scaling_info = False
                
                # Check if bounds are swapped (common WMS issue)
                raster_bounds = ds.bounds
                polygon_bounds = polygon_geom.bounds
                
                print(f"📍 Polygon bounds: {polygon_bounds}")
                print(f"📍 Raw raster bounds: {raster_bounds}")
                
                # For WCS data in projected coordinates, don't swap - it should be correct
                # Only apply swapping logic for WMS data that might have coordinate issues
                bounds_swapped = False
                
                # Only check for swapping if we got this data from WMS (not WCS)
                if str(ds.dtypes[0]) == 'uint8':  # This indicates WMS data
                    print("🔍 Checking WMS data for coordinate swapping...")
                    
                    # Check if the "left" bound looks like a latitude (20-30 range for Delhi)
                    if (20 <= raster_bounds.left <= 35 and 70 <= raster_bounds.bottom <= 85):
                        print("🔄 Detected swapped coordinates: left/bottom appear to be lat/lon instead of lon/lat")
                        bounds_swapped = True
                    
                    # Alternative check: if left > right or bottom > top, definitely swapped
                    elif (raster_bounds.left > raster_bounds.right or raster_bounds.bottom > raster_bounds.top):
                        print("🔄 Detected swapped coordinates: left>right or bottom>top")
                        bounds_swapped = True
                    
                    # Another check: if polygon and raster bounds don't overlap at all, try swapping
                    elif not (raster_bounds.left <= polygon_bounds[2] and raster_bounds.right >= polygon_bounds[0] and
                             raster_bounds.bottom <= polygon_bounds[3] and raster_bounds.top >= polygon_bounds[1]):
                        print("🔄 No overlap detected, trying coordinate swap")
                        bounds_swapped = True
                else:
                    print("🔍 WCS data detected - using coordinates as-is (no swapping)")
                    # For WCS data, check if we have reasonable overlap
                    if ds.crs == 'EPSG:32643':  # UTM coordinates
                        # Transform polygon to UTM for comparison
                        from pyproj import Transformer
                        try:
                            transformer = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True)
                            utm_minx, utm_miny = transformer.transform(polygon_bounds[0], polygon_bounds[1])
                            utm_maxx, utm_maxy = transformer.transform(polygon_bounds[2], polygon_bounds[3])
                            print(f"📍 Polygon in UTM: ({utm_minx:.1f}, {utm_miny:.1f}, {utm_maxx:.1f}, {utm_maxy:.1f})")
                            
                            # Check overlap in UTM coordinates
                            if (utm_minx < raster_bounds.right and utm_maxx > raster_bounds.left and
                                utm_miny < raster_bounds.top and utm_maxy > raster_bounds.bottom):
                                print("✅ Polygon and raster bounds overlap in UTM coordinates")
                            else:
                                print("⚠️ No overlap in UTM coordinates - polygon might be outside raster extent")
                        except Exception as e:
                            print(f"⚠️ Could not check UTM overlap: {e}")
                    elif ds.crs == 'EPSG:4326':  # Geographic coordinates
                        # Check overlap directly
                        if (polygon_bounds[0] < raster_bounds.right and polygon_bounds[2] > raster_bounds.left and
                            polygon_bounds[1] < raster_bounds.top and polygon_bounds[3] > raster_bounds.bottom):
                            print("✅ Polygon and raster bounds overlap in geographic coordinates")
                        else:
                            print("⚠️ No overlap in geographic coordinates")
                    
                if bounds_swapped:
                    # Swap coordinates: left<->bottom, right<->top
                    corrected_left = raster_bounds.bottom
                    corrected_bottom = raster_bounds.left  
                    corrected_right = raster_bounds.top
                    corrected_top = raster_bounds.right
                    
                    print(f"📍 Corrected bounds: left={corrected_left}, bottom={corrected_bottom}, right={corrected_right}, top={corrected_top}")
                    
                    # Use corrected bounds for overlap check
                    raster_bounds_geom = shape({
                        "type": "Polygon",
                        "coordinates": [[
                            [corrected_left, corrected_bottom],
                            [corrected_right, corrected_bottom],
                            [corrected_right, corrected_top],
                            [corrected_left, corrected_top],
                            [corrected_left, corrected_bottom]
                        ]]
                    })
                    
                    # Also create a corrected transform for masking
                    # We need to swap the coordinates in the actual data processing too
                    coordinates_swapped = True
                else:
                    # Use original bounds
                    raster_bounds_geom = shape({
                        "type": "Polygon",
                        "coordinates": [[
                            [raster_bounds.left, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.bottom]
                        ]]
                    })
                    coordinates_swapped = False
                
                print(f"📍 Final raster geometry bounds: {raster_bounds_geom.bounds}")
                
                # Transform polygon to match raster CRS if needed
                original_polygon = polygon_geom
                if ds.crs and ds.crs != 'EPSG:4326':
                    print(f"🔄 Transforming polygon from EPSG:4326 to {ds.crs}")
                    try:
                        transformed_geom = transform_geom('EPSG:4326', ds.crs, polygon_geom.__geo_interface__)
                        polygon_geom = shape(transformed_geom)
                        print(f"📍 Transformed polygon bounds: {polygon_geom.bounds}")
                        
                        # Double-check the transformation worked correctly
                        transformed_bounds = polygon_geom.bounds
                        print(f"📊 Transformed polygon: ({transformed_bounds[0]:.1f}, {transformed_bounds[1]:.1f}, {transformed_bounds[2]:.1f}, {transformed_bounds[3]:.1f})")
                        print(f"📊 Raster bounds:       ({raster_bounds.left:.1f}, {raster_bounds.bottom:.1f}, {raster_bounds.right:.1f}, {raster_bounds.top:.1f})")
                        
                        # Check if transformation looks reasonable for UTM
                        if str(ds.crs) == 'EPSG:32643':
                            # UTM Zone 43N coordinates should be in the range of 600k-800k for X and 3M-3.3M for Y in Delhi area
                            if (600000 <= transformed_bounds[0] <= 800000 and 3000000 <= transformed_bounds[1] <= 3300000):
                                print("✅ Transformed polygon coordinates look reasonable for UTM Zone 43N")
                            else:
                                print(f"⚠️ Transformed polygon coordinates seem outside expected UTM range")
                        
                    except Exception as transform_error:
                        print(f"⚠️ Coordinate transformation failed: {transform_error}")
                        # Continue with original polygon
                else:
                    print("🔍 Raster and polygon are both in EPSG:4326 - no transformation needed")
                
                # Check if polygon overlaps with raster bounds
                if bounds_swapped:
                    # Use corrected bounds for overlap check (only for WMS data)
                    raster_bounds_geom = shape({
                        "type": "Polygon",
                        "coordinates": [[
                            [corrected_left, corrected_bottom],
                            [corrected_right, corrected_bottom],
                            [corrected_right, corrected_top],
                            [corrected_left, corrected_top],
                            [corrected_left, corrected_bottom]
                        ]]
                    })
                    coordinates_swapped = True
                else:
                    # Use original bounds (normal case for WCS data)
                    raster_bounds_geom = shape({
                        "type": "Polygon",
                        "coordinates": [[
                            [raster_bounds.left, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.bottom],
                            [raster_bounds.right, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.top],
                            [raster_bounds.left, raster_bounds.bottom]
                        ]]
                    })
                    coordinates_swapped = False
                
                print(f"📍 Final raster geometry bounds: {raster_bounds_geom.bounds}")
                
                # For WCS data in projected coordinates, use direct overlap check
                if not bounds_swapped and ds.crs == 'EPSG:32643':
                    # Check overlap in projected coordinates
                    poly_bounds = polygon_geom.bounds
                    if (poly_bounds[0] < raster_bounds.right and poly_bounds[2] > raster_bounds.left and
                        poly_bounds[1] < raster_bounds.top and poly_bounds[3] > raster_bounds.bottom):
                        print("✅ Polygon overlaps with raster bounds in projected coordinates")
                        polygon_overlaps = True
                    else:
                        print("❌ No overlap between polygon and raster in projected coordinates")
                        polygon_overlaps = False
                else:
                    # Use geometric intersection check
                    polygon_overlaps = polygon_geom.intersects(raster_bounds_geom)
                    if polygon_overlaps:
                        print("✅ Polygon overlaps with raster bounds")
                    else:
                        print("❌ No geometric overlap detected")
                
                if not polygon_overlaps:
                    print(f"❌ Polygon bounds {polygon_geom.bounds} do not overlap with raster bounds {raster_bounds_geom.bounds}")
                    print("🔍 Trying to find intersection or use raster bounds...")
                    
                    # Try to intersect with raster bounds
                    intersection = polygon_geom.intersection(raster_bounds_geom)
                    if intersection.is_empty or intersection.area < 1e-10:
                        # If no intersection, use a sample area from the raster center
                        rb = raster_bounds_geom.bounds
                        center_x = (rb[0] + rb[2]) / 2
                        center_y = (rb[1] + rb[3]) / 2
                        sample_size = min(rb[2] - rb[0], rb[3] - rb[1]) * 0.1
                        
                        polygon_geom = Polygon([
                            (center_x - sample_size/2, center_y - sample_size/2),
                            (center_x + sample_size/2, center_y - sample_size/2),
                            (center_x + sample_size/2, center_y + sample_size/2),
                            (center_x - sample_size/2, center_y + sample_size/2),
                            (center_x - sample_size/2, center_y - sample_size/2)
                        ])
                        print(f"🎯 Using center sample area: {polygon_geom.bounds}")
                    else:
                        polygon_geom = intersection
                        print(f"🎯 Using intersection area: {polygon_geom.bounds}")
                else:
                    print("✅ Polygon overlaps with raster bounds")
                
                # Clip the raster with the polygon geometry
                try:
                    # First try with the polygon as-is
                    print(f"🔍 About to mask with polygon. Polygon type: {type(polygon_geom)}")
                    print(f"🔍 Polygon bounds: {polygon_geom.bounds}")
                    print(f"🔍 Polygon area: {polygon_geom.area}")
                    print(f"🔍 Is polygon valid: {polygon_geom.is_valid}")
                    
                    masked_data, mask_transform = mask(ds, [polygon_geom], crop=True, nodata=ds.nodata, filled=True)
                    print(f"✅ Successfully clipped raster: {masked_data.shape}")
                    
                    # Analyze the masked data
                    print(f"🔍 Masked data type: {masked_data.dtype}")
                    print(f"🔍 Masked data shape: {masked_data.shape}")
                    band_data = masked_data[0] if len(masked_data.shape) > 2 else masked_data
                    
                    unique_values = np.unique(band_data)
                    print(f"🔍 Unique values in masked data (first 20): {unique_values[:20]}")
                    print(f"🔍 Total unique values: {len(unique_values)}")
                    print(f"🔍 Data range: {np.min(band_data)} to {np.max(band_data)}")
                    
                    # Check for nodata values
                    if ds.nodata is not None:
                        nodata_count = np.sum(band_data == ds.nodata)
                        valid_count = np.sum(band_data != ds.nodata)
                        print(f"🔍 NoData count: {nodata_count}, Valid data count: {valid_count}")
                    else:
                        print(f"🔍 No explicit nodata value set")
                        
                    # Check if we have any non-zero values
                    nonzero_count = np.count_nonzero(band_data)
                    print(f"🔍 Non-zero values: {nonzero_count} / {band_data.size}")
                    
                    if nonzero_count == 0 and ds.nodata != 0:
                        print("⚠️ WARNING: All values are zero but nodata is not zero!")
                        print("💡 This might indicate the polygon doesn't intersect actual data")
                        
                except Exception as mask_error:
                    print(f"❌ Masking failed: {mask_error}")
                    
                    # Try alternative approaches for WMS data
                    try:
                        # Method 1: Try without cropping first
                        print("🔄 Trying mask without crop...")
                        masked_data, mask_transform = mask(ds, [polygon_geom], crop=False, nodata=ds.nodata, filled=True)
                        print(f"✅ Successfully masked without crop: {masked_data.shape}")
                    except Exception as mask_error2:
                        print(f"❌ Mask without crop failed: {mask_error2}")
                        
                        try:
                            # Method 2: Use pixel coordinates instead of world coordinates
                            print("🔄 Trying pixel-based sampling...")
                            
                            # Convert polygon bounds to pixel coordinates
                            transform = ds.transform
                            poly_bounds = polygon_geom.bounds
                            
                            # Convert world coordinates to pixel coordinates
                            from rasterio.transform import rowcol
                            min_row, min_col = rowcol(transform, poly_bounds[0], poly_bounds[3])  # top-left
                            max_row, max_col = rowcol(transform, poly_bounds[2], poly_bounds[1])  # bottom-right
                            
                            # Ensure bounds are within raster dimensions
                            min_row = max(0, min(min_row, max_row))
                            max_row = min(ds.height, max(min_row, max_row))
                            min_col = max(0, min(min_col, max_col))
                            max_col = min(ds.width, max(min_col, max_col))
                            
                            if min_row < max_row and min_col < max_col:
                                # Read the pixel subset
                                window = rasterio.windows.Window(min_col, min_row, max_col - min_col, max_row - min_row)
                                masked_data = ds.read(window=window)
                                print(f"✅ Successfully sampled pixels: {masked_data.shape}")
                            else:
                                raise Exception("Invalid pixel bounds")
                                
                        except Exception as pixel_error:
                            print(f"❌ Pixel sampling failed: {pixel_error}")
                            # Final fallback: sample from center of raster
                            print("🔄 Final fallback: Using center sample of entire raster")
                            
                            # Sample a small area from center
                            center_row = ds.height // 2
                            center_col = ds.width // 2
                            sample_size = min(ds.height, ds.width, 512) // 4
                            
                            window = rasterio.windows.Window(
                                center_col - sample_size//2, 
                                center_row - sample_size//2, 
                                sample_size, 
                                sample_size
                            )
                            masked_data = ds.read(window=window)
                            print(f"✅ Using center sample: {masked_data.shape}")
                    
                min_max = {}
                
                # Process each band
                for i in range(ds.count):
                    if len(masked_data.shape) == 3:
                        band_data = masked_data[i]
                    else:
                        band_data = masked_data  # Single band case
                    
                    print(f"🔍 Band {i+1} data shape: {band_data.shape}, dtype: {band_data.dtype}")
                    print(f"🔍 Band {i+1} unique values sample: {np.unique(band_data.flatten())[:20]}")
                    
                    # Check if band contains all zeros
                    unique_values = np.unique(band_data.flatten())
                    if len(unique_values) == 1 and unique_values[0] == 0:
                        print(f"🔍 Band {i+1} contains only zeros")
                        
                        # Check if zero is actually the nodata value
                        if ds.nodata == 0.0:
                            print(f"⚠️ Band {i+1}: zeros are nodata values")
                            # min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region (all nodata)"}
                            # min_max[f"band_{i+1}"] = "Null"
                            min_max[f"band_{i+1}"] = {
                                    "min": "Null",
                                    "max": "Null",
                                    "mean": "Null",
                                    "std": "Null",
                                    "count": "Null",
                                    "data_type": "Null"
                                }
                            continue
                        else:
                            print(f"✅ Band {i+1}: zeros are legitimate data values")
                            # Zero is a valid data value, so process it normally
                            valid_mask = ~np.isnan(band_data) if ds.nodata is None else band_data != ds.nodata
                            if np.sum(valid_mask) > 0:
                                valid_data = band_data[valid_mask]
                                min_max[f"band_{i+1}"] = {
                                    "min": float(np.min(valid_data)),
                                    "max": float(np.max(valid_data)), 
                                    "mean": float(np.mean(valid_data)),
                                    "std": float(np.std(valid_data)),
                                    "count": int(np.sum(valid_mask)),
                                    "data_type": str(ds.dtypes[i])
                                }
                            else:
                                # min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region"}
                                min_max[f"band_{i+1}"] = {
                                    "min": "Null",
                                    "max": "Null",
                                    "mean": "Null",
                                    "std": "Null",
                                    "count": "Null",
                                    "data_type": "Null"
                                }
                            continue
                    
                    # Create mask for valid data - be more permissive for WMS data
                    if ds.nodata is not None:
                        valid_mask = band_data != ds.nodata
                    else:
                        valid_mask = ~np.isnan(band_data)
                    
                    print(f"🔍 Initial valid pixels: {np.sum(valid_mask)}")
                    
                    # For WMS uint8 data, be less strict about filtering
                    if str(ds.dtypes[i]) == 'uint8' and ds.nodata == 0.0:
                        # For WMS data, only exclude pure black (0) which is typically nodata
                        # Don't exclude 255 (white) as it might be valid data
                        valid_mask = band_data > 0
                        print(f"🔍 After excluding zeros: {np.sum(valid_mask)}")
                        
                        # If we still have no data, be even more permissive
                        if not valid_mask.any():
                            # Include everything except exact nodata value
                            valid_mask = band_data != ds.nodata
                            print(f"🔍 Most permissive mask: {np.sum(valid_mask)}")
                    else:
                        # For non-WMS data, use standard filtering
                        if ds.nodata == 0.0:
                            valid_mask = valid_mask & (band_data > 0)
                    
                    # Final fallback: if no valid data, sample some pixels anyway
                    if not valid_mask.any():
                        print(f"⚠️ No valid data found with standard masking, sampling center region...")
                        # Sample center 10% of the image
                        h, w = band_data.shape
                        center_h, center_w = h // 2, w // 2
                        sample_h, sample_w = h // 10, w // 10
                        
                        center_slice = band_data[
                            center_h - sample_h:center_h + sample_h,
                            center_w - sample_w:center_w + sample_w
                        ]
                        
                        if center_slice.size > 0:
                            # Create a mask for the center region
                            valid_mask = np.zeros_like(band_data, dtype=bool)
                            valid_mask[
                                center_h - sample_h:center_h + sample_h,
                                center_w - sample_w:center_w + sample_w
                            ] = True
                            print(f"🔍 Center sample mask: {np.sum(valid_mask)} pixels")
                    
                    if not valid_mask.any():
                        # min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region"}
                        # min_max[f"band_{i+1}"] = "Null"
                        min_max[f"band_{i+1}"] = {
                                    "min": "Null",
                                    "max": "Null",
                                    "mean": "Null",
                                    "std": "Null",
                                    "count": "Null",
                                    "data_type": "Null"
                                }
                        continue
                    
                    valid_data = band_data[valid_mask]
                    
                    # Apply reverse scaling if we have original data range information
                    if has_scaling_info and str(ds.dtypes[i]) == 'uint8':
                        # Convert back from 0-255 to original range
                        print(f"🔄 Rescaling band {i+1} from 0-255 to {scaling_min:.2f}-{scaling_max:.2f}")
                        scaled_data = valid_data.astype(np.float64)
                        # Scale from 0-255 to original range
                        scaled_data = (scaled_data / 255.0) * (scaling_max - scaling_min) + scaling_min
                        valid_data = scaled_data
                        data_type_info = f"uint8 (rescaled to original range {scaling_min:.2f}-{scaling_max:.2f})"
                        rescaled_warning = None
                    else:
                        data_type_info = str(ds.dtypes[i])
                        rescaled_warning = "Values may be WMS-scaled (0-255)" if str(ds.dtypes[0]) == 'uint8' else None
                    
                    # Calculate statistics
                    band_stats = {
                        "min": float(np.min(valid_data)),
                        "max": float(np.max(valid_data)),
                        "mean": float(np.mean(valid_data)),
                        "std": float(np.std(valid_data)),
                        "count": int(np.sum(valid_mask)),
                        "data_type": data_type_info
                    }
                    
                    if rescaled_warning:
                        band_stats["warning"] = rescaled_warning
                    
                    min_max[f"band_{i+1}"] = band_stats
                
                print(f"📈 Calculated statistics: {min_max}")
                
                return JsonResponse({
                    'status': 'success',
                    'layer': layer,
                    'min_max': min_max,
                    'geometry_type': original_polygon.geom_type,
                    'clip_bounds': list(original_polygon.bounds),
                    'method': 'WCS/WMS (with scaling correction)' if has_scaling_info else 'WMS (may be scaled values)',
                    'raster_info': {
                        'bands': ds.count,
                        'width': ds.width,
                        'height': ds.height,
                        'crs': str(ds.crs),
                        'data_type': str(ds.dtypes[0]),
                        'nodata': ds.nodata,
                        'raster_bounds': list(ds.bounds),
                        'scaling_applied': has_scaling_info if 'has_scaling_info' in locals() else False
                    }
                })
                
        except Exception as raster_error:
            print(f"❌ Raster processing error: {raster_error}")
            return JsonResponse({'error': f'Failed to process raster data: {str(raster_error)}'}, status=500)
        
    except Exception as e:
        print(f"💥 Error in get_raster_stats: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

