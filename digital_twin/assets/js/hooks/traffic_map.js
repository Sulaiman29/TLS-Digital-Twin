/**
 * TrafficMap — LeafletJS hook for the Tartu Digital Twin
 *
 * Renders an OpenStreetMap centered on Tartu city center,
 * places intersection markers, and moves vehicle markers in real-time.
 *
 * Coordinate transform: SUMO .net.xml XY → Tartu GPS
 *   Anchor: TRiia_Turu (Kaubamaja) at SUMO (232, 529) = GPS 58.37798, 26.72738
 *   lat = 58.37798 + (sumo_y - 529) / 111320
 *   lon = 26.72738 + (sumo_x - 232) / 58367
 */

// Intersection positions (from rebuilt SUMO .net.xml)
// netOffset = 301.40, 529.00
const INTERSECTIONS = [
  { id: "TRiia_Kalevi", x: 143.9, y: 374.7, label: "Riia × Ülikooli/Kalevi" },
  { id: "TRiia_Turu", x: 301.4, y: 529.0, label: "Riia × Turu (Kaubamaja)" },
  { id: "TTuru_Vaks", x: 564.5, y: 433.2, label: "Turu × Vaksali" },
  { id: "TTuru_Alek", x: 687.4, y: 197.0, label: "Turu × Aleksandri" },
];

// SUMO XY → Leaflet LatLng (anchor-based transform)
const ANCHOR_SUMO_X = 301.4;   // TRiia_Turu x in .net.xml
const ANCHOR_SUMO_Y = 529.0;   // TRiia_Turu y in .net.xml
const ANCHOR_LAT = 58.37798;   // Riia × Turu intersection latitude
const ANCHOR_LON = 26.72892;   // Riia × Turu intersection longitude (road center, not Kaubamaja building)
const M_PER_DEG_LAT = 111320;  // meters per degree latitude
const M_PER_DEG_LON = 58367;   // meters per degree longitude at ~58.4°N

function sumoToLatLng(x, y) {
  const lat = ANCHOR_LAT + (y - ANCHOR_SUMO_Y) / M_PER_DEG_LAT;
  const lon = ANCHOR_LON + (x - ANCHOR_SUMO_X) / M_PER_DEG_LON;
  return [lat, lon];
}

// Traffic light color from SUMO phase state character
function tlColor(state) {
  if (!state) return "#888";
  const chars = state.split("");
  if (chars.some((c) => c === "G" || c === "g")) return "#00e676";
  if (chars.some((c) => c === "y" || c === "Y")) return "#ffea00";
  return "#ff1744";
}

// Vehicle color based on speed
function vehicleColor(speed) {
  if (speed < 0.5) return "#ff1744"; // stopped
  if (speed < 5) return "#ff9100"; // slow
  if (speed < 10) return "#ffea00"; // medium
  return "#00e676"; // fast
}

const TrafficMap = {
  mounted() {
    // Create map centered on Tartu
    this.map = L.map(this.el, {
      zoomControl: true,
      attributionControl: true,
    }).setView([58.3793, 26.7270], 16);

    // Dark tile layer for professional look
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }
    ).addTo(this.map);

    // Intersection markers
    this.intersectionMarkers = {};
    INTERSECTIONS.forEach((int) => {
      const pos = sumoToLatLng(int.x, int.y);
      const marker = L.circleMarker(pos, {
        radius: 12,
        color: "#fff",
        fillColor: "#888",
        fillOpacity: 0.9,
        weight: 2,
      }).addTo(this.map);
      marker.bindTooltip(int.label, {
        permanent: true,
        direction: "top",
        offset: [0, -15],
        className: "intersection-tooltip",
      });
      this.intersectionMarkers[int.id] = marker;
    });

    // Vehicle marker layer
    this.vehicleMarkers = {};
    this.vehicleLayer = L.layerGroup().addTo(this.map);

    // Listen for server-pushed events
    this.handleEvent("traffic_update", (data) => {
      this.updateVehicles(data.vehicles || []);
      this.updateTrafficLights(data.traffic_lights || []);
    });
  },

  updateVehicles(vehicles) {
    const activeIds = new Set();

    vehicles.forEach((v) => {
      activeIds.add(v.id);
      const pos = sumoToLatLng(v.x, v.y);

      if (this.vehicleMarkers[v.id]) {
        // Move existing marker
        this.vehicleMarkers[v.id].setLatLng(pos);
        this.vehicleMarkers[v.id].setStyle({
          fillColor: vehicleColor(v.speed),
        });
      } else {
        // Create new marker
        const marker = L.circleMarker(pos, {
          radius: 4,
          color: "transparent",
          fillColor: vehicleColor(v.speed),
          fillOpacity: 0.85,
          weight: 0,
        });
        marker.bindTooltip(
          `${v.id}<br/>Speed: ${v.speed} m/s<br/>Lane: ${v.lane}`,
          { direction: "top", offset: [0, -8] }
        );
        this.vehicleLayer.addLayer(marker);
        this.vehicleMarkers[v.id] = marker;
      }
    });

    // Remove departed vehicles
    Object.keys(this.vehicleMarkers).forEach((id) => {
      if (!activeIds.has(id)) {
        this.vehicleLayer.removeLayer(this.vehicleMarkers[id]);
        delete this.vehicleMarkers[id];
      }
    });
  },

  updateTrafficLights(lights) {
    lights.forEach((tl) => {
      const marker = this.intersectionMarkers[tl.id];
      if (marker) {
        const color = tlColor(tl.state);
        marker.setStyle({ fillColor: color });
      }
    });
  },

  destroyed() {
    if (this.map) {
      this.map.remove();
    }
  },
};

export default TrafficMap;
