#!/usr/bin/env python3
"""Kontrollkarta i webbläsaren: var kartan har skog, trädkronor och utplacerade träd.

Skapar en mapp med en HTML-sida som visar, med lager som kan tändas och släckas:
- ortofotot som bakgrund (eller OpenStreetMap)
- laserns trädkronor (laser_trees.py), färgade efter höjd
- träden som build_map.py har satt ut, i skogen och utanför skogen
- Marktäckes skogar och Jordbruksverkets fält
Klick på kartan visar koordinaten i spelet, samma som på kartan i spelet.

Kör efter build_map.py. Mappen innehåller ortofoto och ska bara visas på dina
egna datorer: kopiera den till Windows och öppna index.html. Ladda inte upp
den någonstans.

    build/<namn>/kontrollkarta/index.html

Användning:
    python scripts/kontrollkarta.py [--map tysslinge]
"""
import argparse
import json
import sys

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds

from area import add_map_argument, open_map

to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform
ORTHO_RES = 1.0          # m per pixel i kontrollkartans ortofoto
MARGIN = 100.0           # m runt kartan

PAGE = """<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kontrollkarta __TITLE__</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  html, body, #map { height: 100%; margin: 0; }
  body { font-family: system-ui, sans-serif; background: #1d2321; }
  .box { background: rgba(255,255,255,.93); padding: 8px 10px; border-radius: 6px; font-size: 13px; line-height: 1.5; }
  .box b { display: block; margin-bottom: 2px; }
  .sw { display: inline-block; width: 12px; height: 12px; border-radius: 6px; margin-right: 6px; vertical-align: -1px; }
</style></head>
<body><div id="map"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="data.js"></script>
<script>
const map = L.map('map', {preferCanvas: true});
const b = DATA.bounds;   // [[syd, väst], [nord, öst]] för bilderna
map.fitBounds(DATA.square);
const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '© OpenStreetMap-bidragsgivare'});
const base = {'OpenStreetMap': osm};
if (DATA.ortho) base['Ortofoto (Lantmäteriet)'] = L.imageOverlay('ortofoto.jpg', b, {attribution: 'Ortofoto © Lantmäteriet'});
(base['Ortofoto (Lantmäteriet)'] || osm).addTo(map);
const over = {};
if (DATA.canopy) over['Laserns trädkronor'] = L.imageOverlay('krontak.png', b, {opacity: 0.75}).addTo(map);
function poly(list, style) { return L.layerGroup(list.map(r => L.polygon(r, style))); }
over['Marktäckes skog (kontur)'] = poly(DATA.forest, {color: '#7CFC00', weight: 1.5, fill: false}).addTo(map);
over['Fält (kontur)'] = poly(DATA.fields, {color: '#ffb347', weight: 1.2, fill: false});
function dots(list, color) {
  return L.layerGroup(list.map(p => L.circleMarker(p, {radius: 2.2, stroke: false, fillColor: color, fillOpacity: 0.95})));
}
over['Träd i skogen (spelet)'] = dots(DATA.trees_forest, '#0b5d1e');
over['Träd utanför skogen (spelet)'] = dots(DATA.trees_loose, '#ff2d95').addTo(map);
L.rectangle(DATA.square, {color: '#fff', weight: 2, fill: false, dashArray: '6 4'}).addTo(map);
L.control.layers(base, over, {collapsed: false}).addTo(map);
const info = L.control({position: 'bottomleft'});
info.onAdd = () => {
  const d = L.DomUtil.create('div', 'box');
  d.innerHTML = '<b>' + DATA.title + '</b>' +
    '<span class="sw" style="background:#0b5d1e"></span>träd i skogen: ' + DATA.trees_forest.length + '<br>' +
    '<span class="sw" style="background:#ff2d95"></span>träd utanför skogen: ' + DATA.trees_loose.length + '<br>' +
    'Trädkronor: ljusgrön under 8 m, mörkare högre.<br>Klicka för koordinat i spelet.';
  return d;
};
info.addTo(map);
map.on('click', e => {
  const [x, z] = DATA.toGame(e.latlng.lat, e.latlng.lng);
  L.popup().setLatLng(e.latlng).setContent('Spelet: ' + Math.round(x) + ', ' + Math.round(z)).openOn(map);
});
</script></body></html>
"""


def latlon(e, n):
    lon, lat = to_wgs(e, n)
    return [round(lat, 6), round(lon, 6)]


