import React, { useState, useContext, useEffect, useRef } from "react";
import { GlobalContext } from "../../../App";
import { HOST } from "../../host";
import "../../BoundaryCanvas"
import L from "leaflet"
import { ToastContainer, toast } from "react-toastify";

function Clipper() {
    const [show, setShow] = useState(false);
    const [layer, setLayer] = useState("");
    const [type, setType] = useState("");
    const [projects, setProjects] = useState([]);
    const [pro, setPro] = useState("");
    const { vis, userInfo, layerControls, selectedLayers, Canvas, map, SetLayers } = useContext(GlobalContext);
    const toolvisRef = useRef(null);
    const [FLayers, setFLayers] = useState([])
    const [selLayer, SetlLayer] = useState(null)
    const [selStyle, setSstyle] = useState(null)
    const [styles, setStyles] = useState([])
    const [vectors, setVectors] = useState([]);
    
    useEffect(() => {
        if (layerControls && show) { 
            let layers = []
            Object.keys(selectedLayers).forEach((ele) => {
                if (selectedLayers[ele] && selectedLayers[ele]._url) {
                    layers.push({ "name": ele.split("#")[0], "id": ele });

                }
            });
            setFLayers(layers)
            setVectors(Canvas.getLayers());
        }
        SetlLayer(null)
    }, [show])

    const applySLD = () => {
        console.log(selLayer, selStyle)
        let id = Canvas.getLayerId(selStyle)
        console.log('id', id)
        let geo = Canvas.getLayerGeo(id)
        console.log('geo', geo)
        let bounds = geo[1]
        console.log('bounds', bounds)
        bounds = L.latLngBounds(
            [geo[1][0], geo[1][1]],
            [geo[1][2], geo[1][3]]
        );

        let url = selectedLayers[selLayer]._url
        console.log(geo)

        selectedLayers[selLayer].remove()
        let layer = L.TileLayer.boundaryCanvas(url, {
            boundary: geo[0],
            zIndex: 1000,
            bounds: bounds,
            maxZoom: 20,
        });
        layerControls.addOverlay(layer, `clipped ${selLayer} by ${selStyle}`);
        layer.addTo(map);
        SetLayers(prevDictionary => ({
            ...prevDictionary,
            [selLayer]: layer,
        }));

    };


    function close() {
        setShow(false);
    }

    return (
        <div
            style={{ position: vis ? "absolute" : "relative" }}
            className="toolscont"
        >
            <button
                title="Raster Layer Clipper"
                className="btn text-white"
                id="roadroute"
                onClick={() => setShow((prevShow) => !prevShow)}
                style={{
                    zIndex: "1000",
                    fontSize: "15px",
                    backgroundColor:'black',
                    padding: "2px 2px",
                    width: "40px",
                    height: "40px",
                    borderRadius: "50%",
                    border: "none"
                    
                    
                }}
            >
                <i className="fa-solid fa-scissors"></i>
            </button>
            {show && (
                <div
                    ref={toolvisRef}
                    className="toolsvis"
                    id="toolvis"
                    style={{ display: "flex", flexDirection: "column", width: "200px" }}
                >
                       <span
                        onClick={close}
                        className="toolclose"
                    >
                        &times;
                    </span>

                    <div>
                        <select onChange={(e) => SetlLayer(e.target.value)} value={selLayer} className="form-select text-white mt-1 swipe-options" style={{ marginBottom: "5px", backgroundColor:'transparent', border:'2px solid white', fontSize: '13px' }}>
                            <option value="" >Select A Raster Layer</option>
                            {FLayers && FLayers.length && FLayers.map((layer) => (
                                <option key={layer.id} value={layer.id}>
                                    {layer.name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <select onChange={(e) => setSstyle(e.target.value)} value={selStyle} className="form-select text-white mt-1 swipe-options" style={{ marginBottom: "5px", backgroundColor:'transparent', border:'2px solid white', fontSize: '13px' }}>
                            <option value="">Select A vector Laye</option>

                            {vectors && vectors.length && vectors.map((comp) => (
                                <option key={comp} value={comp}>
                                    {comp}
                                </option>
                            ))}
                        </select>
                    </div>

                    <button onClick={() => applySLD()} className='btn btn-primary border-0 mt-2 mb-2' style={{ width: '98%', height: '30px', fontSize: '13px'}} >Clip</button>
                </div>
            )}
        </div>
    );
}

export default Clipper;