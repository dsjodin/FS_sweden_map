"""Gemensam hjälpkod: läser config/area.json och räknar ut kartrutan i SWEREF 99 TM."""
import json
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "area.json"

to_sweref = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True).transform


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def map_bbox(margin=0.0, config=None):
    """Kartrutan som (min_e, min_n, max_e, max_n) i SWEREF 99 TM, med valfri marginal i meter."""
    cfg = config or load_config()
    e, n = to_sweref(cfg["center"]["lon"], cfg["center"]["lat"])
    h = cfg["size_m"] / 2 + margin
    return (e - h, n - h, e + h, n + h)
