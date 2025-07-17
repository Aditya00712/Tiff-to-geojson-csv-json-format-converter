import os
import numpy as np
import pandas as pd
import rasterio
import json
from rasterio.warp import transform
from pyproj import Transformer
from pathlib import Path

def extract_elevation_data(tiff_file_path, output_file_path):
    """
    Extract x, y coordinates and elevation (z) values from ALL pixels in a TIFF file
    and save to optimized formats to minimize file size.
    
    Args:
        tiff_file_path (str): Path to the input TIFF file
        output_file_path (str): Base path for output files
    """
    try:
        # Open the TIFF file
        with rasterio.open(tiff_file_path) as dataset:
            # Read the elevation data
            elevation_data = dataset.read(1)  # Read the first band
            
            # Get the transform information
            transform = dataset.transform
            
            # Get dimensions
            height, width = elevation_data.shape
            
            print(f"Processing {tiff_file_path}...")
            print(f"Dimensions: {width} x {height}")
            print(f"CRS: {dataset.crs}")
            print(f"Total pixels: {height * width}")
            print(f"NoData value: {dataset.nodata}")
            
            # Extract ALL coordinates efficiently using numpy
            print("Extracting coordinates for ALL pixels...")
            
            # Create coordinate grids efficiently
            rows, cols = np.meshgrid(np.arange(height), np.arange(width), indexing='ij')
            rows_flat = rows.flatten()
            cols_flat = cols.flatten()
            
            # Convert all pixel coordinates to world coordinates at once
            x_coords, y_coords = rasterio.transform.xy(transform, rows_flat, cols_flat)
            z_values = elevation_data.flatten()
            
            # Convert to numpy arrays for efficient processing
            x_coords = np.array(x_coords, dtype=np.float32)  # Use float32 to save space
            y_coords = np.array(y_coords, dtype=np.float32)  # Use float32 to save space
            z_values = z_values.astype(np.float32)  # Use float32 to save space
            
            total_points = len(x_coords)
            print(f"Extracted {total_points} total points")
            
            # Transform coordinates to WGS84 (EPSG:4326) for all output formats
            print("Transforming coordinates to WGS84 (EPSG:4326)...")
            transformer = Transformer.from_crs(dataset.crs, 'EPSG:4326', always_xy=True)
            
            # Transform all coordinates to WGS84
            lon_coords, lat_coords = transformer.transform(x_coords, y_coords)
            
            # Round coordinates to reduce precision and file size
            # For WGS84: use 6 decimal places for lat/lon (≈1 meter precision)
            lon_rounded = np.round(lon_coords, 6)  # longitude
            lat_rounded = np.round(lat_coords, 6)  # latitude
            z_rounded = np.round(z_values, 2)     # elevation
            
            # Use full resolution - no sampling
            print("Using full resolution - all points will be included")
            
            # Use all data points (no sampling)
            lon_sampled = lon_rounded  # longitude
            lat_sampled = lat_rounded  # latitude
            z_sampled = z_rounded      # elevation
            
            sampled_count = len(lon_sampled)
            print(f"Full resolution data points: {sampled_count:,}")
            
            # Only create GeoJSON format (full resolution)
            base_path = Path(output_file_path)
            geojson_wgs84_path = str(base_path).replace('.txt', '_wgs84.geojson')
            
            # Create GeoJSON features (full resolution - all points)
            print("Creating GeoJSON with all points...")
            
            # Use all data points (no additional sampling)
            geo_indices = np.arange(sampled_count)
            
            # Data is already in WGS84, no transformation needed
            features_wgs84 = []
            
            for i in geo_indices:
                lon_val = float(lon_sampled[i])   # already WGS84 longitude
                lat_val = float(lat_sampled[i])   # already WGS84 latitude
                z_val = float(z_sampled[i])       # elevation
                
                features_wgs84.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [lon_val, lat_val, z_val]  # [longitude, latitude, elevation]
                    }
                })
            
            # WGS84 GeoJSON only
            geojson_wgs84 = {
                'type': 'FeatureCollection',
                'crs': {
                    'type': 'name',
                    'properties': {
                        'name': 'EPSG:4326'
                    }
                },
                'metadata': {
                    'source_file': Path(tiff_file_path).name,
                    'coordinate_system': 'EPSG:4326 (WGS84)',
                    'total_original_points': total_points,
                    'geojson_points': len(features_wgs84),
                    'note': 'Coordinates: [longitude, latitude, elevation]'
                },
                'features': features_wgs84
            }
            
            # Save WGS84 version only
            with open(geojson_wgs84_path, 'w') as f:
                json.dump(geojson_wgs84, f, separators=(',', ':'))
            
            geojson_wgs84_size_mb = os.path.getsize(geojson_wgs84_path) / 1000000
            
            print(f"Saved GeoJSON (WGS84): {geojson_wgs84_path} ({geojson_wgs84_size_mb:.2f} MB, {len(features_wgs84):,} points)")
            
            print(f"\nFull resolution GeoJSON file (WGS84):")
            print(f"  GeoJSON: {geojson_wgs84_size_mb:.2f} MB ({len(features_wgs84):,} points)")
            print(f"  All original points included - no sampling")
            
            # Create a simple text file with instructions
            instructions_path = base_path.with_suffix('.readme.txt')
            with open(instructions_path, 'w') as f:
                f.write(f"Elevation data for {Path(tiff_file_path).name}\n")
                f.write(f"Original points: {total_points:,}\n")
                f.write(f"Output points: {sampled_count:,}\n")
                f.write(f"Full resolution - no sampling applied\n")
                f.write(f"Original coordinate system: {dataset.crs}\n")
                f.write(f"Output coordinate system: EPSG:4326 (WGS84 lat/lon)\n\n")
                f.write("Available format:\n")
                f.write(f"1. {Path(geojson_wgs84_path).name} - GeoJSON for web mapping ({geojson_wgs84_size_mb:.2f} MB)\n\n")
                f.write("Recommended usage:\n")
                f.write("- Use GeoJSON for web mapping libraries (Google Maps, Leaflet, etc.)\n")
                f.write("- Uses WGS84 coordinates (EPSG:4326)\n")
                f.write("- Directly readable by JavaScript\n")
                f.write(f"- Full resolution data - all {sampled_count:,} points included\n")
            
            return total_points
            
    except Exception as e:
        print(f"Error processing {tiff_file_path}: {str(e)}")
        return 0

