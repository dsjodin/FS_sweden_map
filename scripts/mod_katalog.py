#!/usr/bin/env python3
"""Bildkatalog över byggnader (placeables) i FS25-moddar.

Går igenom moddarnas zip-filer, hittar alla byggnader och gör en webbsida med
butiksbild, namn, mått, kategori, pris, modd och fil för varje byggnad. Då går
det att se vilken fil som är vilken byggnad, och välja vilka som ska användas
i kartan. Måtten läses ur byggnadens XML (<base><size width length>), så de
behöver inte gissas.

Resultat:
    build/mod_katalog/index.html     katalogen (öppna i webbläsaren)
    build/mod_katalog/katalog.json   samma uppgifter för skripten

Användning:
    python scripts/mod_katalog.py MAPP_MED_MODDAR
    python scripts/mod_katalog.py data/mods --sok barn house shed
"""
import argparse
import html
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

from area import ROOT

OUT = ROOT / "build" / "mod_katalog"
THUMB = 256

PAGE = """<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Byggnader i moddar</title>
<style>
  :root { --bg: #f4f2ec; --card: #fff; --fg: #1f2421; --muted: #6a706b; --line: #ddd8cc; --accent: #2f6b3a; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
    --bg: #1b1f1c; --card: #252b27; --fg: #e9ece8; --muted: #a2aaa3; --line: #38403a; --accent: #7fc48c; } }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.4 system-ui, sans-serif; }
  header { position: sticky; top: 0; background: var(--bg); padding: 12px 16px; border-bottom: 1px solid var(--line); z-index: 1; }
  input { width: 100%; max-width: 420px; padding: 8px 10px; font-size: 15px; border: 1px solid var(--line);
          border-radius: 6px; background: var(--card); color: var(--fg); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; padding: 16px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  .card img { width: 100%; aspect-ratio: 1; object-fit: contain; background: #0001; display: block; }
  .noimg { aspect-ratio: 1; display: grid; place-items: center; color: var(--muted); }
  .body { padding: 8px 10px 10px; }
  .name { font-weight: 600; }
  .size { color: var(--accent); font-weight: 600; }
  .meta { color: var(--muted); font-size: 12px; word-break: break-all; }
</style></head>
<body>
<header><b>__COUNT__ byggnader</b> i __MODS__ moddar &nbsp;
<input id="q" placeholder="Sök: namn, modd, kategori, fil …" autofocus></header>
<div class="grid" id="grid">__CARDS__</div>
<script>
const cards = [...document.querySelectorAll('.card')];
document.getElementById('q').addEventListener('input', e => {
  const words = e.target.value.toLowerCase().split(/\\s+/).filter(Boolean);
  cards.forEach(c => c.style.display = words.every(w => c.dataset.text.includes(w)) ? '' : 'none');
});
</script></body></html>
"""


def text_of(el, path):
    node = el.find(path) if el is not None else None
    if node is None:
        return ""
    en = node.find("en")
    return ((en.text if en is not None else node.text) or "").strip()


def translations(z, root_prefix):
    """l10n-texter ur modDesc.xml och translations/*_en.xml (namn som börjar med $l10n_)."""
    out = {}
    names = [n for n in z.namelist() if n.lower().endswith("moddesc.xml")
             or re.search(r"(translation|l10n)[^/]*_en\.xml$", n, re.I)]
    for n in names:
        try:
            r = ET.fromstring(z.read(n))
        except ET.ParseError:
            continue
        for t in r.iter("text"):
            key = t.get("name")
            if not key:
                continue
            en = t.find("en")
            val = (en.text if en is not None else t.get("text") or t.text) or ""
            if val.strip():
                out.setdefault(key, val.strip())
    return out


def find_image(z, xml_name, ref):
    """Butiksbilden: sökvägen är relativ till moddens rot; spelet byter .png mot .dds."""
    if not ref:
        return None
    ref = ref.replace("\\", "/").replace("$moddir$", "")
    names = {n.lower(): n for n in z.namelist()}
    stem = str(PurePosixPath(ref).with_suffix(""))
    for cand in (ref, stem + ".dds", stem + ".png", str(PurePosixPath(xml_name).parent / ref)):
        hit = names.get(cand.lower().lstrip("./"))
        if hit:
            return hit
    base = PurePosixPath(stem).name.lower()
    for low, n in names.items():
        if PurePosixPath(low).stem == base and low.endswith((".dds", ".png")):
            return n
    return None