def rings(geom):
    polys = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    return [[latlon(x, y) for x, y in p.simplify(2).exterior.coords] for p in polys if not p.is_empty]


def canopy_png(chm_path, bounds, out):
    """Krontaket som genomskinlig PNG: grönt efter höjd, inget där det saknas kronor."""
    with rasterio.open(chm_path) as src:
        chm = src.read(1, window=from_bounds(*bounds, src.transform), boundless=True, fill_value=0)
    rgba = np.zeros(chm.shape + (4,), np.uint8)
    for lo, hi, color in ((0.01, 8, (170, 255, 120)), (8, 20, (40, 200, 60)), (20, 99, (0, 110, 30))):
        m = (chm >= lo) & (chm < hi)
        rgba[m] = color + (230,)
    Image.fromarray(rgba, "RGBA").save(out)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    args = parser.parse_args()
    project = open_map(args.map)

    import build_map as bm     # efter argumenten: build_map läser in fs25-empty-map
    world = bm.World(project)
    placed = project.build / "trad_placerade.json"
    if not placed.exists():
        sys.exit(f"Hittar inte {project.rel(placed)}. Kör build_map.py först.")
    trees = json.loads(placed.read_text(encoding="utf-8"))
    out = project.build / "kontrollkarta"
    out.mkdir(parents=True, exist_ok=True)
    sq = world.square(-MARGIN)
    x0, y0, x1, y1 = sq.bounds

    ortho = project.lm / "ortofoto" / "ortofoto.tif"
    if ortho.exists():
        with rasterio.open(ortho) as src:
            size = (int((y1 - y0) / ORTHO_RES), int((x1 - x0) / ORTHO_RES))
            rgb = src.read([1, 2, 3], window=from_bounds(x0, y0, x1, y1, src.transform),
                           out_shape=(3,) + size, boundless=True, fill_value=0)
        Image.fromarray(rgb.transpose(1, 2, 0)).save(out / "ortofoto.jpg", quality=82)
    chm = project.lm / "laser" / "krontak.tif"
    if chm.exists():
        canopy_png(chm, (x0, y0, x1, y1), out / "krontak.png")

    osm, _ = bm.load_land(project, world)
    areas, roads, waterways = osm[0], osm[1], osm[2]
    inner = world.square()
    forest = [r for c, g in areas if c == "forest" and g.intersects(inner) for r in rings(g.intersection(inner))]
    fields = [r for g, _, _ in bm.load_fields(project, world, bm.obstacles(roads, waterways, world, areas))
              for r in rings(g)]
    ix0, iy0, ix1, iy1 = inner.bounds
    e0, n0 = world.e0, world.n0
    data = {
        "title": project.config.get("title", project.name),
        "bounds": [latlon(x0, y0), latlon(x1, y1)],
        "square": [latlon(ix0, iy0), latlon(ix1, iy1)],
        "ortho": ortho.exists(), "canopy": chm.exists(),
        "forest": forest, "fields": fields,
        "trees_forest": [latlon(e, n) for e, n in trees["skog"]],
        "trees_loose": [latlon(e, n) for e, n in trees["utanfor"]],
    }
    # Spelets kartkoordinat: x österut, z söderut, 0 i kartans nordvästra hörn (som på kartan i spelet).
    # Omräkningen lat/lon -> SWEREF görs grovt linjärt över kartans lilla yta.
    (sw, ne) = data["bounds"]
    js = ("const DATA = " + json.dumps(data, separators=(",", ":")) + ";\n"
          f"DATA.toGame = (lat, lon) => {{ const e = {x0} + (lon - {sw[1]}) / ({ne[1]} - {sw[1]}) * {x1 - x0};"
          f" const n = {y0} + (lat - {sw[0]}) / ({ne[0]} - {sw[0]}) * {y1 - y0};"
          f" return [e - {e0} + {world.half}, {n0} - n + {world.half}]; }};\n")
    (out / "data.js").write_text(js, encoding="utf-8")
    (out / "index.html").write_text(PAGE.replace("__TITLE__", data["title"]), encoding="utf-8")
    print(f"Skrev {project.rel(out)}/index.html "
          f"({len(data['trees_forest'])} skogsträd, {len(data['trees_loose'])} träd utanför skogen)")
    print("Mappen innehåller ortofoto: visa den bara på dina egna datorer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
