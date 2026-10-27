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
# Trädarter i spelets data/maps/trees (avläst ur spelets installation). Gran, ask och riktig lönn
# finns inte i FS25; närmaste ersättare: askbladig lönn (boxelder), asiatisk björk och lind.
TREE_DIR = "$data/maps/trees"
TREE_SPECIES = {   # art: (svenskt namn, filnamn per storlek, passar i svensk natur)
    "pinusSylvestris": ("Tall", ["stage01", "stage02", "stage03", "stage04", "stage05"], True),
    "lodgepolePine": ("Contortatall", ["stage01", "stage02", "stage02Var2", "stage03", "stage03Var2"], True),
    "betulaErmanii": ("Björk", ["stage01", "stage02", "stage03", "stage04"], True),
    "aspen": ("Asp", ["stage01", "stage02", "stage03", "stage04", "stage05", "stage06_var01", "stage06_var02"], True),
    "oak": ("Ek", ["stage01", "stage02", "stage03", "stage04", "stage05"], True),
    "tiliaAmurensis": ("Lind", ["stage01", "stage02", "stage03", "stage04"], True),
    "americanElm": ("Alm", ["stage01", "stage02", "stage03", "stage04", "stage05"], True),
    "boxelder": ("Lönn (askbladig)", ["stage01", "stage02", "stage03"], True),
    "beech": ("Bok", ["stage01", "stage02", "stage02_var02", "stage02_var03", "stage03", "stage04", "stage05",
                      "stage06_var01", "stage06_var02"], True),
    "cherry": ("Körsbär", ["stage01", "stage02", "stage03", "stage04"], True),
    "apple": ("Äpple", ["stage03"], True),
    "downyServiceBerry": ("Häggmispel (buske)", ["stage01", "stage02", "stage03"], True),
    "goldenRain": ("Gullregn", ["stage01", "stage02", "stage03", "stage04"], False),
    "chineseElm": ("Kinesisk alm", ["stage01", "stage02", "stage03", "stage04"], False),
    "japaneseZelkova": ("Japansk zelkova", ["stage01", "stage02", "stage03", "stage04"], False),
    "northernCatalpa": ("Trumpetträd", ["stage01", "stage02", "stage03", "stage04"], False),
    "shagbarkHickory": ("Hickory", ["stage01", "stage02", "stage03", "stage04"], False),
    "pinusTabuliformis": ("Kinesisk tall", ["stage01", "stage02", "stage03", "stage04", "stage05"], False),
}


def tree(art, stage, weight):
    return (art, f"{art}_{stage}", weight)


# Urval (art, fil, vikt) för den automatiska skogen och träden utanför skogen.
CONIFER_MATURE = [tree("pinusSylvestris", "stage04", 3), tree("pinusSylvestris", "stage05", 4),
                  tree("lodgepolePine", "stage03", 1), tree("lodgepolePine", "stage03Var2", 1),
                  tree("betulaErmanii", "stage04", 1)]
CONIFER_EDGE = [tree("pinusSylvestris", "stage02", 2), tree("pinusSylvestris", "stage03", 3),
                tree("lodgepolePine", "stage02", 1), tree("betulaErmanii", "stage02", 1),
                tree("betulaErmanii", "stage03", 2), tree("downyServiceBerry", "stage02", 1)]
MATURE = [tree("betulaErmanii", "stage04", 4), tree("aspen", "stage05", 2), tree("aspen", "stage06_var01", 1),
          tree("oak", "stage04", 2), tree("oak", "stage05", 1), tree("tiliaAmurensis", "stage04", 1),
          tree("americanElm", "stage05", 1), tree("boxelder", "stage03", 1)]
EDGE = [tree("betulaErmanii", "stage02", 2), tree("betulaErmanii", "stage03", 3), tree("aspen", "stage03", 2),
        tree("aspen", "stage04", 2), tree("oak", "stage02", 1), tree("oak", "stage03", 1),
        tree("downyServiceBerry", "stage01", 1), tree("downyServiceBerry", "stage02", 2), tree("cherry", "stage02", 1)]
LOOSE_MATURE = [tree("oak", "stage04", 3), tree("oak", "stage05", 2), tree("tiliaAmurensis", "stage04", 2),
                tree("betulaErmanii", "stage04", 3), tree("americanElm", "stage05", 1), tree("boxelder", "stage03", 2),
                tree("aspen", "stage05", 1)]
