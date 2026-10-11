#!/usr/bin/env python3
"""Hämtar OSM-data (markanvändning, vägar, vatten, byggnader, ortnamn) för
kartområdets bbox i config/area.json och sparar till data/raw/osm.json.

Användning:
    python scripts/fetch_osm.py
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "area.json"
OUT = ROOT / "data" / "raw" / "osm.json"

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def build_query(b):
    bbox = f'({b["south"]},{b["west"]},{b["north"]},{b["east"]})'
    return (
        "[out:json][timeout:180];("
        f'way["landuse"]{bbox};'
        f'relation["landuse"]{bbox};'
        f'way["natural"~"wood|water|wetland|scrub|grassland"]{bbox};'
        f'relation["natural"~"wood|water|wetland"]{bbox};'
        f'way["highway"]{bbox};'
        f'way["railway"]{bbox};'
        f'way["waterway"]{bbox};'
        f'way["building"]{bbox};'
        f'node["place"]{bbox};'
        ");out geom;"
    )


def main():
    area = json.loads(CONFIG.read_text(encoding="utf-8"))
    data = urllib.parse.urlencode({"data": build_query(area["osm_bbox"])}).encode()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        for url in MIRRORS:
            print(f"Hämtar från {url} ...")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "fs-sweden-map/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    body = resp.read()
                json.loads(body)
            except Exception as exc:  # nätverksfel, timeout eller HTML-felsida
                print(f"  misslyckades: {exc}")
                time.sleep(4 * (attempt + 1))
                continue
            OUT.write_bytes(body)
            print(f"Sparade {len(body) / 1e6:.1f} MB till {OUT.relative_to(ROOT)}")
            return 0
    print("Kunde inte hämta OSM-data från någon server.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
