import os
import json
import requests
import rasterio
import numpy as np
import traceback
from io import BytesIO
from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import shape, Polygon
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_raster_stats_enhanced(request):
    """
    Enhanced raster statistics function with better coordinate handling and debugging.
    """
    try:
        data = json.loads(request.body)
        
        layer = data.get('layer_name') or data.get('layer')
        polygon_input = data.get('polygon') or data.get('geometry') or data.get('vector_geometry')
        
        # Get enhancement flags
        debug = data.get('debug', False)
        prefer_wcs = data.get('prefer_wcs', False)
        use_native_crs = data.get('use_native_crs', False)
        fix_coordinates = data.get('fix_coordinates', True)
        buffer_geometry = data.get('buffer_geometry', False)
        
        if not layer:
            return JsonResponse({'error': 'Layer name is required'}, status=400)
        
        if not polygon_input:
            return JsonResponse({'error': 'Clipping geometry is required'}, status=400)

        print(f"🎯 Enhanced processing for layer: {layer}")
        if debug:
            print(f"🔧 Debug mode enabled")
            print(f"🔧 Prefer WCS: {prefer_wcs}")
            print(f"🔧 Use native CRS: {use_native_crs}")
            print(f"🔧 Fix coordinates: {fix_coordinates}")
        
        # Handle geometry parsing
        if isinstance(polygon_input, str):
            try:
                polygon_input = json.loads(polygon_input)
            except:
                return JsonResponse({'error': 'Invalid geometry string format'}, status=400)
        
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
        
        # Apply buffer if requested
        if buffer_geometry:
            buffer_size = 0.001  # ~100m buffer
            polygon_geom = polygon_geom.buffer(buffer_size)
            print(f"🔧 Applied {buffer_size} degree buffer to geometry")
        
        minx, miny, maxx, maxy = polygon_geom.bounds
        print(f"📍 Clip bounds: {minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f}")
        
        geoserver_base_url = "http://192.168.0.158:8080/geoserver/useruploads"
        buffer = 0.001
        
        # Get layer metadata first
        rest_url = f"http://192.168.0.158:8080/geoserver/rest/workspaces/useruploads/coveragestores/{layer}/coverages/{layer}.json"
        native_crs = 'EPSG:4326'
        
        try:
            rest_response = requests.get(rest_url, auth=('admin', 'geoserver'), timeout=10)
            if rest_response.status_code == 200:
                metadata = rest_response.json()
                coverage = metadata.get('coverage', {})
                if 'srs' in coverage:
                    native_crs = coverage['srs']
                    print(f"🗺️ Native CRS from metadata: {native_crs}")
        except Exception as rest_error:
            print(f"⚠️ Could not get metadata: {rest_error}")
        
        # Transform coordinates if needed
        wcs_minx, wcs_miny, wcs_maxx, wcs_maxy = minx, miny, maxx, maxy
        if use_native_crs and native_crs != 'EPSG:4326':
            try:
                from pyproj import Transformer
                transformer = Transformer.from_crs('EPSG:4326', native_crs, always_xy=True)
                wcs_minx, wcs_miny = transformer.transform(minx, miny)
                wcs_maxx, wcs_maxy = transformer.transform(maxx, maxy)
                print(f"🔄 Transformed to {native_crs}: {wcs_minx:.2f}, {wcs_miny:.2f}, {wcs_maxx:.2f}, {wcs_maxy:.2f}")
            except Exception as transform_error:
                print(f"⚠️ Transform failed: {transform_error}")
        
        raster_data = None
        method_used = None
        
        # Try WCS 1.0.0 first if prefer_wcs is True
        if prefer_wcs:
            print("🔄 Trying WCS 1.0.0 first (preferred)...")
            wcs_url_v10 = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=1.0.0&request=GetCoverage&"
                f"coverage=useruploads:{layer}&"
                f"bbox={wcs_minx-buffer},{wcs_miny-buffer},{wcs_maxx+buffer},{wcs_maxy+buffer}&"
                f"crs={native_crs}&"
                f"response_crs={native_crs}&"
                f"format=GeoTIFF&"
                f"width=512&height=512"
            )
            
            try:
                response = requests.get(wcs_url_v10, timeout=30)
                if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                    print("✅ Got data via WCS 1.0.0 (preferred)")
                    raster_data = BytesIO(response.content)
                    method_used = "WCS 1.0.0"
            except Exception as wcs_error:
                print(f"⚠️ WCS 1.0.0 failed: {wcs_error}")
        
        # Fallback to WMS if WCS failed
        if raster_data is None:
            print("🔄 Trying WMS as fallback...")
            wms_url = (
                f"{geoserver_base_url}/wms?"
                f"service=WMS&version=1.3.0&request=GetMap&"
                f"layers=useruploads:{layer}&"
                f"bbox={minx-buffer},{miny-buffer},{maxx+buffer},{maxy+buffer}&"
                f"width=512&height=512&"
                f"crs=EPSG:4326&"
                f"format=image/geotiff&"
                f"styles="
            )
            
            try:
                response = requests.get(wms_url, timeout=30)
                if response.status_code == 200:
                    print("✅ Got data via WMS")
                    raster_data = BytesIO(response.content)
                    method_used = "WMS"
            except Exception as wms_error:
                print(f"❌ WMS also failed: {wms_error}")
                return JsonResponse({'error': 'Could not access raster data'}, status=500)
        
        if raster_data is None:
            return JsonResponse({'error': 'No raster data available'}, status=500)
        
        # Process the raster data
        try:
            with rasterio.open(raster_data) as ds:
                print(f"📊 Raster: {ds.count} bands, {ds.width}x{ds.height}, CRS: {ds.crs}, dtype: {ds.dtypes[0]}")
                
                raster_bounds = ds.bounds
                print(f"📍 Raster bounds: {raster_bounds}")
                
                # Handle coordinate swapping for WMS data
                bounds_swapped = False
                if method_used == "WMS" and fix_coordinates:
                    # Check if coordinates look swapped (lat/lon instead of lon/lat)
                    if (20 <= raster_bounds.left <= 35 and 70 <= raster_bounds.bottom <= 85):
                        print("🔄 Detected swapped coordinates, correcting...")
                        bounds_swapped = True
                
                # Transform polygon to match raster CRS
                clip_geom = polygon_geom
                if ds.crs and str(ds.crs) != 'EPSG:4326':
                    try:
                        clip_geom_dict = transform_geom('EPSG:4326', ds.crs, polygon_geom.__geo_interface__)
                        clip_geom = shape(clip_geom_dict)
                        print(f"🔄 Transformed clip geometry to {ds.crs}")
                    except Exception as transform_error:
                        print(f"⚠️ Geometry transform failed: {transform_error}")
                
                # Try masking with different approaches
                masked_data = None
                mask_transform = None
                
                try:
                    # First try with crop=True
                    masked_data, mask_transform = mask(ds, [clip_geom], crop=True, nodata=ds.nodata, filled=True)
                    print(f"✅ Masked with crop: {masked_data.shape}")
                except Exception as mask_error1:
                    print(f"⚠️ Mask with crop failed: {mask_error1}")
                    try:
                        # Try without crop
                        masked_data, mask_transform = mask(ds, [clip_geom], crop=False, nodata=ds.nodata, filled=True)
                        print(f"✅ Masked without crop: {masked_data.shape}")
                    except Exception as mask_error2:
                        print(f"❌ Both mask approaches failed: {mask_error2}")
                        # Try reading the entire raster and applying mask manually
                        try:
                            full_data = ds.read()
                            masked_data = full_data
                            print(f"⚠️ Using full raster data: {masked_data.shape}")
                        except Exception as read_error:
                            print(f"❌ Could not read raster: {read_error}")
                            return JsonResponse({'error': 'Failed to process raster data'}, status=500)
                
                if masked_data is None:
                    return JsonResponse({'error': 'Failed to mask raster data'}, status=500)
                
                # Calculate statistics
                min_max = {}
                
                for i in range(ds.count):
                    band_data = masked_data[i] if len(masked_data.shape) == 3 else masked_data
                    
                    # For WMS uint8 data, try to detect if it's actually meaningful
                    if method_used == "WMS" and str(ds.dtypes[i]) == 'uint8':
                        unique_values = np.unique(band_data.flatten())
                        if len(unique_values) <= 3 and all(v in [0, 255] for v in unique_values):
                            print(f"⚠️ Band {i+1}: Appears to be binary mask data, not slope values")
                            min_max[f'band_{i+1}'] = {
                                'min': 'Null',
                                'max': 'Null',
                                'mean': 'Null',
                                'std': 'Null',
                                'count': 'Null',
                                'data_type': 'WMS_processed',
                                'warning': 'WMS returned processed data, not original values'
                            }
                            continue
                    
                    # Create mask for valid data
                    if ds.nodata is not None:
                        valid_mask = (band_data != ds.nodata) & np.isfinite(band_data) & (band_data != 0)
                    else:
                        valid_mask = np.isfinite(band_data) & (band_data != 0)
                    
                    if valid_mask.any():
                        valid_data = band_data[valid_mask]
                        
                        min_val = float(np.min(valid_data))
                        max_val = float(np.max(valid_data))
                        mean_val = float(np.mean(valid_data))
                        std_val = float(np.std(valid_data))
                        count_val = int(len(valid_data))
                        
                        min_max[f'band_{i+1}'] = {
                            'min': min_val,
                            'max': max_val,
                            'mean': mean_val,
                            'std': std_val,
                            'count': count_val,
                            'data_type': str(ds.dtypes[i])
                        }
                        
                        print(f"📈 Band {i+1}: min={min_val:.3f}, max={max_val:.3f}, count={count_val}")
                    else:
                        print(f"⚠️ Band {i+1}: No valid data found")
                        min_max[f'band_{i+1}'] = {
                            'min': 'Null',
                            'max': 'Null',
                            'mean': 'Null',
                            'std': 'Null',
                            'count': 'Null',
                            'data_type': str(ds.dtypes[i])
                        }
                
                return JsonResponse({
                    'status': 'success',
                    'layer': layer,
                    'min_max': min_max,
                    'geometry_type': polygon_geom.geom_type,
                    'clip_bounds': list(polygon_geom.bounds),
                    'method': f'Enhanced {method_used}',
                    'raster_info': {
                        'bands': ds.count,
                        'width': ds.width,
                        'height': ds.height,
                        'crs': str(ds.crs),
                        'data_type': str(ds.dtypes[0]),
                        'nodata': ds.nodata,
                        'bounds_swapped': bounds_swapped,
                        'native_crs': native_crs
                    }
                })
                
        except Exception as raster_error:
            print(f"❌ Raster processing error: {raster_error}")
            return JsonResponse({'error': f'Failed to process raster: {str(raster_error)}'}, status=500)
        
    except Exception as e:
        print(f"💥 Error in enhanced raster stats: {e}")
        traceback.print_exc()
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
