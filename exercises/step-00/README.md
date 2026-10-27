# Step 0 — try the baseline

Follow the setup in the repository README and open the app. The map opens with
the portfolio, incident footprints and communes. Reloading starts a fresh chat and map.

Ask these questions and record the answers:

1. Which sites lie inside the wildfire footprint, and how many distinct sites is that?
2. What TIV do these sites represent, and which companies have the highest exposed TIV?
3. For each company, what share of its full portfolio TIV is inside the footprint?

At this stage the assistant can load data and control the map. It has no computation
tools: screening answers come from its own reasoning over the returned data and may
be inaccurate, or the assistant may decline a calculation. Record these outcomes
too, and inspect any highlighted sites and tables. Try the other questions in the
app's prompt library, including the commune burnt-area questions.

`describe_data` lists datasets and map layers. `get_dataset` reads attributes and
returns a reusable `result_id`; `include_geometry=true` also returns rounded GeoJSON
for baseline reasoning. Data access keeps the map unchanged. Use `show_layer`,
`hide_layer`, `highlight_sites` and `zoom_map` to control it explicitly.

Continue with [Step 1](../step-01/README.md) to build deterministic atomic tools and
compare their composed results with this baseline, including company exposure shares.