def parse_placeable(data):
    try:
        r = ET.fromstring(data)
    except ET.ParseError:
        return None
    if r.tag != "placeable":
        return None
    sd = r.find("storeData")
    size = r.find("base/size")
    w = l = None
    if size is not None:
        w, l = size.get("width"), size.get("length")
    return {
        "name": text_of(sd, "name"), "category": text_of(sd, "category"),
        "price": text_of(sd, "price"), "image": text_of(sd, "image"),
        "width": float(w) if w else None, "length": float(l) if l else None,
        "type": r.get("type", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="mapp med moddarnas zip-filer")
    parser.add_argument("--sok", nargs="*", help="ta bara med moddar vars filnamn innehåller något av orden")
    args = parser.parse_args()
    folder = Path(args.folder).expanduser()
    zips = sorted(folder.glob("*.zip"))
    if args.sok:
        zips = [z for z in zips if any(w.lower() in z.name.lower() for w in args.sok)]
    if not zips:
        sys.exit(f"Inga zip-filer i {folder}.")
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    items = []
    for zpath in zips:
        mod = zpath.stem
        try:
            z = zipfile.ZipFile(zpath)
        except zipfile.BadZipFile:
            print(f"  {zpath.name}: inte en zip-fil, hoppar över", file=sys.stderr)
            continue
        with z:
            l10n = translations(z, "")
            for name in z.namelist():
                if not name.lower().endswith(".xml") or name.lower().endswith("moddesc.xml"):
                    continue
                data = z.read(name)
                if b"<placeable" not in data[:2000]:
                    continue
                info = parse_placeable(data)
                if info is None:
                    continue
                if info["name"].startswith("$l10n_"):
                    info["name"] = l10n.get(info["name"][6:], info["name"])
                img_name = find_image(z, name, info["image"])
                thumb = None
                if img_name:
                    try:
                        im = Image.open(io.BytesIO(z.read(img_name))).convert("RGBA")
                        im.thumbnail((THUMB, THUMB))
                        thumb = f"img/{len(items):04d}.png"
                        im.save(OUT / thumb)
                    except Exception:   # noqa: BLE001 - okänt DDS-format: visa utan bild
                        thumb = None
                items.append({**info, "mod": mod, "file": name, "path": f"$moddir${mod}/{name}", "thumb": thumb})
        print(f"  {mod}: {sum(i['mod'] == mod for i in items)} byggnader")

    cards = []
    for it in sorted(items, key=lambda i: (i["mod"], i["name"])):
        size = f"{it['width']:g} × {it['length']:g} m" if it["width"] and it["length"] else "mått saknas"
        text = " ".join(str(it[k]) for k in ("name", "mod", "category", "file", "type")).lower()
        img = (f'<img src="{it["thumb"]}" loading="lazy" alt="">' if it["thumb"]
               else '<div class="noimg">ingen bild</div>')
        cards.append(
            f'<div class="card" data-text="{html.escape(text)}">{img}<div class="body">'
            f'<div class="name">{html.escape(it["name"] or PurePosixPath(it["file"]).stem)}</div>'
            f'<div class="size">{size}</div>'
            f'<div class="meta">{html.escape(it["category"])} · pris {html.escape(it["price"])}<br>'
            f'{html.escape(it["mod"])}<br>{html.escape(it["file"])}</div></div></div>')
    (OUT / "index.html").write_text(PAGE.replace("__COUNT__", str(len(items))).replace("__MODS__", str(len(zips)))
                                    .replace("__CARDS__", "\n".join(cards)), encoding="utf-8")
    (OUT / "katalog.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {OUT.relative_to(ROOT)}/index.html ({len(items)} byggnader, "
          f"{sum(1 for i in items if i['thumb'])} med bild)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
