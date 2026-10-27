import { api } from "./api.js";
import { escapeHtml, formatEur } from "./format.js";

const COLORS = { flood: "#1e8fd6", wildfire: "#f07c00", other: "#7c3aed", site: "#343c3d", selected: "#ff1721",
  brand: "#00008f", district: "#5f6b6d", building: "#0e9f8e", buildingLine: "#076b5f" };
// Positron vector basemap from OpenFreeMap: no API key (CARTO's Positron tiles now need one). Its tiles carry
// their own OpenFreeMap / OpenMapTiles / OpenStreetMap attribution.
const BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const FALLBACK_STYLE = {
  version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#eef1f4" } }],
};

// The style is fetched first: if the network blocks it, the map still starts, without a basemap.
async function basemapStyle() {
  try {
    const response = await fetch(BASEMAP_STYLE_URL, { signal: AbortSignal.timeout(8000) });
    if (response.ok) return await response.json();
  } catch {
    // fall through to the plain background
  }
  return null;
}
// Drawing order, bottom to top. Layers are added only when a tool shows them.
const RANK = { districts: 1, incident: 2, parcels: 3, buildings: 4, sites: 5, line: 6 };

let map;
let ready;
const catalog = new Map(); // layer_id -> metadata from /api/layers
const added = new Map(); // layer_id -> { rank, mapLayerIds, visible }
const loading = new Map(); // layer_id -> pending fetch/add promise
const shapeSiteIds = new Map(); // buildings/parcels -> site IDs with replacement geometry
const extents = new Map(); // layer_id -> [west, south, east, north]
const legendBoxes = new Map(); // layer_id -> checkbox
let sitesById = new Map();

