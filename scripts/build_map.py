#!/usr/bin/env python3
"""Bygger en färdig FS25-kartmodd från våra data, utan MapToPlay.

Grunden är fs25-empty-map (third_party/fs25_empty_map), som skriver alla
filer en FS25-karta behöver. Ovanpå den lägger vi:

- terräng från Lantmäteriets höjdmodell (data/<namn>/lm/hojd/dtm_area.tif)
- fält från Jordbruksverkets skiften: fältnoder i i3d-filen, kultiverad
  åkerjord i densityMap_ground
- farmlands: FS25 tillåter ett fält per markområde, så varje fält blir ett
  köpbart markområde (fält N på markområde N). Med fastighetsgränser
  (data/<namn>/fastigheter.geojson, se fastigheter.py) går resten av en
  fastighet till dess närmaste fält, och fastigheter utan fält blir egna
  markområden. Fälten på fastigheten närmast startpunkten ägs från start.
  Övrig mark delas i skiften längs vägar, vattendrag och skogskanter.
- marktyper (skog, vatten, bebyggelse, öppen mark) från Lantmäteriets
  Marktäcke eller Topografi 10, vattendrag, vägar och byggnader från
  Topografi 10 (data/topografi10/, se landcover.py). Det som saknas tas från
  OSM, liksom gårdsplaner och gårdsvägar.
- marktexturer: asfalt, grus, skogsmark, åkerjord och gräs
- översiktskarta (PDA) ritad från samma data. Spelet visar den över dubbla
  kartytan, så den täcker också omgivningen runt kartan.
- träd i skogarna och, om laser_trees.py har körts, bara där laserdata visar
  kronor, samt åkerholmar, trädrader och gårdsträd utanför skogen. Granar ur
  FS25_sprucepack_prefab.zip i data/mods, annars tall (prefab_trees.py). Startgård med gårdshus, maskinhall och silo, en
  spannmålsmottagning och plats för köpta fordon (scripts/fs25_objects.py)
- fältens grödor vid nytt spel från skiftenas grödkoder (maps/fields.xml)
- byggnader och objekt som du placerat i spelet och hämtat med
  import_savegame.py (maps/<namn>/placeringar.json)

Kräver: fetch_osm.py, fetch_fields.py och fetch_heightmap.py för kartan.

Resultat:
    build/<namn>/<mod_name>/        modmappen
    build/<namn>/<mod_name>.zip     att lägga i spelets mods-mapp

Användning:
    python scripts/build_map.py [--map tysslinge] [--floor 10]
"""
import argparse
import copy
import json
import sys
import zipfile

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

from area import ROOT, add_map_argument, open_map, to_sweref

FEM = ROOT / "third_party" / "fs25_empty_map" / "tools"
sys.path.insert(0, str(FEM))
sys.path.insert(0, str(ROOT / "scripts"))
import binfmt  # noqa: E402
import gen_configs  # noqa: E402
import gen_data  # noqa: E402
import gen_i3d  # noqa: E402
import mapcfg  # noqa: E402
from analyze_area import load_features  # noqa: E402
import fs25_objects as obj  # noqa: E402
import landcover  # noqa: E402
import water  # noqa: E402
import drawings as drawn  # noqa: E402
import prefab_trees  # noqa: E402
import fastigheter  # noqa: E402

# Marklager (namn i spelets standarduppsättning) i prioritetsordning: senare vinner.
GROUND = [
    ("grass01", "gräs"),
    ("forestLeaves01", "skog"),
    ("gravelSmall01", "gårdsplan"),
    ("mudDark01", "åker"),
    ("gravel01", "grusväg"),
    ("asphalt01", "asfalt"),
]
GROUND_NAMES = [name for name, _ in GROUND]
ROAD_STYLE = {  # vägklass från analyze_area -> (marklager, bredd i meter)
    "motorväg/riksväg": ("asphalt01", 12),
    "länsväg": ("asphalt01", 7),
    "småväg": ("asphalt01", 5),
    "grusväg/brukningsväg": ("gravel01", 3.5),
    "gårdsväg/infart": ("gravel01", 3),
}
MEADOW_CODES = {52, 53}      # betesmark och slåtteräng blir inte fält (antaget, se make_osm_fields.py)
BUFFER_CODES = {77, 314}     # skyddszoner längs vattendrag: bara cirka 6 m breda remsor, får inte odlas
MIN_FIELD_WIDTH = 15.0       # m medelbredd (2 × yta / omkrets); smalare remsor blir gräs, inte fält
ARM_WIDTH = 12.0             # m: delar av ett fält som är smalare än så klipps bort
FARMLAND_REACH = 300.0       # m: mark utan fält hör till närmaste jordbruksblock inom detta avstånd
OTHER_LAND_CELL = 600.0      # m: största sida på skiften utanför jordbruksblocken
MIN_OTHER_HA = 3.0           # ha: mindre rester går till närmaste markområde
# Markpris i spelet (€/ha för åker). Spelets egna kartor har 60 000, vilket ger miljonbelopp för svenska
# fastigheter på 50-100 ha. 15 000 € motsvarar ungefär svenskt snittpris på åkermark (cirka 150 000 kr/ha).
# Kan ändras per karta med "markpris_per_ha" i maps/<namn>/area.json.
LAND_PRICE_PER_HA = 15000
START_MAX_HA = 80.0          # ha: största fastighet som väljs som startgård (om inte "startfastighet" anges)
LAND_PRICE_SCALE = {"åker": 1.0, "skog": 0.6, "tomt": 1.5, "övrigt": 0.5}   # del av åkerpriset
NO_BUILD_WATER = 2.5         # m på var sida om diken och bäckar där man inte får bygga
GROUND_CULTIVATED = 2        # terrainDetail groundType 2 = kultiverad
YARD_APRON = 4.0             # m grus runt byggnader från byggeditorn
# Växtlighet målad i densityMap_fruits. Värdet är lagrets nummer i fruits-lagret (1 = decoFoliage, i
# ordningen i base_foliage.json) plus tillståndet × 32; tillstånden räknas från 1 i foliage-filens
# ordning. Avläst och bekräftat i GIANTS Editor (Foliage-panelen): gräs harvestReady = 6 + 4 × 32 = 134,
# vete harvestReady = 7 + 8 × 32 = 263, harvested = 10, dead = 9. Skördeklart tillstånd per gröda, alla
# avlästa i GIANTS Editor (kommentaren i barley.xml, "1 1 1 0 - harvest ready", stämmer inte: det är 8).
CROP_STATE = {"WHEAT": ("wheat", 8), "BARLEY": ("barley", 8), "OAT": ("oat", 5), "CANOLA": ("canola", 9),
              "GRASS": ("grass", 4)}
OPEN_GRASS = ("grass", 3)    # greenMiddle: gräs på öppen mark (marklagret grass01 utanför fälten)
LAWN_GRASS = ("grass", 2)    # greenSmall: kortare gräs på en egen gårdsplan
# Tillstånden i fruits-lagrets dekorationslager, i ordningen i GIANTS Editors lista (räknas från 1).
DECO_STATES = {
    "forestPlants": ["dry branches", "clovers", "starflower", "bunchberry", "salmonBerryBush",
                     "starryFalseSolomonSeal", "swordFern", "deerFern", "grass", "riceLongGrainDeco"],
    "waterPlants": ["typhaLatifoliaSmall", "typhaLatifoliaMedium", "typhaLatifoliaLarge", "miscanthusSinensisSmall",
                    "miscanthusSinensisMedium", "miscanthusSinensisLarge", "stipaTenuissimaSmall",
                    "stipaTenuissimaLarge"],
    "decoFoliage": ["smallDenseMix", "smallRumex", "apera", "whiteTallWeed", "greenTallWeed", "cirsium",
                    "papaverRhoeas", "rumex", "grassSmall", "grassMedium", "grassCut", "coneflower",
                    "slenderMountainMint", "wildBergamot", "prairieBlazingStar"],
}
# Blandningar (tillstånd, vikt) som passar svensk natur; None = bar mark. De amerikanska präriearterna
# och laxbärsbusken används inte.
FOREST_FLOOR = [("dry branches", 3), ("starflower", 2), ("bunchberry", 2), ("deerFern", 3), ("swordFern", 1),
                ("clovers", 1), ("grass", 2), (None, 4)]     # skogsstjärna, hönsbär, ormbunkar, ris
