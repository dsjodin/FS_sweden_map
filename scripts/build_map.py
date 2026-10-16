#!/usr/bin/env python3
"""Bygger en färdig FS25-kartmodd från våra data, utan MapToPlay.

Grunden är fs25-empty-map (third_party/fs25_empty_map), som skriver alla
filer en FS25-karta behöver. Ovanpå den lägger vi:

- terräng från Lantmäteriets höjdmodell (data/<namn>/lm/hojd/dtm_area.tif)
- fält från Jordbruksverkets skiften: fältnoder i i3d-filen, kultiverad
  åkerjord i densityMap_ground
- farmlands = jordbruksblock: varje block som har fält blir ett köpbart
  markområde. Blocket närmast startpunkten ägs från start.
- marktexturer från OSM: asfalt, grus, skogsmark, åkerjord och gräs
- översiktskarta (PDA) ritad från samma data
- träd i OSM:s skogar, startgård med gårdshus, maskinhall och silo, en
  spannmålsmottagning och plats för köpta fordon (scripts/fs25_objects.py)
- fältens grödor vid nytt spel från skiftenas grödkoder (maps/fields.xml)

Kräver: fetch_osm.py, fetch_fields.py och fetch_heightmap.py för kartan.

Resultat:
    build/<namn>/<mod_name>/        modmappen
    build/<namn>/<mod_name>.zip     att lägga i spelets mods-mapp

Användning:
    python scripts/build_map.py [--map tysslinge] [--floor 10]
"""
import argparse
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

# Marklager (namn i spelets standarduppsättning) i prioritetsordning: senare vinner.
GROUND = [
    ("grass01", "gräs"),
    ("forestLeaves01", "skog"),
    ("gravelSmall01", "gårdsplan"),
    ("mudDark01", "åker"),
    ("gravel01", "grusväg"),
    ("asphalt01", "asfalt"),
]
ROAD_STYLE = {  # vägklass från analyze_area -> (marklager, bredd i meter)
    "motorväg/riksväg": ("asphalt01", 12),
    "länsväg": ("asphalt01", 7),
    "småväg": ("asphalt01", 5),
    "grusväg/brukningsväg": ("gravel01", 3.5),
    "gårdsväg/infart": ("gravel01", 3),
}
MEADOW_CODES = {52, 53}      # betesmark och slåtteräng blir inte fält (antaget, se make_osm_fields.py)
GROUND_CULTIVATED = 2        # terrainDetail groundType 2 = kultiverad
FIELD_SHRINK = 1.5           # m, ger renar mellan skiften
FIELD_EDGE = 5               # m, fält hålls så här långt från kartkanten
MIN_FIELD_HA = 0.5
ROAD_MARGIN = 1.5            # m fri kant mellan vägkant och fält
WATER_CUT = {"river": 8, "canal": 4, "stream": 3, "ditch": 1.5, "drain": 1.5}  # halv bredd inkl. kant, m
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


def obstacles(roads, waterways, world):
    """Vägar och vattendrag som buffrade ytor, att skära bort ur fälten."""
    sq = world.square(-50)
    parts = []
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
        if p.get("grdkod_mar") in MEADOW_CODES:
            continue
        geom = shape(f["geometry"]).buffer(0).buffer(-FIELD_SHRINK, join_style="mitre").intersection(inner)
        if geom.intersects(cut):
            # Skär bort vägar och vatten, och rensa bort remsor smalare än 4 m längs kanterna.
            geom = geom.difference(cut).buffer(-2, join_style="mitre").buffer(2, join_style="mitre")
        geom = geom.simplify(1.0, preserve_topology=True)
        parts = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
        for part in parts:
            if part.area / 10_000 >= MIN_FIELD_HA:
                fields.append((part, str(p.get("blockid")), p.get("grdkod_mar")))
    fields.sort(key=lambda t: (-t[0].centroid.y, t[0].centroid.x))  # nummer från nordväst, rad för rad
    return fields


