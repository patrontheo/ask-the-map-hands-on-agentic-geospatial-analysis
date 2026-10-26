import { api } from "./api.js";
import { escapeHtml, formatEur } from "./format.js";

const COLORS = { flood: "#1e8fd6", wildfire: "#f07c00", other: "#7c3aed", site: "#343c3d", selected: "#ff1721",
  brand: "#00008f", district: "#5f6b6d" };
// OpenStreetMap standard tiles: no API key; attribution required by the OSM tile usage policy.
const STYLE = {
  version: 8,
  sources: {
    osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#eef1f4" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.6, "raster-opacity": 0.9 } },
  ],
};
// Drawing order, bottom to top. Layers are added only when a tool shows them.
const RANK = { districts: 1, buildings: 2, parcels: 2, incident: 3, simplified_footprint: 4, sites: 5, line: 6 };

let map;
let ready;
const catalog = new Map(); // layer_id -> metadata from /api/layers
const added = new Map(); // layer_id -> { rank, mapLayerIds }
const legendBoxes = new Map(); // layer_id -> checkbox
let sitesById = new Map();

export function initMap(container) {
  map = new maplibregl.Map({
    container,
    style: STYLE,
    center: [2.35, 46.6],
    zoom: 5,
    attributionControl: { compact: true, customAttribution: "Footprints © Copernicus EMS. Portfolio is synthetic." },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  // MapLibre only re-measures on window resize; the grid layout can change the container size without one.
  new ResizeObserver(() => map.resize()).observe(map.getContainer());
  watchBasemap();
  ready = (async () => {
    await new Promise((resolve) => map.on("load", resolve));
    for (const layer of await api.layers()) catalog.set(layer.id, layer);
  })();
  return ready;
}

function watchBasemap() {
  let failures = 0;
  map.on("error", (e) => {
    if (e.sourceId !== "osm" || ++failures !== 4) return;
    map.setLayoutProperty("osm", "visibility", "none");
    const el = document.getElementById("map-notice");
    el.textContent = "Basemap tiles are unavailable from this network. Showing the data layers only.";
    el.hidden = false;
  });
}

function perilColor(peril) {
  return COLORS[peril] ?? COLORS.other;
}

function beforeId(rank) {
  const above = [...added.values()].filter((l) => l.rank > rank).sort((a, b) => a.rank - b.rank)[0];
  return above?.mapLayerIds[0];
}

function addMapLayers(layerId, rank, geojson, specs) {
  map.addSource(layerId, { type: "geojson", data: geojson });
  const before = beforeId(rank);
  for (const spec of specs) map.addLayer({ ...spec, source: layerId }, before);
  added.set(layerId, { rank, mapLayerIds: specs.map((s) => s.id) });
}

async function ensureLayer(layerId) {
  if (added.has(layerId)) return;
  const meta = catalog.get(layerId);
  if (!meta) throw new Error(`Unknown layer ${layerId}`);
  const geojson = await api.layer(meta.url);
  if (added.has(layerId)) return; // added meanwhile by a concurrent action
  const rank = RANK[meta.kind] ?? 2;

  if (meta.kind === "sites") {
    sitesById = new Map(geojson.features.map((f) => [f.properties.site_id, f]));
    const radius = (lo, hi) => ["interpolate", ["linear"], ["zoom"], 8, lo, 14, hi];
    addMapLayers(layerId, rank, geojson, [
      { id: "sites", type: "circle",
        paint: { "circle-radius": radius(3.5, 6.5), "circle-color": COLORS.site, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } },
      { id: "sites-highlight", type: "circle", filter: ["in", ["get", "site_id"], ["literal", []]],
        paint: { "circle-radius": radius(5.5, 9), "circle-color": COLORS.selected, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } },
    ]);
    for (const id of ["sites", "sites-highlight"]) {
      map.on("click", id, (e) => showSitePopup(e.features[0]));
      map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
    }
    addLegendEntry(layerId, "Portfolio sites", { color: COLORS.site, shape: "dot" });
  } else if (meta.kind === "incident") {
    const color = perilColor(meta.peril);
    addMapLayers(layerId, rank, geojson, [
      { id: `${layerId}-fill`, type: "fill", paint: { "fill-color": color, "fill-opacity": 0.3 } },
      { id: `${layerId}-line`, type: "line", paint: { "line-color": color, "line-width": 1.2 } },
    ]);
    addLegendEntry(layerId, meta.name, { color });
    addLegendEntry(`simplified:${meta.incident_id}`, "Simplified copy read by the model",
      { shape: "outline", checked: false, indent: true, rank: rank - 0.5 });
  } else if (meta.kind === "simplified_footprint") {
    addMapLayers(layerId, rank, geojson, [
      { id: `${layerId}-line`, type: "line", paint: { "line-color": COLORS.brand, "line-width": 2, "line-dasharray": [2, 1.5] } },
    ]);
  } else if (meta.kind === "districts") {
    addMapLayers(layerId, rank, geojson, [
      { id: "districts-line", type: "line",
        paint: { "line-color": COLORS.district, "line-width": 1, "line-opacity": 0.7, "line-dasharray": [4, 3] } },
    ]);
    addLegendEntry(layerId, "Districts", { color: "transparent" });
  } else {
    addMapLayers(layerId, rank, geojson, [
      { id: `${layerId}-fill`, type: "fill", paint: { "fill-color": COLORS.brand, "fill-opacity": 0.15 } },
    ]);
    addLegendEntry(layerId, meta.name, { color: COLORS.brand });
  }
}

function setVisible(layerId, visible) {
  const layer = added.get(layerId);
  if (layer) for (const id of layer.mapLayerIds) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  const box = legendBoxes.get(layerId);
  if (box) box.checked = visible;
}

async function showLayer(layerId) {
  await ensureLayer(layerId);
  setVisible(layerId, true);
}

function addLegendEntry(layerId, text, { color, shape, checked = true, indent = false, rank }) {
  if (legendBoxes.has(layerId)) return;
  const label = document.createElement("label");
  if (indent) label.classList.add("sub");
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked });
  box.addEventListener("change", () => (box.checked ? showLayer(layerId) : setVisible(layerId, false)));
  const swatch = document.createElement("span");
  swatch.className = `swatch${shape ? ` ${shape}` : ""}`;
  if (color === "transparent") swatch.style.border = `1px dashed ${COLORS.district}`;
  else if (color) swatch.style.background = color;
  label.append(box, swatch, document.createTextNode(text));
  legendBoxes.set(layerId, box);

  // Keep the legend in drawing order, top layer first.
  const legend = document.getElementById("legend");
  const order = rank ?? RANK[catalog.get(layerId)?.kind] ?? 2;
  label.dataset.rank = order;
  const after = [...legend.children].find((el) => Number(el.dataset.rank) < order);
  legend.insertBefore(label, after ?? null);
}

