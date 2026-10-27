#!/usr/bin/env python3
"""Byggeditor i webbläsaren: placera moddbyggnader på de verkliga byggnaderna.

Startar en liten webbserver på servern. Öppna den från Windows-datorn i
webbläsaren (http://ClaudeVM:8080). Där syns:

- ortofotot eller spelets kartbild som bakgrund
- Topografi 10:s byggnader som konturer (röda = utan byggnad, gröna = klara)
- byggnader ur modd-katalogen (mod_katalog.py), sorterade efter hur bra de
  passar i storlek för den kontur du klickat på

Välj en byggnad så hamnar den mitt i konturen, vriden efter långsidan. Dra den
med musen, vrid med knapparna eller Q/E, ta bort med Delete. Allt sparas direkt
i maps/<namn>/byggnader.json, och "Bygg kartan" kör build_map.py.

Ortofotot visas bara här, på dina egna datorer. Servern lyssnar på hela
hemnätverket men inte utanför det, om routern inte vidarebefordrar porten.

Användning:
    python scripts/byggeditor.py [--map tysslinge] [--port 8080]
"""
import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.windows import from_bounds

from area import ROOT, add_map_argument, open_map

TEMPLATE = ROOT / "tools" / "byggeditor.html"
CATALOG = ROOT / "build" / "mod_katalog"
MIN_AREA = 12.0          # m², mindre byggnader visas inte
ORTHO_RES = 1.0          # m per pixel för bakgrunden
DEFAULT_SIZE = 10.0      # m, för byggnader utan mått i moddens XML


def footprint(poly):
    """Mitt, längd, bredd och långsidans vinkel (grader moturs från öster) för en byggnadskontur."""
    rect = poly.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    sides = [(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2)]
    lens = [float(np.hypot(*s)) for s in sides]
    k = int(np.argmax(lens))
    angle = float(np.degrees(np.arctan2(sides[k][1], sides[k][0]))) % 180
    c = rect.centroid
    return c.x, c.y, max(lens), min(lens), angle


def prepare(project, world, out):
    """Byggnader, bakgrunder och katalog för editorn. Koordinater i meter från kartans mitt
    (x österut, y norrut)."""
    import landcover
    area = world.square(-50)
    blds = []
    for i, (poly, attrs) in enumerate(landcover.load_buildings(area)):
        if poly.area < MIN_AREA or not poly.intersects(world.square()):
            continue
        cx, cy, length, width, angle = footprint(poly)
        blds.append({
            "id": i, "type": attrs.get("objekttyp") or "", "purpose": (attrs.get("andamal1") or "").strip(";"),
            "main": attrs.get("huvudbyggnad") == "Ja", "area": round(poly.area),
            "poly": [[round(x - world.e0, 1), round(y - world.n0, 1)] for x, y in poly.simplify(0.3).exterior.coords],
            "cx": round(cx - world.e0, 1), "cy": round(cy - world.n0, 1),
            "length": round(length, 1), "width": round(width, 1), "angle": round(angle, 1)})
    out.mkdir(parents=True, exist_ok=True)
    backgrounds = []
    ortho = project.lm / "ortofoto" / "ortofoto.tif"
    if ortho.exists():
        h = world.half + 100
        with rasterio.open(ortho) as src:
            size = int(2 * h / ORTHO_RES)
            rgb = src.read([1, 2, 3], window=from_bounds(world.e0 - h, world.n0 - h, world.e0 + h, world.n0 + h,
                                                         src.transform),
                           out_shape=(3, size, size), boundless=True, fill_value=0)
        Image.fromarray(rgb.transpose(1, 2, 0)).save(out / "ortofoto.jpg", quality=82)
        backgrounds.append({"name": "Ortofoto", "file": "bg/ortofoto.jpg", "half": h})
    mod_name = project.config.get("mod_name") or f"FS25_{project.name.capitalize()}"
    overview = project.build / mod_name / "maps" / "overview.png"
    if overview.exists():
        backgrounds.append({"name": "Spelets kartbild", "file": "bg/overview.png", "half": world.size})
    catalog = json.loads((CATALOG / "katalog.json").read_text(encoding="utf-8")) if (CATALOG / "katalog.json").exists() else []
    for c in catalog:              # mått saknas i XML-filen: anta 10 × 10 m, kan ändras i editorn
        c["guess"] = not (c.get("width") and c.get("length"))
        if c["guess"]:
            c["width"] = c["length"] = DEFAULT_SIZE
    return {"title": project.config.get("title", project.name), "half": world.half,
            "buildings": blds, "backgrounds": backgrounds, "catalog": catalog}, overview


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    project = open_map(args.map)

    import build_map as bm
    world = bm.World(project)
    out = project.build / "editor"
    print("Förbereder byggnader och bakgrunder ...")
    data, overview = prepare(project, world, out)
    print(f"  {len(data['buildings'])} byggnader, {len(data['catalog'])} moddbyggnader i katalogen")
    if not data["catalog"]:
        print("  Katalogen saknas eller är tom: kör först python scripts/mod_katalog.py data/mods", file=sys.stderr)
    store = project.dir / "byggnader.json"
    build = {"running": False, "log": ""}

    def run_build():
        build.update(running=True, log="")
        proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "build_map.py"), "--map", project.name],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            build["log"] += line
        build["log"] += f"\nKlart (kod {proc.wait()})."
        build["running"] = False

    files = {"/": (TEMPLATE, "text/html; charset=utf-8"),
             "/bg/ortofoto.jpg": (out / "ortofoto.jpg", "image/jpeg"),
             "/bg/overview.png": (overview, "image/png")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/data":
                placed = json.loads(store.read_text(encoding="utf-8")) if store.exists() else []
                return self.send(200, json.dumps({**data, "placed": placed}).encode())
            if path == "/api/build":
                return self.send(200, json.dumps(build).encode())
            if path in files and files[path][0].exists():
                return self.send(200, files[path][0].read_bytes(), files[path][1])
            if path.startswith("/img/"):
                f = (CATALOG / "img" / Path(path).name)
                if f.exists():
                    return self.send(200, f.read_bytes(), "image/png")
            self.send(404, b"{}")

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
            if self.path == "/api/save":
                placed = json.loads(body or b"[]")
                store.write_text(json.dumps(placed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                return self.send(200, json.dumps({"ok": True, "count": len(placed)}).encode())
            if self.path == "/api/build" and not build["running"]:
                threading.Thread(target=run_build, daemon=True).start()
                return self.send(200, b'{"started": true}')
            self.send(409, b"{}")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Byggeditorn körs. Öppna http://<serverns namn eller IP>:{args.port} i webbläsaren. Avsluta med Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
