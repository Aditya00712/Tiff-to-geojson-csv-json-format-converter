# TIFF Elevation Data Extraction Tool

## Overview
This tool extracts elevation data from TIFF raster files and converts it into multiple frontend-friendly formats optimized for web applications and data analysis. The script processes all pixels in TIFF files and outputs the data in CSV, JSON, and GeoJSON formats with WGS84 coordinate transformation.

## Features
- **Complete Pixel Extraction**: Extracts elevation data from ALL pixels in TIFF files
- **Coordinate Transformation**: Automatically transforms coordinates to WGS84 (EPSG:4326)
- **Multiple Output Formats**: 
  - CSV for spreadsheet applications
  - JSON with metadata for programmatic access
  - GeoJSON for web mapping applications
- **Optimized File Sizes**: Uses float32 precision and smart sampling for large datasets
- **Frontend-Ready**: All outputs are optimized for web applications and JavaScript
- **Batch Processing**: Processes multiple TIFF files automatically
- **Master Catalog**: Creates a navigation catalog for frontend applications

## Input Requirements
- TIFF files (.tif, .tiff) containing elevation/raster data
- Files should be placed in the `tiffData/` directory
- Supports any coordinate reference system (automatically transformed to WGS84)

## Output Formats

### 1. CSV Format (`*_elevation_data.csv`)
- Columns: `longitude`, `latitude`, `elevation`
- Coordinates in WGS84 decimal degrees
- Optimized for spreadsheet applications and data analysis
- Sample rate applied for large datasets (max 100K points)

### 2. JSON Format (`*_elevation_data.json`)
- Complete metadata including bounds, CRS information, and statistics
- Structured data arrays for programmatic access
- Includes original file dimensions and transformation details
- Perfect for web applications and APIs

### 3. GeoJSON Format (`*_elevation_data_wgs84.geojson`)
- Standard GeoJSON format with Point features
- Each point contains longitude, latitude, and elevation
- Ready for web mapping libraries (Leaflet, Google Maps, etc.)
- Limited to 10K points for optimal performance

### 4. Master Catalog (`elevation_catalog.json`)
- Index of all processed files with bounds and metadata
- Enables efficient spatial queries for large datasets
- Frontend can determine which files to load based on area of interest

## Usage

### Basic Usage
```python
python test.py
```

### Script Configuration
The script automatically processes all TIFF files in the configured directories:
- **Input Directory**: `tiffData/` (contains your TIFF files)
- **Output Directory**: `elevation_output/` (generated files)

### Key Functions

#### `extract_elevation_data(tiff_file_path, output_file_path)`
Extracts elevation data from a single TIFF file and creates all output formats.

#### `process_all_tiff_files(input_directory, output_directory)`
Batch processes all TIFF files in the input directory.

#### `create_master_catalog(output_directory)`
Creates a master catalog for frontend navigation and spatial queries.

## File Structure After Processing
```
elevation_output/
├── 16.tif_elevation_data.csv          # CSV format
├── 16.tif_elevation_data.json         # JSON with metadata
├── 16.tif_elevation_data_wgs84.geojson # GeoJSON format
├── 16.tif_elevation_data.readme.txt   # Individual file instructions
├── elevation_catalog.json             # Master catalog
├── MASTER_README.txt                  # Summary of all processed files
└── frontend_usage_example.js          # JavaScript usage examples
```

## Dependencies
Install required packages using:
```bash
pip install -r requirements.txt
```

Required packages:
- `rasterio` - TIFF file reading and geospatial operations
- `pandas` - Data manipulation and CSV output
- `numpy` - Numerical operations and array processing
- `pyproj` - Coordinate transformation
- `pathlib` - File path operations

## Performance Optimizations
- **Memory Efficient**: Processes data in chunks for large files
- **Reduced Precision**: Uses float32 instead of float64 to reduce file sizes
- **Smart Sampling**: Automatically samples large datasets for frontend use
- **Batch Processing**: Processes multiple files without memory accumulation

## Frontend Integration
The tool generates a JavaScript example file (`frontend_usage_example.js`) showing how to:
- Load the elevation catalog
- Find files intersecting with an area of interest
- Load specific elevation data formats
- Use data with web mapping libraries

## Output File Sizes
For a typical elevation raster:
- **Original TIFF**: ~50MB
- **CSV Output**: ~2-5MB (sampled)
- **JSON Output**: ~3-7MB (with metadata)
- **GeoJSON Output**: ~1-3MB (10K points max)

## Coordinate Systems
- **Input**: Any CRS supported by the TIFF file
- **Output**: WGS84 (EPSG:4326) longitude/latitude
- **Precision**: 6 decimal places for coordinates (~1 meter accuracy)
- **Elevation**: 2 decimal places for elevation values

## Error Handling
- Graceful handling of corrupted or unsupported TIFF files
- Automatic detection and handling of NoData values
- Memory optimization for very large raster files
- Detailed error reporting for debugging

## Use Cases
- **Web Mapping**: Direct integration with Leaflet, Google Maps, etc.
- **Data Analysis**: CSV format for statistical analysis
- **API Development**: JSON format for REST APIs
- **Scientific Applications**: Preserve spatial accuracy with metadata
- **Mobile Apps**: Optimized file sizes for mobile data usage

## Notes
- All coordinates are output in WGS84 (EPSG:4326) format
- Large files are automatically sampled to maintain reasonable file sizes
- The master catalog enables efficient spatial indexing
- All outputs are optimized for web application consumption

## Support
For issues or questions, refer to the individual file readme files generated in the output directory, which contain specific metadata and usage instructions for each processed TIFF file.