def process_all_tiff_files(input_directory, output_directory):
    """
    Process all TIFF files in the input directory and save ALL elevation data
    using optimized formats to minimize file size.
    
    Args:
        input_directory (str): Directory containing TIFF files
        output_directory (str): Directory to save output files
    """
    # Create output directory if it doesn't exist
    Path(output_directory).mkdir(exist_ok=True)
    
    # Find all TIFF files
    tiff_files = []
    for ext in ['*.tif', '*.tiff', '*.TIF', '*.TIFF']:
        tiff_files.extend(Path(input_directory).glob(ext))
    
    if not tiff_files:
        print(f"No TIFF files found in {input_directory}")
        return
    
    print(f"Found {len(tiff_files)} TIFF files")
    
    total_points = 0
    for tiff_file in tiff_files:
        # Create output filename
        output_filename = f"{tiff_file.stem}_elevation_data.txt"
        output_path = Path(output_directory) / output_filename
        
        # Extract elevation data with optimization
        points = extract_elevation_data(str(tiff_file), str(output_path))
        total_points += points
        
        print(f"Completed: {tiff_file.name}")
        print("-" * 50)
    
    print(f"\nProcessing complete!")
    print(f"Total data points extracted: {total_points}")
    print(f"Output files saved in: {output_directory}")