export function initMap(container) {
  ready = (async () => {
    const basemap = await basemapStyle();
    map = new maplibregl.Map({
      container,
      style: basemap ?? FALLBACK_STYLE,
      center: [2.35, 46.6],
      zoom: 5,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    // MapLibre only re-measures on window resize; the grid layout can change the container size without one.
    new ResizeObserver(() => map.resize()).observe(map.getContainer());
    if (basemap) watchBasemap(basemap);
    else showBasemapNotice();
    await new Promise((resolve) => map.on("load", resolve));
    // Add attribution after the initial style/source updates, then collapse its default expanded state.
    map.addControl(new maplibregl.AttributionControl({
      compact: true, customAttribution: "Footprints © Copernicus EMS. Portfolio is synthetic.",
    }), "bottom-right");
    const attribution = map.getContainer().querySelector(".maplibregl-ctrl-attrib");
    if (attribution) {
      attribution.open = false;
      attribution.classList.remove("maplibregl-compact-show");
    }
    for (const layer of await api.layers()) catalog.set(layer.id, layer);
  })();
  return ready;
}

function showBasemapNotice() {
  const el = document.getElementById("map-notice");
  el.textContent = "Basemap tiles are unavailable from this network. Showing the data layers only.";
  el.hidden = false;
}

// After repeated tile failures, hide the basemap rather than show a half-drawn one.
function watchBasemap(style) {
  const sources = new Set(Object.keys(style.sources));
  const layerIds = style.layers.filter((l) => l.type !== "background").map((l) => l.id);
  let failures = 0;
  map.on("error", (e) => {
    if (!sources.has(e.sourceId) || ++failures !== 4) return;
    for (const id of layerIds) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
    showBasemapNotice();
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
  added.set(layerId, { rank, mapLayerIds: specs.map((s) => s.id), visible: true });
}

async function ensureLayer(layerId) {
  if (added.has(layerId)) return;
  if (!loading.has(layerId)) {
    loading.set(layerId, loadLayer(layerId).finally(() => loading.delete(layerId)));
  }
  await loading.get(layerId);
}

async function loadLayer(layerId) {
  const meta = catalog.get(layerId);
  if (!meta) throw new Error(`Unknown layer ${layerId}`);
  const geojson = await api.layer(meta.url);
  extents.set(layerId, geojsonBounds(geojson));
  const rank = RANK[meta.kind] ?? 2;

  if (meta.kind === "sites") {
    sitesById = new Map(geojson.features.map((f) => [f.properties.site_id, f]));
    for (const id of ["parcels", "buildings"]) if (catalog.has(id)) await ensureLayer(id);
    const radius = (lo, hi) => ["interpolate", ["linear"], ["zoom"], 8, lo, 14, hi];
    const point = (lo, hi, color, stroke) => ({ "circle-radius": radius(lo, hi), "circle-color": color, "circle-stroke-color": "#fff",
      "circle-stroke-width": stroke });
    addMapLayers(layerId, rank, geojson, [
      { id: "sites", type: "circle", paint: point(3.5, 6.5, COLORS.site, 1.5) },
      { id: "sites-highlight", type: "circle", filter: ["in", ["get", "site_id"], ["literal", []]],
        paint: point(5.5, 9, COLORS.selected, 2) },
    ]);
    // One handler, so a click on a point over a building over a parcel opens a single popup.
    const clickable = () => ["sites-highlight", "sites", "site-buildings-fill", "site-parcels-fill"].filter((id) => map.getLayer(id));
    const siteAt = (point) => map.queryRenderedFeatures(point, { layers: clickable() })[0]?.properties.site_id;
    map.on("click", (e) => {
      const siteId = siteAt(e.point);
      if (siteId) showSitePopup(sitesById.get(siteId));
    });
    map.on("mousemove", (e) => { map.getCanvas().style.cursor = siteAt(e.point) ? "pointer" : ""; });
    addLegendEntry(layerId, "Portfolio sites", { color: COLORS.site, shape: "dot" });
  } else if (meta.kind === "parcels" || meta.kind === "buildings") {
    shapeSiteIds.set(layerId, geojson.features.filter((f) => f.geometry).map((f) => f.properties.site_id));
    addMapLayers(layerId, rank, geojson, siteShapeSpecs(meta.kind));
  } else if (meta.kind === "incident") {
    const color = perilColor(meta.peril);
    addMapLayers(layerId, rank, geojson, [
      { id: `${layerId}-fill`, type: "fill", paint: { "fill-color": color, "fill-opacity": 0.15 } },
      { id: `${layerId}-line`, type: "line", paint: { "line-color": color, "line-width": 2 } },
    ]);
    addLegendEntry(layerId, meta.name, { color });
  } else if (meta.kind === "districts") {
    addMapLayers(layerId, rank, geojson, [
      { id: "districts-line", type: "line",
        paint: { "line-color": COLORS.district, "line-width": 1, "line-opacity": 0.7, "line-dasharray": [4, 3] } },
    ]);
    addLegendEntry(layerId, "Communes", { color: "transparent" });
  } else {
    addMapLayers(layerId, rank, geojson, [
      { id: `${layerId}-fill`, type: "fill", paint: { "fill-color": COLORS.brand, "fill-opacity": 0.15 } },
    ]);
    addLegendEntry(layerId, meta.name, { color: COLORS.brand });
  }
}

// Each site's parcels and buildings, shown from SITE_SHAPES_MINZOOM; past POINTS_FADE_ZOOM they replace the point.
const SITE_SHAPES_MINZOOM = 11;
const POINTS_FADE_ZOOM = [14, 15];

function siteShapeSpecs(kind) {
  if (kind === "parcels") {
    // A faint tint: the whole parcel reads as one site and can be clicked when the point is hidden.
    return [
      { id: "site-parcels-fill", type: "fill", minzoom: SITE_SHAPES_MINZOOM,
        paint: { "fill-color": COLORS.brand, "fill-opacity": 0.06 } },
      { id: "site-parcels-line", type: "line", minzoom: SITE_SHAPES_MINZOOM,
        paint: { "line-color": COLORS.brand, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 1.2, 18, 2.5],
          "line-opacity": 0.9, "line-dasharray": [2, 1.5] } },
      { id: "site-parcels-highlight", type: "line", minzoom: SITE_SHAPES_MINZOOM,
        filter: ["in", ["get", "site_id"], ["literal", []]],
        paint: { "line-color": COLORS.selected, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 2, 18, 3.5] } },
    ];
  }
  return [
    { id: "site-buildings-fill", type: "fill", minzoom: SITE_SHAPES_MINZOOM,
      paint: { "fill-color": COLORS.building, "fill-opacity": 0.85 } },
    { id: "site-buildings-highlight", type: "fill", minzoom: SITE_SHAPES_MINZOOM,
      filter: ["in", ["get", "site_id"], ["literal", []]],
      paint: { "fill-color": COLORS.selected, "fill-opacity": 0.95 } },
    // A real line layer: fill outlines are always 1 px. Thicker as you zoom in, so small buildings still read.
    { id: "site-buildings-line", type: "line", minzoom: SITE_SHAPES_MINZOOM,
      paint: { "line-color": COLORS.buildingLine, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 1, 16, 1.5, 19, 2.5] } },
  ];
}

function updatePointOpacity() {
  if (!added.has("sites")) return;
  const ids = [...new Set([...shapeSiteIds].filter(([id]) => added.get(id)?.visible).flatMap(([, ids]) => ids))];
  // Keep the zoom expression at the top level, as MapLibre's style specification requires.
  const opacity = ids.length ? ["interpolate", ["linear"], ["zoom"], POINTS_FADE_ZOOM[0], 1,
    POINTS_FADE_ZOOM[1], ["case", ["in", ["get", "site_id"], ["literal", ids]], 0, 1]] : 1;
  for (const id of ["sites", "sites-highlight"]) {
    map.setPaintProperty(id, "circle-opacity", opacity);
    map.setPaintProperty(id, "circle-stroke-opacity", opacity);
  }
}

function setHighlight(siteIds) {
  const filter = ["in", ["get", "site_id"], ["literal", siteIds]];
  for (const id of ["sites-highlight", "site-buildings-highlight", "site-parcels-highlight"]) {
    if (map.getLayer(id)) map.setFilter(id, filter);
  }
}

function setVisible(layerId, visible) {
  // The portfolio legend controls its points and shapes together; tools can also hide each shape layer.
  const ids = layerId === "sites" ? ["sites", "parcels", "buildings"] : [layerId];
  for (const id of ids) {
    const layer = added.get(id);
    if (!layer) continue;
    layer.visible = visible;
    for (const mapId of layer.mapLayerIds) map.setLayoutProperty(mapId, "visibility", visible ? "visible" : "none");
  }
  updatePointOpacity();
  const box = legendBoxes.get(layerId);
  if (box) box.checked = visible;
}

async function showLayer(layerId) {
  await ensureLayer(layerId);
  setVisible(layerId, true);
}

function addLegendEntry(layerId, text, { color, shape }) {
  if (legendBoxes.has(layerId)) return;
  const label = document.createElement("label");
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: true });
  box.addEventListener("change", () => (box.checked ? showLayer(layerId) : setVisible(layerId, false)));
  const swatch = document.createElement("span");
  swatch.className = `swatch${shape ? ` ${shape}` : ""}`;
  if (color === "transparent") swatch.style.border = `1px dashed ${COLORS.district}`;
  else if (color) swatch.style.background = color;
  label.append(box, swatch, document.createTextNode(text));
  legendBoxes.set(layerId, box);

  // Keep the legend in drawing order, top layer first.
  const legend = document.getElementById("legend");
  const order = RANK[catalog.get(layerId)?.kind] ?? 2;
  label.dataset.rank = order;
  const after = [...legend.children].find((el) => Number(el.dataset.rank) < order);
  legend.insertBefore(label, after ?? null);
}

