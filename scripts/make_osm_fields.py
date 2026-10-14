#!/usr/bin/env python3
"""Bygger en OSM-fil för kartgeneratorn (MapToPlay) där OpenStreetMaps
åkrar är utbytta mot Jordbruksverkets verkliga skiften.

1. Hämtar fullständig OSM-data för hela området runt kartan (dubbla
   kartstorleken) om den saknas: data/<namn>/raw/osm_full.osm
2. Tar bort alla OSM-ytor med landuse=farmland, och ängar (landuse=meadow)
   som till mer än hälften täcks av skiften.
3. Lägger till skiftena från data/<namn>/raw/jbv_skiften.geojson som nya ytor:
   åkrar som landuse=farmland, betesmark och slåtteräng som landuse=meadow.
   Varje skifte krymps 1,5 m runt om, så att intilliggande skiften blir
   separata fält med en smal ren emellan.
4. Skriver build/<namn>/<namn>_faltskiften.osm

Kör fetch_fields.py först. Användning:
    python scripts/make_osm_fields.py [--map tysslinge] [--shrink 1.5] [--min-area 0.5]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from pyproj import Transformer
from shapely.geometry import Polygon, shape
from shapely.strtree import STRtree

from area import add_map_argument, open_map

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform
to_sweref = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform

# Grödkoder som blir äng (landuse=meadow) i stället för åker. 52 och 53 är
# betesmark respektive slåtteräng enligt Jordbruksverkets kodlista (antaget,
# se docs/datakallor.md). Allt annat blir åker.
MEADOW_CODES = {52, 53}
# Grödor att skriva som crop=* för information. Koderna 1, 4, 20 och 50 är
# inte bekräftade mot Jordbruksverkets lista men stämmer med fördelningen.
CROP_TAGS = {1: "barley", 2: "barley", 3: "oats", 4: "wheat", 5: "wheat",
             20: "rape", 21: "rape", 49: "grass", 50: "grass"}


def download_full_osm(project, out):
    # Samma område som dtm_total.tif (halva kartstorleken runt om) plus 100 m.
    min_e, min_n, max_e, max_n = project.bbox(project.size / 2 + 100)
    lon0, lat0 = to_wgs(min_e, min_n)
    lon1, lat1 = to_wgs(max_e, max_n)
    bbox = f"{lat0:.6f},{lon0:.6f},{lat1:.6f},{lon1:.6f}"
    query = f"[timeout:300];(nwr({bbox}););(._;>;);out meta;"
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(3):
        for url in MIRRORS:
            print(f"Hämtar fullständig OSM-data från {url} ...")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "fs-sweden-map/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=360) as resp:
                    body = resp.read()
                if not body.lstrip().startswith(b"<?xml") or b"<osm" not in body[:500]:
                    raise ValueError("svaret är inte OSM-XML")
            except Exception as exc:
                print(f"  misslyckades: {exc}")
                time.sleep(4 * (attempt + 1))
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(body)
            print(f"  sparade {len(body) / 1e6:.1f} MB")
            return True
    return False


def tags_of(el):
    return {t.get("k"): t.get("v") for t in el.findall("tag")}


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--shrink", type=float, default=1.5, help="meter som varje skifte krymps runt om")
    parser.add_argument("--min-area", type=float, default=0.5, help="minsta skifte i hektar som tas med")
    args = parser.parse_args()

    project = open_map(args.map)
    SKIFTEN = project.raw / "jbv_skiften.geojson"
    OSM_FULL = project.raw / "osm_full.osm"
    OUT = project.build / f"{project.name}_faltskiften.osm"
    if not SKIFTEN.exists():
        print(f"Hittar inte {project.rel(SKIFTEN)}. Kör scripts/fetch_fields.py först.", file=sys.stderr)
        return 1
    if not OSM_FULL.exists() and not download_full_osm(project, OSM_FULL):
        print("Kunde inte hämta OSM-data.", file=sys.stderr)
        return 1

    # Skiften, krympta och förenklade, i SWEREF 99 TM.
    fields = []
    for f in json.loads(SKIFTEN.read_text(encoding="utf-8"))["features"]:
        geom = shape(f["geometry"]).buffer(0)
        if geom.area / 10_000 < args.min_area:
            continue
        geom = geom.buffer(-args.shrink, join_style="mitre").simplify(0.5, preserve_topology=True)
        polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
        for poly in polys:
            if poly.area / 10_000 >= args.min_area / 2:
                fields.append((poly, f["properties"]))
    field_tree = STRtree([p for p, _ in fields])

    tree = ET.parse(OSM_FULL)
    root = tree.getroot()
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.iter("node")}

    def way_polygon(way):
        refs = [nd.get("ref") for nd in way.findall("nd")]
        if len(refs) < 4 or refs[0] != refs[-1] or any(r not in nodes for r in refs):
            return None
        poly = Polygon([to_sweref(*nodes[r]) for r in refs]).buffer(0)
        return poly if poly.area > 0 else None

    removed_farmland = removed_meadow = 0
    for el in list(root):
        if el.tag not in ("way", "relation"):
            continue
        landuse = tags_of(el).get("landuse")
        if landuse == "farmland":
            root.remove(el)
            removed_farmland += 1
        elif landuse == "meadow" and el.tag == "way":
            poly = way_polygon(el)
            if poly is None:
                continue
            covered = sum(poly.intersection(fields[i][0]).area for i in field_tree.query(poly))
            if covered > 0.5 * poly.area:
                root.remove(el)
                removed_meadow += 1

    # Nya objekt får höga id:n som inte krockar med OSM:s.
    next_id = [9_000_000_000_000]

    def new_id():
        next_id[0] += 1
        return str(next_id[0])

    meta = {"version": "1", "visible": "true", "timestamp": "2025-01-01T00:00:00Z"}
    n_farmland = n_meadow = 0
    for poly, props in fields:
        code = props.get("grdkod_mar")
        ring = list(poly.exterior.coords)
        node_ids = []
        for x, y in ring[:-1]:
            lon, lat = to_wgs(x, y)
            nid = new_id()
            ET.SubElement(root, "node", {"id": nid, "lat": f"{lat:.7f}", "lon": f"{lon:.7f}", **meta})
            node_ids.append(nid)
        way = ET.SubElement(root, "way", {"id": new_id(), **meta})
        for nid in node_ids + node_ids[:1]:
            ET.SubElement(way, "nd", {"ref": nid})
        is_meadow = code in MEADOW_CODES
        tags = {
            "landuse": "meadow" if is_meadow else "farmland",
            "name": f"Skifte {props.get('blockid')}-{props.get('skiftesbeteckning')}",
            "source": "Jordbruksverket jordbruksskiften " + str(props.get("arslager")),
            "sjv:grodkod": str(code),
        }
        if is_meadow:
            tags["meadow"] = "agricultural"
        elif code in CROP_TAGS:
            tags["crop"] = CROP_TAGS[code]
        for k, v in tags.items():
            ET.SubElement(way, "tag", {"k": k, "v": v})
        n_meadow += is_meadow
        n_farmland += not is_meadow

    # OSM-filer ska ha noder före vägar före relationer.
    order = {"bounds": 0, "node": 1, "way": 2, "relation": 3}
    root[:] = sorted(root, key=lambda el: order.get(el.tag, 4))
    root.set("generator", "FS_sweden_map make_osm_fields.py")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tree.write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"Tog bort {removed_farmland} OSM-åkrar och {removed_meadow} OSM-ängar som täcks av skiften")
    print(f"La till {n_farmland} åkrar och {n_meadow} ängar från Jordbruksverket")
    print(f"Skrev {project.rel(OUT)} ({OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
