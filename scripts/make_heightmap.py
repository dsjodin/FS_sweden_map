#!/usr/bin/env python3
"""Gör om Lantmäteriets höjdmodell (data/<namn>/lm/hojd/dtm_area.tif) till FS25:s
höjdkarta.

FS25 vill ha en 16-bitars gråskale-PNG på (kartstorlek + 1) pixlar i fyrkant,
alltså 4097×4097 för en 4096 m-karta, med en pixel per meter. Pixelvärdet
0..65535 motsvarar höjden 0..heightScale meter i spelet.

Höjderna läggs så att den lägsta punkten hamnar FLOOR meter över spelets
nollnivå. Det ger utrymme att gräva diken och dammar under den verkliga
lägsta punkten. Skalan blir 1:1, så en meter i verkligheten blir en meter i
spelet.

Skriver:
    build/<namn>/data/dem.png               höjdkartan till kartmappen
    build/<namn>/preview/dem_hillshade.png  förhandsvisning med skuggning (1024 px)
    build/<namn>/heightmap.json             värden att föra in i GIANTS Editor

Användning:
    python scripts/make_heightmap.py [--map tysslinge] [--height-scale 255] [--floor 10]
"""
import argparse
import json
import sys

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from area import add_map_argument, open_map, to_sweref


def resample_to_map_grid(cfg, src_path):
    """Läser höjdmodellen i ett rutnät där pixlarnas mitt ligger på kartans hela meter."""
    size = cfg["size_m"]
    e, n = to_sweref(cfg["center"]["lon"], cfg["center"]["lat"])
    west, north = e - size / 2, n + size / 2
    pixels = size + 1
    # Pixel (0, 0) ska ha sin mittpunkt i kartans nordvästra hörn.
    dst_transform = from_origin(west - 0.5, north + 0.5, 1.0, 1.0)
    out = np.full((pixels, pixels), np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=src.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return out


def hillshade(z, azimuth=315, altitude=45):
    gy, gx = np.gradient(z)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(azimuth), np.radians(altitude)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(shade * 255, 0, 255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--height-scale", type=float, default=255.0,
                        help="Kartans heightScale i meter (standard 255)")
    parser.add_argument("--floor", type=float, default=10.0,
                        help="Meter mellan spelets nollnivå och den lägsta verkliga punkten")
    args = parser.parse_args()

    project = open_map(args.map)
    src = project.lm / "hojd" / "dtm_area.tif"
    BUILD = project.build
    if not src.exists():
        print(f"Hittar inte {project.rel(src)}. Kör scripts/fetch_heightmap.py först.", file=sys.stderr)
        return 1

    cfg = project.config
    z = resample_to_map_grid(cfg, src)
    missing = np.isnan(z)
    if missing.all():
        print(f"Höjdmodellen täcker inte kartrutan. Kontrollera maps/{project.name}/area.json.", file=sys.stderr)
        return 1
    if missing.any():
        print(f"Varning: {missing.sum()} pixlar saknar höjd och sätts till lägsta höjden.", file=sys.stderr)
        z[missing] = np.nanmin(z)

    real_min, real_max = float(z.min()), float(z.max())
    base = real_min - args.floor  # verklig höjd som blir spelets nollnivå
    game = z - base
    if game.max() > args.height_scale:
        print(f"Terrängen blir {game.max():.1f} m hög i spelet, vilket är mer än heightScale "
              f"{args.height_scale:.0f}. Höj --height-scale.", file=sys.stderr)
        return 1

    dem = np.round(game / args.height_scale * 65535).astype(np.uint16)
    (BUILD / "data").mkdir(parents=True, exist_ok=True)
    (BUILD / "preview").mkdir(parents=True, exist_ok=True)
    Image.fromarray(dem).save(BUILD / "data" / "dem.png")

    preview = Image.fromarray(hillshade(z)).resize((1024, 1024), Image.LANCZOS)
    preview.save(BUILD / "preview" / "dem_hillshade.png")

    info = {
        "dem_size_px": int(dem.shape[0]),
        "map_size_m": cfg["size_m"],
        "unitsPerPixel": 1,
        "heightScale": args.height_scale,
        "real_height_at_game_zero_m": round(base, 2),
        "real_min_m": round(real_min, 2),
        "real_max_m": round(real_max, 2),
        "game_min_m": round(args.floor, 2),
        "game_max_m": round(real_max - base, 2),
        "height_step_mm": round(args.height_scale / 65535 * 1000, 2),
    }
    (BUILD / "heightmap.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Skrev {project.rel(BUILD / 'data' / 'dem.png')} ({dem.shape[1]}×{dem.shape[0]} px, 16 bitar)")
    print(f"Skrev {project.rel(BUILD / 'preview' / 'dem_hillshade.png')}")
    print(f"Verklig höjd {real_min:.1f}–{real_max:.1f} m blir {args.floor:.1f}–{real_max - base:.1f} m i spelet "
          f"(heightScale {args.height_scale:.0f}, steg {info['height_step_mm']} mm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
