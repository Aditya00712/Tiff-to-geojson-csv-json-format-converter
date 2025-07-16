import os
import numpy as np
import pandas as pd
import rasterio
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
            
            # Method 1: Compressed CSV with reduced precision
            base_path = Path(output_file_path)
            csv_path = base_path.with_suffix('.csv')
            
            # Round coordinates to reduce precision and file size
            x_rounded = np.round(x_coords, 2)  # 2 decimal places
            y_rounded = np.round(y_coords, 2)  # 2 decimal places
            z_rounded = np.round(z_values, 2)  # 2 decimal places for elevation
            
            # Create DataFrame with reduced precision
            df = pd.DataFrame({
                'x': x_rounded,
                'y': y_rounded,
                'z': z_rounded
            })
            
            # Save as compressed CSV
            df.to_csv(csv_path, index=False, float_format='%.2f', compression='gzip')
            csv_size_mb = os.path.getsize(csv_path) / 1000000
            print(f"Saved compressed CSV: {csv_path} ({csv_size_mb:.2f} MB)")
            
            # Method 2: Binary format (NPZ) - Much smaller
            npz_path = base_path.with_suffix('.npz')
            np.savez_compressed(npz_path,
                               x=x_rounded,
                               y=y_rounded, 
                               z=z_rounded,
                               metadata={
                                   'source_file': Path(tiff_file_path).name,
                                   'crs': str(dataset.crs),
                                   'dimensions': [width, height],
                                   'nodata_value': float(dataset.nodata) if dataset.nodata is not None else None
                               })
            npz_size_mb = os.path.getsize(npz_path) / 1000000
            print(f"Saved compressed NPZ: {npz_path} ({npz_size_mb:.2f} MB)")
            
            # Method 3: Compact JSON with minimal formatting
            json_path = base_path.with_suffix('.json')
            
            # Create compact structure
            data_dict = {
                'meta': {
                    'file': Path(tiff_file_path).name,
                    'crs': str(dataset.crs),
                    'dims': [width, height],
                    'nodata': float(dataset.nodata) if dataset.nodata is not None else None,
                    'count': total_points
                },
                # Store as lists of rounded values
                'x': x_rounded.tolist(),
                'y': y_rounded.tolist(), 
                'z': z_rounded.tolist()
            }
            
            import json
            import gzip
            
            # Save as compressed JSON
            with gzip.open(json_path + '.gz', 'wt') as f:
                json.dump(data_dict, f, separators=(',', ':'))  # No spaces
            
            json_size_mb = os.path.getsize(json_path + '.gz') / 1000000
            print(f"Saved compressed JSON: {json_path}.gz ({json_size_mb:.2f} MB)")
            
            # Method 4: Ultra-compact format for frontend (grid-based)
            compact_path = base_path.with_suffix('.compact')
            
            # Store as grid metadata + elevation values only
            compact_data = {
                'meta': {
                    'file': Path(tiff_file_path).name,
                    'crs': str(dataset.crs),
                    'width': width,
                    'height': height,
                    'transform': list(dataset.transform),
                    'nodata': float(dataset.nodata) if dataset.nodata is not None else None
                },
                'elevation_grid': z_rounded.reshape(height, width).tolist()
            }
            
            with gzip.open(compact_path + '.gz', 'wt') as f:
                json.dump(compact_data, f, separators=(',', ':'))
            
            compact_size_mb = os.path.getsize(compact_path + '.gz') / 1000000
            print(f"Saved ultra-compact format: {compact_path}.gz ({compact_size_mb:.2f} MB)")
            
            print(f"\nFile size comparison:")
            print(f"  Compressed CSV: {csv_size_mb:.2f} MB")
            print(f"  Binary NPZ: {npz_size_mb:.2f} MB")
            print(f"  Compressed JSON: {json_size_mb:.2f} MB") 
            print(f"  Ultra-compact: {compact_size_mb:.2f} MB")
            
            # Create a simple text file with instructions
            instructions_path = base_path.with_suffix('.readme.txt')
            with open(instructions_path, 'w') as f:
                f.write(f"Elevation data for {Path(tiff_file_path).name}\n")
                f.write(f"Total points: {total_points:,}\n")
                f.write(f"Coordinate system: {dataset.crs}\n\n")
                f.write("Available formats:\n")
                f.write(f"1. {csv_path.name} - Standard CSV (gzip compressed, {csv_size_mb:.2f} MB)\n")
                f.write(f"2. {npz_path.name} - Binary NumPy format ({npz_size_mb:.2f} MB)\n")
                f.write(f"3. {json_path.name}.gz - Compressed JSON ({json_size_mb:.2f} MB)\n")
                f.write(f"4. {compact_path.name}.gz - Ultra-compact grid format ({compact_size_mb:.2f} MB)\n\n")
                f.write("Recommended for frontend: Use the compact format for smallest size\n")
                f.write("or NPZ format for fastest loading in Python.\n")
            
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
    print("Using multiple optimized formats to minimize file size:")
    print("  - Compressed CSV (gzip)")
    print("  - Binary NPZ (fastest)")
    print("  - Compressed JSON")
    print("  - Ultra-compact grid format")
    
    for tiff_file in tiff_files[:2]:  # Analyze first 2 files
        analyze_tiff_file(str(tiff_file))
    
    print("\n" + "="*60)
    print("=== Processing TIFF Files ===")
    
    # Process all TIFF files with optimization
    process_all_tiff_files(input_dir, output_dir)
    
    # Create a combined file (optional)
    create_combined_file(output_dir)
    
    print("\nOutput file format:")
    print("Each file contains columns: x, y, z")
    print("- x: X coordinate (longitude or easting)")
    print("- y: Y coordinate (latitude or northing)")
    print("- z: Elevation value")
    print("- source_file: Original TIFF file name (in combined file only)")