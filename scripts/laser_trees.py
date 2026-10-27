#!/usr/bin/env python3
"""Träd ur Lantmäteriets laserdata (Laserdata Skog, CC BY 4.0).

Laserskanningen mäter höjden på allt som står på marken. Höjd över mark får
vi genom att dra av markhöjdmodellen. Allt som är 2,5–45 m högt och inte en
byggnad räknas som trädkrona. Det fungerar oavsett årstid och ger:

- trädkronor i hela kartan, också utanför skogen: åkerholmar, trädrader längs
  diken och åar, alléer och gårdsträd
- var Marktäckes skogar faktiskt har träd (kalhyggen och gläntor blir tomma)
- trädens höjd, så att låga träd blir unga träd i spelet

Laserdatan är COPC-filer på upp till några GB per 10×10 km-ruta, men bara
kartans område läses över nätet (HTTP Range).

Resultat:
    data/<namn>/lm/laser/krontak.tif   höjd över mark (m) per 2×2 m, 0 = ingen krona
    data/<namn>/lm/trad.json           träd utanför skogen [[e, n, höjd], ...], läses av build_map.py

Kräver behörighet till Laserdata Nedladdning, skog på Geotorget (LM_USER och
LM_PASSWORD) och höjdmodellen (fetch_heightmap.py).

Användning:
    python scripts/laser_trees.py [--map tysslinge]
    python scripts/laser_trees.py --map tysslinge --hamta-om     läs laserdatan på nytt
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import numpy as np
import rasterio
import shapely
from PIL import Image, ImageFilter
from pyproj import Transformer
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from shapely.geometry import shape

from area import add_map_argument, open_map

STAC_SEARCH = "https://api.lantmateriet.se/stac-hojd/v1/search"
COLLECTION = "dsm-skoglig-copc"
CELL = 2.0               # m per cell i krontaket
MIN_H, MAX_H = 2.5, 45.0  # m över mark som räknas som trädkrona
SKIP_CLASSES = {2, 7, 9, 18}   # mark, lågt brus, vatten, högt brus
MIN_CROWN = 16.0         # m², mindre fläckar räknas som brus (ledningar, enstaka träffar)
TREE_SPACING = 7.0       # m mellan träd i en trädgrupp
MARGIN = 20.0            # m utanför kartrutan
to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def search(bounds):
    lon0, lat0 = to_wgs(bounds[0], bounds[1])
    lon1, lat1 = to_wgs(bounds[2], bounds[3])
    url = STAC_SEARCH + "?" + urllib.parse.urlencode(
        {"collections": COLLECTION, "bbox": f"{lon0},{lat0},{lon1},{lat1}", "limit": 100})
    with urllib.request.urlopen(url, timeout=60) as resp:
        items = json.load(resp)["features"]
    return [(f["id"], f["properties"]["proj:bbox"], f["assets"]["data"]["href"]) for f in items]


def read_points(href, bounds, user, password):
    """x, y, z, klass för punkterna inom bounds ur en COPC-fil över HTTP."""
    import laspy  # pip install "laspy[lazrs]" requests
    import laspy.copc as copc

    orig = copc.requests_retry_session

    def with_auth(*a, **k):           # laspy:s HTTP-trådar skapar egna sessioner
        s = orig(*a, **k)
        s.auth = (user, password)
        return s

    copc.requests_retry_session = with_auth
    try:
        with laspy.CopcReader.open(href) as reader:
            b = laspy.copc.Bounds(mins=np.array([bounds[0], bounds[1]]), maxs=np.array([bounds[2], bounds[3]]))
            pts = reader.query(bounds=b)
    finally:
        copc.requests_retry_session = orig
    return np.asarray(pts.x), np.asarray(pts.y), np.asarray(pts.z), np.asarray(pts.classification)


def canopy_height(x, y, z, cls, ground, bounds):
    """Högsta höjd över mark per cell. ground(x, y) ger markhöjden."""
    x0, y0, x1, y1 = bounds
    nx, ny = int(round((x1 - x0) / CELL)), int(round((y1 - y0) / CELL))
    keep = ~np.isin(cls, list(SKIP_CLASSES)) & (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    x, y, z = x[keep], y[keep], z[keep]
    hag = z - ground(x, y)
    ok = (hag >= MIN_H) & (hag <= MAX_H)
    col = np.clip(((x[ok] - x0) / CELL).astype(int), 0, nx - 1)
    row = np.clip(((y1 - y[ok]) / CELL).astype(int), 0, ny - 1)
    chm = np.zeros(ny * nx, np.float32)
    np.maximum.at(chm, row * nx + col, hag[ok].astype(np.float32))
    return chm.reshape(ny, nx)


def ground_sampler(dtm_path):
    src = rasterio.open(dtm_path)
    data = src.read(1)
    inv = ~src.transform

    def ground(x, y):
        c, r = inv * (x, y)
        r = np.clip(r.astype(int), 0, data.shape[0] - 1)
        c = np.clip(c.astype(int), 0, data.shape[1] - 1)
        return data[r, c]

    return ground


def crown_mask(chm, blocked):
    """Kronor: celler med höjd, glapp mellan glesa laserträffar fyllda, brus bort."""
    m = Image.fromarray(((chm > 0) & ~blocked).astype(np.uint8) * 255)
    m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))   # stängning: fyll glapp
    return (np.array(m) > 0) & ~blocked


def tree_points(mask, chm, transform):
    """Träd med cirka TREE_SPACING mellanrum i varje krona, med kronans höjd där."""
    hmax = np.array(Image.fromarray(chm).filter(ImageFilter.MaxFilter(3)))   # högsta höjd inom 3 celler
    inv = ~transform
    out = []
    for geom, v in shapes(mask.astype(np.uint8), mask=mask, transform=transform):
        crown = shape(geom)
        if v != 1 or crown.area < MIN_CROWN:
            continue
        minx, miny, maxx, maxy = crown.bounds
        ge, gn = np.meshgrid(np.arange(minx + TREE_SPACING / 2, maxx, TREE_SPACING),
                             np.arange(miny + TREE_SPACING / 2, maxy, TREE_SPACING))
        ge, gn = ge.ravel(), gn.ravel()
        inside = shapely.contains_xy(crown, ge, gn)
        ge, gn = ge[inside], gn[inside]
        if ge.size == 0:                       # liten krona: ett träd mitt i
            p = crown.representative_point()
            ge, gn = np.array([p.x]), np.array([p.y])
        c, r = inv * (ge, gn)
        h = hmax[np.clip(r.astype(int), 0, chm.shape[0] - 1), np.clip(c.astype(int), 0, chm.shape[1] - 1)]
        out += [[round(float(e), 1), round(float(n), 1), round(float(hh), 1)] for e, n, hh in zip(ge, gn, h) if hh > 0]
    return out


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--hamta-om", action="store_true", help="läs laserdatan på nytt även om krontaket finns")
    args = parser.parse_args()
    project = open_map(args.map)

    import build_map as bm     # efter argumenten: build_map läser in fs25-empty-map
    world = bm.World(project)
    x0, y0, x1, y1 = world.square(-MARGIN).bounds
    transform = from_origin(x0, y1, CELL, CELL)
    out_dir = project.lm / "laser"
    chm_path = out_dir / "krontak.tif"

    if args.hamta_om or not chm_path.exists():
        dtm = project.lm / "hojd" / "dtm_area.tif"
        if not dtm.exists():
            sys.exit(f"Hittar inte {project.rel(dtm)}. Kör fetch_heightmap.py först.")
        user, password = os.environ.get("LM_USER"), os.environ.get("LM_PASSWORD")
        if not user or not password:
            sys.exit("Ange Geotorget-kontot i LM_USER och LM_PASSWORD.")
        ground = ground_sampler(dtm)
        tiles = search((x0, y0, x1, y1))
        print(f"{len(tiles)} laserrutor berör kartan")
        chm = None
        for tile_id, (tx0, ty0, tx1, ty1), href in tiles:
            b = (max(x0, tx0), max(y0, ty0), min(x1, tx1), min(y1, ty1))
            if b[0] >= b[2] or b[1] >= b[3]:
                continue
            print(f"  läser {tile_id} ({(b[2] - b[0]) / 1000:.1f}×{(b[3] - b[1]) / 1000:.1f} km) ...", flush=True)
            try:
                x, y, z, cls = read_points(href, b, user, password)
            except Exception as exc:   # noqa: BLE001 - visa felet och fortsätt inte
                sys.exit(f"Kunde inte läsa {href}: {exc}\nHar kontot behörighet till Laserdata Nedladdning, skog?")
            print(f"    {len(x):,} punkter".replace(",", " "))
            part = canopy_height(x, y, z, cls, ground, (x0, y0, x1, y1))
            chm = part if chm is None else np.maximum(chm, part)   # rutor kan överlappa
        if chm is None:
            sys.exit("Ingen laserdata täcker kartan.")
        out_dir.mkdir(parents=True, exist_ok=True)
        with rasterio.open(chm_path, "w", driver="GTiff", width=chm.shape[1], height=chm.shape[0], count=1,
                           dtype="float32", crs="EPSG:3006", transform=transform, compress="deflate") as dst:
            dst.write(chm, 1)
        print(f"Sparade {project.rel(chm_path)}")
    with rasterio.open(chm_path) as src:
        chm = src.read(1)

    print("Kronor utanför skogen ...")
    osm, _ = bm.load_land(project, world)
    areas, roads, waterways, _rail, buildings, _pl = osm
    cut = bm.obstacles(roads, waterways, world, areas)
    fields = [g for g, _, _ in bm.load_fields(project, world, cut)]
    forest = [g for c, g in areas if c == "forest"]
    shp = chm.shape

    def burn(geoms):
        geoms = [g for g in geoms if not g.is_empty]
        if not geoms:
            return np.zeros(shp, bool)
        return rasterize(((g, 1) for g in geoms), out_shape=shp, transform=transform, dtype="uint8") > 0

    blocked = burn([b.buffer(2) for b in buildings] + forest + [g.buffer(-1) for g in fields])
    mask = crown_mask(chm, blocked)
    points = tree_points(mask, chm, transform)

    in_forest = burn(forest)
    cover = ((chm > 0) & in_forest).sum() / max(in_forest.sum(), 1)
    near_water = 0.0
    if points:
        water = shapely.union_all([ln.buffer(20) for _, ln in waterways]
                                  + [g.boundary.buffer(20) for c, g in areas if c == "water"])
        pts = np.array(points)
        near_water = shapely.contains_xy(water, pts[:, 0], pts[:, 1]).mean() if not water.is_empty else 0
    print(f"  {(chm > 0).mean():.0%} av kartan har trädkronor, {cover:.0%} av Marktäckes skogsyta.")
    print(f"  Utanför skogen: {mask.sum() * CELL * CELL / 10_000:.1f} ha kronor, {len(points)} träd, "
          f"{near_water:.0%} av dem inom 20 m från vatten.")
    if points:
        hs = np.array([p[2] for p in points])
        print(f"  Höjd: median {np.median(hs):.0f} m, {np.mean(hs < 8):.0%} under 8 m.")
    path = project.lm / "trad.json"
    path.write_text(json.dumps({"kalla": "Laserdata Nedladdning, skog, © Lantmäteriet", "points": points}),
                    encoding="utf-8")
    print(f"Skrev {project.rel(path)}. Bygg om kartan med build_map.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
