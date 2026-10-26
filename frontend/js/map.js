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

let map;
let ready = false;
let sitesById = new Map();

export async function initMap(container) {
  map = new maplibregl.Map({
    container,
    style: STYLE,
    center: [2.35, 46.6],
    zoom: 5,
    attributionControl: { compact: true, customAttribution: "Footprints © Copernicus EMS. Portfolio is synthetic." },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  watchBasemap();

  await new Promise((resolve) => map.on("load", resolve));
  const layers = await api.layers();
  const data = Object.fromEntries(await Promise.all(layers.map(async (l) => [l.id, await api.layer(l.url)])));

  addDistricts(data.districts);
  for (const layer of layers.filter((l) => l.kind === "incident")) addIncident(layer, data[layer.id]);
  for (const layer of layers.filter((l) => l.kind === "baseline_footprint")) addBaselineFootprint(layer, data[layer.id]);
  addSites(data.sites);
  addHighlightAndLine();
  buildLegend(layers);
  fitTo(data.sites);
  ready = true;
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

function addDistricts(geojson) {
  map.addSource("districts", { type: "geojson", data: geojson });
  map.addLayer({ id: "districts-line", type: "line", source: "districts",
    paint: { "line-color": COLORS.district, "line-width": 1, "line-opacity": 0.7, "line-dasharray": [4, 3] } });
}

function addIncident(layer, geojson) {
  const color = perilColor(layer.peril);
  map.addSource(layer.id, { type: "geojson", data: geojson });
  map.addLayer({ id: `${layer.id}-fill`, type: "fill", source: layer.id, paint: { "fill-color": color, "fill-opacity": 0.3 } });
  map.addLayer({ id: `${layer.id}-line`, type: "line", source: layer.id, paint: { "line-color": color, "line-width": 1.2 } });
}

function addBaselineFootprint(layer, geojson) {
  map.addSource(layer.id, { type: "geojson", data: geojson });
  map.addLayer({ id: `${layer.id}-line`, type: "line", source: layer.id, layout: { visibility: "none" },
    paint: { "line-color": COLORS.brand, "line-width": 2, "line-dasharray": [2, 1.5] } });
}

function addSites(geojson) {
  sitesById = new Map(geojson.features.map((f) => [f.properties.site_id, f]));
  map.addSource("sites", { type: "geojson", data: geojson });
  map.addLayer({ id: "sites", type: "circle", source: "sites",
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3.5, 14, 6.5],
      "circle-color": COLORS.site, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
  for (const id of ["sites"]) {
    map.on("click", id, (e) => showSitePopup(e.features[0]));
    map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
  }
}

function addHighlightAndLine() {
  map.addLayer({ id: "sites-highlight", type: "circle", source: "sites", filter: ["in", ["get", "site_id"], ["literal", []]],
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 5.5, 14, 9],
      "circle-color": COLORS.selected, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  map.addSource("line", { type: "geojson", data: emptyCollection() });
  map.addLayer({ id: "line", type: "line", source: "line",
    paint: { "line-color": COLORS.brand, "line-width": 2.5, "line-dasharray": [2, 1] } });
  map.on("click", "sites-highlight", (e) => showSitePopup(e.features[0]));
}

function showSitePopup(feature) {
  const p = feature.properties;
  const rows = [["Company", p.company_name], ["Address", `${p.address}, ${p.city}`], ["District", p.district_name],
    ["Property", p.property_type], ["TIV", formatEur(p.tiv_eur)]];
  const html = `<h3>${escapeHtml(p.site_id)}</h3><dl>${rows.map(([k, v]) =>
    `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join("")}</dl>`;
  new maplibregl.Popup({ offset: 10, maxWidth: "300px" }).setLngLat(feature.geometry.coordinates).setHTML(html).addTo(map);
}

function buildLegend(layers) {
  const legend = document.getElementById("legend");
  const groups = [
    [
      { label: "Portfolio sites", ids: ["sites"], color: COLORS.site, shape: "dot" },
      { label: "Selected sites", ids: ["sites-highlight"], color: COLORS.selected, shape: "dot" },
    ],
    layers.filter((l) => l.kind === "incident").map((l) => ({
      label: l.name, ids: [`${l.id}-fill`, `${l.id}-line`], color: perilColor(l.peril),
    })),
    [
      ...layers.filter((l) => l.kind === "baseline_footprint").map((l) => ({
        label: `What the model sees: ${l.incident_id}`, ids: [`${l.id}-line`], shape: "outline", off: true,
        title: l.simplification?.simplified ? "Simplified footprint given to the model in its prompt" : "Unchanged footprint",
      })),
      { label: "Districts", ids: ["districts-line"], color: "transparent" },
    ],
  ];
  groups.filter((g) => g.length).forEach((group, i) => {
    if (i > 0) legend.append(Object.assign(document.createElement("div"), { className: "group-gap" }));
    for (const entry of group) legend.append(legendEntry(entry));
  });
}

function legendEntry(entry) {
  const label = document.createElement("label");
  if (entry.title) label.title = entry.title;
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: !entry.off });
  box.addEventListener("change", () => {
    for (const id of entry.ids) map.setLayoutProperty(id, "visibility", box.checked ? "visible" : "none");
  });
  const swatch = document.createElement("span");
  swatch.className = `swatch${entry.shape ? ` ${entry.shape}` : ""}`;
  if (entry.color === "transparent") swatch.style.border = `1px dashed ${COLORS.district}`;
  else if (entry.color) swatch.style.background = entry.color;
  label.append(box, swatch, document.createTextNode(entry.label));
  return label;
}

export function applyMapActions(actions = []) {
  if (!ready) return;
  for (const action of actions) {
    if (action.type === "highlight_sites") {
      map.setFilter("sites-highlight", ["in", ["get", "site_id"], ["literal", action.site_ids]]);
    } else if (action.type === "clear_highlight") {
      map.setFilter("sites-highlight", ["in", ["get", "site_id"], ["literal", []]]);
    } else if (action.type === "fit_bounds") {
      const [w, s, e, n] = action.bbox;
      map.fitBounds([[w, s], [e, n]], { padding: 60, maxZoom: 15 });
    } else if (action.type === "draw_line") {
      const a = sitesById.get(action.site_a), b = sitesById.get(action.site_b);
      if (!a || !b) continue;
      map.getSource("line").setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {},
        geometry: { type: "LineString", coordinates: [a.geometry.coordinates, b.geometry.coordinates] } }] });
    }
  }
}

function fitTo(geojson) {
  const coords = geojson.features.map((f) => f.geometry.coordinates);
  if (!coords.length) return;
  const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
  map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
    { padding: 80, maxZoom: 14, duration: 0 });
}

function emptyCollection() {
  return { type: "FeatureCollection", features: [] };
}
