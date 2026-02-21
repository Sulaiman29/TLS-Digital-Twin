/**
 * TrafficMap — LeafletJS hook for the Tartu Digital Twin
 *
 * Renders an OpenStreetMap centered on Tartu city center,
 * places intersection markers, and moves vehicle markers in real-time.
 *
 * Coordinate transform: SUMO XY → Tartu GPS
 *   lat = 58.3780 + y * 0.000009
 *   lon = 26.7230 + x * 0.0000167
 */

// Intersection positions (from SUMO .net.xml — NOT nodes.nod.xml)
const INTERSECTIONS = [
  { id: "TRiia_Vaba", x: 200, y: 500, label: "Riia × Vabaduse" },
  { id: "TRiia_Turu", x: 200, y: 200, label: "Riia × Turu (Kaubamaja)" },
  { id: "TTuru_Vaks", x: 500, y: 200, label: "Turu × Vaksali" },
  { id: "TTuru_Alek", x: 800, y: 200, label: "Turu × Aleksandri" },
];

// SUMO XY → Leaflet LatLng
const ORIGIN_LAT = 58.378;
const ORIGIN_LON = 26.723;
const SCALE_LAT = 0.000009;
const SCALE_LON = 0.0000167;

function sumoToLatLng(x, y) {
  return [ORIGIN_LAT + y * SCALE_LAT, ORIGIN_LON + x * SCALE_LON];
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
