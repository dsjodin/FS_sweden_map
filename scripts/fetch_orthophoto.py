#!/usr/bin/env python3
"""Hämtar Lantmäteriets ortofoto (färg, 16–25 cm, CC BY 4.0) för kartrutan
via Lantmäteriets STAC-tjänst och sparar en sammanfogad GeoTIFF i lägre
upplösning, lagom för kartgeneratorer och som förlaga i GIANTS Editor:

    data/<namn>/lm/ortofoto/ortofoto.tif   (SWEREF 99 TM, RGB, JPEG-komprimerad)

Kräver behörighet till Ortofoto Nedladdning på Geotorget. Kontot anges
som för höjdmodellen, med miljövariablerna LM_USER och LM_PASSWORD.

Bilderna tas från det senaste år som täcker hela området, så att färgerna
blir enhetliga. Finns inget sådant år tas varje 2,5×2,5 km-ruta från den
senaste flygningen. Med --year väljs ett visst år.

Användning:
    python scripts/fetch_orthophoto.py [--map tysslinge] [--margin M] [--res 0.5] [--year 2024]

Som standard täcks hela området runt kartan (marginal = halva kartstorleken).
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

from area import ROOT, add_map_argument, open_map

STAC_SEARCH = "https://api.lantmateriet.se/stac-bild/v1/search"
to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def search_items(bbox):
    min_e, min_n, max_e, max_n = bbox
    lon0, lat0 = to_wgs(min_e, min_n)
    lon1, lat1 = to_wgs(max_e, max_n)
    url = f"{STAC_SEARCH}?" + urllib.parse.urlencode({"bbox": f"{lon0},{lat0},{lon1},{lat1}", "limit": 100})
    items = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:
            page = json.load(resp)
        items.extend(page["features"])
        url = next((l["href"] for l in page.get("links", []) if l.get("rel") == "next"), None)
    return items


def pick_tiles(items, year=None):
    """En bild per ruta: färgbilden (inte IR) från senaste året, eller angivet år."""
    best = {}
    for it in items:
        href = it["assets"]["data"]["href"]
        if "_25i_" in href:  # infraröda bilder
            continue
        m = re.match(r"o(\d+)_(\d+)_25_", it["id"])
        if not m:
            continue
        when = it["properties"].get("datetime") or ""
        if year and not when.startswith(str(year)):
            continue
        key = m.groups()
        if key not in best or when > best[key][0]:
            best[key] = (when, it["id"], href)
    return sorted(best.values(), key=lambda t: t[1])


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--margin", type=float, help="meter utanför kartrutan (standard halva kartstorleken)")
    parser.add_argument("--res", type=float, default=0.5, help="upplösning i meter per pixel (standard 0,5)")
    parser.add_argument("--year", type=int, help="använd bara bilder från detta år")
    parser.add_argument("--out", help="utfil (relativt repots rot)")
    parser.add_argument("--list", action="store_true", help="visa vilka bilder som skulle användas och avsluta")
    args = parser.parse_args()

    project = open_map(args.map)
    if args.margin is None:
        args.margin = project.size / 2
    bbox = project.bbox(args.margin)
    min_e, min_n = np.floor(bbox[0]), np.floor(bbox[1])
    max_e, max_n = np.ceil(bbox[2]), np.ceil(bbox[3])
    items = search_items((min_e, min_n, max_e, max_n))
    year = args.year
    if year is None:
        n_tiles = len(pick_tiles(items))
        candidates = sorted({(it["properties"].get("datetime") or "")[:4] for it in items}, reverse=True)
        year = next((int(y) for y in candidates if y and len(pick_tiles(items, int(y))) == n_tiles), None)
    tiles = pick_tiles(items, year)
    if not tiles:
        print("Hittade inga ortofoton för området.", file=sys.stderr)
        return 1
    years = sorted({t[0][:4] for t in tiles})
    print(f"{len(tiles)} rutor, flygår {', '.join(years)}")
    if args.list:
        for when, tile_id, _ in tiles:
            print(f"  {tile_id}  {when[:10]}")
        return 0

    user, password = os.environ.get("LM_USER"), os.environ.get("LM_PASSWORD")
    if not user or not password:
        print("Ange Geotorget-kontot i miljövariablerna LM_USER och LM_PASSWORD.", file=sys.stderr)
        return 1

    width = int(round((max_e - min_e) / args.res))
    height = int(round((max_n - min_n) / args.res))
    out = np.zeros((3, height, width), dtype=np.uint8)
    env = rasterio.Env(
        GDAL_HTTP_AUTH="BASIC",
        GDAL_HTTP_USERPWD=f"{user}:{password}",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    )
    with env:
        for i, (when, tile_id, href) in enumerate(tiles, 1):
            print(f"  [{i}/{len(tiles)}] {tile_id} ({when[:10]}) ...")
            try:
                src = rasterio.open(f"/vsicurl/{href}")
            except rasterio.errors.RasterioIOError as exc:
                print(f"Kunde inte öppna {href}: {exc}\n"
                      "Kontrollera att kontot har behörighet till Ortofoto Nedladdning.", file=sys.stderr)
                return 1
            with src:
                l, b, r, t = src.bounds
                x0, y0, x1, y1 = max(min_e, l), max(min_n, b), min(max_e, r), min(max_n, t)
                if x0 >= x1 or y0 >= y1:
                    continue
                c0, c1 = int(round((x0 - min_e) / args.res)), int(round((x1 - min_e) / args.res))
                r0, r1 = int(round((max_n - y1) / args.res)), int(round((max_n - y0) / args.res))
                data = src.read(
                    [1, 2, 3],
                    window=from_bounds(x0, y0, x1, y1, src.transform),
                    out_shape=(3, r1 - r0, c1 - c0),
                    resampling=Resampling.average,
                )
                out[:, r0:r1, c0:c1] = data

    path = ROOT / args.out if args.out else project.lm / "ortofoto" / "ortofoto.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(
        driver="GTiff", width=width, height=height, count=3, dtype="uint8", crs="EPSG:3006",
        transform=from_origin(min_e, max_n, args.res, args.res), photometric="YCBCR",
        compress="JPEG", jpeg_quality=90, tiled=True, blockxsize=512, blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out)
    size_mb = path.stat().st_size / 1e6
    print(f"Sparade {project.rel(path)} ({width}×{height} px, {args.res} m/px, {size_mb:.0f} MB)")
    print("Källa: Ortofoto © Lantmäteriet (CC BY 4.0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
