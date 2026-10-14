#!/usr/bin/env python3
"""Kör hela kedjan för en karta, från data till filer för MapToPlay och
GIANTS Editor.

Steg:
    osm          hämta OSM-data till områdesväljaren        (fetch_osm.py)
    analys       statistik per kartstorlek                    (analyze_area.py)
    valjare      bygg områdesväljaren                         (build_area_picker.py)
    falt         hämta Jordbruksverkets block och skiften     (fetch_fields.py)
    osmfil       OSM-fil med skiften som fält, till MapToPlay (make_osm_fields.py)
    hojd         höjdmodell för kartrutan                     (fetch_heightmap.py)
    hojd_total   höjdmodell för hela området, till MapToPlay  (fetch_heightmap.py --total)
    dem          höjdkarta dem.png för FS25                   (make_heightmap.py)
    karta        färdig FS25-modd utan MapToPlay              (build_map.py)
    ortofoto     ortofoto (bara med --ortofoto)               (fetch_orthophoto.py)

Stegen som hämtar från Lantmäteriet kräver LM_USER och LM_PASSWORD. Saknas
de hoppas stegen över.

Användning:
    python scripts/pipeline.py --map vreta
    python scripts/pipeline.py --map vreta --only osm analys valjare
    python scripts/pipeline.py --map vreta --from falt
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from area import add_map_argument, open_map

SCRIPTS = Path(__file__).resolve().parent
STEPS = [
    ("osm", ["fetch_osm.py"], False),
    ("analys", ["analyze_area.py"], False),
    ("valjare", ["build_area_picker.py"], False),
    ("falt", ["fetch_fields.py"], False),
    ("osmfil", ["make_osm_fields.py"], False),
    ("hojd", ["fetch_heightmap.py"], True),
    ("hojd_total", ["fetch_heightmap.py", "--total"], True),
    ("dem", ["make_heightmap.py"], False),
    ("karta", ["build_map.py"], False),
    ("ortofoto", ["fetch_orthophoto.py"], True),
]
NAMES = [s[0] for s in STEPS]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_map_argument(parser)
    parser.add_argument("--only", nargs="+", choices=NAMES, help="kör bara dessa steg")
    parser.add_argument("--from", dest="start", choices=NAMES, help="börja på detta steg")
    parser.add_argument("--ortofoto", action="store_true", help="hämta även ortofoto (kräver behörighet)")
    args = parser.parse_args()
    project = open_map(args.map)

    steps = STEPS
    if args.start:
        steps = steps[NAMES.index(args.start):]
    if args.only:
        steps = [s for s in steps if s[0] in args.only]
    elif not args.ortofoto:
        steps = [s for s in steps if s[0] != "ortofoto"]

    has_lm = bool(os.environ.get("LM_USER") and os.environ.get("LM_PASSWORD"))
    skipped = []
    for name, cmd, needs_lm in steps:
        if needs_lm and not has_lm:
            skipped.append(name)
            continue
        if name in ("dem", "karta") and not (project.lm / "hojd" / "dtm_area.tif").exists():
            skipped.append(name)
            continue
        print(f"\n=== {name}: {' '.join(cmd)} ===", flush=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / cmd[0]), *cmd[1:], "--map", project.name])
        if result.returncode != 0:
            print(f"\nSteget '{name}' misslyckades. Rätta felet och fortsätt med --from {name}.", file=sys.stderr)
            return result.returncode

    print(f"\nKlart för {project.config.get('title', project.name)}.")
    if skipped:
        print(f"Hoppade över: {', '.join(skipped)}. Lantmäteriets steg kräver LM_USER och LM_PASSWORD.")
    mod = project.config.get("mod_name", "FS25_" + project.name.capitalize())
    print(f"Färdig modd: build/{project.name}/{mod}.zip")
    print(f"Till MapToPlay: data/{project.name}/lm/hojd/dtm_total.tif och build/{project.name}/{project.name}_faltskiften.osm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
