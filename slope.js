import React, { useEffect, useState, useContext } from 'react';
import L from "leaflet";
import { HOST, HOST_MEDIA_URL } from "../host";
import { GlobalContext } from "../../App";
import { ToastContainer, toast } from "react-toastify";
import Options from "../Main/Actions/clipComp"; // adjust path if needed
import "leaflet/dist/leaflet.css";
import "bootstrap/dist/css/bootstrap.min.css";
import "react-toastify/dist/ReactToastify.css";
import "./popupselect.css";
import { SideBarContext } from '../Main/sidebar';
import bbox from '@turf/bbox';
import bboxPolygon from '@turf/bbox-polygon';
import union from '@turf/union';


export default function Slope() {
  const [clip, setClip] = useState(false);
  const [clipBox, setClipBox] = useState(false);
  const [clipLayer, setClipLayer] = useState(false);
  const [AddBound, setBound] = useState(false);
  const [selCont, setCont] = useState(""); 
  const [selState, setState] = useState("");
  const [selDis, setDis] = useState("");
  const [selCLayer, setCLayer] = useState("");
  const [selectedTehsil, setSelectedTehsil] = useState("");
  const [selectedVillage, setSelectedVillage] = useState("");
  const [villageGeojsonFiles, setVillageGeojsonFiles] = useState([])
  const [filteredTehsilGeojson, setFilteredTehsilGeojson] = useState(null);
  const [filteredVillageGeojson, setFilteredVillageGeojson] = useState(null);
  const [selectedTehsilFeature, setSelectedTehsilFeature] = useState(null);
  const [isAdditionalOptionsOpen, setAdditionalOptionsOpen] = useState(false);
  const [rasterStats, setRasterStats] = useState(null); // Store min/max statistics

  const {
    map,
    layerControls,
    lastRect,
    drawnItems,
    isSidebarTabs,
    setName, Canvas
    // mapBoxContainerRef,
  } = useContext(GlobalContext);
  const { setloader } = useContext(SideBarContext);


  // const loadSlopeWMSLayer = () => {
  //     // Clear previous instance
  //     map.eachLayer(layer => {
  //       if (layer.options?.layers === "useruploads:slopeAll_Data") {
  //         map.removeLayer(layer);
  //       }
  //     });

  //     // Create WMS layer with correct format
  //     const wmsLayer = L.tileLayer.wms("http://192.168.0.158:8080/geoserver/useruploads/wms", {
  //       layers: "useruploads:slopeAll_Data",
  //       format: "image/png",  
  //       transparent: true,
  //       version: "1.3.0",
  //       crs: L.CRS.EPSG4326,
  //       zIndex: 1000,
  //       styles: ''  
  //     });

  //     // Add to map and ensure proper ordering
  //     wmsLayer.addTo(map).bringToFront();
  //     if (layerControls) { 
  //         layerControls.addOverlay(wmsLayer, "Slope");
  //       }

  //     // Set bounds
  //     const bounds = L.latLngBounds(
  //       [7.498748722032755, 65.61316512455743],
  //       [37.73152956922792, 98.85043041471211]
  //     );
  //     map.fitBounds(bounds);

  //     // Debugging
  //     wmsLayer.on('load', () => console.log('WMS loaded successfully'));
  //     wmsLayer.on('error', (err) => console.error('WMS error:', err));
  //   };

  const getRegionArea = async () => {
    var payload = {};
    if (selectedVillage && selectedTehsil) {
      payload["clip"] = ["village", [selectedVillage, selectedTehsil, selDis, selState, selCont]];
    } else if (selectedTehsil) {
      payload["clip"] = ["tehsil", [selectedTehsil, selDis, selState, selCont]];
    } else if (selDis && selDis !== "") {
      payload["clip"] = ["dis", [selDis, selState, selCont]];
    } else if (selState && selState !== "") {
      payload["clip"] = ["state", [selState, selCont]];
    } else if (selCont && selCont !== "") {
      payload["clip"] = ["cont", [selCont]];
    }

    const response = await fetch(`${HOST}/get-region-area`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ data: payload }),
    });

    const data = await response.json();
    console.log(data);
    return data.region_geojson; // <-- return geometry
  };

  // Alternative function to get raster stats using direct file access
  const getRasterStatsDirectFile = async (clipGeometry) => {
    try {
      console.log('🔍 Trying direct file access method...');
      
      const payload = {
        layer_name: 'slopeAll_1',
        geometry: clipGeometry,
        method: 'direct_file', // Request direct file access
        use_original_files: true, // Flag to use original TIFF files
        skip_wms: true // Skip WMS/WCS processing
      };

      console.log('📤 Sending direct file access payload:', payload);

      const response = await fetch(`${HOST}/maps/raster-stats/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ Direct file access HTTP Error:', errorText);
        throw new Error(`HTTP error! status: ${response.status} - Direct file access not available`);
      }

      const data = await response.json();
      console.log('📊 Direct file access response:', data);
      
      return data;
    } catch (error) {
      console.warn('⚠️ Direct file access failed:', error);
      return null;
    }
  };

  // Test function to help debug coordinate and data issues
  const testRasterAccess = async () => {
    try {
      console.log('🧪 Testing raster access methods...');
      
      // Create a simple test geometry around a known area (Delhi/NCR region)
      const testGeometry = {
        "type": "Polygon",
        "coordinates": [[
          [77.0, 28.0],  // Bottom-left
          [77.5, 28.0],  // Bottom-right  
          [77.5, 28.5],  // Top-right
          [77.0, 28.5],  // Top-left
          [77.0, 28.0]   // Close polygon
        ]]
      };
      
      console.log('🔍 Test geometry:', testGeometry);
      
      // Test 1: Try existing endpoint with enhanced parameters
      console.log('🧪 Test 1: Enhanced WMS/WCS method...');
      try {
        const payload = {
          layer_name: 'slopeAll_1',
          geometry: testGeometry,
          debug: true,
          prefer_wcs: true,
          fix_coordinates: true,
          buffer_geometry: true
        };

        const response = await fetch(`${HOST}/maps/raster-stats/`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });

        if (response.ok) {
          const result = await response.json();
          console.log('✅ Enhanced WMS/WCS test result:', result);
          
          if (result.status === 'success' && result.min_max) {
            const hasValidData = Object.values(result.min_max).some(band => 
              band && band.min !== 'Null' && band.max !== 'Null' && 
              band.min !== null && band.max !== null
            );
            
            if (hasValidData) {
              toast.success('✅ Enhanced method found valid slope data!');
              return; // Success, no need to test other methods
            } else {
              console.warn('⚠️ Enhanced method returned null values');
            }
          }
        } else {
          console.warn(`⚠️ Enhanced method failed with status: ${response.status}`);
        }
      } catch (enhancedError) {
        console.warn('⚠️ Enhanced method error:', enhancedError);
      }
      
      // Test 2: Try direct file access method
      console.log('🧪 Test 2: Direct file access method...');
      try {
        const directPayload = {
          layer_name: 'slopeAll_1',
          geometry: testGeometry,
          method: 'direct_file',
          use_original_files: true,
          debug: true
        };

        const directResponse = await fetch(`${HOST}/maps/raster-stats/`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(directPayload),
        });

        if (directResponse.ok) {
          const directResult = await directResponse.json();
          console.log('✅ Direct file access result:', directResult);
          
          if (directResult.status === 'success' && directResult.min_max) {
            const hasValidData = Object.values(directResult.min_max).some(band => 
              band && band.min !== 'Null' && band.max !== 'Null' && 
              band.min !== null && band.max !== null
            );
            
            if (hasValidData) {
              toast.success('✅ Direct file access found valid slope data!');
              return;
            }
          }
        } else {
          const errorText = await directResponse.text();
          console.warn(`⚠️ Direct file access failed: ${directResponse.status} - ${errorText.substring(0, 200)}...`);
        }
      } catch (directError) {
        console.warn('⚠️ Direct file access error:', directError);
      }
      
      // Test 3: Basic test with original method
      console.log('🧪 Test 3: Original method...');
      try {
        const basicPayload = {
          layer_name: 'slopeAll_1',
          geometry: testGeometry
        };

        const basicResponse = await fetch(`${HOST}/maps/raster-stats/`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(basicPayload),
        });

        if (basicResponse.ok) {
          const basicResult = await basicResponse.json();
          console.log('📊 Original method result:', basicResult);
        } else {
          console.warn(`⚠️ Original method failed: ${basicResponse.status}`);
        }
      } catch (basicError) {
        console.warn('⚠️ Original method error:', basicError);
      }
      
      toast.info('🧪 All tests completed - check console for detailed results');
      
    } catch (error) {
      console.error('❌ Test suite failed:', error);
      toast.error(`Test failed: ${error.message}`);
    }
  };

  // Enhanced function that tries multiple approaches
  const getRasterStats = async (clipGeometry) => {
    try {
      // Log the geometry we're sending for debugging
      console.log('🔍 Sending clip geometry:', JSON.stringify(clipGeometry, null, 2));
      
      // First try direct file access if available
      const directResult = await getRasterStatsDirectFile(clipGeometry);
      if (directResult && directResult.status === 'success' && directResult.min_max) {
        const hasValidData = Object.values(directResult.min_max).some(band => 
          band && band.min !== 'Null' && band.max !== 'Null' && 
          band.min !== null && band.max !== null
        );
        
        if (hasValidData) {
          console.log('✅ Got valid stats from direct file access');
          return directResult.min_max;
        }
      }
      
      // Fallback to original WMS/WCS method with enhanced parameters
      const payload = {
        layer_name: 'slopeAll_1',
        layer: 'slopeAll_1',
        geometry: clipGeometry,
        polygon: clipGeometry,
        vector_geometry: clipGeometry,
        // Add debugging flags
        debug: true,
        prefer_wcs: true, // Prefer WCS over WMS
        use_native_crs: true, // Use native coordinate system
        fix_coordinates: true, // Apply coordinate fixing
        buffer_geometry: true // Add small buffer to geometry
      };

      console.log('📤 Sending enhanced payload to backend:', payload);

      const response = await fetch(`${HOST}/maps/raster-stats/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      console.log('📥 Response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ HTTP Error Response:', errorText);
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      console.log('📊 Full raster statistics response:', data);
      
      if (data.status === 'success' && data.min_max) {
        // Check if we got actual values or nulls
        const hasValidData = Object.values(data.min_max).some(band => 
          band && band.min !== 'Null' && band.max !== 'Null' && 
          band.min !== null && band.max !== null
        );
        
        if (!hasValidData) {
          console.warn('⚠️ Backend returned null statistics - this might indicate:');
          console.warn('   - Clipping geometry is outside raster bounds');
          console.warn('   - Coordinate system mismatch');
          console.warn('   - All values in clipped area are nodata');
          console.warn('   - WMS is returning processed RGB data instead of slope values');
          toast.warn('No valid data found in the clipped region. The slope data might be in a different format or coordinate system.');
          return null;
        }
        
        return data.min_max;
      } else {
        throw new Error(data.error || 'Failed to get raster statistics');
      }
    } catch (error) {
      console.error('❌ Error getting raster stats:', error);
      toast.error(`Failed to get statistics: ${error.message}`);
      return null;
    }
  };

  const loadSlopeWMSLayer = async () => {
    if (!map) return;

    setloader(true); // Show loading indicator
    
    let clipGeometry = null;

    try {
      // ✅ Option 1: Clipping by Drawn Rectangle (Box)
      if (clipBox && lastRect && drawnItems.hasLayer(lastRect)) {
        const drawnLayer = drawnItems.getLayer(lastRect).toGeoJSON();
        const drawnBbox = bbox(drawnLayer);
        const clipPoly = bboxPolygon(drawnBbox);
        clipGeometry = clipPoly;
      }

      // ✅ Option 2: Clipping by Region (Continent/State/District)
      if (clip) {
        const regionGeojson = await getRegionArea();
        if (!regionGeojson || !regionGeojson.features || regionGeojson.features.length === 0) {
          toast.error("No region geometry available.");
          return;
        }

        const regions = regionGeojson.features;
        clipGeometry = regions.length === 1
          ? regions[0]
          : regions.reduce((acc, f) => acc ? union(acc, f) : f);
      }

      // ✅ Option 3: Clipping by Another Layer (Canvas Layer)
      if (clipLayer && selCLayer) {
        const layerData = Canvas.getLayerData(selCLayer);
        if (!layerData) {
          toast.error("Selected layer not found.");
          return;
        }

        if (layerData.type === "FeatureCollection") {
          const polys = layerData.features.filter(f =>
            f.geometry.type === "Polygon" || f.geometry.type === "MultiPolygon"
          );
          if (polys.length === 0) {
            toast.warn("No polygons found in the selected layer.");
            return;
          }
          clipGeometry = polys.length === 1
            ? polys[0]
            : polys.reduce((acc, f) => acc ? union(acc, f) : f);
        } else if (layerData.type === "Feature") {
          clipGeometry = layerData;
        }
      }

      if (!clipGeometry) {
        toast.warn("No valid clipping geometry available.");
        return;
      }

      // 📊 Get min/max statistics for the clipped region
      console.log('🔍 Getting raster statistics for clipped region...');
      const rasterStatsResult = await getRasterStats(clipGeometry);
      
      if (rasterStatsResult) {
        console.log('📊 Processing statistics result:', rasterStatsResult);
        
        // Try different band naming conventions
        const possibleBandKeys = ['1', 'band_1', 'band1', Object.keys(rasterStatsResult)[0]];
        let band1Stats = null;
        
        for (const key of possibleBandKeys) {
          if (rasterStatsResult[key] && 
              rasterStatsResult[key].min !== 'Null' && 
              rasterStatsResult[key].min !== null) {
            band1Stats = rasterStatsResult[key];
            console.log(`✅ Found valid stats in band key: ${key}`);
            break;
          }
        }
        
        if (band1Stats) {
          const { min, max } = band1Stats;
          toast.success(`📊 Slope Statistics - Min: ${min.toFixed(2)}, Max: ${max.toFixed(2)}`);
          console.log('📈 Slope Min/Max:', { min, max });
          
          // Store these values in state for further processing
          setRasterStats({ min, max, fullStats: rasterStatsResult });
        } else {
          console.warn('⚠️ No valid statistics found in any band');
          toast.warn('📊 Statistics calculated but no valid data found in clipped region');
          setRasterStats({ 
            min: null, 
            max: null, 
            fullStats: rasterStatsResult,
            error: 'No valid data in clipped region'
          });
        }
      } else {
        console.warn('⚠️ Failed to get raster statistics');
        setRasterStats(null);
      }

      // Calculate bounds from the geometry
      const bounds = L.geoJSON(clipGeometry).getBounds();

      // WMTS URL for slopeAll_1
      const wmtsUrl = "http://192.168.0.158:8080/geoserver/gwc/service/wmts?" +
        "layer=useruploads:slopeAll_1" +
        "&style=" +
        "&tilematrixset=EPSG:900913" +
        "&Service=WMTS&Request=GetTile&Version=1.0.0" +
        "&Format=image/png" +
        "&TileMatrix=EPSG:900913:{z}" +
        "&TileCol={x}&TileRow={y}";

      const tileLayer = L.TileLayer.boundaryCanvas(wmtsUrl, {
        boundary: clipGeometry,
        bounds: bounds,
        maxZoom: 22,
        zIndex: 1000,
      });

      tileLayer.addTo(map);
      const layerName = `Slope (Clipped) - ${new Date().toISOString().split('T')[0]}`;

      setName('slopeAll_1'); // Set the name for the layer control
      layerControls?.addOverlay(tileLayer, layerName);
      map.fitBounds(bounds);

    } catch (error) {
      console.error('❌ Error in loadSlopeWMSLayer:', error);
      toast.error(`Failed to load slope layer: ${error.message}`);
    } finally {
      setloader(false); // Hide loading indicator
    }
  };


  // const loadSlopeWMSLayer = async () => {
  //   if (!map) return;

  //   // Get the drawn polygon
  //   const drawn = drawnItems.getLayer(lastRect);
  //   if (!drawn) {
  //     toast.warn("Please draw a boundary before visualizing.");
  //     return;
  //   }

  //   const clipFeature = drawn.toGeoJSON();
  //   const bounds = drawn.getBounds();

  //   // Build WMTS URL
  //   const wmtsUrl = "http://192.168.0.158:8080/geoserver/gwc/service/wmts?" +
  //     "layer=useruploads:slopeAll_Data" +
  //     "&style=" +
  //     "&tilematrixset=EPSG:900913" +
  //     "&Service=WMTS&Request=GetTile&Version=1.0.0" +
  //     "&Format=image/png" +
  //     "&TileMatrix=EPSG:900913:{z}" +
  //     "&TileCol={x}&TileRow={y}";

  //   // Create tile layer with clipping boundary
  //   const tileLayer = L.TileLayer.boundaryCanvas(wmtsUrl, {
  //     boundary: clipFeature,
  //     bounds: bounds,
  //     maxZoom: 22,
  //     zIndex: 1000,
  //   });

  //   tileLayer.addTo(map);
  //   const layerName = "Slope (Clipped View)"; // Name for layer control
  //   setName(layerName); // Set the name for the layer control
  //   layerControls?.addOverlay(tileLayer, "Slope (Clipped View)");
  //   map.fitBounds(bounds);
  // };


  return (
    <div>
      <div className="hide-show-container">
        <div className="sidepanel-container">
          <div
            style={{ paddingLeft: "5px", cursor: "pointer" }}
            onClick={() => setAdditionalOptionsOpen(!isAdditionalOptionsOpen)}
          >
            Additional Options
          </div>
        </div>


        {/* Conditionally show Options UI */}
        {(clip || clipBox || clipLayer || isAdditionalOptionsOpen) && (
          <div style={{ minWidth: "100%" }}>
            <Options
              clip={clip}
              AddBound={AddBound}
              clipBox={clipBox}
              clipLayer={clipLayer}
              selCont={selCont}
              selState={selState}
              setClip={setClip}
              setBound={setBound}
              setClipBox={setClipBox}
              setClipLayer={setClipLayer}
              setCLayer={setCLayer}
              setCont={setCont}
              setState={setState}
              setDis={setDis}
              selDis={selDis}
              selectedTehsil={selectedTehsil}
              setSelectedTehsil={setSelectedTehsil}
              selectedVillage={selectedVillage}
              setSelectedVillage={setSelectedVillage}
              villageGeojsonFiles={villageGeojsonFiles}
              setVillageGeojsonFiles={setVillageGeojsonFiles}
              filteredTehsilGeojson={filteredTehsilGeojson}
              setFilteredTehsilGeojson={setFilteredTehsilGeojson}
              filteredVillageGeojson={filteredVillageGeojson}
              setFilteredVillageGeojson={setFilteredVillageGeojson}
              selectedTehsilFeature={selectedTehsilFeature}
              setSelectedTehsilFeature={setSelectedTehsilFeature}
              adv_options={true}
              req_box={true}
              req_layer={true}
              req_region={false}
              isAdditionalOptionsOpen={isAdditionalOptionsOpen}
              setAdditionalOptionsOpen={setAdditionalOptionsOpen}
              adv_params={false}
            />
          </div>

        )}
      </div>

      {/* Display current statistics if available */}
      {rasterStats && (
        <div className="stats-display" style={{ 
          padding: "10px", 
          margin: "5px", 
          backgroundColor: rasterStats.error ? "#fff3cd" : "#f8f9fa", 
          border: `1px solid ${rasterStats.error ? "#ffeaa7" : "#dee2e6"}`, 
          borderRadius: "4px",
          fontSize: "12px" 
        }}>
          <strong>Current Slope Statistics:</strong><br/>
          {rasterStats.min !== null && rasterStats.max !== null ? (
            <>Min: {rasterStats.min?.toFixed(2)} | Max: {rasterStats.max?.toFixed(2)}</>
          ) : (
            <span style={{ color: "#856404" }}>
              {rasterStats.error || "No valid data in selected region"}
            </span>
          )}
        </div>
      )}

      {/* Action Button */}

      <div style={{ display: 'flex', gap: '10px', margin: '10px 5px' }}>
        <button
          onClick={loadSlopeWMSLayer}
          className={`visualize-btn ${isSidebarTabs ? "shifted-up" : ""}`}
          style={{ flex: 1 }}
        >
          Visualize
        </button>
        
        <button
          onClick={testRasterAccess}
          className="btn btn-secondary btn-sm"
          style={{ whiteSpace: 'nowrap' }}
          title="Test raster data access methods"
        >
          🧪 Test
        </button>
      </div>


      <ToastContainer position="bottom-right" theme="colored" />
    </div>
  )
}



