import os
import json
import glob
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import shape
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import traceback


@csrf_exempt
def get_raster_stats_direct(request):
    """
    Direct file access method to get raster statistics from original TIFF files.
    This bypasses GeoServer WMS/WCS issues and works directly with the source files.
    """
    try:
        data = json.loads(request.body)
        
        layer = data.get('layer_name') or data.get('layer', 'slopeAll_Data')
        polygon_input = data.get('polygon') or data.get('geometry') or data.get('vector_geometry')
        
        if not polygon_input:
            return JsonResponse({'error': 'Clipping geometry is required'}, status=400)

        print(f"🎯 Direct file processing for layer: {layer}")
        
        # Handle geometry from frontend
        if isinstance(polygon_input, str):
            try:
                polygon_input = json.loads(polygon_input)
            except:
                return JsonResponse({'error': 'Invalid geometry string format'}, status=400)
        
        # Parse geometry
        if isinstance(polygon_input, list) and len(polygon_input) >= 2:
            actual_geometry = polygon_input[0]
            polygon_geom = shape(actual_geometry)
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
        
        print(f"📍 Clip bounds: {polygon_geom.bounds}")
        
        # Define possible locations for slope TIFF files
        possible_data_dirs = [
            r"C:\Program Files (x86)\GeoServer 2.25.1\data_dir\data\useruploads",
            r"C:\Program Files\GeoServer\data_dir\data\useruploads", 
            r"D:\GeoServer\data_dir\data\useruploads",
            r".\data\useruploads",
            r".\tiffData",
            os.path.join(os.path.dirname(__file__), "tiffData"),
            r"C:\Users\adity\Downloads\tiff\tiffData"
        ]
        
        # Look for slope TIFF files
        slope_files = []
        for data_dir in possible_data_dirs:
            if os.path.exists(data_dir):
                print(f"🔍 Checking directory: {data_dir}")
                
                # Look for various slope file patterns
                patterns = [
                    os.path.join(data_dir, "*.tif"),
                    os.path.join(data_dir, "*.tiff"),
                    os.path.join(data_dir, "*slope*.tif"),
                    os.path.join(data_dir, "*slope*.tiff"),
                    os.path.join(data_dir, f"{layer}*.tif"),
                    os.path.join(data_dir, f"{layer}*.tiff"),
                    os.path.join(data_dir, "**", "*.tif"),
                    os.path.join(data_dir, "**", "*.tiff")
                ]
                
                for pattern in patterns:
                    files = glob.glob(pattern, recursive=True)
                    slope_files.extend(files)
                    if files:
                        print(f"✅ Found {len(files)} files with pattern: {pattern}")
        
        # Remove duplicates and filter
        slope_files = list(set(slope_files))
        print(f"📁 Total TIFF files found: {len(slope_files)}")
        
        if not slope_files:
            return JsonResponse({
                'error': 'No TIFF files found. Checked directories: ' + ', '.join(possible_data_dirs),
                'status': 'error'
            }, status=404)
        
        # Process each TIFF file to find overlapping data
        all_stats = {}
        valid_files = []
        
        for i, tiff_file in enumerate(slope_files[:10]):  # Limit to first 10 files for performance
            try:
                print(f"🔍 Processing file {i+1}/{min(len(slope_files), 10)}: {os.path.basename(tiff_file)}")
                
                with rasterio.open(tiff_file) as src:
                    # Check if polygon overlaps with this TIFF
                    raster_bounds = src.bounds
                    
                    # Create a polygon from raster bounds
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
                        print(f"⏭️ Skipping {os.path.basename(tiff_file)} - no overlap")
                        continue
                    
                    print(f"✅ File overlaps: {os.path.basename(tiff_file)}")
                    print(f"   📊 Raster info: {src.count} bands, {src.width}x{src.height}, CRS: {src.crs}")
                    print(f"   📊 Data type: {src.dtypes[0]}, NoData: {src.nodata}")
                    print(f"   📍 Bounds: {raster_bounds}")
                    
                    # Transform polygon to match raster CRS if needed
                    clip_geom = polygon_geom
                    if src.crs and str(src.crs) != 'EPSG:4326':
                        print(f"🔄 Transforming geometry to {src.crs}")
                        try:
                            from rasterio.warp import transform_geom
                            clip_geom_dict = transform_geom('EPSG:4326', src.crs, polygon_geom.__geo_interface__)
                            clip_geom = shape(clip_geom_dict)
                        except Exception as transform_error:
                            print(f"⚠️ Transformation failed: {transform_error}")
                            continue
                    
                    try:
                        # Mask the raster with the polygon
                        masked_data, mask_transform = mask(src, [clip_geom], crop=True, nodata=src.nodata)
                        print(f"✅ Successfully masked: {masked_data.shape}")
                        
                        # Calculate statistics for each band
                        file_stats = {}
                        for band_idx in range(src.count):
                            band_data = masked_data[band_idx] if len(masked_data.shape) > 2 else masked_data
                            
                            # Create mask for valid data
                            if src.nodata is not None:
                                valid_mask = (band_data != src.nodata) & np.isfinite(band_data)
                            else:
                                valid_mask = np.isfinite(band_data)
                            
                            if valid_mask.any():
                                valid_data = band_data[valid_mask]
                                
                                if len(valid_data) > 0:
                                    min_val = float(np.min(valid_data))
                                    max_val = float(np.max(valid_data))
                                    mean_val = float(np.mean(valid_data))
                                    std_val = float(np.std(valid_data))
                                    count_val = int(len(valid_data))
                                    
                                    band_key = f"band_{band_idx + 1}"
                                    file_stats[band_key] = {
                                        'min': min_val,
                                        'max': max_val,
                                        'mean': mean_val,
                                        'std': std_val,
                                        'count': count_val,
                                        'data_type': str(src.dtypes[band_idx]),
                                        'file': os.path.basename(tiff_file)
                                    }
                                    
                                    print(f"📈 Band {band_idx + 1}: min={min_val:.3f}, max={max_val:.3f}, count={count_val}")
                            else:
                                print(f"⚠️ Band {band_idx + 1}: No valid data")
                        
                        if file_stats:
                            all_stats[os.path.basename(tiff_file)] = file_stats
                            valid_files.append(tiff_file)
                            
                    except Exception as mask_error:
                        print(f"❌ Masking failed for {os.path.basename(tiff_file)}: {mask_error}")
                        continue
                        
            except Exception as file_error:
                print(f"❌ Error processing {os.path.basename(tiff_file)}: {file_error}")
                continue
        
        if not all_stats:
            return JsonResponse({
                'error': 'No valid slope data found in the clipped region',
                'files_checked': len(slope_files),
                'valid_files': len(valid_files),
                'status': 'error'
            }, status=404)
        
        # Combine statistics from all files
        combined_stats = {}
        all_values = {}
        
        # Collect all values by band
        for file_name, file_stats in all_stats.items():
            for band_key, band_stats in file_stats.items():
                if band_key not in all_values:
                    all_values[band_key] = []
                
                # For simplicity, we'll use the min/max from each file
                # In a more sophisticated approach, you'd combine the actual data
                all_values[band_key].extend([band_stats['min'], band_stats['max']])
        
        # Calculate overall statistics
        for band_key, values in all_values.items():
            if values:
                combined_stats[band_key] = {
                    'min': float(min(values)),
                    'max': float(max(values)),
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)) if len(values) > 1 else 0.0,
                    'count': len(values),
                    'data_type': 'float32',
                    'files_used': len([f for f in all_stats.keys() if band_key in all_stats[f]])
                }
        
        print(f"📈 Combined statistics: {combined_stats}")
        
        return JsonResponse({
            'status': 'success',
            'layer': layer,
            'min_max': combined_stats,
            'geometry_type': polygon_geom.geom_type,
            'clip_bounds': list(polygon_geom.bounds),
            'method': 'Direct file access',
            'files_processed': len(valid_files),
            'total_files_found': len(slope_files),
            'file_details': all_stats
        })
        
    except Exception as e:
        print(f"💥 Error in get_raster_stats_direct: {e}")
        traceback.print_exc()
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