def ground_labels(osm, world, fields, res):
    """Etikettbild (index i GROUND) för marklagren, 1 pixel per meter."""
    areas, roads = osm[0], osm[1]
    img = Image.new("L", (res, res), 0)
    d = ImageDraw.Draw(img)
    idx = {name: i for i, (name, _) in enumerate(GROUND)}
    sq = world.square(-50)
    for cls, geom in areas:
        if not geom.intersects(sq):
            continue
        if cls == "forest":
            draw_polygon(d, geom, world, res, idx["forestLeaves01"], idx["grass01"])
        elif cls in ("farmyard", "residential"):
            draw_polygon(d, geom, world, res, idx["gravelSmall01"], idx["grass01"])
    for geom, _, _ in fields:
        draw_polygon(d, geom.buffer(FIELD_SHRINK), world, res, idx["mudDark01"])
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
    osm = load_features(project.raw / "osm.json")
    fields = load_fields(project, world, obstacles(osm[1], osm[2], world))
    labels = ground_labels(osm, world, fields, cfg.weight_res)
    cut = obstacles(osm[1], osm[2], world)

    # Farmlands: ett per jordbruksblock med fält. Startgården = blocket närmast startpunkten.
    start = cfg_map.get("start") or cfg_map["center"]
    se, sn = to_sweref(start["lon"], start["lat"])
    start_pt = Point(se, sn)
    blocks = {}
    for geom, block, _ in fields:
        blocks.setdefault(block, []).append(geom)
    start_block = min(blocks, key=lambda b: unary_union(blocks[b]).distance(start_pt))
    order = [start_block] + sorted(b for b in blocks if b != start_block)
    if len(order) > 254:
        sys.exit(f"{len(order)} block med fält, men farmland-lagret rymmer högst 254.")
    farmland_id = {b: i + 1 for i, b in enumerate(order)}

    print("Gård, spannmålsmottagning och planering ...")
    areas, roads, _ww, _rail, buildings, _pl = osm
    field_union = unary_union([g.buffer(3) for g, _, _ in fields])
    inner = world.square(150)
    farm = obj.farm_site(start_pt, [g for c, g in areas if c == "farmyard"], unary_union([field_union, cut]), inner)
    if farm is None:
        sys.exit("Hittade ingen ledig plats för startgården nära startpunkten.")
    mill_blocked = unary_union([field_union, cut, farm.box.buffer(200)]
                               + [g for c, g in areas if c in ("forest", "water", "residential")] + buildings)
    mill = obj.mill_site(roads, farm, mill_blocked, inner)
    sites = [farm] + ([mill] if mill else [])
    obj.flatten(game, world, sites)
    if game.max() > gen_i3d.HEIGHT_SCALE or game.min() < 0:
        sys.exit("Höjderna hamnar utanför heightScale efter planering.")
    dem = np.round(game / gen_i3d.HEIGHT_SCALE * 65535).astype(np.uint16)
    height_at = height_sampler(game, world)
    idx_yard = [name for name, _ in GROUND].index("gravelSmall01")
    for s_ in sites:
        x0, y0 = world.px(s_.e - s_.size / 2, s_.n + s_.size / 2, cfg.weight_res)
        x1, y1 = world.px(s_.e + s_.size / 2, s_.n - s_.size / 2, cfg.weight_res)
        labels[int(y0):int(y1), int(x0):int(x1)] = idx_yard
    spawn_pt = Point(farm.e - 15, farm.n + 38)   # framför gårdshuset
    trees = obj.tree_points([g for c, g in areas if c == "forest"],
                            unary_union([cut, field_union] + [s_.box.buffer(10) for s_ in sites]), world.square(5))

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
    add_fields_to_i3d(i3d_path, fields, world, height_at, spawn_pt, trees, farm)

    # Data: fs25-empty-map skriver tomma lager, sedan ersätter vi med våra.
    gen_data.build(cfg, str(data_dir))
    (data_dir / "grass_weight.png").unlink(missing_ok=True)  # ersätts av grass01_weight.png
    Image.fromarray(dem).save(data_dir / "map_dem.png")
    for i, (name, _) in enumerate(GROUND):
        Image.fromarray(np.where(labels == i, 255, 0).astype(np.uint8)).save(data_dir / f"{name}_weight.png")

    N = cfg.density_res
    ground = Image.new("L", (N, N), 0)
    farm_img = Image.new("L", (cfg.il_res["farmland"],) * 2, 0)
    dg, dfarm = ImageDraw.Draw(ground), ImageDraw.Draw(farm_img)
    for geom, block, _ in fields:
        draw_polygon(dg, geom.buffer(-1), world, N, GROUND_CULTIVATED)        # arbetsyta 1 m in från kanten
        draw_polygon(dfarm, geom.buffer(FIELD_SHRINK), world, farm_img.width, farmland_id[block])
    draw_polygon(dfarm, farm.box, world, farm_img.width, 1)               # gården hör till startgården
    binfmt.paint_gdm(str(data_dir / "densityMap_ground.gdm"), N, np.array(ground, dtype=np.uint16), 11, 1, 0)
    binfmt.paint_grle(str(data_dir / "infoLayer_farmland.grle"), np.array(farm_img, dtype=np.uint8))

    # Konfiguration: fs25-empty-map:s filer, sedan våra farmlands, modDesc-text och översiktskarta.
    gen_configs.build(cfg, str(mod_dir), str(maps_dir))
    write_farmlands(maps_dir / "farmlands.xml", order)
    obj.write_placeables(maps_dir / "placeables.xml", farm, mill, world)
    obj.write_fields_xml(maps_dir / "fields.xml", fields)
    obj.patch_map_xml(maps_dir / "map.xml")
    write_moddesc_description(mod_dir / "modDesc.xml", title, cfg_map.get("description", ""))
    make_overview(maps_dir / "overview.png", labels, osm, world, cfg.overview_res)

    missing = [f for f in local_files if not (maps_dir / f).exists()]
    if missing:
        sys.exit(f"Filer som i3d-filen pekar på saknas: {missing}")

    zip_path = project.build / f"{mod_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(mod_dir.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(mod_dir))

    owned_ha = sum(g.area for g in blocks[start_block]) / 10_000
    print(f"\n{title}: {len(fields)} fält i {len(order)} farmlands, terräng {base:.1f}–{real_max:.1f} m ö.h.")
    print(f"Startgård: block {start_block} med {len(blocks[start_block])} fält, {owned_ha:.1f} ha")
    print(f"Träd: {len(trees)}. Spannmålsmottagning: {'ja' if mill else 'ingen ledig plats hittades'}")
    print(f"Skrev {project.rel(zip_path)} ({zip_path.stat().st_size / 1e6:.1f} MB)")


