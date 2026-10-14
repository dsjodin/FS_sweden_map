#!/usr/bin/env python3
"""Hämtar OSM-data (markanvändning, vägar, vatten, byggnader, ortnamn) för
kartans osm_bbox i maps/<namn>/area.json och sparar till
data/<namn>/raw/osm.json. Används av områdesväljaren.

Användning:
    python scripts/fetch_osm.py [--map tysslinge]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

from area import add_map_argument, open_map

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
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    project = open_map(parser.parse_args().map)
    out = project.raw / "osm.json"
    data = urllib.parse.urlencode({"data": build_query(project.config["osm_bbox"])}).encode()
    out.parent.mkdir(parents=True, exist_ok=True)
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
            out.write_bytes(body)
            print(f"Sparade {len(body) / 1e6:.1f} MB till {project.rel(out)}")
            return 0
    print("Kunde inte hämta OSM-data från någon server.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
