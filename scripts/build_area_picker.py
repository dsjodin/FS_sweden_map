#!/usr/bin/env python3
"""Bygger områdesväljaren maps/<namn>/omradesval.html från mallen
tools/omradesval.template.html och maps/<namn>/area_features.geojson.
Kör fetch_osm.py och analyze_area.py först.

Användning:
    python scripts/build_area_picker.py [--map tysslinge]
"""
import argparse
import html as htmllib
import json

from area import ROOT, add_map_argument, open_map

TEMPLATE = ROOT / "tools" / "omradesval.template.html"
LEAFLET_CSS = ROOT / "tools" / "vendor" / "leaflet-1.9.4.min.css"


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    project = open_map(parser.parse_args().map)
    features = json.loads((project.dir / "area_features.geojson").read_text(encoding="utf-8"))
    osm = json.loads((project.raw / "osm.json").read_text(encoding="utf-8"))
    payload = {
        "config": project.config,
        "osm_date": osm.get("osm3s", {}).get("timestamp_osm_base", "")[:10],
        "features": features,
    }
    title = project.config.get("title", project.name.capitalize())
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__MAP_TITLE__", htmllib.escape(title))
    html = html.replace("/*__LEAFLET_CSS__*/", LEAFLET_CSS.read_text(encoding="utf-8"))
    html = html.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    out = project.dir / "omradesval.html"
    out.write_text(html, encoding="utf-8")
    print(f"Skrev {project.rel(out)} ({len(html) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
