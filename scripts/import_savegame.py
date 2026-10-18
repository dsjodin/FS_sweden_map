#!/usr/bin/env python3
"""Hämtar byggnader och objekt som du placerat i spelets byggläge till kartan.

I spelet sparas det du bygger bara i sparfilen (savegame), inte i kartan.
Skriptet läser sparfilens placeables.xml och sparar allt som inte redan finns
i kartan till maps/<namn>/placeringar.json. build_map.py lägger sedan in dem i
kartans placeables.xml, så att de finns med i varje nytt spel och varje
ombyggnad. Objekt från andra moddar blir beroenden i kartans modDesc.xml.

Kör flera gånger efter hand: nya objekt läggs till, och sådant som redan
finns i placeringar.json eller i kartan hoppas över.

Kopiera först sparfilen från Windows till servern, till exempel:
    scp -r "$env:USERPROFILE\\Documents\\My Games\\FarmingSimulator2025\\savegame1" root@ClaudeVM:~/FS_sweden_map/data/tysslinge/

Användning:
    python scripts/import_savegame.py [--map tysslinge] data/tysslinge/savegame1
    python scripts/import_savegame.py ... --ersatt     ersätt listan i stället för att lägga till
    python scripts/import_savegame.py ... --visa       visa vad som skulle importeras och avsluta
"""
import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from area import add_map_argument, open_map, to_sweref

SAME_DIST = 1.0          # m: samma fil inom detta avstånd räknas som samma objekt
MOD_RE = re.compile(r"^\$moddir\$([^/\\]+)[/\\]", re.IGNORECASE)


def mod_of(filename, attrs):
    """Moddnamnet för ett objekt från en annan modd, annars None (spelets egna filer)."""
    if attrs.get("modName"):
        return attrs["modName"]
    m = MOD_RE.match(filename)
    return m.group(1) if m else None


def read_savegame(path):
    path = Path(path)
    xml_path = path / "placeables.xml" if path.is_dir() else path
    if not xml_path.exists():
        sys.exit(f"Hittar inte {xml_path}. Ange sparfilens mapp eller dess placeables.xml.")
    out = []
    for el in ET.parse(xml_path).getroot().iter("placeable"):
        a = el.attrib
        if "filename" not in a or "position" not in a:
            continue
        if a.get("mapBoundId"):          # objekt som hör till kartan själv
            continue
        out.append({
            "filename": a["filename"],
            "position": [float(v) for v in a["position"].split()],
            "rotation": [float(v) for v in a.get("rotation", "0 0 0").split()],
            "mod": mod_of(a["filename"], a),
        })
    return out


def read_map_placeables(path):
    if not path.exists():
        return []
    return [{"filename": el.get("filename"), "position": [float(v) for v in el.get("position").split()]}
            for el in ET.parse(path).getroot().iter("placeable") if el.get("position")]


def same(a, b):
    pa, pb = a["position"], b["position"]
    return (Path(a["filename"]).name == Path(b["filename"]).name
            and math.hypot(pa[0] - pb[0], pa[2] - pb[2]) < SAME_DIST)


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("savegame", help="sparfilens mapp (savegameN) eller dess placeables.xml")
    parser.add_argument("--ersatt", action="store_true", help="ersätt placeringar.json helt")
    parser.add_argument("--visa", action="store_true", help="visa vad som skulle importeras och avsluta")
    args = parser.parse_args()
    project = open_map(args.map)

    mod_name = project.config.get("mod_name") or f"FS25_{project.name.capitalize()}"
    built = read_map_placeables(project.build / mod_name / "maps" / "placeables.xml")
    out_path = project.dir / "placeringar.json"
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    existing = [] if args.ersatt else previous
    # Kartans egna objekt från build_map (gård, silo, mottagning) ska inte dubbleras.
    map_own = [b for b in built if not any(same(b, p) for p in previous)]

    e0, n0 = to_sweref(project.config["center"]["lon"], project.config["center"]["lat"])
    new, skipped = [], 0
    for p in read_savegame(args.savegame):
        if any(same(p, q) for q in map_own + existing + new):
            skipped += 1
            continue
        x, _y, z = p["position"]
        p["sweref"] = [round(e0 + x, 2), round(n0 - z, 2)]
        p["kalla"] = "sparfil"
        new.append(p)

    for p in new:
        x, y, z = p["position"]
        print(f"  + {Path(p['filename']).stem:40s} x {x:8.1f}  z {z:8.1f}  höjd {y:6.2f}"
              + (f"  (modd {p['mod']})" if p["mod"] else ""))
    print(f"{len(new)} nya objekt, {skipped} fanns redan i kartan eller i {project.rel(out_path)}.")
    mods = sorted({p["mod"] for p in existing + new if p.get("mod")})
    if mods:
        print("Moddar som kartan kommer att kräva: " + ", ".join(mods))
    if args.visa or not new and not args.ersatt:
        return 0
    out_path.write_text(json.dumps(existing + new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Skrev {project.rel(out_path)}. Bygg om kartan med build_map.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
