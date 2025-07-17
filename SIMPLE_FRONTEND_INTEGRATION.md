# Simple Frontend Integration for Your Workflow

## Your Exact Flow:
1. **User uploads TIFF** → GeoServer (creates layer like `delhi_misiac7909`)
2. **Frontend sends**: layer name + clipping geometry
3. **Backend**: Fetches from WMS → Calculates stats → Returns min/max

## Simplified Backend Call

```javascript
// Updated applySLD function for your React Clipper component
const applySLD = async () => {
    console.log('Selected layer:', selLayer);
    console.log('Selected vector:', selStyle);
    
    // Get layer name (e.g., "delhi_misiac7909") 
    let layerName = selLayer.split("#")[0]; // Remove any hash identifier
    
    // Get vector geometry from Canvas
    let vectorId = Canvas.getLayerId(selStyle);
    let vectorGeo = Canvas.getLayerGeo(vectorId);
    let geometry = vectorGeo[0]; // The clipping geometry
    
    // Prepare simple request data
    const requestData = {
        layer_name: layerName,        // e.g., "delhi_misiac7909"
        polygon: geometry             // GeoJSON geometry for clipping
    };
    
    try {
        // Call simplified backend endpoint
        const response = await fetch('/api/get_raster_stats/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify(requestData)
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            console.log('✅ Clipping successful!');
            console.log('Statistics:', result.min_max);
            
            // Display the min/max values to user
            displayClippingResults(result, layerName, selStyle);
            
            // Create the clipped layer on map
            createClippedLayer(result, layerName, selStyle, vectorGeo);
            
        } else {
            console.error('❌ Clipping failed:', result.error);
            toast.error(`Failed: ${result.error}`);
        }
        
    } catch (error) {
        console.error('❌ Network error:', error);
        toast.error('Network error');
    }
};

function displayClippingResults(result, layerName, vectorName) {
    // Show the statistics to the user
    const stats = result.min_max.band_1;
    
    if (stats.error) {
        toast.warning(`No data in clipped area: ${stats.error}`);
        return;
    }
    
    const message = `
        Clipped ${layerName} with ${vectorName}
        Min: ${stats.min.toFixed(2)}
        Max: ${stats.max.toFixed(2)}
        Mean: ${stats.mean.toFixed(2)}
        Points: ${stats.count.toLocaleString()}
    `;
    
    toast.success(message);
    
    // You could also update a UI panel with detailed stats
    updateStatsPanel(stats, layerName);
}

function createClippedLayer(result, layerName, vectorName, vectorGeo) {
    // Create the clipped layer on the map
    let bounds = L.latLngBounds(
        [result.clip_bounds[1], result.clip_bounds[0]], // [minLat, minLon]
        [result.clip_bounds[3], result.clip_bounds[2]]  // [maxLat, maxLon]
    );
    
    // Remove original layer
    selectedLayers[selLayer].remove();
    
    // Create new clipped layer
    let clippedLayer = L.TileLayer.boundaryCanvas(selectedLayers[selLayer]._url, {
        boundary: vectorGeo[0],  // Use the clipping geometry as boundary
        zIndex: 1000,
        bounds: bounds,
        maxZoom: 20,
    });
    
    // Add to map and controls
    const clippedName = `${layerName}_clipped_by_${vectorName}`;
    layerControls.addOverlay(clippedLayer, clippedName);
    clippedLayer.addTo(map);
    
    // Update layers state
    SetLayers(prevLayers => ({
        ...prevLayers,
        [clippedName]: clippedLayer,
    }));
}

function updateStatsPanel(stats, layerName) {
    // Update a statistics panel in your UI
    const statsHtml = `
        <div class="stats-panel">
            <h4>Statistics for ${layerName}</h4>
            <table>
                <tr><td>Minimum:</td><td>${stats.min.toFixed(2)}</td></tr>
                <tr><td>Maximum:</td><td>${stats.max.toFixed(2)}</td></tr>
                <tr><td>Mean:</td><td>${stats.mean.toFixed(2)}</td></tr>
                <tr><td>Std Dev:</td><td>${stats.std.toFixed(2)}</td></tr>
                <tr><td>Valid Points:</td><td>${stats.count.toLocaleString()}</td></tr>
            </table>
        </div>
    `;
    
    // Display in your stats container
    document.getElementById('stats-container').innerHTML = statsHtml;
}

// Helper function for CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
```

## Backend Response Format

Your simplified backend now returns:

```json
{
    "status": "success",
    "layer": "delhi_misiac7909",
    "min_max": {
        "band_1": {
            "min": 45.2,
            "max": 234.8,
            "mean": 142.5,
            "std": 56.3,
            "count": 15847
        }
    },
    "geometry_type": "Polygon",
    "clip_bounds": [77.123, 28.456, 77.789, 28.987],
    "raster_info": {
        "bands": 1,
        "width": 512,
        "height": 512,
        "crs": "EPSG:4326"
    }
}
```

## Key Simplifications

1. **Direct WMS**: No file searching, pattern matching - straight to GeoServer WMS
2. **Simple Input**: Just `layer_name` and `polygon` 
3. **Clear Output**: Min/max stats and basic info
4. **Error Handling**: Clear error messages for debugging

Your backend is now optimized for your exact workflow! 🚀
