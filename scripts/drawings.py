"""Ritningar från byggeditorn (läget "Måla mark") som build_map.py lägger ovanpå datan.

maps/<namn>/ritningar.json: [{"kind": "yta" | "väg", "type": ..., "points": [[x, y], ...], "width": m}]
med x, y i meter från kartans mitt (x österut, y norrut).

Ytor tar över det som fanns där innan, i den ordning de ritades:
- gräs, gårdsplan, asfaltyta: marktextur, inga fält, ingen skog och inga träd
- åker: ett nytt fält (eget markområde), fält och skog som fanns där tas bort
- skog: skogsmark och träd
- sudda vägar: vägar inom ytan tas bort (marken under blir gräs)
- inga träd: de automatiska träden inom ytan tas bort, marken ändras inte
Vägar: grusväg eller asfaltväg med vald bredd.
Träd ({"kind": "träd", "type": "oak_stage04", "art": "oak", "points": [[x, y]]}): ett träd av vald art
och storlek på platsen, oavsett vad som finns där.
"""
import json

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

AREA_LAYER = {"gräs": "grass01", "åker": "mudDark01", "gårdsplan": "gravelSmall01",
              "asfaltyta": "asphalt01", "skog": "forestLeaves01", "sudda vägar": "grass01"}
ROAD_LAYER = {"grusväg": "gravel01", "asfaltväg": "asphalt01"}
CLEARS_ROADS = {"gräs", "åker", "skog", "sudda vägar"}     # ytor som tar bort vägar under sig
NO_TREES = "inga träd"
GROUND_TYPES = set(AREA_LAYER)                               # ytor som ändrar marken
MIN_FIELD_HA = 0.1


def load(project, world):
    """Ritningarna med geometrier i SWEREF 99 TM."""
    path = project.dir / "ritningar.json"
    if not path.exists():
        return []
    out = []
    for d in json.loads(path.read_text(encoding="utf-8")):
        pts = [(world.e0 + x, world.n0 + y) for x, y in d.get("points", [])]
        if d.get("kind") == "yta" and len(pts) >= 3 and (d.get("type") in AREA_LAYER or d.get("type") == NO_TREES):
            geom = Polygon(pts).buffer(0)
        elif d.get("kind") == "väg" and len(pts) >= 2 and d.get("type") in ROAD_LAYER:
            geom = LineString(pts)
        elif d.get("kind") == "träd" and pts and d.get("type") and d.get("art"):
            geom = Point(pts[0])
        else:
            continue
        if not geom.is_empty:
            out.append({**d, "geom": geom})
    return out


def areas_of(drawings, types=GROUND_TYPES):
    return [d["geom"] for d in drawings if d["kind"] == "yta" and d["type"] in types]


def apply_land(osm, drawings, road_style):
    """OSM-tupeln med ritningarna: vägar tas bort och läggs till, skog och gårdsplaner ändras."""
    if not drawings:
        return osm
    areas, roads, waterways, rail, buildings, places = osm
    clear = unary_union(areas_of(drawings, CLEARS_ROADS))
    if not clear.is_empty:
        new_roads = []
        for cls, line in roads:
            rest = line.difference(clear) if line.intersects(clear) else line
            parts = [rest] if rest.geom_type == "LineString" else [g for g in getattr(rest, "geoms", [])
                                                                    if g.geom_type == "LineString"]
            new_roads += [(cls, p) for p in parts if p.length > 1]
        roads = new_roads
    for d in drawings:
        if d["kind"] == "väg":
            width = float(d.get("width") or 4)
            cls = f"ritad {d['type']} {width:g} m"
            road_style[cls] = (ROAD_LAYER[d["type"]], width)
            roads.append((cls, d["geom"]))
    covered = unary_union(areas_of(drawings))
    if not covered.is_empty:   # ritade ytor tar över skog och gårdsplaner under sig
        kept = []
        for cls, g in areas:
            if cls in ("forest", "barrskog", "farmyard") and g.intersects(covered):
                g = g.difference(covered)
                if g.is_empty:
                    continue
            kept.append((cls, g))
        areas = kept
    areas = areas + [("forest", g) for g in areas_of(drawings, {"skog"})] \
                  + [("farmyard", g) for g in areas_of(drawings, {"gårdsplan", "asfaltyta"})]
    return areas, roads, waterways, rail, buildings, places


def apply_fields(fields, drawings, cut, inner, shrink):
    """Fälten utan ritade ytor, plus ritade åkrar som nya fält (eget block, okänd gröda)."""
    covered = unary_union(areas_of(drawings))
    if covered.is_empty:
        return fields
    out = []
    for geom, block, code in fields:
        if geom.intersects(covered):
            geom = geom.difference(covered.buffer(shrink))
            parts = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", [])
                                                                 if g.geom_type == "Polygon"]
            out += [(p, block, code) for p in parts if p.area / 10_000 >= MIN_FIELD_HA]
        else:
            out.append((geom, block, code))
    for i, d in enumerate(d for d in drawings if d["kind"] == "yta" and d["type"] == "åker"):
        geom = d["geom"].intersection(inner).difference(cut).buffer(-shrink, join_style="mitre")
        parts = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", [])
                                                             if g.geom_type == "Polygon"]
        out += [(p, f"ritat-{i + 1}", None) for p in parts if p.area / 10_000 >= MIN_FIELD_HA]
    return out


def overrides(drawings):
    """[(marklager, yta)] att måla över fält och skog, i ritordning."""
    return [(AREA_LAYER[d["type"]], d["geom"]) for d in drawings if d["kind"] == "yta" and d["type"] in AREA_LAYER]


def no_tree_zone(drawings):
    return unary_union(areas_of(drawings, (GROUND_TYPES - {"skog"}) | {NO_TREES}))


def trees(drawings, tree_file):
    """Utsatta träd som (e, n, steg, fil) i samma form som fs25_objects.tree_points."""
    return [(d["geom"].x, d["geom"].y, d["type"], tree_file(d["art"], d["type"]))
            for d in drawings if d["kind"] == "träd"]