def analyze_tiff_file(tiff_file_path):
    """
    Analyze a TIFF file to understand its properties and data distribution.
    
    Args:
        tiff_file_path (str): Path to the TIFF file
    """
    try:
        with rasterio.open(tiff_file_path) as dataset:
            print(f"\n=== Analysis of {tiff_file_path} ===")
            print(f"Dimensions: {dataset.width} x {dataset.height}")
            print(f"Number of bands: {dataset.count}")
            print(f"Data type: {dataset.dtypes}")
            print(f"CRS: {dataset.crs}")
            print(f"NoData value: {dataset.nodata}")
            print(f"Transform: {dataset.transform}")
            
            # Read the data
            data = dataset.read(1)
            
            # Basic statistics
            print(f"\nData Statistics:")
            print(f"  Shape: {data.shape}")
            print(f"  Min value: {data.min()}")
            print(f"  Max value: {data.max()}")
            print(f"  Mean value: {np.mean(data)}")
            
            # Check for valid data
            if dataset.nodata is not None:
                valid_mask = data != dataset.nodata
                valid_count = np.sum(valid_mask)
                print(f"  Valid pixels: {valid_count} / {data.size}")
                print(f"  Percentage valid: {(valid_count / data.size) * 100:.2f}%")
                
                if valid_count > 0:
                    valid_data = data[valid_mask]
                    print(f"  Valid data range: {valid_data.min()} to {valid_data.max()}")
                    print(f"  Valid data mean: {valid_data.mean()}")
            
            # Sample some pixels
            print(f"\nSample pixel values (first 5x5):")
            sample_size = min(5, data.shape[0]), min(5, data.shape[1])
            for i in range(sample_size[0]):
                row_values = []
                for j in range(sample_size[1]):
                    row_values.append(f"{data[i,j]:.2e}")
                print(f"  Row {i}: {' '.join(row_values)}")
            
    except Exception as e:
        print(f"Error analyzing {tiff_file_path}: {str(e)}")

def create_combined_file(output_directory):
    """
    Combine all individual elevation data files into one master file.
    
    Args:
        output_directory (str): Directory containing individual text files
    """
    # Find all elevation data files
    data_files = list(Path(output_directory).glob("*_elevation_data.txt"))
    
    if not data_files:
        print("No elevation data files found to combine")
        return
    
    print(f"Combining {len(data_files)} files...")
    
    # Read and combine all files
    combined_df = pd.DataFrame()
    
    for file_path in data_files:
        df = pd.read_csv(file_path)
        # Add a column to identify the source file
        df['source_file'] = file_path.stem.replace('_elevation_data', '')
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    
    # Save combined file
    combined_path = Path(output_directory) / "combined_elevation_data.txt"
    combined_df.to_csv(combined_path, index=False, sep=',')
    
    print(f"Combined file saved: {combined_path}")
    print(f"Total combined data points: {len(combined_df)}")

