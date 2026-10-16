#!/usr/bin/env python3
"""Hämtar Lantmäteriets Marktäcke och Byggnad (Nedladdning, vektor, CC BY 4.0)
för kartans område via Lantmäteriets STAC-tjänst.

Datan levereras som en zip-fil per kommun. Skriptet laddar ner de kommuner som
området berör, packar upp dem och skriver en sammanfattning av vilka lager,
fält och klasser som finns. Sammanfattningen behövs för att koppla
Lantmäteriets klasser (skog, åker, sankmark med flera) till FS25:s marklager.

Kräver behörighet till Marktäcke Nedladdning, vektor och Byggnad Nedladdning,
vektor på Geotorget. Kontot anges i LM_USER och LM_PASSWORD.

Resultat:
    data/<namn>/lm/vektor/<produkt>_<kommun>/   uppackade filer
    data/<namn>/lm/vektor/sammanfattning.txt    lager, fält och klasser

Användning:
    python scripts/fetch_landcover.py [--map tysslinge] [--list]
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import Counter

from pyproj import Transformer

from area import add_map_argument, open_map

STAC_SEARCH = "https://api.lantmateriet.se/stac-vektor/v1/search"
COLLECTIONS = ("marktacke", "byggnader")
to_wgs = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True).transform


def search(bbox):
    min_e, min_n, max_e, max_n = bbox
    lon0, lat0 = to_wgs(min_e, min_n)
    lon1, lat1 = to_wgs(max_e, max_n)
    url = STAC_SEARCH + "?" + urllib.parse.urlencode({
        "collections": ",".join(COLLECTIONS), "bbox": f"{lon0},{lat0},{lon1},{lat1}", "limit": 50})
    with urllib.request.urlopen(url, timeout=60) as resp:
        return [(f["collection"], f["id"], f["assets"]["data"]["href"]) for f in json.load(resp)["features"]]


def download(href, path, user, password):
    req = urllib.request.Request(href)
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=600) as resp, open(path, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def summarize(folder):
    """Lager, fält och vanligaste värden i alla vektorfiler i mappen."""
    import pyogrio  # följer med geopandas/pyogrio; installeras vid behov

    lines = []
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".gpkg", ".shp", ".geojson", ".gml")):
        for layer, geomtype in pyogrio.list_layers(path):
            info = pyogrio.read_info(path, layer=layer)
            lines.append(f"\n## {path.name} / {layer} ({geomtype}, {info['features']} objekt)")
            lines.append("Fält: " + ", ".join(info["fields"]))
            df = pyogrio.read_dataframe(path, layer=layer, read_geometry=False, max_features=200_000)
            for col in df.columns:
                if df[col].dtype == object and df[col].nunique() <= 60:
                    top = Counter(df[col].dropna().astype(str)).most_common(40)
                    lines.append(f"  {col}: " + "; ".join(f"{v} ({n})" for v, n in top))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--list", action="store_true", help="visa vilka filer som skulle hämtas och avsluta")
    args = parser.parse_args()
    project = open_map(args.map)

    items = search(project.bbox(project.size / 2))
    print(f"{len(items)} filer: " + ", ".join(f"{c} kommun {i}" for c, i, _ in items))
    if args.list:
        return 0
    user, password = os.environ.get("LM_USER"), os.environ.get("LM_PASSWORD")
    if not user or not password:
        print("Ange Geotorget-kontot i LM_USER och LM_PASSWORD.", file=sys.stderr)
        return 1

    out_dir = project.lm / "vektor"
    out_dir.mkdir(parents=True, exist_ok=True)
    for coll, item_id, href in items:
        target = out_dir / f"{coll}_{item_id}"
        zpath = out_dir / f"{coll}_{item_id}.zip"
        if not target.exists():
            print(f"Hämtar {coll} för kommun {item_id} ...")
            try:
                download(href, zpath, user, password)
            except urllib.error.HTTPError as exc:
                print(f"  {exc}. Har kontot behörighet till {coll}?", file=sys.stderr)
                return 1
            with zipfile.ZipFile(zpath) as z:
                z.extractall(target)
            zpath.unlink()
        print(f"  {project.rel(target)}")

    try:
        text = summarize(out_dir)
    except ImportError:
        print("Installera pyogrio för sammanfattningen: pip install pyogrio pandas", file=sys.stderr)
        return 1
    (out_dir / "sammanfattning.txt").write_text(text, encoding="utf-8")
    print(f"\nSkrev {project.rel(out_dir / 'sammanfattning.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
