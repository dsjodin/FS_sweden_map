"""Fastighetsgränser som markområden (farmlands) i spelet, för build_map.py.

data/<namn>/fastigheter.geojson: fastighetsområden som polygoner (WGS 84 eller SWEREF 99 TM) med
beteckningen i TITEL och typen i BESKRIVNING ("Fastighetsområde", "Samfällighetsområde", ...).

- Varje fastighet, med alla sina delar (samma beteckning), blir ett köpbart markområde.
- Samfälligheter och områden utan beteckning (vägar, diken, gemensam mark) får inget eget
  markområde. De fylls av grannarna, liksom fastigheter under MIN_HA.
- Fält som ligger på flera fastigheter delas längs gränsen när den andra fastighetens del är
  stor nog (SPLIT_HA och SPLIT_SHARE av fältet). Annars hör hela fältet till fastigheten med
  störst del.

Beteckningarna används bara här, för att hålla ihop en fastighets delar, och hamnar inte i
modden. Filen ligger under data/ och checkas inte in.
"""
import json

import shapely
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from area import ROOT, to_sweref

MIN_HA = 0.5           # mindre fastigheter (tomter) går till grannen
SPLIT_HA = 1.0         # ett fält delas bara där den andra fastigheten har minst så här mycket ...
SPLIT_SHARE = 0.25     # ... och minst så stor del av fältet


def path(project):
    return ROOT / "data" / project.name / "fastigheter.geojson"


def polygons(geom):
    """Polygonerna i en geometri (klippning kan ge samlingar med linjer och punkter)."""
    if geom.geom_type == "Polygon":
        return [geom]
    return [p for g in getattr(geom, "geoms", []) for p in polygons(g)]


def load(project, world):
    """{beteckning: yta i SWEREF} inom kartan, största först. Tom om filen saknas."""
    p = path(project)
    if not p.exists():
        return {}
    groups = {}
    for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
        props = f.get("properties") or {}
        title = (props.get("TITEL") or "").strip()
        if not title or not (props.get("BESKRIVNING") or "").startswith("Fastighetsområde"):
            continue
        geom = shape(f["geometry"])
        if abs(geom.bounds[0]) <= 180:                 # lon/lat: till SWEREF 99 TM
            geom = transform(to_sweref, geom)
        groups.setdefault(title, []).append(shapely.make_valid(geom))
    square = world.square()
    out = {}
    for title, parts in groups.items():
        geom = unary_union(polygons(unary_union(parts).intersection(square)))   # bara ytor, inga linjer
        if geom.area / 10_000 >= MIN_HA:
            out[title] = geom
    return dict(sorted(out.items(), key=lambda kv: -kv[1].area))


def assign_fields(fields, props, min_ha):
    """Fälten [(yta, block, gröda)] med fastighetens beteckning i stället för jordbruksblocket.
    Fält utanför alla fastigheter behåller blocket."""
    keys = list(props)
    tree = shapely.STRtree([props[k] for k in keys])
    out = []
    for geom, block, code in fields:
        shares = sorted(((geom.intersection(props[keys[i]]).area, keys[i]) for i in tree.query(geom)), reverse=True)
        if not shares or shares[0][0] == 0:
            out.append((geom, block, code))
            continue
        rest = geom
        for area, key in shares[1:]:
            if area / 10_000 >= SPLIT_HA and area >= SPLIT_SHARE * geom.area:
                out += [(p, key, code) for p in polygons(geom.intersection(props[key])) if p.area / 10_000 >= min_ha]
                rest = rest.difference(props[key])
        out += [(p, shares[0][1], code) for p in polygons(rest) if p.area / 10_000 >= min_ha]
    out.sort(key=lambda t: (-t[0].centroid.y, t[0].centroid.x))     # nummer från nordväst, rad för rad
    return out
