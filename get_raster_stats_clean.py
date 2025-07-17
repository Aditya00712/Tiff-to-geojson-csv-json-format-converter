import json
import os
import requests
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import shape
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from pyproj import Transformer

@csrf_exempt
def get_raster_stats(request):
    """
    Clean, focused function to get original raster statistics from GeoServer.
    Prioritizes WCS for original values, with minimal WMS fallback.
    """
    try:
        data = json.loads(request.body)
        
        layer = data.get('layer_name') or data.get('layer')
        polygon_input = data.get('polygon') or data.get('geometry') or data.get('vector_geometry')
        
        if not layer or not polygon_input:
            return JsonResponse({'error': 'Layer name and clipping geometry are required'}, status=400)

        print(f"🎯 Processing layer: {layer}")
        
        # Parse geometry from frontend
        if isinstance(polygon_input, str):
            polygon_input = json.loads(polygon_input)
        
        if isinstance(polygon_input, list) and len(polygon_input) >= 2:
            polygon_geom = shape(polygon_input[0])  # Canvas format [geometry, bounds]
        elif isinstance(polygon_input, dict):
            if polygon_input.get("type") == "FeatureCollection":
                polygon_geom = shape(polygon_input["features"][0]["geometry"])
            elif polygon_input.get("type") == "Feature":
                polygon_geom = shape(polygon_input["geometry"])
            else:
                polygon_geom = shape(polygon_input)
        else:
            return JsonResponse({'error': 'Unsupported geometry format'}, status=400)
        
        minx, miny, maxx, maxy = polygon_geom.bounds
        print(f"📍 Clip bounds: {minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f}")
        
        geoserver_base_url = "http://192.168.0.158:8080/geoserver/useruploads"
        buffer = 0.001
        
        # Get layer metadata for native CRS
        rest_url = f"http://192.168.0.158:8080/geoserver/rest/workspaces/useruploads/coveragestores/{layer}/coverages/{layer}.json"
        native_crs = 'EPSG:4326'  # Default
        
        try:
            rest_response = requests.get(rest_url, auth=('admin', 'geoserver'), timeout=10)
            if rest_response.status_code == 200:
                metadata = rest_response.json()
                coverage = metadata.get('coverage', {})
                native_crs = coverage.get('srs', 'EPSG:4326')
                print(f"🗺️ Using native CRS: {native_crs}")
        except:
            print("⚠️ Could not get metadata, using EPSG:4326")
        
        # Transform bounds to native CRS if needed
        wcs_minx, wcs_miny, wcs_maxx, wcs_maxy = minx, miny, maxx, maxy
        if native_crs != 'EPSG:4326':
            try:
                transformer = Transformer.from_crs('EPSG:4326', native_crs, always_xy=True)
                wcs_minx, wcs_miny = transformer.transform(minx, miny)
                wcs_maxx, wcs_maxy = transformer.transform(maxx, maxy)
                print(f"🔄 Transformed bounds to {native_crs}: {wcs_minx:.2f}, {wcs_miny:.2f}, {wcs_maxx:.2f}, {wcs_maxy:.2f}")
            except Exception as e:
                print(f"⚠️ Transform failed: {e}")
        
        # Try WCS (primary method - gets original values)
        raster_data = None
        source_method = "Unknown"
        
        # WCS with correct axis labels
        if native_crs == 'EPSG:4326':
            wcs_url = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=2.0.1&request=GetCoverage&"
                f"coverageId=useruploads:{layer}&"
                f"subset=Long({wcs_minx-buffer},{wcs_maxx+buffer})&"
                f"subset=Lat({wcs_miny-buffer},{wcs_maxy+buffer})&"
                f"format=image/geotiff&outputCRS={native_crs}"
            )
        else:
            # For projected CRS, use E/N axis labels (this is what worked!)
            wcs_url = (
                f"{geoserver_base_url}/wcs?"
                f"service=WCS&version=2.0.1&request=GetCoverage&"
                f"coverageId=useruploads:{layer}&"
                f"subset=E({wcs_minx-buffer},{wcs_maxx+buffer})&"
                f"subset=N({wcs_miny-buffer},{wcs_maxy+buffer})&"
                f"format=image/geotiff&outputCRS={native_crs}"
            )
        
        print(f"🌐 Trying WCS: {wcs_url}")
        
        try:
            response = requests.get(wcs_url, timeout=30)
            if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                raster_data = BytesIO(response.content)
                source_method = "WCS 2.0.1 (original values)"
                print("✅ Got data via WCS")
        except Exception as e:
            print(f"⚠️ WCS failed: {e}")
        
        # Fallback to WMS if WCS fails
        if raster_data is None:
            print("🔄 Trying WMS fallback...")
            wms_url = (
                f"{geoserver_base_url}/wms?"
                f"service=WMS&version=1.3.0&request=GetMap&"
                f"layers=useruploads:{layer}&"
                f"bbox={minx-buffer},{miny-buffer},{maxx+buffer},{maxy+buffer}&"
                f"width=1024&height=1024&crs=EPSG:4326&"
                f"format=image/geotiff&styles="
            )
            
            try:
                response = requests.get(wms_url, timeout=30)
                if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                    raster_data = BytesIO(response.content)
                    source_method = "WMS (may be scaled 0-255)"
                    print("✅ Got data via WMS")
            except Exception as e:
                print(f"❌ WMS also failed: {e}")
                return JsonResponse({'error': 'Could not access raster data'}, status=500)
        
        # Process the raster data
        with rasterio.open(raster_data) as ds:
            print(f"📊 Raster: {ds.count} bands, {ds.width}x{ds.height}, {ds.dtypes[0]}, CRS: {ds.crs}")
            
            # Transform polygon to match raster CRS
            if ds.crs and ds.crs != 'EPSG:4326':
                transformed_geom = transform_geom('EPSG:4326', ds.crs, polygon_geom.__geo_interface__)
                polygon_geom = shape(transformed_geom)
                print(f"📍 Transformed polygon bounds: {polygon_geom.bounds}")
            
            # Clip raster with polygon
            try:
                masked_data, _ = mask(ds, [polygon_geom], crop=True, nodata=ds.nodata, filled=True)
                print(f"✅ Clipped raster: {masked_data.shape}")
                
                # Calculate statistics for each band
                min_max = {}
                for i in range(ds.count):
                    band_data = masked_data[i] if len(masked_data.shape) == 3 else masked_data
                    
                    # Filter out nodata values
                    if ds.nodata is not None:
                        valid_data = band_data[band_data != ds.nodata]
                    else:
                        valid_data = band_data[~np.isnan(band_data)]
                    
                    if len(valid_data) > 0:
                        min_max[f"band_{i+1}"] = {
                            "min": float(np.min(valid_data)),
                            "max": float(np.max(valid_data)),
                            "mean": float(np.mean(valid_data)),
                            "std": float(np.std(valid_data)),
                            "count": len(valid_data),
                            "data_type": str(ds.dtypes[i])
                        }
                        print(f"📈 Band {i+1}: min={np.min(valid_data):.1f}, max={np.max(valid_data):.1f}, count={len(valid_data)}")
                    else:
                        min_max[f"band_{i+1}"] = {"error": "No valid data in clipped region"}
                
                return JsonResponse({
                    'status': 'success',
                    'layer': layer,
                    'min_max': min_max,
                    'method': source_method,
                    'raster_info': {
                        'bands': ds.count,
                        'width': ds.width,
                        'height': ds.height,
                        'crs': str(ds.crs),
                        'data_type': str(ds.dtypes[0]),
                        'nodata': ds.nodata
                    }
                })
                
            except Exception as mask_error:
                print(f"❌ Masking failed: {mask_error}")
                return JsonResponse({'error': f'Failed to clip raster: {str(mask_error)}'}, status=500)
        
    except Exception as e:
        print(f"💥 Error: {e}")
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
