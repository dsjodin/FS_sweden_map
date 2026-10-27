"""Objekt i FS25-kartan: träd, byggnader (placeables), plats för köpta fordon,
planad mark under byggnader och fältens startgrödor (fields.xml).

Formaten är avlästa från spelets egen karta Zielonka (mapEU):
- träd är <ReferenceNode> i scenen som pekar på $data/maps/trees/<art>/<art>_stageNN.i3d
- byggnader och försäljningsställen står i config/placeables.xml och pekar på $data/placeables/...
- köpta fordon dyker upp vid storeSpawnPlace (onCreate BaseMission.onCreateStoreSpawnPlace)
- fältens gröda vid nytt spel står i config/fields.xml
Vi refererar bara spelets egna filer, inget kopieras från deras karta.
"""
import math
import xml.etree.ElementTree as ET

import numpy as np
import shapely
from shapely.geometry import Point, box
from shapely.ops import unary_union

# --- Träd --------------------------------------------------------------------------------------
# Bara filer som är bekräftade i spelets data (används av mapEU). Barrträd läggs till när vi
# vet deras filnamn.
TREE_DIR = "$data/maps/trees"
MATURE = [("aspen", "aspen_stage05", 3), ("aspen", "aspen_stage06_var01", 4), ("aspen", "aspen_stage06_var02", 4),
          ("beech", "beech_stage05", 3), ("beech", "beech_stage06_var01", 4), ("beech", "beech_stage06_var02", 4),
          ("oak", "oak_stage04", 3)]
EDGE = [("aspen", "aspen_stage03", 3), ("aspen", "aspen_stage04", 3), ("beech", "beech_stage03", 2),
        ("beech", "beech_stage04", 2), ("oak", "oak_stage02", 2), ("oak", "oak_stage03", 2),
        ("downyServiceBerry", "downyServiceBerry_stage01", 2), ("downyServiceBerry", "downyServiceBerry_stage02", 2)]
TREE_SPACING = 10.0     # m mellan träd i skogen (med slumpad förskjutning)
EDGE_WIDTH = 15.0       # m in från skogskanten där yngre träd och buskar står
MAX_TREES = 15000

# --- Byggnader ---------------------------------------------------------------------------------
# Startgård: inbördes placering som en gård i spelets egen karta (meter relativt gårdens mitt).
FARM = [
    {"file": "$data/placeables/mapEU/brandless/buildings/farmBuildings/farmBuilding03/farmBuilding03Preplaced.xml",
     "dx": -15, "dz": 15, "rot": "0 0 0", "farmhouse": True},
    {"file": "$data/placeables/mapEU/brandless/buildings/farmSheds/farmShed04.xml", "dx": -15, "dz": -16.5,
     "rot": "0 0 0"},
    {"file": "data/placeables/unia/farma/farma400/farma400.xml", "dx": 15, "dz": 3, "rot": "0 -90 0"},
]
FARM_SIZE = 100         # m, planad yta för startgården
GRAIN_MILL = "$data/placeables/mapEU/sellingPoints/grainMill/grainMill.xml"
MILL_SIZE = 110         # m, planad yta för spannmålsmottagningen
FLATTEN_BLEND = 20      # m övergång mellan planad yta och terräng


class Site:
    """En planad plats i SWEREF: mitt, storlek och planad höjd (sätts av flatten)."""

    def __init__(self, name, e, n, size):
        self.name, self.e, self.n, self.size = name, e, n, size
        self.height = None

    @property
    def box(self):
        h = self.size / 2
        return box(self.e - h, self.n - h, self.e + h, self.n + h)


def find_site(name, candidates, size, blocked, inner, prefer):
    """Första/bästa kandidat (e, n) där en ruta med sidan size inte krockar med blocked."""
    best = None
    for e, n in candidates:
        b = box(e - size / 2, n - size / 2, e + size / 2, n + size / 2)
        if not inner.contains(b) or b.intersects(blocked):
            continue
        score = prefer(e, n)
        if best is None or score < best[0]:
            best = (score, e, n)
    if best is None:
        return None
    return Site(name, best[1], best[2], size)


def farm_site(start_pt, farmyards, blocked, inner):
    """Startgården: gårdsplanen närmast startpunkten, annars närmaste lediga yta runt den."""
    cands = [(g.centroid.x, g.centroid.y) for g in farmyards if g.centroid.distance(start_pt) < 1500]
    cands += [(start_pt.x + dx, start_pt.y + dy) for dx in range(-800, 801, 20) for dy in range(-800, 801, 20)]
    return find_site("gård", cands, FARM_SIZE, blocked, inner, lambda e, n: Point(e, n).distance(start_pt))


