// Map behaviour tests without a browser, network access or additional packages.
import assert from "node:assert/strict";
import test from "node:test";

const collection = (ids, type = "Point") => ({ type: "FeatureCollection", features: ids.map((id, i) => ({
  type: "Feature", properties: { site_id: id },
  geometry: type === "Point" ? { type, coordinates: [2 + i / 100, 46] }
    : { type, coordinates: [[[2, 46], [2.01, 46], [2.01, 46.01], [2, 46]]] },
})) });

function element() {
  return { style: {}, dataset: {}, children: [], append() {}, addEventListener() {},
    insertBefore(child) { this.children.push(child); } };
}

class FakeMap {
  sources = new Map();
  layers = new Map();
  fits = [];
  handlers = new Map();
  constructor(options) { FakeMap.instance = this; this.options = options; }
  on(name, callback) {
    if (!this.handlers.has(name)) this.handlers.set(name, []);
    this.handlers.get(name).push(callback);
    if (name === "load") queueMicrotask(() => { this.loaded = true; callback(); });
  }
  emit(name, event) { for (const handler of this.handlers.get(name) ?? []) handler(event); }
  addControl(control) {
    if (!control.isAttribution) return;
    assert.ok(this.loaded, "Attribution is added after the initial map load");
    this.attributionOptions = control.options;
    const classes = new Set(["maplibregl-ctrl-attrib", "maplibregl-compact", "maplibregl-compact-show"]);
    this.attribution = { open: true, classList: { remove: (name) => classes.delete(name), contains: (name) => classes.has(name) } };
  }
  getContainer() { return { querySelector: () => this.attribution }; }
  resize() {}
  getSource(id) { return this.sources.get(id); }
  getLayer(id) { return this.layers.get(id); }
  addSource(id, spec) {
    assert.ok(!this.sources.has(id), `Duplicate source: ${id}`);
    this.sources.set(id, { ...spec, setData(data) { this.data = data; } });
  }
  addLayer(spec, before) {
    assert.ok(!this.layers.has(spec.id), `Duplicate layer: ${spec.id}`);
    if (before) assert.ok(this.layers.has(before));
    this.layers.set(spec.id, { ...spec, layout: {} });
  }
  setLayoutProperty(id, property, value) { this.layers.get(id).layout[property] = value; }
  setPaintProperty(id, property, value) { this.layers.get(id).paint[property] = value; }
  setFilter(id, filter) { this.layers.get(id).filter = filter; }
  fitBounds(bounds, options) { this.fits.push({ bounds, options }); }
  cameraForBounds() { return { zoom: 10 }; }
  jumpTo() {}
}

