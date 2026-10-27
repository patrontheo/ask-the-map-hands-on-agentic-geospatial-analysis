# prep — organiser data pipeline

Builds the app's data bundle in `data/`: the incident footprint, catalog and the synthetic portfolio. The
curated edge cases are ordinary portfolio sites; `out/edge_cases.json` is the organiser answer key saying
which is which. That report records the address-point quotas used to curate the
teaching portfolio. App screening uses building intersections; its current reference
answers are in `tests/expected.json`.

For now the bundle has one incident, the Le Porge wildfire (EMSR899). The Garonne flood (EMSR866) is parked
in `incidents.py` (`PARKED`); move it back into `INCIDENTS` to reactivate it.

## Inputs

| Path | What | Licence |
|---|---|---|
| `raw/<incident>/*.zip` | Copernicus EMS Rapid Mapping packages, untouched | Copernicus EMS terms; attribution in `incidents.py` |
| `sources/buildings-<incident>.gpkg` | IGN BD TOPO buildings (industrial, commercial, agricultural; plus undifferentiated around the fire) within 6 km of the footprint | Licence Ouverte 2.0 (Etalab), © IGN |
| `sources/communes.gpkg` | IGN ADMIN EXPRESS communes | Licence Ouverte 2.0 (Etalab), © IGN |

## Steps

Run from the repository root. Steps 2 and 4 need internet access to `data.geopf.fr` (IGN).
The other steps are offline and deterministic (fixed seed).

```bash
uv run python prep/build_events.py
uv run python prep/fetch_ign.py
uv run python prep/select_candidates.py
uv run --no-project --python 3.12 --with /Users/b515hn/Documents/Code/footprinter-core-engine --with tqdm python prep/footprint_candidates.py
uv run python prep/build_portfolio.py
```

1. `build_events.py` generalises each published EMS layer to at most 3,000 vertices (`generalise.py`:
   closes small gaps, drops small parts, simplifies edges, keeping the shape whose area differs least) and
   writes it to `data/events/<id>.geojson`, plus `data/catalog.json`. **That generalised shape is the
   incident footprint for everything**: the tools, the map, what the model reads, and every later prep step.
   Several minutes per incident.
2. `fetch_ign.py` downloads buildings in 5 km tiles, cached in `sources/tiles/`, so a rerun only fetches
   what is missing.
3. `select_candidates.py` writes `work/candidates.csv`: buildings in five bands (inside; within 30 m of the
   edge on either side; within 2 km; 2–6 km). The site point is a point inside the building.
4. `footprint_candidates.py` runs the footprinter in its own environment (it pins numpy < 2), in **site
   mode**: for each candidate point it gets every building on the cadastral parcel, widened to neighbouring
   parcels that the buildings spill onto, and those parcels. IGN responses are cached in
   `work/.footprinter-cache`. Certificates are checked against the macOS trust store, so the AXA proxy's
   root certificate is accepted; `FOOTPRINTER_VERIFY_SSL=False` turns checking off, as a last resort only.
5. `build_portfolio.py` re-bands the candidates against the footprint in `data/events/`, then writes
   `data/portfolio/{sites,companies}.csv`, `data/portfolio/{buildings,parcels}.geojson` (one merged polygon
   per site), `data/admin/districts.geojson`, and the answer key `prep/out/edge_cases.json`. It recomputes
   inclusion from scratch and fails if any curated edge case is missing.

After changing the footprint (step 1), rerun step 5; steps 2–4 only when candidates must change.

## Portfolio rules (build_portfolio.py)

- 100 sites, 15 fictional companies (3–12 sites each); 40 address points inside the
  footprint. Building-intersection screening affects 43 sites in the frozen bundle.
- Sites have coordinates and a commune, **no street address**. `address` and `postcode` are empty and
  `city` is the commune name, so the app's column set is unchanged.
- No two sites share a parcel: when site mode expands two candidates to the same estate, only the
  higher-scoring one is kept (checked again at the end).
- `property_type` comes from the main building (the one under the site point): BD TOPO use, footprint and floor count.
- TIV: building = floor area of **all** the site's buildings × cost per m² for the type (EUR 400–2,000), ±25 %
  noise, floor area capped at 40,000 m². Storeys are IGN's recorded count; otherwise derived from height for
  offices, shops and hotels, and 1 for industrial, warehouse and agricultural buildings. Contents = 30–100 %
  of building by type. Rounded to EUR 1,000. No BI.
- Districts are communes: the ADMIN EXPRESS polygon covering the site point, cross-checked against the
  parcel's commune code (mismatches are listed in `edge_cases.json`).

## Curated edge cases

| Case | How |
|---|---|
| Site on a footprint vertex | One site within 30 m of the edge is moved onto the nearest footprint vertex (moved distance recorded). It is the only site whose point was moved |
| Zero TIV inside | One inside site of C07 |
| Exact tie | C05 and C06 have equal exposed TIV; the tie rule puts C05 first |
| Absolute vs share | C01 is top by exposed TIV; C15 (all sites inside) is top by share |
| All inside / none inside | C15 / C14 |
| Near the edge | Sites just inside and just outside the edge, preferring ones where the building polygon disagrees with the point |

Company names are invented and have not been checked against real company registers.
