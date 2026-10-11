#!/usr/bin/env python3
"""Analyserar vad olika kartstorlekar får med runt mittpunkten i config/area.json.

Läser data/raw/osm.json (från fetch_osm.py), projicerar till SWEREF 99 TM
(EPSG:3006) och räknar ut åkermark, skog, vatten, byggnader, gårdar, vägar och
ortnamn inom kvadrater på 2, 4 och 8 km (FS25:s kartstorlekar). Skriver:

  data/area_stats.json      statistik per kartstorlek
  data/area_features.geojson förenklade objekt (WGS84) för områdesväljaren

Användning:
    python scripts/analyze_area.py [--center LAT,LON]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import linemerge, polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "area.json"
OSM = ROOT / "data" / "raw" / "osm.json"
STATS_OUT = ROOT / "data" / "area_stats.json"
FEATURES_OUT = ROOT / "data" / "area_features.geojson"

SIZES = [2048, 4096, 8192]
# Hur långt utanför 8 km-rutan objekt exporteras, så att rutan kan flyttas i väljaren.
EXPORT_HALF = 6500

to_sweref = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform
to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform

AREA_CLASSES = {
    "farmland": lambda t: t.get("landuse") == "farmland",
    "meadow": lambda t: t.get("landuse") in ("meadow", "grass") or t.get("natural") == "grassland",
    "forest": lambda t: t.get("landuse") == "forest" or t.get("natural") in ("wood", "scrub"),
    "water": lambda t: t.get("natural") == "water" or t.get("landuse") == "reservoir",
    "wetland": lambda t: t.get("natural") == "wetland",
    "farmyard": lambda t: t.get("landuse") == "farmyard",
    "residential": lambda t: t.get("landuse") in ("residential", "industrial", "commercial"),
}

ROAD_CLASSES = {
    "motorväg/riksväg": ("motorway", "motorway_link", "trunk", "trunk_link"),
    "länsväg": ("primary", "secondary", "secondary_link", "tertiary"),
    "småväg": ("unclassified", "residential", "road"),
    "grusväg/brukningsväg": ("track",),
    "gårdsväg/infart": ("service",),
}


def wgs_coords(xy):
    """SWEREF 99 TM -> WGS84, avrundat till 5 decimaler (~1 m)."""
    lon, lat = to_wgs(xy[:, 0], xy[:, 1])
    return np.round(np.column_stack([lon, lat]), 5)


def classify_area(tags):
    for name, test in AREA_CLASSES.items():
        if test(tags):
            return name
    return None


def classify_road(tags):
    hw = tags.get("highway")
    for name, values in ROAD_CLASSES.items():
        if hw in values:
            return name
    return None


def way_coords(geom):
    return [to_sweref(p["lon"], p["lat"]) for p in geom]


def relation_polygon(rel):
    outers, inners = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        line = LineString(way_coords(m["geometry"]))
        (inners if m.get("role") == "inner" else outers).append(line)
    if not outers:
        return None
    outer = unary_union(list(polygonize(linemerge(outers))))
    if inners:
        outer = outer.difference(unary_union(list(polygonize(linemerge(inners)))))
    return outer if not outer.is_empty else None


def load_features():
    data = json.loads(OSM.read_text(encoding="utf-8"))
    areas, roads, waterways, rail, buildings, places = [], [], [], [], [], []
    for el in data["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "node":
            if "place" in tags and tags.get("name"):
                places.append((Point(to_sweref(el["lon"], el["lat"])), tags["name"], tags["place"]))
            continue
        if el["type"] == "relation":
            cls = classify_area(tags)
            if cls:
                poly = relation_polygon(el)
                if poly is not None:
                    areas.append((cls, poly.buffer(0)))
            continue
        coords = way_coords(el.get("geometry", []))
        if len(coords) < 2:
            continue
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        if "building" in tags and closed:
            buildings.append(Polygon(coords))
        elif "highway" in tags:
            cls = classify_road(tags)
            if cls:
                roads.append((cls, LineString(coords)))
        elif "waterway" in tags:
            waterways.append((tags["waterway"], LineString(coords)))
        elif "railway" in tags:
            rail.append(LineString(coords))
        elif closed:
            cls = classify_area(tags)
            if cls:
                areas.append((cls, Polygon(coords).buffer(0)))
    return areas, roads, waterways, rail, buildings, places


def stats_for(square, areas, roads, waterways, buildings, places):
    area_ha = defaultdict(float)
    field_blocks = 0
    farmyards = 0
    for cls, geom in areas:
        if not geom.intersects(square):
            continue
        clipped = geom.intersection(square)
        area_ha[cls] += clipped.area / 10_000
        if cls == "farmland" and clipped.area > 5_000:  # skiften under 0,5 ha räknas inte
            field_blocks += 1
        if cls == "farmyard":
            farmyards += 1
    road_km = defaultdict(float)
    for cls, line in roads:
        if line.intersects(square):
            road_km[cls] += line.intersection(square).length / 1000
    water_km = sum(l.intersection(square).length for _, l in waterways if l.intersects(square)) / 1000
    total_ha = square.area / 10_000
    return {
        "total_ha": round(total_ha),
        "area_ha": {k: round(v, 1) for k, v in sorted(area_ha.items())},
        "area_pct": {k: round(100 * v / total_ha, 1) for k, v in sorted(area_ha.items())},
        "field_blocks": field_blocks,
        "farmyards": farmyards,
        "buildings": sum(1 for b in buildings if b.centroid.within(square)),
        "road_km": {k: round(v, 1) for k, v in road_km.items()},
        "waterway_km": round(water_km, 1),
        "places": sorted({n for p, n, kind in places if p.within(square) and kind != "locality"}),
    }


def export_features(center, areas, roads, waterways, rail, buildings, places):
    cx, cy = center.x, center.y
    extent = box(cx - EXPORT_HALF, cy - EXPORT_HALF, cx + EXPORT_HALF, cy + EXPORT_HALF)

    def to_feature(geom, props, tolerance):
        g = geom.intersection(extent)
        if g.is_empty:
            return None
        g = g.simplify(tolerance, preserve_topology=True)
        g = shapely.transform(g, wgs_coords)
        return {"type": "Feature", "properties": props, "geometry": mapping(g)}

    feats = []
    for cls, geom in areas:
        if geom.intersects(extent):
            feats.append(to_feature(geom, {"k": cls}, 3))
    for cls, line in roads:
        if line.intersects(extent):
            feats.append(to_feature(line, {"k": "road", "c": cls}, 2))
    for kind, line in waterways:
        if line.intersects(extent):
            feats.append(to_feature(line, {"k": "waterway", "c": kind}, 3))
    for line in rail:
        if line.intersects(extent):
            feats.append(to_feature(line, {"k": "rail"}, 3))
    for b in buildings:
        if b.centroid.within(extent):
            feats.append(to_feature(b, {"k": "building"}, 1))
    for p, name, kind in places:
        if p.within(extent):
            feats.append(to_feature(p, {"k": "place", "name": name, "c": kind}, 0))
    return {"type": "FeatureCollection", "features": [f for f in feats if f]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--center", help="LAT,LON (annars mittpunkten i config/area.json)")
    args = parser.parse_args()
    area = json.loads(CONFIG.read_text(encoding="utf-8"))
    lat, lon = (map(float, args.center.split(",")) if args.center
                else (area["center"]["lat"], area["center"]["lon"]))
    center = Point(to_sweref(lon, lat))

    areas, roads, waterways, rail, buildings, places = load_features()
    result = {"center": {"lat": lat, "lon": lon}, "sizes": {}}
    for size in SIZES:
        h = size / 2
        square = box(center.x - h, center.y - h, center.x + h, center.y + h)
        result["sizes"][str(size)] = stats_for(square, areas, roads, waterways, buildings, places)

    STATS_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    FEATURES_OUT.write_text(
        json.dumps(export_features(center, areas, roads, waterways, rail, buildings, places),
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    for size, s in result["sizes"].items():
        print(f"\n== {int(size) // 1024}x{int(size) // 1024} km ({size} m) ==")
        print(f"  Åker {s['area_ha'].get('farmland', 0)} ha ({s['area_pct'].get('farmland', 0)} %), "
              f"skog {s['area_ha'].get('forest', 0)} ha, vatten {s['area_ha'].get('water', 0)} ha")
        print(f"  Åkerskiften (OSM) {s['field_blocks']}, gårdsplaner {s['farmyards']}, byggnader {s['buildings']}")
        print(f"  Vägar km: {s['road_km']}")
        print(f"  Orter: {', '.join(s['places'])}")
    print(f"\nSkrev {STATS_OUT.relative_to(ROOT)} och {FEATURES_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
