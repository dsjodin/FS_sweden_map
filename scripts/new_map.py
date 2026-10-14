#!/usr/bin/env python3
"""Skapar en ny karta: maps/<namn>/area.json.

Ange platsen med ett ortnamn (söks upp i OpenStreetMap) eller med
koordinater. Platser som ska markeras i områdesväljaren anges med --poi.

Exempel:
    python scripts/new_map.py tysslinge --place "Tysslinge, Örebro"
    python scripts/new_map.py vreta --title "Vreta kloster" --center 58.4870,15.5110 --size 4096 \\
        --poi "Vreta klosterkyrka=58.4892,15.5096"

Därefter:
    python scripts/pipeline.py --map <namn>
"""
import argparse
import json
import math
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

from area import MAPS

SIZES = (2048, 4096, 8192, 16384)


def geocode(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "se"})
    req = urllib.request.Request(url, headers={"User-Agent": "fs-sweden-map/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        hits = json.load(resp)
    if not hits:
        sys.exit(f"Hittade ingen plats som heter '{query}'. Prova att lägga till kommun, eller ange --center.")
    hit = hits[0]
    print(f"Hittade: {hit['display_name']}")
    return float(hit["lat"]), float(hit["lon"])


def parse_latlon(text):
    lat, lon = (float(v) for v in text.split(","))
    if not (55 <= lat <= 69.1 and 10.5 <= lon <= 24.2):
        sys.exit(f"{text} ligger inte i Sverige. Ange som LAT,LON, till exempel 59.27,15.02.")
    return lat, lon


def mod_name(title):
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", ascii_title)
    return "FS25_" + "".join(w[:1].upper() + w[1:] for w in words)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="kortnamn med små bokstäver, siffror och _ (blir mappnamnet)")
    parser.add_argument("--title", help="visningsnamn, till exempel 'Vreta kloster' (standard: namnet)")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--place", help="ortnamn att söka upp, till exempel 'Tysslinge, Örebro'")
    where.add_argument("--center", help="mittpunkt som LAT,LON")
    parser.add_argument("--size", type=int, default=4096, choices=SIZES, help="kartstorlek i meter (standard 4096)")
    parser.add_argument("--poi", action="append", default=[], help="plats att markera, 'Namn=LAT,LON' (flera går bra)")
    parser.add_argument("--description", default="", help="kort beskrivning av området")
    parser.add_argument("--force", action="store_true", help="skriv över en befintlig karta")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9_]+", args.name):
        sys.exit("Namnet får bara innehålla små bokstäver a–z, siffror och _, till exempel 'vreta_kloster'.")
    path = MAPS / args.name / "area.json"
    if path.exists() and not args.force:
        sys.exit(f"Kartan '{args.name}' finns redan. Använd --force för att skriva över.")

    lat, lon = geocode(args.place) if args.place else parse_latlon(args.center)
    title = args.title or args.name.replace("_", " ").title()
    pois = {}
    for item in args.poi:
        name, _, coords = item.partition("=")
        pois[name.strip()] = dict(zip(("lat", "lon"), parse_latlon(coords)))

    # OSM-utdraget till områdesväljaren ska rymma rutan i alla storlekar och lite till.
    half_m = max(7000, args.size)
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    config = {
        "name": args.name,
        "title": title,
        "mod_name": mod_name(title),
        "description": args.description,
        "center": {"lat": round(lat, 5), "lon": round(lon, 5)},
        "size_m": args.size,
        "crs": "EPSG:3006",
        "points_of_interest": pois,
        "osm_bbox": {
            "south": round(lat - dlat, 4), "west": round(lon - dlon, 4),
            "north": round(lat + dlat, 4), "east": round(lon + dlon, 4),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Skapade maps/{args.name}/area.json: {title}, {args.size} m, mittpunkt {lat:.5f}, {lon:.5f}")
    print(f"Mod-namn: {config['mod_name']}")
    print(f"Nästa steg: python scripts/pipeline.py --map {args.name}")


if __name__ == "__main__":
    main()