def add_fields_to_i3d(i3d_path, fields, world, height_at, start_pt, trees, farm):
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
    obj.add_store_spawn(root, farm, world, nid)
    ET.indent(root, space="  ")
    tree.write(i3d_path, encoding="iso-8859-1", xml_declaration=True)


def write_farmlands(path, order):
    rows = [f'        <farmland id="1" priceScale="1" npcName="FARMER" defaultFarmProperty="true" />']
    rows += [f'        <farmland id="{i}" priceScale="1" npcName="FARMER" />' for i in range(2, len(order) + 1)]
    path.write_text(
        '<?xml version="1.0" encoding="utf-8" standalone="no" ?>\n<map>\n'
        '    <farmlands densityMapFilename="maps/data/infoLayer_farmland.grle" numChannels="8" pricePerHa="60000">\n'
        + "\n".join(rows) + "\n    </farmlands>\n</map>\n", encoding="utf-8")


def write_moddesc_description(path, title, description):
    import html
    description = description.strip()
    if description and not description.endswith("."):
        description += "."
    text = (f"{title}: verklig svensk landsbygd. {description} "
            "Höjddata: Markhöjdmodell Nedladdning, grid 1+, © Lantmäteriet, bearbetad, CC BY 4.0. "
            "Fält: jordbruksskiften, © Jordbruksverket, bearbetad. "
            "Vägar och skog: © OpenStreetMap-bidragsgivare, ODbL. "
            "Kartgrund: fs25-empty-map (MIT).")
    s = path.read_text(encoding="utf-8")
    start, end = s.index("<description>"), s.index("</description>") + len("</description>")
    s = s[:start] + f"<description><en>{html.escape(text)}</en></description>" + s[end:]
    s = s.replace("<author>fs25-empty-map</author>", "<author>FS_sweden_map</author>")
    path.write_text(s, encoding="utf-8")


def make_overview(path, labels, osm, world, res):
    palette = np.array([OVERVIEW_COLORS[name] for name, _ in GROUND], dtype=np.uint8)
    img = Image.fromarray(palette[labels]).resize((res, res), Image.NEAREST)
    d = ImageDraw.Draw(img)
    areas, _roads, waterways, _rail, buildings, _places = osm
    for cls, geom in areas:
        if cls == "water":
            draw_polygon(d, geom, world, res, (88, 130, 170), (88, 130, 170))
    for kind, line in waterways:
        if kind in ("river", "stream", "canal"):
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
