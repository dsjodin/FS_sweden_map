#!/usr/bin/env python3
"""Hämtar Lantmäteriets Markhöjdmodell (1 m grid, CC BY 4.0) för kartrutan via
Lantmäteriets STAC-tjänst och sparar en sammanfogad, klippt GeoTIFF:

    data/<namn>/lm/hojd/dtm_area.tif    kartrutan + 64 m, till make_heightmap.py
    data/<namn>/lm/hojd/dtm_total.tif   med --total: hela området runt kartan
                                        (dubbla kartstorleken), till MapToPlay

Allt i SWEREF 99 TM, höjd i RH 2000, meter.

Nedladdningen kräver inloggning med ett Geotorget-konto (gratis). Ange
uppgifterna som miljövariabler:

    Windows (PowerShell):  $env:LM_USER="namn"; $env:LM_PASSWORD="lösenord"
    macOS/Linux:           export LM_USER=namn LM_PASSWORD=lösenord

Bara den del av varje 10×10 km-ruta som behövs läses (filerna är
molnoptimerade), så nedladdningen blir liten.

Användning:
    python scripts/fetch_heightmap.py [--map tysslinge] [--total] [--margin M] [--out FIL]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from pyproj import Transformer

from area import ROOT, add_map_argument, open_map

STAC_SEARCH = "https://api.lantmateriet.se/stac-hojd/v1/search"
COLLECTION = "dtm-cog"
MARGIN = 64  # meter utanför kartrutan som standard, ger utrymme för kantutjämning
NODATA = -9999.0

to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def find_tiles(bbox):
    min_e, min_n, max_e, max_n = bbox
    lon0, lat0 = to_wgs(min_e, min_n)
    lon1, lat1 = to_wgs(max_e, max_n)
    params = urllib.parse.urlencode({
        "collections": COLLECTION,
        "bbox": f"{lon0},{lat0},{lon1},{lat1}",
        "limit": 50,
    })
    with urllib.request.urlopen(f"{STAC_SEARCH}?{params}", timeout=60) as resp:
        items = json.load(resp)["features"]
    return [(it["id"], it["assets"]["data"]["href"]) for it in items]


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--total", action="store_true",
                        help="hämta hela området runt kartan (för MapToPlay) till dtm_total.tif")
    parser.add_argument("--margin", type=float, help="meter utanför kartrutan")
    parser.add_argument("--out", help="utfil (relativt repots rot)")
    args = parser.parse_args()
    project = open_map(args.map)
    if args.margin is None:
        args.margin = project.size / 2 if args.total else MARGIN
    path = (ROOT / args.out if args.out else
            project.lm / "hojd" / ("dtm_total.tif" if args.total else "dtm_area.tif"))

    user, password = os.environ.get("LM_USER"), os.environ.get("LM_PASSWORD")
    if not user or not password:
        print("Ange Geotorget-kontot i miljövariablerna LM_USER och LM_PASSWORD (se skriptets hjälptext).",
              file=sys.stderr)
        return 1

    bbox = project.bbox(args.margin)
    # Avrunda till hela meter så att pixlarna linjerar med Lantmäteriets grid.
    min_e, min_n = np.floor(bbox[0]), np.floor(bbox[1])
    max_e, max_n = np.ceil(bbox[2]), np.ceil(bbox[3])
    width, height = int(max_e - min_e), int(max_n - min_n)
    out = np.full((height, width), NODATA, dtype=np.float32)
    transform = from_origin(min_e, max_n, 1.0, 1.0)

    tiles = find_tiles((min_e, min_n, max_e, max_n))
    print(f"{len(tiles)} rutor från Lantmäteriet: {', '.join(t[0] for t in tiles)}")

    env = rasterio.Env(
        GDAL_HTTP_AUTH="BASIC",
        GDAL_HTTP_USERPWD=f"{user}:{password}",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    )
    with env:
        for tile_id, href in tiles:
            print(f"  läser {tile_id} ...")
            try:
                src = rasterio.open(f"/vsicurl/{href}")
            except rasterio.errors.RasterioIOError as exc:
                print(f"Kunde inte öppna {href}: {exc}\n"
                      "Kontrollera Geotorget-kontot och att du har godkänt villkoren för Markhöjdmodell.",
                      file=sys.stderr)
                return 1
            with src:
                l, b, r, t = src.bounds
                ix0, iy0 = max(min_e, l), max(min_n, b)
                ix1, iy1 = min(max_e, r), min(max_n, t)
                if ix0 >= ix1 or iy0 >= iy1:
                    continue
                data = src.read(1, window=from_bounds(ix0, iy0, ix1, iy1, src.transform))
                col, row = int(ix0 - min_e), int(max_n - iy1)
                out[row:row + data.shape[0], col:col + data.shape[1]] = data

    missing = np.count_nonzero(out == NODATA)
    if missing:
        print(f"Varning: {missing} pixlar saknar höjd.", file=sys.stderr)

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32",
                       crs="EPSG:3006", transform=transform, nodata=NODATA, compress="deflate",
                       predictor=3, tiled=True, blockxsize=512, blockysize=512) as dst:
        dst.write(out, 1)

    valid = out[out != NODATA]
    print(f"Sparade {project.rel(path)} ({width}×{height} m)")
    print(f"Höjd: lägst {valid.min():.1f} m, högst {valid.max():.1f} m, skillnad {valid.max() - valid.min():.1f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
