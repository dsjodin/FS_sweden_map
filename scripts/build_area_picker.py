#!/usr/bin/env python3
"""Bygger tools/omradesval.html (områdesväljaren) från mallen och
data/area_features.geojson. Kör analyze_area.py först.

Användning:
    python scripts/build_area_picker.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "tools" / "omradesval.template.html"
LEAFLET_CSS = ROOT / "tools" / "vendor" / "leaflet-1.9.4.min.css"
OUT = ROOT / "tools" / "omradesval.html"


def main():
    config = json.loads((ROOT / "config" / "area.json").read_text(encoding="utf-8"))
    features = json.loads((ROOT / "data" / "area_features.geojson").read_text(encoding="utf-8"))
    osm = json.loads((ROOT / "data" / "raw" / "osm.json").read_text(encoding="utf-8"))
    payload = {
        "config": config,
        "osm_date": osm.get("osm3s", {}).get("timestamp_osm_base", "")[:10],
        "features": features,
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__LEAFLET_CSS__*/", LEAFLET_CSS.read_text(encoding="utf-8"))
    html = html.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    OUT.write_text(html, encoding="utf-8")
    print(f"Skrev {OUT.relative_to(ROOT)} ({len(html) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
