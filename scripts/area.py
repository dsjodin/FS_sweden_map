"""Gemensam hjälpkod för alla kartor i repot.

Varje karta har en egen mapp med inställningar och sina egna data- och
byggmappar:

    maps/<namn>/area.json   mittpunkt, storlek, platser (checkas in)
    data/<namn>/raw/        OSM och Jordbruksverket (checkas inte in)
    data/<namn>/lm/         Lantmäteriets höjddata och ortofoto (checkas inte in)
    build/<namn>/           färdiga kartfiler (checkas inte in)

Skripten väljer karta med --map <namn>, miljövariabeln FS_MAP, eller
automatiskt om det bara finns en karta.
"""
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "maps"

to_sweref = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform


@dataclass
class MapProject:
    name: str
    config: dict

    @property
    def dir(self):
        return MAPS / self.name

    @property
    def raw(self):
        return ROOT / "data" / self.name / "raw"

    @property
    def lm(self):
        return ROOT / "data" / self.name / "lm"

    @property
    def build(self):
        return ROOT / "build" / self.name

    @property
    def size(self):
        return self.config["size_m"]

    def bbox(self, margin=0.0):
        return map_bbox(margin, self.config)

    def rel(self, path):
        """Sökväg relativt repots rot, för utskrifter."""
        return Path(path).resolve().relative_to(ROOT)


def list_maps():
    return sorted(p.parent.name for p in MAPS.glob("*/area.json"))


def add_map_argument(parser):
    parser.add_argument("--map", default=os.environ.get("FS_MAP"),
                        help="kartans namn (mapp under maps/). Standard: FS_MAP eller den enda kartan")


def open_map(name=None):
    maps = list_maps()
    if name is None:
        if len(maps) == 1:
            name = maps[0]
        else:
            sys.exit(f"Ange vilken karta med --map. Kartor: {', '.join(maps) or 'inga (skapa med new_map.py)'}")
    path = MAPS / name / "area.json"
    if not path.exists():
        sys.exit(f"Kartan '{name}' finns inte. Kartor: {', '.join(maps) or 'inga'}")
    return MapProject(name, json.loads(path.read_text(encoding="utf-8")))


def map_bbox(margin, config):
    """Kartrutan som (min_e, min_n, max_e, max_n) i SWEREF 99 TM, med valfri marginal i meter."""
    e, n = to_sweref(config["center"]["lon"], config["center"]["lat"])
    h = config["size_m"] / 2 + margin
    return (e - h, n - h, e + h, n + h)
