#!/usr/bin/env python3
"""Hämtar Jordbruksverkets jordbruksblock och skiften (öppna data, senaste
årslagret) för kartrutan plus marginal. Skiftena är de verkliga fälten som
lantbrukarna sökt stöd för, med grödkod.

Sparar i SWEREF 99 TM:
    data/<namn>/raw/jbv_block.geojson
    data/<namn>/raw/jbv_skiften.geojson

Användning:
    python scripts/fetch_fields.py [--map tysslinge] [--margin M]

Som standard täcks hela området runt den spelbara ytan (marginal = halva
kartstorleken, alltså 8×8 km för en 4×4 km-karta).
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

from area import add_map_argument, open_map

WFS = "https://epub.sjv.se/inspire/inspire/wfs"
LAYERS = {
    "jbv_block": "inspire:senaste_arslager_block",
    "jbv_skiften": "inspire:senaste_arslager_skifte",
}
PAGE = 1000

# Grödkoder som är bekräftade mot Jordbruksverkets förordningstexter. Övriga visas som "kod N".
CROPS = {
    2: "Korn (vår)",
    3: "Havre",
    5: "Vete (vår)",
    12: "Blandsäd",
    13: "Spannmål/baljväxtblandning",
    16: "Stråsäd till grönfoder/ensilage",
    21: "Raps (vår)",
    23: "Rybs (vår)",
    29: "Rågvete (vår)",
    40: "Oljelin",
}


def fetch_layer(type_name, bbox):
    min_e, min_n, max_e, max_n = bbox
    features, start = [], 0
    while True:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
            "outputFormat": "application/json",
            "count": PAGE,
            "startIndex": start,
            # EPSG:3006 som URN har axelordningen nord, öst.
            "bbox": f"{min_n},{min_e},{max_n},{max_e},urn:ogc:def:crs:EPSG::3006",
        }
        url = f"{WFS}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            page = json.load(resp)
        features.extend(page["features"])
        if len(page["features"]) < PAGE:
            return features
        start += PAGE


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--margin", type=float, help="meter utanför kartrutan (standard halva kartstorleken)")
    args = parser.parse_args()
    project = open_map(args.map)
    if args.margin is None:
        args.margin = project.size / 2
    bbox = project.bbox(args.margin)
    out_dir = project.raw
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, type_name in LAYERS.items():
        print(f"Hämtar {type_name} ...")
        feats = fetch_layer(type_name, bbox)
        fc = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3006"}},
            "features": feats,
        }
        path = out_dir / f"{name}.geojson"
        path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(feats)} objekt till {project.rel(path)}")
        result[name] = feats

    skiften = result["jbv_skiften"]
    if not skiften:
        print("Inga skiften hittades.", file=sys.stderr)
        return 1
    by_crop = defaultdict(lambda: [0, 0.0])
    for f in skiften:
        p = f["properties"]
        code = p.get("grdkod_mar")
        by_crop[code][0] += 1
        by_crop[code][1] += p.get("faststalld_areal_ha") or p.get("ansokt_areal_ha") or 0
    years = sorted({f["properties"].get("arslager") for f in skiften})
    print(f"\nSkiften {years} (ruta + {args.margin:.0f} m marginal), per grödkod:")
    for code, (n, ha) in sorted(by_crop.items(), key=lambda kv: -kv[1][1]):
        label = CROPS.get(code, f"kod {code}")
        print(f"  {label:<34} {n:>4} skiften {ha:>8.1f} ha")
    return 0


if __name__ == "__main__":
    sys.exit(main())