LOOSE_YOUNG = [tree("betulaErmanii", "stage02", 2), tree("betulaErmanii", "stage03", 2), tree("boxelder", "stage02", 2),
               tree("cherry", "stage03", 1), tree("downyServiceBerry", "stage02", 2), tree("downyServiceBerry", "stage03", 2),
               tree("oak", "stage02", 1)]
TREE_SPACING = 10.0     # m mellan träd i skogen (med slumpad förskjutning)
EDGE_WIDTH = 15.0       # m in från skogskanten där yngre träd och buskar står
YOUNG_HEIGHT = 8.0      # m: lägre träd utanför skogen blir unga träd och buskar
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
def tree_points(forests, cut, inner, seed=7, mature=MATURE, edge=EDGE, max_trees=MAX_TREES):
    """Träd i skogsytorna: jitterat rutnät, fullvuxna inne i skogen och yngre i kanten.
    Returnerar [(e, n, art, filnamn)]."""
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
    if len(gx) > max_trees:
        idx = rng.choice(len(gx), max_trees, replace=False)
        gx, gy = gx[idx], gy[idx]
    shapely.prepare(core)
    in_core = shapely.contains_xy(core, gx, gy)

    def pick(pool, k):
        weights = np.array([w for *_, w in pool], dtype=float)
        return rng.choice(len(pool), k, p=weights / weights.sum())

    out = []
    pm, pe = pick(mature, len(gx)), pick(edge, len(gx))
    for i, (e, n) in enumerate(zip(gx, gy)):
        art, stage, _ = mature[pm[i]] if in_core[i] else edge[pe[i]]
        out.append((float(e), float(n), stage, f"{TREE_DIR}/{art}/{stage}.i3d"))
    return out


def loose_trees(points, cut, inner, seed=9):
    """Träd utanför skogen på givna platser [[e, n] eller [e, n, höjd], ...] (laser_trees.py).
    Låga träd (under YOUNG_HEIGHT m) blir unga träd och buskar, övriga fullvuxna lövträd
    (ek, lind, björk, alm, lönn och asp)."""
    rng = np.random.default_rng(seed)
    if not points:
        return []
    pts = np.array([list(p) + [99.0] * (3 - len(p)) for p in points], dtype=float)
    shapely.prepare(inner)
    keep = shapely.contains_xy(inner, pts[:, 0], pts[:, 1])
    if not cut.is_empty:
        shapely.prepare(cut)
        keep &= ~shapely.contains_xy(cut, pts[:, 0], pts[:, 1])
    out = []
    for pool, sel in ((LOOSE_YOUNG, pts[keep][pts[keep][:, 2] < YOUNG_HEIGHT]),
                      (LOOSE_MATURE, pts[keep][pts[keep][:, 2] >= YOUNG_HEIGHT])):
        weights = np.array([w for *_, w in pool], dtype=float)
        pick = rng.choice(len(pool), len(sel), p=weights / weights.sum())
        out += [(float(e), float(n), pool[k][1], f"{TREE_DIR}/{pool[k][0]}/{pool[k][1]}.i3d")
                for (e, n, _h), k in zip(sel, pick)]
    return out


def has_canopy(trees, chm_path, radius_cells=1):
    """Behåll bara träd där laserns krontak har en krona (inom radius_cells celler)."""
    import rasterio
    from PIL import Image, ImageFilter

    if not trees:
        return trees
    with rasterio.open(chm_path) as src:
        chm, inv = src.read(1), ~src.transform
    near = np.array(Image.fromarray(chm).filter(ImageFilter.MaxFilter(2 * radius_cells + 1))) > 0
    xy = np.array([(e, n) for e, n, *_ in trees])
    c, r = inv * (xy[:, 0], xy[:, 1])
    r, c = r.astype(int), c.astype(int)
    inside = (r >= 0) & (r < chm.shape[0]) & (c >= 0) & (c < chm.shape[1])
    ok = np.ones(len(trees), bool)            # utanför krontaket: behåll
    ok[inside] = near[r[inside], c[inside]]
    return [t for t, k in zip(trees, ok) if k]


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
             '    <treeTypes maxNumTrees="25000" />\n')
    anchor = '    <farmlands filename="maps/farmlands.xml" />\n'
    if anchor not in s:
        raise ValueError("Hittar inte farmlands-raden i map.xml")
    path.write_text(s.replace(anchor, anchor + extra), encoding="utf-8")