VERGE = [("grassMedium", 6), ("smallDenseMix", 2), ("apera", 2), ("rumex", 1), ("cirsium", 1),
         ("papaverRhoeas", 1), ("whiteTallWeed", 1), ("greenTallWeed", 1)]   # vägrenar: gräs, ven, syra, tistel, vallmo
VERGE_WIDTH = 4.0            # m vägren med örter utanför vägkanten
REEDS = [("typhaLatifoliaSmall", 2), ("typhaLatifoliaMedium", 3), ("typhaLatifoliaLarge", 2), (None, 3)]   # kaveldun
REED_WIDTH = 3.0             # m kaveldun längs diken, åar och stränder
# Buskar i decoBush (eget lager, densityMap_groundFoliage, värdet = tillståndet i GIANTS Editors lista).
BUSH_STATES = ["Small", "Medium", "Big", "Super Big", "Blueberry Short", "Blueberry Small", "Blueberry Medium",
               "Blueberry Big", "Blueberry Tall", "Boxwood Small", "Boxwood Medium", "Boxwood Big",
               "Hazelnut Small", "Hazelnut Medium", "Hazelnut Big"]
BLUEBERRY = [("Blueberry Short", 3), ("Blueberry Small", 3), ("Blueberry Medium", 2), ("Blueberry Big", 1),
             ("Blueberry Tall", 1), (None, 6)]           # blåbärsris i barrskogen
EDGE_BUSHES = [("Small", 2), ("Medium", 2), ("Big", 1), ("Hazelnut Small", 2), ("Hazelnut Medium", 2),
               ("Hazelnut Big", 1), (None, 4)]           # buskar och hassel i skogskanterna
BUSH_EDGE = 8.0              # m in från skogskanten
PATCH = 6.0                  # m: växterna står i fläckar av ungefär den här storleken
VEHICLE_CLEAR = 8.0          # m utan träd runt startgårdens maskiner
FIELD_SHRINK = 1.5           # m, ger renar mellan skiften
FIELD_EDGE = 5               # m, fält hålls så här långt från kartkanten
MIN_FIELD_HA = 0.5
ROAD_MARGIN = 1.5            # m fri kant mellan vägkant och fält
WATER_CUT = {"river": 8, "canal": 4, "stream": 3, "ditch": 1.5, "drain": 1.5,   # halv bredd inkl. kant, m
             "vattendrag": 2}   # Topografi 10: bäckar och större diken som linjer, breda åar är ytor
OVERVIEW_COLORS = {
    "grass01": (126, 146, 84), "forestLeaves01": (52, 82, 46), "gravelSmall01": (150, 140, 120),
    "mudDark01": (168, 140, 92), "gravel01": (190, 176, 150), "asphalt01": (70, 70, 72),
}


class World:
    """Omräkning SWEREF 99 TM <-> spelets koordinater (x österut, z söderut, origo i kartans mitt)."""

    def __init__(self, project):
        self.size = project.size
        self.half = project.size / 2
        self.e0, self.n0 = to_sweref(project.config["center"]["lon"], project.config["center"]["lat"])

    def xz(self, e, n):
        return e - self.e0, self.n0 - n

    def px(self, e, n, res):
        """SWEREF -> pixel (kolumn, rad) i en bild med res pixlar över hela kartan."""
        s = res / self.size
        return (e - self.e0 + self.half) * s, (self.n0 - n + self.half) * s

    def scaled(self, factor):
        """Samma mittpunkt men factor gånger så stor yta (för översiktskartan)."""
        big = copy.copy(self)
        big.size, big.half = self.size * factor, self.half * factor
        return big

    def square(self, inset=0.0):
        h = self.half - inset
        return box(self.e0 - h, self.n0 - h, self.e0 + h, self.n0 + h)


def draw_polygon(draw, geom, world, res, fill, hole_fill=0):
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        draw.polygon([world.px(x, y, res) for x, y in p.exterior.coords], fill=fill)
        for ring in p.interiors:
            draw.polygon([world.px(x, y, res) for x, y in ring.coords], fill=hole_fill)