let moduleId = 0;
async function setupMap(t, { shapes = {}, beforeFetch = async () => {} } = {}) {
  const globals = ["fetch", "document", "maplibregl", "ResizeObserver"];
  const original = new Map(globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  t.after(() => {
    for (const [key, descriptor] of original) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  const elements = new Map();
  globalThis.document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    createElement: element, createTextNode: (text) => text,
  };
  globalThis.ResizeObserver = class { observe() {} };
  globalThis.maplibregl = { Map: FakeMap, NavigationControl: class {}, ScaleControl: class {},
    AttributionControl: class { constructor(options) { this.isAttribution = true; this.options = options; } },
  };
  const data = { sites: collection(["S01", "S02"]), districts: collection([], "Polygon"), ...shapes };
  const counts = new Map();
  globalThis.fetch = async (url) => {
    if (url.startsWith("https://")) return { ok: false };
    if (url === "/api/layers") return { ok: true, json: async () => Object.keys(data).map((id) => ({
      id, kind: id, url: `/api/layers/${id}`,
    })) };
    const id = url.slice("/api/layers/".length);
    counts.set(id, (counts.get(id) ?? 0) + 1);
    await beforeFetch(id, counts.get(id));
    return { ok: true, json: async () => data[id] };
  };
  const api = await import(new URL(`../frontend/js/map.js?test=${++moduleId}`, import.meta.url));
  await api.initMap("map");
  return { ...api, map: FakeMap.instance, counts, elements };
}

// Evaluate the small set of style expressions used for point opacity.
function evaluate(expression, { siteId, zoom }) {
  if (!Array.isArray(expression)) return expression;
  const value = (child) => evaluate(child, { siteId, zoom });
  const [op, ...args] = expression;
  if (op === "literal") return args[0];
  if (op === "get") { assert.equal(args[0], "site_id"); return siteId; }
  if (op === "zoom") return zoom;
  if (op === "in") return value(args[1]).includes(value(args[0]));
  if (op === "case") return value(args[0]) ? value(args[1]) : value(args[2]);
  if (op === "interpolate") {
    const input = value(args[1]);
    const stops = [];
    for (let i = 2; i < args.length; i += 2) stops.push([args[i], value(args[i + 1])]);
    if (input <= stops[0][0]) return stops[0][1];
    for (let i = 1; i < stops.length; i++) {
      const [low, a] = stops[i - 1], [high, b] = stops[i];
      if (input <= high) return a + (b - a) * (input - low) / (high - low);
    }
    return stops.at(-1)[1];
  }
  throw new Error(`Unsupported expression: ${op}`);
}

test("attribution starts collapsed after map initialization", async (t) => {
  const { map } = await setupMap(t);
  assert.equal(map.options.attributionControl, false);
  assert.equal(map.attributionOptions.compact, true);
  assert.equal(map.attribution.open, false);
  assert.equal(map.attribution.classList.contains("maplibregl-compact-show"), false);
  assert.equal(map.attribution.classList.contains("maplibregl-compact"), true);
});

test("startup and a tool action share pending layer loads", async (t) => {
  const app = await setupMap(t, { shapes: {
    buildings: collection(["S01"], "Polygon"), parcels: collection(["S01"], "Polygon"),
  } });
  await Promise.all([
    app.showOverview(),
    app.applyMapActions([{ type: "show_layer", layer_id: "sites" }, { type: "fit_bounds", bbox: [2, 46, 2.01, 46.01] }]),
  ]);
  for (const id of ["sites", "parcels", "buildings"]) assert.equal(app.counts.get(id), 1);
  assert.equal(app.map.fits.length, 1, "Remaining tool actions still run");
});

test("failed layer requests can be retried", async (t) => {
  const app = await setupMap(t, { beforeFetch: async (id, count) => {
    if (id === "sites" && count === 1) throw new Error("temporary failure");
  } });
  const actions = [{ type: "show_layer", layer_id: "sites" }];
  await assert.rejects(app.applyMapActions(actions), /temporary failure/);
  await app.applyMapActions(actions);
  assert.equal(app.counts.get("sites"), 2);
  assert.ok(app.map.getLayer("sites"));
});

test("advertised shape IDs control visibility, with point fallback per site", async (t) => {
  const app = await setupMap(t, { shapes: {
    buildings: collection(["S01"], "Polygon"), parcels: collection(["S01"], "Polygon"),
  } });
  await app.showOverview();
  const opacity = (siteId, zoom = 15) => evaluate(app.map.getLayer("sites").paint["circle-opacity"], { siteId, zoom });
  assert.equal(opacity("S01"), 0);
  assert.equal(opacity("S01", 14.5), 0.5);
  assert.equal(opacity("S02"), 1, "Sites missing replacement shapes stay visible");
  await app.applyMapActions([{ type: "hide_layer", layer_id: "buildings" }]);
  assert.equal(app.map.getLayer("site-buildings-fill").layout.visibility, "none");
  assert.equal(app.map.getLayer("site-parcels-fill").layout.visibility, "visible");
  await app.applyMapActions([{ type: "hide_layer", layer_id: "parcels" }]);
  assert.equal(opacity("S01"), 1, "Hiding all shapes restores points");
  await app.applyMapActions([{ type: "show_layer", layer_id: "buildings" }]);
  assert.equal(app.map.getLayer("site-buildings-fill").layout.visibility, "visible");
  assert.equal(opacity("S01"), 0);
  await app.applyMapActions([{ type: "hide_layer", layer_id: "sites" }]);
  for (const id of ["sites", "sites-highlight", "site-buildings-fill", "site-parcels-fill"]) {
    assert.equal(app.map.getLayer(id).layout.visibility, "none");
  }
});

test("fixture points and highlights remain visible at close zoom", async (t) => {
  const app = await setupMap(t);
  await app.showOverview();
  await app.applyMapActions([{ type: "highlight_sites", site_ids: ["S01"] },
    { type: "fit_bounds", bbox: [2, 46, 2, 46] }]);
  for (const id of ["sites", "sites-highlight"]) {
    assert.equal(evaluate(app.map.getLayer(id).paint["circle-opacity"], { siteId: "S01", zoom: 18 }), 1);
  }
  assert.deepEqual(app.map.getLayer("sites-highlight").filter.at(-1), ["literal", ["S01"]]);
});

test("basemap changes preserve source layers, highlights and camera", async (t) => {
  const api = await setupMap(t, { shapes: { buildings: collection(["S01"], "Polygon"), parcels: collection(["S01"], "Polygon") } });
  await api.showOverview();
  await api.applyMapActions([{ type: "highlight_sites", site_ids: ["S01"] }]);
  const sites = api.map.getLayer("sites");
  const highlight = structuredClone(api.map.getLayer("sites-highlight").filter);
  const fits = api.map.fits.length;
  api.setBasemap("satellite");
  assert.equal(api.map.getLayer("satellite-imagery-layer").layout.visibility, "visible");
  assert.match(api.map.getSource("satellite-imagery").attribution, /Esri/);
  api.setBasemap("data");
  assert.equal(api.map.getLayer("satellite-imagery-layer").layout.visibility, "none");
  api.setBasemap("street");
  api.setBasemap("satellite"); // Reuse the raster source rather than adding it twice.
  assert.equal(api.map.getLayer("sites"), sites);
  assert.deepEqual(api.map.getLayer("sites-highlight").filter, highlight);
  assert.equal(api.map.fits.length, fits);
  assert.equal(api.map.getLayer("site-buildings-fill").layout.visibility, "visible");
});


test("satellite failures leave data visible and inactive errors cannot hide a new basemap", async (t) => {
  const api = await setupMap(t);
  await api.showOverview();
  api.setBasemap("satellite");
  for (let i=0; i<4; i++) api.map.emit("error", {sourceId:"satellite-imagery"});
  assert.equal(api.map.getLayer("satellite-imagery-layer").layout.visibility, "none");
  assert.equal(api.elements.get("map-notice").hidden, false);
  assert.match(api.elements.get("map-notice").textContent, /Choose Street or Data only/);
  assert.equal(api.map.getLayer("sites").layout.visibility, "visible");
  api.setBasemap("data");
  for (let i=0; i<5; i++) api.map.emit("error", {sourceId:"satellite-imagery"});
  assert.equal(api.elements.get("map-notice").hidden, true);
});