def create_master_catalog(output_directory):
    """
    Create a master catalog file with boundaries and metadata for all processed TIFF files.
    This allows frontend to quickly determine which files to load based on area of interest.
    
    Args:
        output_directory (str): Directory containing processed elevation files
    """
    catalog = {
        'type': 'elevation_catalog',
        'created': str(pd.Timestamp.now()),
        'total_files': 0,
        'coordinate_system': None,
        'overall_bounds': {
            'min_x': float('inf'),
            'max_x': float('-inf'),
            'min_y': float('inf'),
            'max_y': float('-inf'),
            'min_z': float('inf'),
            'max_z': float('-inf')
        },
        'files': []
    }
    
    # Find all JSON files (they contain the metadata)
    json_files = list(Path(output_directory).glob("*_elevation_data.json"))
    
    if not json_files:
        print("No JSON metadata files found for catalog creation")
        return
    
    print(f"Creating master catalog from {len(json_files)} files...")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            metadata = data['metadata']
            bounds = metadata['bounds']
            
            # Bounds are now already in WGS84 format from the JSON files
            wgs84_bounds = {
                'min_longitude': bounds['min_longitude'],
                'max_longitude': bounds['max_longitude'],
                'min_latitude': bounds['min_latitude'],
                'max_latitude': bounds['max_latitude'],
                'min_elevation': bounds['min_elevation'],
                'max_elevation': bounds['max_elevation']
            }
            
            # Update overall bounds (now in WGS84)
            catalog['overall_bounds']['min_x'] = min(catalog['overall_bounds']['min_x'], wgs84_bounds['min_longitude'])
            catalog['overall_bounds']['max_x'] = max(catalog['overall_bounds']['max_x'], wgs84_bounds['max_longitude'])
            catalog['overall_bounds']['min_y'] = min(catalog['overall_bounds']['min_y'], wgs84_bounds['min_latitude'])
            catalog['overall_bounds']['max_y'] = max(catalog['overall_bounds']['max_y'], wgs84_bounds['max_latitude'])
            catalog['overall_bounds']['min_z'] = min(catalog['overall_bounds']['min_z'], wgs84_bounds['min_elevation'])
            catalog['overall_bounds']['max_z'] = max(catalog['overall_bounds']['max_z'], wgs84_bounds['max_elevation'])
            
            # Set original coordinate system for reference
            if catalog['coordinate_system'] is None:
                catalog['coordinate_system'] = metadata['original_crs']
            
            # Add file entry
            file_entry = {
                'source_tiff': metadata['source_file'],
                'file_prefix': json_file.stem.replace('_elevation_data', ''),
                'bounds_wgs84': wgs84_bounds,  # WGS84 bounds for web mapping
                'original_points': metadata['original_total_points'],
                'frontend_points': metadata['frontend_points'],
                'sample_rate': metadata['sample_rate'],
                'has_valid_data': wgs84_bounds['min_elevation'] != wgs84_bounds['max_elevation'],  # Check if not all NoData
                'available_formats': {
                    'csv': f"{json_file.stem}.csv",
                    'json': f"{json_file.stem}.json", 
                    'geojson_wgs84': f"{json_file.stem.replace('_elevation_data', '')}_elevation_data_wgs84.geojson",
                    'readme': f"{json_file.stem}.readme.txt"
                }
            }
            
            catalog['files'].append(file_entry)
            catalog['total_files'] += 1
            
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue
    
    # Sort files by source name for easy lookup
    catalog['files'].sort(key=lambda x: x['source_tiff'])
    
    # Save master catalog
    catalog_path = Path(output_directory) / "elevation_catalog.json"
    with open(catalog_path, 'w') as f:
        json.dump(catalog, f, indent=2)
    
    # Also create a human-readable summary
    summary_path = Path(output_directory) / "MASTER_README.txt"
    with open(summary_path, 'w') as f:
        f.write("ELEVATION DATA CATALOG\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total TIFF files processed: {catalog['total_files']}\n")
        f.write(f"Original coordinate system: {catalog['coordinate_system']}\n")
        f.write(f"Output coordinate system: EPSG:4326 (WGS84 lat/lon)\n")
        f.write(f"Created: {catalog['created']}\n\n")
        
        f.write("OVERALL COVERAGE:\n")
        f.write(f"  Longitude range: {catalog['overall_bounds']['min_x']:.6f} to {catalog['overall_bounds']['max_x']:.6f}\n")
        f.write(f"  Latitude range: {catalog['overall_bounds']['min_y']:.6f} to {catalog['overall_bounds']['max_y']:.6f}\n")
        f.write(f"  Elevation range: {catalog['overall_bounds']['min_z']:.2f} to {catalog['overall_bounds']['max_z']:.2f}\n\n")
        
        f.write("FILE INVENTORY:\n")
        f.write("-" * 50 + "\n")
        
        for file_info in catalog['files']:
            f.write(f"\n{file_info['source_tiff']}:\n")
            f.write(f"  Longitude: {file_info['bounds_wgs84']['min_longitude']:.6f} to {file_info['bounds_wgs84']['max_longitude']:.6f}\n")
            f.write(f"  Latitude: {file_info['bounds_wgs84']['min_latitude']:.6f} to {file_info['bounds_wgs84']['max_latitude']:.6f}\n")
            f.write(f"  Elevation: {file_info['bounds_wgs84']['min_elevation']:.2f} to {file_info['bounds_wgs84']['max_elevation']:.2f}\n")
            f.write(f"  Points: {file_info['frontend_points']:,} (sampled from {file_info['original_points']:,})\n")
            f.write(f"  Has valid data: {file_info['has_valid_data']}\n")
            f.write(f"  Files: {file_info['file_prefix']}_elevation_data.[csv|json] and {file_info['file_prefix']}_elevation_data_wgs84.geojson\n")
    
    print(f"Master catalog created: {catalog_path}")
    print(f"Human-readable summary: {summary_path}")
    print(f"Cataloged {catalog['total_files']} files")
    
    # Create a simple JavaScript-friendly lookup function example
    js_example_path = Path(output_directory) / "frontend_usage_example.js"
    with open(js_example_path, 'w') as f:
        f.write("""// Example: How to use the elevation catalog in frontend
// Load the catalog first
fetch('elevation_catalog.json')
  .then(response => response.json())
  .then(catalog => {
    console.log('Total files available:', catalog.total_files);
    console.log('Overall bounds:', catalog.overall_bounds);
    
    // Find files that intersect with your area of interest (using WGS84 coordinates)
    function findFilesInBounds(minLon, maxLon, minLat, maxLat) {
      return catalog.files.filter(file => {
        const bounds = file.bounds_wgs84;  // Use WGS84 bounds
        return !(bounds.max_longitude < minLon || bounds.min_longitude > maxLon ||
                bounds.max_latitude < minLat || bounds.min_latitude > maxLat);
      });
    }
    
    // Example: Find files in a specific area (WGS84 coordinates)
    const areaOfInterest = {
      minLon: 77.5, maxLon: 78.0,    // Longitude range
      minLat: 8.0, maxLat: 8.5       // Latitude range
    };
    
    const relevantFiles = findFilesInBounds(
      areaOfInterest.minLon, areaOfInterest.maxLon,
      areaOfInterest.minLat, areaOfInterest.maxLat
    );
    
    console.log('Files needed for area:', relevantFiles.map(f => f.source_tiff));
    
    // Load only the files you need
    relevantFiles.forEach(file => {
      if (file.has_valid_data) {
        // Load the format you prefer
        // For web mapping, use the WGS84 GeoJSON format
        fetch(file.available_formats.geojson_wgs84)
          .then(response => response.json())
          .then(geoJsonData => {
            console.log('Loaded GeoJSON (WGS84):', file.source_tiff);
            // GeoJSON is ready for Leaflet, Google Maps, etc.
            // Coordinates are in [longitude, latitude, elevation] format
          });
        
        // Or load JSON for full metadata
        fetch(file.available_formats.json)
          .then(response => response.json())
          .then(elevationData => {
            console.log('Loaded JSON with metadata:', file.source_tiff);
          });
      }
    });
  });
""")
    
    print(f"Frontend usage example: {js_example_path}")
    return catalog_path

