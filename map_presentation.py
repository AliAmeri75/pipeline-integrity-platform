"""High-contrast map overlays, scoped to each Folium map instance."""
from branca.element import Element


def readable_map_overlays(pipeline_map):
    """Keep legends and controls readable on street and satellite basemaps."""
    selector='#'+pipeline_map.get_name()
    pipeline_map.get_root().header.add_child(Element('''<style>
    SELECTOR .legend {
        background: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        box-shadow: 0 3px 12px rgba(15, 23, 42, .22);
        padding: 10px 12px;
        box-sizing: content-box;
        max-width: calc(100vw - 64px);
        height: auto !important;
    }
    SELECTOR .legend svg { display: block; max-width: 100%; overflow: visible; }
    SELECTOR .legend svg text {
        fill: #111827 !important;
        font-family: Arial, sans-serif;
        font-size: 12px;
        text-shadow: none !important;
    }
    SELECTOR .legend .caption { font-weight: 700; }
    SELECTOR .leaflet-control-layers,
    SELECTOR .leaflet-tooltip,
    SELECTOR .leaflet-popup-content-wrapper,
    SELECTOR .leaflet-control-scale-line {
        background: #ffffff !important;
        color: #111827 !important;
        border-color: #cbd5e1;
        text-shadow: none;
    }
    SELECTOR .leaflet-tooltip { opacity: 1 !important; }
    SELECTOR .leaflet-popup-tip { background: #ffffff; }
    </style>'''.replace('SELECTOR',selector)),name='readable_map_overlays')
    return pipeline_map