def mill_site(roads, farm, blocked, inner):
    """Spannmålsmottagningen: ledig yta intill en länsväg, helst cirka 2 km från gården.
    Finns ingen plats längs länsvägarna provas småvägarna."""
    for classes in (("länsväg",), ("länsväg", "småväg")):
        site = _mill_site(roads, farm, blocked, inner, classes)
        if site is not None:
            return site
    return None


def _mill_site(roads, farm, blocked, inner, classes):
    cands = []
    for cls, line in roads:
        if cls not in classes or not line.intersects(inner):
            continue
        for d in np.arange(0, line.length, 40):
            p = line.interpolate(d)
            q = line.interpolate(min(d + 1, line.length))
            dx, dy = q.x - p.x, q.y - p.y
            ln = math.hypot(dx, dy) or 1
            for side in (-1, 1):
                off = MILL_SIZE / 2 + 12
                cands.append((p.x - dy / ln * off * side, p.y + dx / ln * off * side))
    return find_site("spannmålsmottagning", cands, MILL_SIZE, blocked, inner,
                     lambda e, n: abs(Point(e, n).distance(Point(farm.e, farm.n)) - 2000))


def flatten(game, world, sites):
    """Planar höjdkartan (spelets höjder, 2 m per pixel) under varje plats, med mjuk övergång."""
    n = game.shape[0]
    upp = world.size / (n - 1)
    ys, xs = np.mgrid[0:n, 0:n]
    ex = world.e0 - world.half + xs * upp
    ny = world.n0 + world.half - ys * upp
    for s in sites:
        h = s.size / 2
        inside = (np.abs(ex - s.e) <= h) & (np.abs(ny - s.n) <= h)
        s.height = float(np.median(game[inside]))
        dist = np.maximum(np.abs(ex - s.e) - h, np.abs(ny - s.n) - h)   # 0 inne i rutan
        w = np.clip(1 - dist / FLATTEN_BLEND, 0, 1)
        w = w * w * (3 - 2 * w)                                        # mjuk kurva
        game[:] = game * (1 - w) + s.height * w


# --- Träd i skogen -----------------------------------------------------------------------------
def tree_points(forests, cut, inner, seed=7):
    """Träd i skogsytorna: jitterat rutnät. Returnerar [(e, n, art, filnamn)]."""
    rng = np.random.default_rng(seed)
    forest = unary_union([g for g in forests if g.intersects(inner)]).intersection(inner)
    if forest.is_empty:
        return []
    forest = forest.difference(cut)
    core = forest.buffer(-EDGE_WIDTH)
    minx, miny, maxx, maxy = forest.bounds
    xs = np.arange(minx, maxx, TREE_SPACING)
    ys = np.arange(miny, maxy, TREE_SPACING)
    gx, gy = np.meshgrid(xs, ys)
    gx = gx.ravel() + rng.uniform(-0.4, 0.4, gx.size) * TREE_SPACING
    gy = gy.ravel() + rng.uniform(-0.4, 0.4, gy.size) * TREE_SPACING
    shapely.prepare(forest)
    keep = shapely.contains_xy(forest, gx, gy)
    gx, gy = gx[keep], gy[keep]
    if len(gx) > MAX_TREES:
        idx = rng.choice(len(gx), MAX_TREES, replace=False)
        gx, gy = gx[idx], gy[idx]
    shapely.prepare(core)
    in_core = shapely.contains_xy(core, gx, gy)

    def pick(pool, k):
        weights = np.array([w for *_, w in pool], dtype=float)
        return rng.choice(len(pool), k, p=weights / weights.sum())

    out = []
    mature, edge = pick(MATURE, len(gx)), pick(EDGE, len(gx))
    for i, (e, n) in enumerate(zip(gx, gy)):
        art, stage, _ = MATURE[mature[i]] if in_core[i] else EDGE[edge[i]]
        out.append((float(e), float(n), stage, f"{TREE_DIR}/{art}/{stage}.i3d"))
    return out


# --- i3d-tillägg -------------------------------------------------------------------------------
def add_file(root, filename, cache):
    if filename in cache:
        return cache[filename]
    files = root.find("Files")
    fid = str(max(int(f.get("fileId")) for f in files) + 1)
    ET.SubElement(files, "File", {"fileId": fid, "filename": filename})
    cache[filename] = fid
    return fid


def add_trees(root, trees, world, height_at, nid, seed=11):
    rng = np.random.default_rng(seed)
    scene = root.find("Scene")
    group = ET.SubElement(scene, "TransformGroup", {"name": "trees", "nodeId": nid()})
    cache = {}
    for e, n, stage, filename in trees:
        x, z = world.xz(e, n)
        ET.SubElement(group, "ReferenceNode", {
            "name": stage, "translation": f"{x:.2f} {height_at(e, n):.3f} {z:.2f}",
            "rotation": f"0 {rng.uniform(0, 360):.1f} 0", "referenceId": add_file(root, filename, cache),
            "nodeId": nid()})