if __name__ == "__main__":
    # Configuration
    input_dir = "tiffData"  # Directory containing TIFF files
    output_dir = "elevation_output"  # Directory to save output files
    
    print("=== TIFF File Analysis ===")
    # First, let's analyze the TIFF files to understand their content
    tiff_files = []
    for ext in ['*.tif', '*.tiff', '*.TIF', '*.TIFF']:
        tiff_files.extend(Path(input_dir).glob(ext))
    
    print(f"Found {len(tiff_files)} TIFF files")
    print("Note: ALL pixels (including NoData) will be extracted")
    print("Using frontend-friendly formats:")
    print("  - Optimized CSV (reduced precision)")
    print("  - Grid JSON (elevation matrix)")
    print("  - Sample JSON (every 10th point)")
    print("  - Coordinates JSON (point array format)")
    print("  - All formats directly readable by JavaScript")
    
    for tiff_file in tiff_files[:2]:  # Analyze first 2 files
        analyze_tiff_file(str(tiff_file))
    
    print("\n" + "="*60)
    print("=== Processing TIFF Files ===")
    
    # Process all TIFF files with optimization
    process_all_tiff_files(input_dir, output_dir)
    
    # Create master catalog for frontend navigation
    print("\n" + "="*60)
    print("=== Creating Master Catalog ===")
    create_master_catalog(output_dir)
    
    # Create a combined file (optional)
    create_combined_file(output_dir)
    
    # Create master catalog file
    create_master_catalog(output_dir)
    
    print("\nOutput file format:")
    print("Each file contains columns: x, y, z")
    print("- x: X coordinate (longitude or easting)")
    print("- y: Y coordinate (latitude or northing)")
    print("- z: Elevation value")
    print("- source_file: Original TIFF file name (in combined file only)")