function showSitePopup(feature) {
  const p = feature.properties;
  const place = p.address ? ["Address", `${p.address}, ${p.city}`] : ["Commune", p.city];
  const rows = [["Company", p.company_name], place, ["District", p.district_name],
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

function geojsonBounds(geojson) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const walk = (c) => {
    if (typeof c[0] === "number") { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); }
    else for (const part of c) walk(part);
  };
  for (const f of geojson.features) if (f.geometry) walk(f.geometry.coordinates);
  return [w, s, e, n];
}

// The bundle has one portfolio and one incident, so the app opens on them: communes, incident footprints and
// sites, zoomed to the sites and footprints. Tools can still show, hide, highlight and zoom from there.
export async function showOverview() {
  await ready;
  const incidents = [...catalog.values()].filter((l) => l.kind === "incident").map((l) => l.id);
  const layers = ["districts", ...incidents, "sites"].filter((id) => catalog.has(id));
  for (const id of layers) await showLayer(id);
  const boxes = ["sites", ...incidents].map((id) => extents.get(id)).filter(Boolean);
  if (!boxes.length) return;
  const bbox = [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))];
  // One zoom level out from a tight fit, so the area around the event is visible too.
  const camera = map.cameraForBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40 });
  if (camera) map.jumpTo({ ...camera, zoom: camera.zoom - 1 });
}

// Applies a tool result's map actions in order. Tools decide what changes after the opening overview.
export async function applyMapActions(actions = []) {
  await ready;
  for (const action of actions) {
    if (action.type === "show_layer") {
      await showLayer(action.layer_id);
    } else if (action.type === "hide_layer") {
      setVisible(action.layer_id, false);
    } else if (action.type === "highlight_sites") {
      await showLayer("sites");
      setHighlight(action.site_ids);
    } else if (action.type === "clear_highlight") {
      if (added.has("sites")) setHighlight([]);
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