def add_store_spawn(root, farm, world, nid):
    """Plats där köpta fordon dyker upp: en 40 m lång linje i gårdens östra del."""
    scene = root.find("Scene")
    uas = root.find("UserAttributes")
    x, z = world.xz(farm.e + 38, farm.n + 20)
    start_id = nid()
    start = ET.SubElement(scene, "TransformGroup", {"name": "storeSpawnPlace1Start",
                                                    "translation": f"{x:.1f} {farm.height:.2f} {z:.1f}",
                                                    "nodeId": start_id})
    ET.SubElement(start, "TransformGroup", {"name": "storeSpawnPlace1End", "translation": "0 0 40", "nodeId": nid()})
    ua = ET.SubElement(uas, "UserAttribute", {"nodeId": start_id})
    ET.SubElement(ua, "Attribute", {"name": "onCreate", "type": "scriptCallback",
                                    "value": "BaseMission.onCreateStoreSpawnPlace"})
    ET.SubElement(ua, "Attribute", {"name": "yOffset", "type": "float", "value": "0.1"})


# --- Konfigurationsfiler -----------------------------------------------------------------------
def write_placeables(path, farm, mill, world, placements=()):
    rows = ['<?xml version="1.0" encoding="utf-8" standalone="no" ?>', "<placeables>"]
    for b in FARM:
        x, z = world.xz(farm.e + b["dx"], farm.n + b["dz"])
        attrs = f'filename="{b["file"]}" position="{x:.2f} {farm.height:.3f} {z:.2f}" rotation="{b["rot"]}"'
        if b.get("farmhouse"):
            rows += [f"    <placeable {attrs}>", '        <farmhouse isFreeForAll="true"/>',
                     '        <wardrobe isFreeForAll="true"/>', "    </placeable>"]
        else:
            rows.append(f'    <placeable {attrs} boughtWithFarmlandOverwrite="true"/>')
    if mill is not None:
        x, z = world.xz(mill.e, mill.n)
        rows.append(f'    <placeable filename="{GRAIN_MILL}" position="{x:.2f} {mill.height:.3f} {z:.2f}" '
                    'rotation="0 -90 0"/>')
    for p in placements:   # från import_savegame.py, med spelets egna koordinater
        pos = " ".join(f"{v:.3f}" for v in p["position"])
        rot = " ".join(f"{v:g}" for v in p["rotation"])
        rows.append(f'    <placeable filename="{p["filename"]}" position="{pos}" rotation="{rot}" '
                    'boughtWithFarmlandOverwrite="true"/>')
    rows.append("</placeables>")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


# Grödkod (Jordbruksverket) -> FS25-gröda. 4, 1, 20 och 50 är antagna (se fetch_fields.py).
CROP_FRUIT = {1: "BARLEY", 2: "BARLEY", 3: "OAT", 4: "WHEAT", 5: "WHEAT", 12: "BARLEY",
              20: "CANOLA", 21: "CANOLA", 49: "GRASS", 50: "GRASS"}


def write_fields_xml(path, fields):
    """Grödor vid nytt spel: verklig gröda skördeklar, övrigt plöjt."""
    rows = ['<?xml version="1.0" encoding="utf-8" standalone="no" ?>', "<map>", "    <fields>"]
    for i, (_geom, _block, code) in enumerate(fields, 1):
        fruit = CROP_FRUIT.get(code)
        rows.append(f'        <field fieldId="{i}" weedState="0">')
        if fruit is None:
            rows += ['            <fruit type="UNKNOWN" />', '            <ground type="PLOWED" angle="0" />']
        elif fruit == "GRASS":
            rows += ['            <fruit type="GRASS" growthState="HARVESTREADY"/>',
                     '            <ground type="GRASS" angle="0" />']
        else:
            rows += [f'            <fruit type="{fruit}" growthState="HARVESTREADY"/>',
                     '            <ground type="HARVEST_READY" angle="0" />']
        rows += ['            <spray type="NONE" level="0" />', "        </field>"]
    rows += ["    </fields>", "</map>"]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def patch_map_xml(path):
    """Lägg till fältens startgrödor, butik och trädgräns i map.xml."""
    s = path.read_text(encoding="utf-8")
    extra = ('    <fields filename="maps/fields.xml" />\n'
             '    <shop filename="$data/store/ui/shop.xml" />\n'
             '    <treeTypes maxNumTrees="20000" />\n')
    anchor = '    <farmlands filename="maps/farmlands.xml" />\n'
    if anchor not in s:
        raise ValueError("Hittar inte farmlands-raden i map.xml")
    path.write_text(s.replace(anchor, anchor + extra), encoding="utf-8")