function showSitePopup(feature) {
  const p = feature.properties;
  const rows = [["Company", p.company_name], ["Address", `${p.address}, ${p.city}`], ["District", p.district_name],
    ["Property", p.property_type], ["TIV", formatEur(p.tiv_eur)]];
  const html = `<h3>${escapeHtml(p.site_id)}</h3><dl>${rows.map(([k, v]) =>
    `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join("")}</dl>`;
  new maplibregl.Popup({ offset: 10, maxWidth: "300px" }).setLngLat(feature.geometry.coordinates).setHTML(html).addTo(map);
}

function ensureLine() {
  if (added.has("line")) return;
  addMapLayers("line", RANK.line, emptyCollection(), [
    { id: "line", type: "line", paint: { "line-color": COLORS.brand, "line-width": 2.5, "line-dasharray": [2, 1] } },
  ]);
}

// Applies a tool result's map actions in order. Tools decide what is shown; the map never shows data by itself.
export async function applyMapActions(actions = []) {
  await ready;
  for (const action of actions) {
    if (action.type === "show_layer") {
      await showLayer(action.layer_id);
    } else if (action.type === "hide_layer") {
      setVisible(action.layer_id, false);
    } else if (action.type === "highlight_sites") {
      await showLayer("sites");
      map.setFilter("sites-highlight", ["in", ["get", "site_id"], ["literal", action.site_ids]]);
    } else if (action.type === "clear_highlight") {
      if (added.has("sites")) map.setFilter("sites-highlight", ["in", ["get", "site_id"], ["literal", []]]);
    } else if (action.type === "fit_bounds") {
      const [w, s, e, n] = action.bbox;
      map.fitBounds([[w, s], [e, n]], { padding: 60, maxZoom: 15 });
    } else if (action.type === "draw_line") {
      await showLayer("sites");
      const a = sitesById.get(action.site_a), b = sitesById.get(action.site_b);
      if (!a || !b) continue;
      ensureLine();
      map.getSource("line").setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {},
        geometry: { type: "LineString", coordinates: [a.geometry.coordinates, b.geometry.coordinates] } }] });
    }
  }
}

function emptyCollection() {
  return { type: "FeatureCollection", features: [] };
}
