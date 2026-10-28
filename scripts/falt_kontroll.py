#!/usr/bin/env python3
"""Kontroll av fälten i en byggd karta: ligger fältet på sitt eget markområde?

FS25 knyter varje fält till ett markområde utifrån var fältet ligger. Skriptet läser
fälten ur kartans i3d och markområdeslagret (infoLayer_farmland.grle) och visar för
varje fält vilket markområde som finns under olika punkter som spelet kan tänkas använda
(fältets nod, hörnens medelpunkt, mitten av omslutande rektangeln, första hörnet), och hur
stor del av fältet som ligger på fältets eget markområde (fält N ska ligga på område N).

Användning:
    python scripts/falt_kontroll.py --map tysslinge [fältnummer ...]
"""
import argparse
import struct
import sys
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import Polygon

from area import add_map_argument, open_map


def read_grle(path):
    data = open(path, "rb").read()
    assert data[:4] == b"GRLE", path
    w, h, _ch, n = struct.unpack("<IIII", data[5:21])
    p, out, i = data[21:21 + n], np.zeros(w * h, np.uint8), 0
    k = 0
    while k < len(p):
        v = p[k]
        if k + 1 < len(p) and p[k + 1] == v:           # körning: v, v, 0xff*m, rest -> 255*m + rest + 2
            k += 2
            cnt = 2
            while p[k] == 0xFF:
                cnt += 255
                k += 1
            cnt += p[k]
            k += 1
        else:
            cnt = 1
            k += 1
        out[i:i + cnt] = v
        i += cnt
    return out.reshape(h, w)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("falt", nargs="*", type=int)
    args = parser.parse_args()
    project = open_map(args.map)
    mod = project.config.get("mod_name") or f"FS25_{project.name.capitalize()}"
    maps = project.build / mod / "maps"
    farm = read_grle(maps / "data" / "infoLayer_farmland.grle")
    size = project.size
    px = farm.shape[0] / size

    def at(x, z):
        c, r = int((x + size / 2) * px), int((z + size / 2) * px)
        return int(farm[r, c]) if 0 <= r < farm.shape[0] and 0 <= c < farm.shape[1] else -1

    root = ET.parse(maps / f"{project.name}.i3d").getroot()
    group = next(tg for tg in root.iter("TransformGroup") if tg.get("name") == "fields")
    rows = []
    for i, f in enumerate(group, 1):
        fx, _, fz = (float(v) for v in f.get("translation").split())
        pts = [(fx + float(t[0]), fz + float(t[2])) for t in
               (p.get("translation").split() for p in f.find("TransformGroup"))]
        poly = Polygon(pts)
        xs, zs = zip(*pts)
        x0, z0, x1, z1 = poly.bounds
        cols = np.arange(int((x0 + size / 2) * px), int((x1 + size / 2) * px) + 1)
        rws = np.arange(int((z0 + size / 2) * px), int((z1 + size / 2) * px) + 1)
        from shapely import contains_xy
        gx, gz = np.meshgrid((cols + 0.5) / px - size / 2, (rws + 0.5) / px - size / 2)
        inside = contains_xy(poly, gx, gz)
        sub = farm[np.clip(rws, 0, farm.shape[0] - 1)][:, np.clip(cols, 0, farm.shape[1] - 1)]
        own = float((sub[inside] == i).mean()) if inside.any() else 0.0
        rows.append({"nr": i, "ha": poly.area / 1e4, "hörn": len(pts), "egen": own,
                     "nod": at(fx, fz), "medel": at(sum(xs) / len(xs), sum(zs) / len(zs)),
                     "rekt": at((x0 + x1) / 2, (z0 + z1) / 2), "första": at(*pts[0]),
                     "tyngd": at(poly.centroid.x, poly.centroid.y)})
    print("Antal fält där punkten INTE ligger på fältets eget markområde:")
    for key in ("nod", "medel", "rekt", "första", "tyngd"):
        print(f"  {key:7s} {sum(r[key] != r['nr'] for r in rows)}")
    print(f"  under 90 % av fältet på eget område: {sum(r['egen'] < 0.9 for r in rows)}")
    show = [r for r in rows if r["nr"] in args.falt] if args.falt else []
    if show:
        print("\nnr     ha  hörn  egen%  nod  medel  rekt  första  tyngd")
        for r in show:
            print(f"{r['nr']:3d} {r['ha']:6.1f} {r['hörn']:5d} {r['egen'] * 100:6.0f} {r['nod']:4d} {r['medel']:6d}"
                  f" {r['rekt']:5d} {r['första']:7d} {r['tyngd']:6d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