def make_dem(project, world, floor):
    """Höjdkarta med 2 m per pixel: (storlek/2 + 1) pixlar, pixelmitt på kartans jämna meter."""
    src_path = project.lm / "hojd" / "dtm_area.tif"
    if not src_path.exists():
        sys.exit(f"Hittar inte {project.rel(src_path)}. Kör fetch_heightmap.py först.")
    upp = mapcfg.Cfg.UNITS_PER_PIXEL
    n = project.size // upp + 1
    out = np.full((n, n), np.nan, dtype=np.float32)
    transform = from_origin(world.e0 - world.half - upp / 2, world.n0 + world.half + upp / 2, upp, upp)
    with rasterio.open(src_path) as src:
        reproject(source=rasterio.band(src, 1), destination=out, src_transform=src.transform, src_crs=src.crs,
                  src_nodata=src.nodata, dst_transform=transform, dst_crs=src.crs, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
    if np.isnan(out).all():
        sys.exit("Höjdmodellen täcker inte kartrutan.")
    out[np.isnan(out)] = np.nanmin(out)
    base = float(out.min()) - floor
    game = out - base
    scale = gen_i3d.HEIGHT_SCALE
    if game.max() > scale:
        sys.exit(f"Terrängen blir {game.max():.0f} m hög, mer än heightScale {scale}.")
    return game, base, float(out.max())


def height_sampler(game, world):
    n = game.shape[0]

    def height_at(e, n_):
        c, r = world.px(e, n_, n - 1)
        c, r = int(round(min(max(c, 0), n - 1))), int(round(min(max(r, 0), n - 1)))
        return float(game[r, c])

    return height_at


def obstacles(roads, waterways, world, areas=()):
    """Vägar, vattendrag och vattenytor som buffrade ytor, att skära bort ur fälten."""
    sq = world.square(-50)
    parts = [g.buffer(ROAD_MARGIN) for cls, g in areas if cls == "water" and g.intersects(sq)]
    for cls, line in roads:
        if line.intersects(sq):
            parts.append(line.buffer(ROAD_STYLE[cls][1] / 2 + ROAD_MARGIN, cap_style="flat"))
    for kind, line in waterways:
        if kind in WATER_CUT and line.intersects(sq):
            parts.append(line.buffer(WATER_CUT[kind], cap_style="flat"))
    return unary_union(parts)


def load_fields(project, world, cut):
    """Skiften inom kartan som fält: (polygon i SWEREF, blockid, grödkod). Vägar och
    vattendrag skärs bort, så ett skifte som korsas av en väg blir flera fält."""
    path = project.raw / "jbv_skiften.geojson"
    if not path.exists():
        sys.exit(f"Hittar inte {project.rel(path)}. Kör fetch_fields.py först.")
    inner = world.square(FIELD_EDGE)
    fields = []
    for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        if p.get("grdkod_mar") in MEADOW_CODES | BUFFER_CODES:
            continue
        geom = shape(f["geometry"]).buffer(0).buffer(-FIELD_SHRINK, join_style="mitre").intersection(inner)
        if geom.intersects(cut):
            geom = geom.difference(cut)          # skär bort vägar och vatten
        # Ta bort smala armar och remsor (kantzoner längs diken), även när de sitter ihop med ett
        # större fält. Hörnen behålls tack vare mitre.
        geom = geom.buffer(-ARM_WIDTH / 2, join_style="mitre").buffer(ARM_WIDTH / 2, join_style="mitre")
        geom = geom.simplify(1.0, preserve_topology=True)
        parts = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
        for part in parts:
            if part.area / 10_000 >= MIN_FIELD_HA and 2 * part.area / part.length >= MIN_FIELD_WIDTH:
                fields.append((part, str(p.get("blockid")), p.get("grdkod_mar")))
    fields.sort(key=lambda t: (-t[0].centroid.y, t[0].centroid.x))  # nummer från nordväst, rad för rad
    return fields


def surrounding_fields(project, world):
    """Alla skiften inom world (även utanför kartan), som (polygon, None, None) för översiktskartan."""
    sq = world.square()
    out = []
    for f in json.loads((project.raw / "jbv_skiften.geojson").read_text(encoding="utf-8"))["features"]:
        if f["properties"].get("grdkod_mar") in MEADOW_CODES | BUFFER_CODES:
            continue
        geom = shape(f["geometry"]).buffer(0).buffer(-FIELD_SHRINK, join_style="mitre")
        if geom.intersects(sq):
            for part in ([geom] if geom.geom_type == "Polygon" else getattr(geom, "geoms", [])):
                if part.geom_type == "Polygon":
                    out.append((part, None, None))
    return out


def ground_labels(osm, world, fields, res, overrides=()):
    """Etikettbild (index i GROUND) för marklagren, 1 pixel per meter. overrides = [(marklager, yta)]
    från byggeditorns ritningar målas över fält och skog, före vägarna."""
    areas, roads = osm[0], osm[1]
    img = Image.new("L", (res, res), 0)
    d = ImageDraw.Draw(img)
    idx = {name: i for i, (name, _) in enumerate(GROUND)}
    sq = world.square(-50)
    for cls, geom in areas:
        if not geom.intersects(sq):
            continue
        if cls in landcover.FORESTS:
            draw_polygon(d, geom, world, res, idx["forestLeaves01"], idx["grass01"])
        elif cls in ("farmyard", "residential"):
            draw_polygon(d, geom, world, res, idx["gravelSmall01"], idx["grass01"])
    for geom, _, _ in fields:
        draw_polygon(d, geom.buffer(FIELD_SHRINK), world, res, idx["mudDark01"])
    for layer, geom in overrides:
        draw_polygon(d, geom, world, res, idx[layer], idx[layer])
    for layer in ("gravel01", "asphalt01"):  # grus först, asfalt överst
        for cls, line in roads:
            name, width = ROAD_STYLE[cls]
            if name != layer or not line.intersects(sq):
                continue
            d.line([world.px(x, y, res) for x, y in line.coords], fill=idx[name],
                   width=max(1, int(round(width * res / world.size))), joint="curve")
    return np.array(img)


def build(project, args):
    cfg_map = project.config
    mod_name = cfg_map.get("mod_name") or f"FS25_{project.name.capitalize()}"
    title = cfg_map.get("title", project.name)
    cfg = mapcfg.Cfg(project.size, mod_name.removeprefix("FS25_"), f"{project.size // 1024}x", mod=mod_name,
                     title=title, i3d=f"{project.name}.i3d", starter_field=False)
    world = World(project)
    mod_dir = project.build / mod_name
    maps_dir = mod_dir / "maps"
    data_dir = maps_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    print("Höjdkarta ...")
    game, base, real_max = make_dem(project, world, args.floor)
    print("Fält och marklager ...")
    osm, sources = load_land(project, world)
    osm = osm[:2] + (water.snap_lines(game, world, osm[2]),) + osm[3:]   # vattendragen till dikets botten
    drawings = drawn.load(project, world)                   # byggeditorns "Måla mark"
    if drawings:
        print(f"  Ritningar från byggeditorn: {sum(d['kind'] == 'yta' for d in drawings)} ytor, "
              f"{sum(d['kind'] == 'väg' for d in drawings)} vägar")
    osm = drawn.apply_land(osm, drawings, ROAD_STYLE)
    cut = obstacles(osm[1], osm[2], world, osm[0])
    fields = drawn.apply_fields(load_fields(project, world, cut), drawings, cut, world.square(FIELD_EDGE),
                                FIELD_SHRINK)
    properties = fastigheter.load(project, world)          # verkliga fastighetsgränser, om de finns
    if properties:
        fields = fastigheter.assign_fields(fields, properties, MIN_FIELD_HA)
        print(f"  Fastigheter: {len(properties)} inom kartan, {len(fields)} fält efter delning längs gränserna")
    labels = ground_labels(osm, world, fields, cfg.weight_res, drawn.overrides(drawings))

    # Farmlands. FS25 tillåter bara ett fält per markområde ("There already exists field X on farmland Y",
    # fält nummer två och framåt försvinner), så varje fält blir ett eget markområde, med fält nummer N på
    # markområde N. Resten av en fastighet går till fastighetens närmaste fält; fastigheter utan fält blir
    # egna markområden (fastigheter.py). Startgårdens fält: de som valts i byggeditorns Start-läge
    # (maps/<namn>/start.json), annars fälten på fastigheten (eller jordbruksblocket) närmast startpunkten.
    start = cfg_map.get("start") or cfg_map["center"]
    se, sn = to_sweref(start["lon"], start["lat"])
    start_pt = Point(se, sn)
    blocks = {}
    for geom, block, _ in fields:
        blocks.setdefault(block, []).append(geom)
    wanted = (cfg_map.get("startfastighet") or "").strip().upper()
    if wanted and wanted not in blocks:
        sys.exit(f"startfastighet {wanted} i area.json har inga fält inom kartan (eller saknas i fastigheter.geojson).")
    small = [b for b in blocks if b not in properties or properties[b].area / 10_000 <= START_MAX_HA]
    start_block = wanted or min(small or blocks, key=lambda b: unary_union(blocks[b]).distance(start_pt))
    chosen = load_start(project, world)
    picked = [f for f in fields if any(f[0].contains(pt) for pt in chosen["falt"])] if chosen["falt"] else []
    if chosen["falt"] and not picked:
        print("  Varning: inget av fälten som valts i byggeditorns Start-läge finns kvar, startgården väljs själv")
    if picked:
        fields = picked + [f for f in fields if not any(f is q for q in picked)]
        start_desc = f"{len(picked)} fält valda i byggeditorn"
    else:
        fields = [f for f in fields if f[1] == start_block] + [f for f in fields if f[1] != start_block]
        start_desc = (f"{'fastighet' if start_block in properties else 'block'} {start_block} med "
                      f"{len(blocks[start_block])} fält" + ("" if wanted else
                      f" (närmast startpunkten av dem under {START_MAX_HA:.0f} ha; välj själv i byggeditorns Start-läge)"))
    n_start = len(picked) or len(blocks[start_block])
    save_fields_for_editor(project.build / "falt.json", fields, world, n_start)
    if len(fields) > 254:
        sys.exit(f"{len(fields)} fält, men FS25 tillåter bara ett fält per markområde och högst 254 markområden.")
    lone = [k for k in properties if k not in blocks][:254 - len(fields)]   # fastigheter utan fält, största först
    lone_id = {k: len(fields) + 1 + j for j, k in enumerate(lone)}
    n_named = len(fields) + len(lone)

    print("Gård, spannmålsmottagning och planering ...")
    areas, roads, _ww, _rail, buildings, _pl = osm
    field_union = unary_union([g.buffer(3) for g, _, _ in fields])
    inner = world.square(150)
    forests = [g for c, g in areas if c in landcover.FORESTS]
    if chosen["gard"]:                                       # byggeditorns Start-läge
        farm = obj.Site("gård", world.e0 + chosen["gard"][0], world.n0 + chosen["gard"][1],
                        chosen["bredd"], chosen["langd"], chosen["vridning"])
    else:                                                    # inte på fält, vägar eller i skog
        farm = obj.farm_site(start_pt, [g for c, g in areas if c == "farmyard"],
                             unary_union([field_union, cut] + forests), inner)
    if farm is None:
        sys.exit("Hittade ingen ledig plats för startgården nära startpunkten.")
    mill_blocked = unary_union([field_union, cut, farm.box.buffer(200)]
                               + [g for c, g in areas if c in landcover.FORESTS + ("water", "residential")] + buildings)
    mill = obj.mill_site(roads, farm, mill_blocked, inner)
    sites = [farm] + ([mill] if mill else [])
    edited = load_editor_buildings(project, world)          # byggeditor.py: [(Site, placeable)]
    sites += [site for site, _ in edited]
    # En egen gårdsplan utan spelets byggnader kan behålla terrängens verkliga höjder (Start-läget,
    # "plana gårdsplanen" avbockad): då planas bara marken under varje byggnad.
    keep_terrain = bool(chosen["gard"]) and not chosen["byggnader"] and not chosen["plana"]
    obj.flatten(game, world, [s_ for s_ in sites if not (keep_terrain and s_ is farm)])
    if keep_terrain:
        farm.height = float(height_sampler(game, world)(farm.e, farm.n))
    water_meshes = water.build_water(game, world, areas, osm[2],   # sänker terrängen under vattnet
                                     [(ROAD_STYLE[c][1], ln) for c, ln in roads])
    if game.max() > gen_i3d.HEIGHT_SCALE or game.min() < 0:
        sys.exit("Höjderna hamnar utanför heightScale efter planering.")
    dem = np.round(game / gen_i3d.HEIGHT_SCALE * 65535).astype(np.uint16)
    height_at = height_sampler(game, world)
    idx_yard = [name for name, _ in GROUND].index("gravelSmall01")
    # Gårdsplanerna. En egen gårdsplan (Start-läget, utan spelets byggnader) blir gräs med grus under och
    # runt byggnaderna, och träden från laserdatan får stå kvar där, utom vid byggnader och maskiner.
    # Övriga platser (spelets gård, spannmålsmottagningen) blir grus som förut. Byggeditorns målade ytor
    # (Måla mark) går före inne på gårdsplanerna.
    own_yard = bool(chosen["gard"]) and not chosen["byggnader"]
    on_site = mask_of([s_.box for s_ in sites], world, labels.shape[0])
    labels[mask_of([farm.box] if own_yard else [], world, labels.shape[0])] = GROUND_NAMES.index("grass01")
    labels[mask_of([s_.box.buffer(YARD_APRON) if s_.name.startswith("byggnad") else s_.box for s_ in sites
                    if not (own_yard and s_ is farm)], world, labels.shape[0])] = idx_yard
    for layer, geom in drawn.overrides(drawings):
        labels[mask_of([geom], world, labels.shape[0]) & on_site] = GROUND_NAMES.index(layer)
    spawn_pt = Point(*farm.at(-15, min(38, farm.length / 2 - 2)))   # framför gårdshuset
    keep_clear = ([Point(p).buffer(VEHICLE_CLEAR) for p in vehicle_points(project, world)]
                  + [spawn_pt.buffer(5), Point(*farm.at(min(38, farm.width / 2 - 6), 0)).buffer(25)])
    no_trees = unary_union([cut, field_union, drawn.no_tree_zone(drawings)] + keep_clear
                           + [s_.box.buffer(2 if s_.name.startswith("byggnad") else 10) for s_ in sites
                              if not (own_yard and s_ is farm)])
    conifer = [g for c, g in areas if c == "barrskog"]
    broadleaf = [g for c, g in areas if c == "forest"]
    share = sum(g.area for g in conifer) / max(sum(g.area for g in conifer + broadleaf), 1)
    trees = obj.tree_points(conifer, no_trees, world.square(5), mature=obj.CONIFER_MATURE, edge=obj.CONIFER_EDGE,
                            max_trees=int(obj.MAX_TREES * share)) \
        + obj.tree_points(broadleaf, no_trees, world.square(5), seed=8, max_trees=int(obj.MAX_TREES * (1 - share)))
    chm_path = project.lm / "laser" / "krontak.tif"
    if chm_path.exists():     # laser_trees.py: inga träd där Marktäckes skog saknar kronor (kalhyggen)
        before = len(trees)
        trees = obj.has_canopy(trees, chm_path)
        print(f"  Laserdata: {before - len(trees)} skogsträd borttagna där det inte står träd")
    trees += drawn.trees(drawings, obj.tree_file)         # träd utsatta i byggeditorn
    loose_path = project.lm / "trad.json"
    loose = []
    if loose_path.exists():   # åkerholmar, trädrader och gårdsträd: [[e, n], ...] under "points"
        loose = obj.loose_trees(json.loads(loose_path.read_text(encoding="utf-8"))["points"],
                                unary_union([no_trees] + buildings), world.square(5))
        trees += loose
    prefabs = prefab_trees.install(maps_dir, obj.PREFAB_TREES)   # granar ur data/mods, kopieras in i kartan
    trees = obj.without_missing_prefabs(trees, prefabs)
    if prefabs:
        sources.append("Granar: " + ", ".join(obj.PREFAB_TREES[a]["zip"].removesuffix(".zip") for a in sorted(prefabs))
                       + " (prefab).")
    # Var träden hamnade, för kontrollkartan (kontrollkarta.py).
    project.build.mkdir(parents=True, exist_ok=True)
    (project.build / "trad_placerade.json").write_text(json.dumps({
        "skog": [[round(e, 1), round(n, 1)] for e, n, *_ in trees[:len(trees) - len(loose)]],
        "utanfor": [[round(e, 1), round(n, 1)] for e, n, *_ in loose]}), encoding="utf-8")

    # i3d: fs25-empty-map:s scen, med våra marklager och fält.
    weight_files = {name: f"data/{name}_weight.png" for name, _ in GROUND}

    def emit_layer_block(layers_el):
        R, sub, LD = gen_i3d.R, gen_i3d.sub, gen_i3d.LAYERDEF
        la = sub(layers_el, "LayerAttributes")
        for a in LD["LayerAttribute"]:
            sub(la, "LayerAttribute", **a)
        blank = R.fid("data/blank_weight.png")
        for L in LD["Layer"]:
            attrs = {k: v for k, v in L.items() if not k.endswith("Map")}
            for tk, ak in gen_i3d._TEXMAP:
                if L.get(tk):
                    attrs[ak] = R.fid(L[tk])
            attrs["weightMapId"] = R.fid(weight_files[L["name"]]) if L["name"] in weight_files else blank
            sub(layers_el, "Layer", **attrs)
        for O in LD["OverlayLayer"]:
            attrs = {k: v for k, v in O.items() if not k.endswith("Map")}
            for tk, ak in gen_i3d._TEXMAP:
                if O.get(tk):
                    attrs[ak] = R.fid(O[tk])
            sub(layers_el, "OverlayLayer", **attrs)
        for C in LD["CombinedLayer"]:
            sub(layers_el, "CombinedLayer", **C)
        for C in LD["CombinedOverlayLayer"]:
            sub(layers_el, "CombinedOverlayLayer", **C)

    gen_i3d.emit_layer_block = emit_layer_block
    i3d_path = maps_dir / cfg.i3d
    local_files = gen_i3d.build(cfg, str(i3d_path))
    add_fields_to_i3d(i3d_path, fields, world, height_at, spawn_pt, trees, farm, water_meshes)

    # Data: fs25-empty-map skriver tomma lager, sedan ersätter vi med våra.
    gen_data.build(cfg, str(data_dir))
    (data_dir / "grass_weight.png").unlink(missing_ok=True)  # ersätts av grass01_weight.png
    Image.fromarray(dem).save(data_dir / "map_dem.png")
    for i, (name, _) in enumerate(GROUND):
        Image.fromarray(np.where(labels == i, 255, 0).astype(np.uint8)).save(data_dir / f"{name}_weight.png")

    N = cfg.density_res
    ground = Image.new("L", (N, N), 0)
    dg = ImageDraw.Draw(ground)
    for geom, _block, _ in fields:
        draw_polygon(dg, geom.buffer(-1), world, N, GROUND_CULTIVATED)        # arbetsyta 1 m in från kanten
    binfmt.paint_gdm(str(data_dir / "densityMap_ground.gdm"), N, np.array(ground, dtype=np.uint16), 11, 1, 0)
    paint_vegetation(data_dir / "densityMap_fruits.gdm", fields, labels, [farm.box] if own_yard else [], roads,
                     world, N, osm[2], [g for c, g in areas if c == "water"])
    paint_bushes(data_dir / "densityMap_groundFoliage.gdm", areas, world, N)
    no_build = no_build_mask(osm, world, cfg.il_res["placementCollision"])
    farm_arr = paint_farmlands(fields, properties, lone_id, farm.box, world, cfg.il_res["farmland"])
    if not properties:
        farm_arr = extend_farmlands(farm_arr, no_build, world, osm)
    near_fields = np.mean(farm_arr > 0)
    farm_arr, n_other = fill_farmlands(farm_arr, world, osm, n_named + 1)
    binfmt.paint_grle(str(data_dir / "infoLayer_farmland.grle"), farm_arr)
    binfmt.paint_grle(str(data_dir / "infoLayer_placementCollision.grle"), no_build.astype(np.uint8))
    print(f"Mark: {near_fields:.0%} av kartan hör till {len(fields)} fält"
          + (f" och {len(lone)} fastigheter utan fält" if properties else "") + f", resten till {n_other} skiften "
          f"(skog, tätort och annan mark). {np.mean(no_build):.0%} spärrad för bygge "
          "(vägar, vatten, diken, järnväg)")

    # Konfiguration: fs25-empty-map:s filer, sedan våra farmlands, modDesc-text och översiktskarta.
    gen_configs.build(cfg, str(mod_dir), str(maps_dir))
    price = float(cfg_map.get("markpris_per_ha", LAND_PRICE_PER_HA))
    scales = price_scales(farm_arr, fields, osm, world)
    write_farmlands(maps_dir / "farmlands.xml", n_named + n_other, price, scales, n_start)
    ha = np.bincount(farm_arr.ravel(), minlength=256) * (world.size / farm_arr.shape[0]) ** 2 / 10_000
    costs = sorted(ha[i] * price * scales.get(i, 1.0) for i in range(n_start + 1, n_named + n_other + 1))
    if costs:
        def eur(v):
            return f"{v:,.0f} €".replace(",", " ")
        print(f"Markpris: {eur(price)}/ha för åker, skog och annan mark billigare. Markområdena kostar "
              f"{eur(costs[len(costs) // 2])} i mitten och {eur(costs[-1])} som mest")
    # Kontroll, bara på servern (inte i modden): bild med numren och lista nummer -> fastighet och pris.
    names = {i: f"fält {i} ({(obj.CROP_FRUIT.get(c) or 'plöjt').lower()}), "
                + (k if k in properties else f"jordbruksblock {k}") for i, (_, k, c) in enumerate(fields, 1)}
    names.update({i: k for k, i in lone_id.items()})
    save_farmland_image(project.build / "markomraden.png", farm_arr)
    (project.build / "markomraden.txt").write_text(
        "nr\tha\tpris €\tfastighet\n" + "".join(
            f"{i}\t{ha[i]:.1f}\t{ha[i] * price * scales.get(i, 1.0):.0f}\t"
            f"{names.get(i, 'övrig mark')}{' (startgård)' if i <= n_start else ''}\n"
            for i in range(1, n_named + n_other + 1) if ha[i] > 0), encoding="utf-8")
    placements = load_placements(project) + [dict(pl, position=[pl["position"][0], site.height, pl["position"][2]])
                                             for site, pl in edited]
    obj.write_placeables(maps_dir / "placeables.xml", farm, mill, world, placements, chosen["byggnader"])
    obj.write_fields_xml(maps_dir / "fields.xml", fields)
    obj.patch_map_xml(maps_dir / "map.xml")
    write_moddesc_description(mod_dir / "modDesc.xml", title, cfg_map.get("description", ""), sources)
    vehicle_mods = copy_vehicles(project, maps_dir / "vehicles.xml")       # startgårdens maskiner
    add_mod_dependencies(mod_dir / "modDesc.xml",
                         sorted({p["mod"] for p in placements if p.get("mod")} | vehicle_mods))
    make_overview(project, maps_dir / "overview.png", labels, osm, world, cfg.overview_res)

    missing = [f for f in local_files if not (maps_dir / f).exists()]
    if missing:
        sys.exit(f"Filer som i3d-filen pekar på saknas: {missing}")

    zip_path = project.build / f"{mod_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(mod_dir.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(mod_dir))

    owned_ha = ha[1:n_start + 1].sum()
    print(f"\n{title}: {len(fields)} fält i {n_named + n_other} markområden, terräng {base:.1f}–{real_max:.1f} m ö.h.")
    print(f"Startgård: {start_desc}, {owned_ha:.1f} ha mark"
          + (f", gården där du placerade den ({farm.width:.0f} × {farm.length:.0f} m"
             + ("" if chosen["byggnader"] else ", utan förvalda byggnader") + ")" if chosen["gard"] else ""))
    print(f"Vatten: {sum(m[0].startswith('water') for m in water_meshes)} vattenytor, "
          f"{sum(m[0].startswith('stream') for m in water_meshes)} diken och bäckar")
    print(f"Träd: {len(trees)}" + (f" (varav {len(loose)} utanför skogen)" if loose else "")
          + f". Spannmålsmottagning: {'ja' if mill else 'ingen ledig plats hittades'}")
    if placements:
        print(f"Placerade byggnader och objekt (byggeditorn och spelet): {len(placements)}")
    print(f"Skrev {project.rel(zip_path)} ({zip_path.stat().st_size / 1e6:.1f} MB)")


def load_land(project, world):
    """OSM-data där Lantmäteriets data ersätter det som finns: marktyper från Marktäcke
    (eller Topografi 10), vattendrag, vägar och byggnader från Topografi 10.
    Returnerar (osm-tupeln från load_features, källrader till modDesc)."""
    osm_path = project.raw / "osm.json"
    if not osm_path.exists():
        sys.exit(f"Hittar inte {project.rel(osm_path)}. Kör fetch_osm.py först "
                 f"(python scripts/pipeline.py --map {project.name} --only osm falt).")
    areas, roads, waterways, rail, buildings, places = load_features(osm_path)
    area = world.scaled(2).square()          # dubbel yta för översiktskartan
    lm_sources, osm_parts = [], ["gårdsplaner"]

    def report(what, items):
        counts = {}
        for cls, _ in items:
            counts[cls] = counts.get(cls, 0) + 1
        print(f"  {what}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    if landcover.marktacke_files(project) or landcover.topo_files("mark"):
        lm = landcover.load_marktacke(project, area)
        src = "Marktäcke" if landcover.marktacke_files(project) else "Topografi 10"
        report(f"Marktyper från {src}", lm)
        areas = [a for a in areas if a[0] not in landcover.REPLACES] + lm
        lm_sources.append(f"Marktyper: {src} Nedladdning, vektor")
    else:
        osm_parts.append("marktyper")
    if landcover.has_topo():
        roads = landcover.load_roads(area) + [r for r in roads if r[0] == "gårdsväg/infart"]
        waterways = landcover.load_waterways(area)
        topo_buildings = landcover.load_buildings(area)
        buildings = [g for g, _ in topo_buildings]
        report("Vägar från Topografi 10 (+ OSM:s gårdsvägar)", roads)
        print(f"  Vattendrag från Topografi 10: {len(waterways)}. Byggnader: {len(buildings)}")
        lm_sources.append("Vägar, vattendrag och byggnader: Topografi 10 Nedladdning, vektor")
    else:
        osm_parts += ["vägar", "vattendrag", "byggnader"]
        print("  Vägar, vattendrag och byggnader från OSM (Topografi 10 saknas i data/topografi10/)")
    sources = [f"{s}, © Lantmäteriet, bearbetad, CC BY 4.0." for s in lm_sources]
    sources.append(", ".join(osm_parts).capitalize() + ": © OpenStreetMap-bidragsgivare, ODbL.")
    return (areas, roads, waterways, rail, buildings, places), sources


def add_fields_to_i3d(i3d_path, fields, world, height_at, start_pt, trees, farm, water_meshes=()):
    import xml.etree.ElementTree as ET
    tree = ET.parse(i3d_path)
    root = tree.getroot()
    scene = root.find("Scene")
    uas = root.find("UserAttributes")
    sub, nid = gen_i3d.sub, gen_i3d.nid

    # Startpunkten flyttas till startgården, strax över marken.
    csp = next(tg for tg in scene.iter("TransformGroup") if tg.get("name") == "careerStartPoint")
    x, z = world.xz(start_pt.x, start_pt.y)
    csp.set("translation", f"{x:.1f} {height_at(start_pt.x, start_pt.y) + 1.5:.2f} {z:.1f}")

    fields_id = nid()
    group = sub(scene, "TransformGroup", name="fields", nodeId=fields_id)
    ua = sub(uas, "UserAttribute", nodeId=fields_id)
    sub(ua, "Attribute", name="onCreate", type="scriptCallback", value="FieldUtil.onCreate")
    for i, (geom, _block, _code) in enumerate(fields, 1):
        c = geom.representative_point()
        cx, cz = world.xz(c.x, c.y)
        cy = height_at(c.x, c.y)
        fid = nid()
        field = sub(group, "TransformGroup", name=f"field{i}", translation=f"{cx:.2f} {cy:.2f} {cz:.2f}", nodeId=fid)
        pp = sub(field, "TransformGroup", name="polygonPoints", nodeId=nid())
        for e, n in list(geom.exterior.coords)[:-1]:
            px, pz = world.xz(e, n)
            sub(pp, "TransformGroup", name="p", translation=f"{px - cx:.2f} 0 {pz - cz:.2f}", nodeId=nid())
        sub(field, "TransformGroup", name="nameIndicator", translation="0 0 0", nodeId=nid())
        fua = sub(uas, "UserAttribute", nodeId=fid)
        for nm, ty, val in (("angle", "float", "0"), ("missionAllowed", "boolean", "true"),
                            ("missionOnlyGrass", "boolean", "false"), ("nameIndicatorIndex", "string", "1"),
                            ("polygonIndex", "string", "0"), ("teleportIndicatorIndex", "string", "1")):
            sub(fua, "Attribute", name=nm, type=ty, value=val)
    obj.add_trees(root, trees, world, height_at, nid)
    obj.add_store_spawn(root, farm, world, nid, height_at)
    files_cache = {}
    water.add_to_i3d(root, water_meshes, world, nid, lambda f: obj.add_file(root, f, files_cache))
    ET.indent(root, space="  ")
    tree.write(i3d_path, encoding="iso-8859-1", xml_declaration=True)


def write_farmlands(path, count, price_per_ha, scales, owned=1):
    """Markområde 1..owned ägs från start (startgårdens fält)."""
    rows = [f'        <farmland id="{i}" priceScale="{scales.get(i, 1.0):.2f}" npcName="FARMER"'
            + (' defaultFarmProperty="true"' if i <= owned else "") + " />" for i in range(1, count + 1)]
    path.write_text(
        '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n<map>\n'
        '    <farmlands densityMapFilename="maps/data/infoLayer_farmland.grle" numChannels="8" '
        f'pricePerHa="{price_per_ha:.0f}">\n'
        + "\n".join(rows) + "\n    </farmlands>\n</map>\n", encoding="utf-8")


def info_transform(world, res):
    from rasterio.transform import from_origin
    return from_origin(world.e0 - world.half, world.n0 + world.half, world.size / res, world.size / res)


def no_build_mask(osm, world, res):
    """Spärrat för byggen (placementCollision): vägar, vatten, diken och järnväg."""
    from rasterio.features import rasterize
    areas, roads, waterways, rail = osm[0], osm[1], osm[2], osm[3]
    sq = world.square(-50)
    geoms = [line.buffer(ROAD_STYLE[cls][1] / 2 + 1) for cls, line in roads if line.intersects(sq)]
    geoms += [g for c, g in areas if c == "water" and g.intersects(sq)]
    geoms += [line.buffer(NO_BUILD_WATER) for _, line in waterways if line.intersects(sq)]
    geoms += [line.buffer(3) for line in rail if line.intersects(sq)]
    return rasterize(((g, 1) for g in geoms), out_shape=(res, res), transform=info_transform(world, res),
                     dtype="uint8") > 0


def paint_farmlands(fields, properties, lone_id, farm_box, world, res):
    """Markområdeslagret: fält nummer i på markområde i, fastigheter utan fält (lone_id) som egna
    markområden och resten av varje fastighet till fastighetens närmaste fält. Fastigheterna målas
    som zoner, största först: en fastighets hål målas tomma, så mindre fastigheter i hålen måste
    målas efter. Startgårdens planade yta hör till markområde 1. Mark utanför fastigheterna lämnas 0."""
    farm_img = Image.new("L", (res, res), 0)
    zone_img = Image.new("I", (res, res), 0)
    dfarm, dzone = ImageDraw.Draw(farm_img), ImageDraw.Draw(zone_img)
    zone_of = {k: j + 1 for j, k in enumerate(properties)}               # properties är sorterade största först
    for key in properties:
        draw_polygon(dzone, properties[key], world, res, zone_of[key])
        if key in lone_id:
            draw_polygon(dfarm, properties[key], world, res, lone_id[key])
    for i, (geom, _block, _) in enumerate(fields, 1):
        draw_polygon(dfarm, geom.buffer(FIELD_SHRINK), world, res, i)
    draw_polygon(dfarm, farm_box, world, res, 1)
    farm = np.array(farm_img, dtype=np.uint8)
    if not properties:
        return farm
    zone = np.array(zone_img, dtype=np.int32)
    zone_of_id = np.zeros(256, np.int32)                                    # markområde -> fastighetens zon
    biggest = np.zeros(len(properties) + 1, np.int32)                       # zon -> fastighetens största fält
    for i, (geom, block, _) in sorted(enumerate(fields, 1), key=lambda t: t[1][0].area):
        if block in zone_of:
            zone_of_id[i] = zone_of[block]
            biggest[zone_of[block]] = i                                     # störst sist
    for key, i in lone_id.items():
        zone_of_id[i] = zone_of[key]
    # Resten av fastigheten till dess närmaste fält: först i halv upplösning (snabbare), sedan kanterna.
    small = spread(farm[::2, ::2].copy(), res, zone[::2, ::2], zone_of_id)
    up = np.repeat(np.repeat(small, 2, axis=0), 2, axis=1)[:res, :res]
    take = (farm == 0) & (up > 0) & (zone_of_id[up] == zone)
    farm[take] = up[take]
    farm = spread(farm, 8, zone, zone_of_id)
    rest = (farm == 0) & (biggest[zone] > 0)                                # delar som inte nås: största fältet
    farm[rest] = biggest[zone[rest]]
    return farm


def extend_farmlands(farm, no_build, world, osm):
    """Mark utan fält läggs till närmaste markområde inom FARMLAND_REACH, så att man kan köpa
    och bygga på gårdsplaner, ängar och skogsbryn. Vägar, vatten och tätorter hör inte till blocken
    (fill_farmlands ger dem egna markområden)."""
    from rasterio.features import rasterize
    res = farm.shape[0]
    f = 2                                                   # grövre rutnät för spridningen
    small = spread(farm[::f, ::f].copy(), int(FARMLAND_REACH / (world.size / res * f)))
    grown = np.repeat(np.repeat(small, f, axis=0), f, axis=1)[:res, :res]
    town = [g for c, g in osm[0] if c == "residential"]
    blocked = no_build.copy()
    if town:
        blocked |= rasterize(((g, 1) for g in town), out_shape=farm.shape,
                             transform=info_transform(world, res), dtype="uint8") > 0
    return np.where(farm > 0, farm, np.where(blocked, 0, grown)).astype(np.uint8)


def price_scales(farm, fields, osm, world):
    """Prisfaktor per markområde: ytvägt medel av LAND_PRICE_SCALE för marken i området
    (åker, skog, gårdsplan och tätort, övrigt)."""
    from rasterio.features import rasterize
    res = farm.shape[0]
    tr = info_transform(world, res)
    kind = np.zeros(farm.shape, np.uint8)                   # 0 = övrigt (öppen mark, vägar, vatten)
    for k, geoms in ((1, [g for c, g in osm[0] if c in landcover.FORESTS]),
                     (2, [g for c, g in osm[0] if c in ("farmyard", "residential")]),
                     (3, [g for g, _, _ in fields])):
        if geoms:
            kind[rasterize(((g, 1) for g in geoms), out_shape=farm.shape, transform=tr, dtype="uint8") > 0] = k
    weight = np.array([LAND_PRICE_SCALE[k] for k in ("övrigt", "skog", "tomt", "åker")])[kind]
    sums = np.bincount(farm.ravel(), weights=weight.ravel(), minlength=256)
    counts = np.bincount(farm.ravel(), minlength=256)
    return {i: float(sums[i] / counts[i]) for i in range(1, 256) if counts[i]}


def load_start(project, world):
    """Byggeditorns Start-läge (maps/<namn>/start.json): gårdens mitt (meter från kartans mitt), bredd,
    längd, vridning (grader moturs från öster), om de förvalda byggnaderna ska stå där, och en punkt i
    varje startfält. Punkterna i SWEREF; fälten som innehåller dem blir startgårdens."""
    path = project.dir / "start.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"gard": data.get("gard"), "bredd": float(data.get("bredd") or obj.FARM_SIZE),
            "langd": float(data.get("langd") or obj.FARM_SIZE), "vridning": float(data.get("vridning") or 0),
            "byggnader": data.get("byggnader", True), "plana": data.get("plana", True),
            "falt": [Point(world.e0 + x, world.n0 + y) for x, y in data.get("falt", [])]}


def save_fields_for_editor(path, fields, world, n_start):
    """Fälten från senaste bygget till byggeditorns Start-läge: nummer, gröda och kontur."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([
        {"nr": i, "fruit": (obj.CROP_FRUIT.get(code) or "plöjt").lower(), "ha": round(geom.area / 10_000, 1),
         "start": i <= n_start,
         "poly": [[round(x - world.e0, 1), round(y - world.n0, 1)] for x, y in geom.simplify(1).exterior.coords]}
        for i, (geom, _block, code) in enumerate(fields, 1)]), encoding="utf-8")


def save_farmland_image(path, farm):
    """Markområdena som bild för kontroll (build/<namn>/markomraden.png): en färg per område,
    startgårdens område (1) rött, gränser svarta och områdets nummer i dess största del. Dessutom
    markomraden_kant.png med bara gränser och nummer på genomskinlig botten, för kontrollkartan."""
    rgb = np.random.default_rng(5).integers(90, 230, (256, 3)).astype(np.uint8)
    rgb[0], rgb[1] = (255, 255, 255), (220, 30, 30)
    img = rgb[farm]
    edge = np.zeros(farm.shape, bool)
    edge[1:, :] |= farm[1:, :] != farm[:-1, :]
    edge[:, 1:] |= farm[:, 1:] != farm[:, :-1]
    img[edge] = 0
    im = Image.fromarray(img)
    rgba = np.zeros(farm.shape + (4,), np.uint8)
    rgba[farm == 1] = (220, 30, 30, 70)
    rgba[edge] = (255, 255, 0, 255)
    kant = Image.fromarray(rgba, "RGBA")
    from PIL import ImageFont
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:                                       # äldre Pillow
        font = ImageFont.load_default()
    draws = (ImageDraw.Draw(im), ImageDraw.Draw(kant))
    step = 8                                                # sök platsen för numret i ett glesare rutnät
    small = farm[::step, ::step]
    depth = np.zeros(small.shape, np.int32)                 # avstånd in från områdets kant, i steg
    for _ in range(small.shape[0] // 2):
        same = small > 0
        same[1:, :] &= small[1:, :] == small[:-1, :]
        same[:-1, :] &= small[:-1, :] == small[1:, :]
        same[:, 1:] &= small[:, 1:] == small[:, :-1]
        same[:, :-1] &= small[:, :-1] == small[:, 1:]
        if not same.any():
            break
        depth += same
        small = np.where(same, small, 0)
    for i in np.unique(farm[::step, ::step]):
        if i == 0:
            continue
        d = np.where(farm[::step, ::step] == i, depth, -1)
        y, x = np.unravel_index(np.argmax(d), d.shape)
        for draw in draws:
            draw.text((x * step, y * step), str(int(i)), fill=(0, 0, 0), font=font, anchor="mm",
                      stroke_width=3, stroke_fill=(255, 255, 255))
    im.save(path)
    kant.save(path.with_name("markomraden_kant.png"))


def spread(arr, steps, zone=None, zone_of_id=None):
    """Fyller nollor med grannens markområde, en pixel per steg (åt fyra håll). Med zone (zon per pixel)
    och zone_of_id (zon per markområde) sprids ett markområde bara inom sin egen zon."""
    for _ in range(steps):
        empty = arr == 0
        if zone is not None:
            empty &= zone > 0
        if not empty.any():
            break
        before = int(empty.sum())
        for src, dst in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                         ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                         ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                         ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            nb = arr[src]
            take = empty[dst] & (nb > 0)
            if zone is not None:
                take &= zone_of_id[nb] == zone[dst]
            arr[dst][take] = nb[take]
            empty[dst] &= ~take
        if int(empty.sum()) == before:                      # inget mer att nå
            break
    return arr


def fill_farmlands(farm, world, osm, first_id, max_id=254):
    """Mark som ännu saknar markområde (skog långt från fälten, tätorter, vägar och vatten) delas i
    skiften längs naturliga gränser, som verkliga fastigheter ofta följer: vägar, vattendrag och
    skogs-, tätorts- och sjökanter. Stora skiften delas dessutom i rutor om OTHER_LAND_CELL m.
    Spelet låter alla bygga och fälla träd på mark utan markområde, så hela kartan måste täckas.
    Skiften under MIN_OTHER_HA, och de minsta om det blir fler än lagret rymmer, går till närmaste
    markområde. Byggen på vägar och vatten stoppas ändå av placementCollision.
    Returnerar (lagret, antal nya markområden)."""
    from rasterio.features import rasterize, shapes
    res = farm.shape[0]
    px = world.size / res
    out = farm.copy()
    empty = out == 0
    if not empty.any():
        return out, 0
    tr = info_transform(world, res)
    areas, roads, waterways = osm[0], osm[1], osm[2]
    sq = world.square(-50)
    edges = [ln for _, ln in roads + waterways if ln.intersects(sq)]
    edges += [g.boundary for c, g in areas if c in landcover.FORESTS + ("residential", "water") and g.intersects(sq)]
    barrier = rasterize(((g, 1) for g in edges), out_shape=out.shape, transform=tr, all_touched=True,
                        dtype="uint8") > 0 if edges else np.zeros(out.shape, bool)
    k = max(1, int(round(OTHER_LAND_CELL / px)))
    yy, xx = np.indices(out.shape)
    cell = ((yy // k) * (-(-res // k)) + xx // k).astype(np.int32)
    parts = [(shape(geom), v) for geom, v in shapes(cell, mask=empty & ~barrier, connectivity=4, transform=tr)]
    parts = sorted((g for g, _ in parts if g.area / 10_000 >= MIN_OTHER_HA), key=lambda g: -g.area)
    parts = parts[:max_id - first_id + 1]
    if parts:
        ids = rasterize(((g, first_id + i) for i, g in enumerate(parts)), out_shape=out.shape, transform=tr,
                        dtype="uint8")
        out = np.where(empty, ids, out).astype(np.uint8)
    return spread(out, 2 * res), len(parts)


def load_editor_buildings(project, world):
    """Byggnader från byggeditor.py (maps/<namn>/byggnader.json): marken planas under varje
    byggnad, och den blir en placeable i kartan. Koordinaterna är meter från kartans mitt
    (x österut, y norrut), rot är spelets y-rotation i grader."""
    path = project.dir / "byggnader.json"
    if not path.exists():
        return []
    out = []
    for i, b in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        site = obj.Site(f"byggnad{i}", world.e0 + b["x"], world.n0 + b["y"], max(b["w"], b["l"]) + 2)
        out.append((site, {"filename": b["file"], "position": [b["x"], 0.0, -b["y"]],
                           "rotation": [0.0, b["rot"], 0.0], "mod": b.get("mod")}))
    print(f"  Byggnader från byggeditorn: {len(out)}")
    return out


def load_placements(project):
    """Objekt från import_savegame.py: [{filename, position, rotation, mod}]."""
    path = project.dir / "placeringar.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def fruit_value(layer, state):
    """Värdet i densityMap_fruits för ett växtlager och tillstånd (nummer, eller namn ur DECO_STATES)."""
    names = [t["name"] for L in gen_i3d.FOLIAGE["layers"] if L["attrs"].get("numTypeIndexChannels") == "5"
             for t in L["types"]]
    if isinstance(state, str):
        state = DECO_STATES[layer].index(state) + 1
    return (names.index(layer) + 1) | (state << 5)


def patches(shape, res, world, mix, layer, seed):
    """Växter i fläckar (PATCH m) efter vikterna i mix, som värden i densityMap_fruits (0 = bar mark).
    layer "decoBush" ger värdena för buskarnas eget lager."""
    rng = np.random.default_rng(seed)
    cell = max(1, int(round(PATCH * res / world.size)))
    n = -(-shape[0] // cell)
    weights = np.array([w for _, w in mix], float)
    pick = rng.choice(len(mix), (n, n), p=weights / weights.sum())
    value = (lambda st: BUSH_STATES.index(st) + 1) if layer == "decoBush" else (lambda st: fruit_value(layer, st))
    lut = np.array([value(st) if st else 0 for st, _ in mix], np.uint16)
    out = np.repeat(np.repeat(lut[pick], cell, axis=0), cell, axis=1)[:shape[0], :shape[1]]
    out[rng.integers(0, 100, shape, dtype=np.uint8) < 15] = 0   # glesare i fläckarna
    return out


def paint_bushes(path, areas, world, res):
    """Buskar i densityMap_groundFoliage: blåbärsris i barrskogen, buskar och hassel i skogskanterna."""
    sq = world.square(-50)
    conifer = [g for c, g in areas if c == "barrskog" and g.intersects(sq)]
    forests = [g for c, g in areas if c in landcover.FORESTS and g.intersects(sq)]
    bush = np.zeros((res, res), np.uint16)
    inside = mask_of(conifer, world, res)
    bush[inside] = patches(bush.shape, res, world, BLUEBERRY, "decoBush", 31)[inside]
    edge = mask_of(forests, world, res) & ~mask_of([g.buffer(-BUSH_EDGE) for g in forests], world, res)
    bush[edge] = patches(bush.shape, res, world, EDGE_BUSHES, "decoBush", 32)[edge]
    binfmt.paint_gdm(str(path), res, bush, 4, 1, 0)


def paint_vegetation(path, fields, labels, lawns, roads, world, res, waterways=(), water=()):
    """Växtligheten i densityMap_fruits: grödor på fälten (skördeklara, som fields.xml), gräs på öppen
    mark, örter och blommor på vägrenarna, kaveldun längs vattnet, skogsväxter och ris i skogen och
    kortare gräs på gårdsplanens gräsytor."""
    veg = np.zeros((res, res), np.uint16)
    f = res // labels.shape[0]

    def ground(name):
        return np.repeat(np.repeat(labels == GROUND_NAMES.index(name), f, axis=0), f, axis=1)
    grass = ground("grass01")
    veg[grass] = fruit_value(*OPEN_GRASS)
    sq = world.square(-50)
    verge = grass & mask_of([line.buffer(ROAD_STYLE[cls][1] / 2 + VERGE_WIDTH) for cls, line in roads
                             if line.intersects(sq)], world, res)
    veg[verge] = patches(veg.shape, res, world, VERGE, "decoFoliage", 21)[verge]
    forest = ground("forestLeaves01")
    veg[forest] = patches(veg.shape, res, world, FOREST_FLOOR, "forestPlants", 22)[forest]
    shore = [ln.buffer(REED_WIDTH) for _, ln in waterways if ln.intersects(sq)]
    shore += [g.boundary.buffer(REED_WIDTH) for g in water if g.intersects(sq)]
    reeds = (grass | forest) & mask_of(shore, world, res)
    veg[reeds] = patches(veg.shape, res, world, REEDS, "waterPlants", 23)[reeds]
    veg[grass & mask_of(lawns, world, res)] = fruit_value(*LAWN_GRASS)
    crops = [c for c in CROP_STATE]
    img = Image.new("L", (res, res), 0)
    draw = ImageDraw.Draw(img)
    for geom, _block, code in fields:
        fruit = obj.CROP_FRUIT.get(code)
        draw_polygon(draw, geom.buffer(-1), world, res, crops.index(fruit) + 1 if fruit in CROP_STATE else 255)
    codes = np.array(img)
    veg[codes > 0] = 0                                      # fält utan känd gröda: plöjda, ingen växtlighet
    for k, fruit in enumerate(crops, 1):
        veg[codes == k] = fruit_value(*CROP_STATE[fruit])
    binfmt.paint_gdm(str(path), res, veg, 10, 2, 5, range_splits=(5,))


def mask_of(geoms, world, res):
    """Rutnät (res × res, norr uppåt) som är sant inne i geometrierna."""
    from rasterio.features import rasterize
    geoms = [g for g in geoms if not g.is_empty]            # små ytor kan bli tomma efter negativ buffert
    if not geoms:
        return np.zeros((res, res), bool)
    return rasterize(((g, 1) for g in geoms), out_shape=(res, res), transform=info_transform(world, res),
                     dtype="uint8") > 0


def vehicle_points(project, world):
    """Startgårdens maskiner (maps/<namn>/fordon.xml) som punkter i SWEREF."""
    import xml.etree.ElementTree as ET
    src = project.dir / "fordon.xml"
    if not src.exists():
        return []
    out = []
    for c in ET.parse(src).getroot().iter("component"):
        x, _y, z = (float(v) for v in c.get("position", "0 0 0").split())
        out.append((world.e0 + x, world.n0 - z))
    return out


def copy_vehicles(project, path):
    """Startgårdens maskiner från import_savegame.py --fordon (maps/<namn>/fordon.xml) som kartans
    vehicles.xml. Returnerar moddarna de kommer från."""
    import re
    src = project.dir / "fordon.xml"
    if not src.exists():
        return set()
    text = src.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    n = text.count("<vehicle ")
    print(f"  Startgårdens maskiner: {n} (från {project.rel(src)})")
    return set(re.findall(r'filename="\$moddir\$([^/\\"]+)[/\\]', text)) | set(re.findall(r'modName="([^"]+)"', text))


def add_mod_dependencies(path, mods):
    """Moddar som kartans placeringar kommer från måste vara installerade."""
    if not mods:
        return
    deps = "    <dependencies>\n" + "".join(f"        <dependency>{m}</dependency>\n" for m in mods) + "    </dependencies>\n"
    s = path.read_text(encoding="utf-8")
    path.write_text(s.replace("</modDesc>", deps + "</modDesc>"), encoding="utf-8")


def write_moddesc_description(path, title, description, sources):
    import html
    description = description.strip()
    if description and not description.endswith("."):
        description += "."
    text = (f"{title}: verklig svensk landsbygd. {description} "
            "Höjddata: Markhöjdmodell Nedladdning, grid 1+, © Lantmäteriet, bearbetad, CC BY 4.0. "
            "Fält: jordbruksskiften, © Jordbruksverket, bearbetad. "
            + " ".join(sources) + " Kartgrund: fs25-empty-map (MIT).")
    s = path.read_text(encoding="utf-8")
    start, end = s.index("<description>"), s.index("</description>") + len("</description>")
    s = s[:start] + f"<description><en>{html.escape(text)}</en></description>" + s[end:]
    s = s.replace("<author>fs25-empty-map</author>", "<author>FS_sweden_map</author>")
    path.write_text(s, encoding="utf-8")


def make_overview(project, path, labels, osm, world, res):
    """Översiktskartan. Spelet lägger bilden över dubbla kartytan med kartan i mitten,
    så omgivningen ritas från skiften, marktyper och vägar utanför kartan."""
    palette = np.array([OVERVIEW_COLORS[name] for name, _ in GROUND], dtype=np.uint8)
    big = world.scaled(2)
    img = Image.fromarray(palette[ground_labels(osm, big, surrounding_fields(project, big), res)])
    inner = Image.fromarray(palette[labels]).resize((res // 2, res // 2), Image.NEAREST)
    img.paste(inner, (res // 4, res // 4))
    d = ImageDraw.Draw(img)
    world = big
    areas, _roads, waterways, _rail, buildings, _places = osm
    for cls, geom in areas:
        if cls == "water":
            draw_polygon(d, geom, world, res, (88, 130, 170), (88, 130, 170))
    for kind, line in waterways:
        if kind in ("river", "stream", "canal", "vattendrag"):
            d.line([world.px(x, y, res) for x, y in line.coords], fill=(88, 130, 170),
                   width=max(1, int(round((8 if kind == "river" else 2) * res / world.size))))
    for b in buildings:
        draw_polygon(d, b, world, res, (110, 52, 44))
    img.save(path)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--floor", type=float, default=10.0,
                        help="meter mellan spelets nollnivå och kartans lägsta punkt")
    args = parser.parse_args()
    build(open_map(args.map), args)


if __name__ == "__main__":
    main()
