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


class FolderMod:
    """Uppackad modd (mapp med modDesc.xml) med samma gränssnitt som ZipFile."""

    def __init__(self, root):
        self.root = Path(root)

    def namelist(self):
        return [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]

    def read(self, name):
        return (self.root / name).read_bytes()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SubZip:
    """En mapp inuti en zip-fil, som om den vore zip-filens rot."""

    def __init__(self, z, prefix):
        self.z, self.prefix = z, prefix

    def namelist(self):
        return [n[len(self.prefix):] for n in self.z.namelist() if n.startswith(self.prefix) and n != self.prefix]

    def read(self, name):
        return self.z.read(self.prefix + name)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def unwrap(path):
    """[(moddnamn, arkiv, varning)] för en zip-fil. Klarar zip i zip och en mapp överst i
    zip-filen; båda laddar inte i spelet, så de ger en varning."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    if any(n.lower() == "moddesc.xml" for n in names):
        return [(path.stem, z, None)]
    inner = [n for n in names if n.lower().endswith(".zip")]
    if inner:
        out = []
        for n in inner:
            iz = zipfile.ZipFile(io.BytesIO(z.read(n)))
            if any(x.lower() == "moddesc.xml" for x in iz.namelist()):
                out.append((PurePosixPath(n).stem, iz,
                            f"ligger som zip i zip-filen {path.name}. Spelet laddar den inte så: "
                            f"packa ut {PurePosixPath(n).name} och lägg den direkt i mods-mappen."))
        if out:
            return out
    sub = sorted({n.rsplit("/", 1)[0] + "/" for n in names if n.lower().endswith("/moddesc.xml")}, key=len)
    if sub:
        mod = sub[0].rstrip("/").split("/")[-1]
        return [(mod, SubZip(z, sub[0]),
                 f"har en mapp ({sub[0]}) överst i {path.name}. Spelet laddar den inte så: packa upp och "
                 f"zippa om innehållet i mappen, så att modDesc.xml ligger direkt i zip-filen.")]
    return [(path.stem, z, "saknar modDesc.xml")]


def first_tag(text):
    """Namnet på rotelementet, utan XML-deklaration och kommentarer."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<\?.*?\?>", "", text, flags=re.S)
    m = re.search(r"<([A-Za-z_][\w.-]*)", text)
    return m.group(1) if m else ""


def regex_text(text, tag):
    m = re.search(rf"<{tag}\b[^>]*>\s*(?:<en>)?\s*([^<]+)", text)
    return html.unescape(m.group(1).strip()) if m else ""


def parse_placeable(data):
    """Byggnadens uppgifter, eller None om filen inte är en byggnad. Klarar XML som
    ElementTree inte kan läsa (läser då med reguljära uttryck)."""
    text = data.decode("utf-8", "replace").lstrip("\ufeff")
    if first_tag(text[:50000]) != "placeable":
        return None
    w = l = None
    for tag in re.findall(r"<size\b[^>]*>", text):        # base/size, eller var den nu ligger
        mw, ml = re.search(r'width="([\d.]+)"', tag), re.search(r'length="([\d.]+)"', tag)
        if mw and ml:
            w, l = float(mw.group(1)), float(ml.group(1))
            break
    sd = text[text.find("<storeData"):text.find("</storeData>")] if "<storeData" in text else ""
    mtype = re.search(r'<placeable\b[^>]*\btype="([^"]*)"', text)
    return {"name": regex_text(sd, "name"), "category": regex_text(sd, "category"),
            "price": regex_text(sd, "price"), "image": regex_text(sd, "image"),
            "width": w, "length": l, "type": mtype.group(1) if mtype else ""}


AREA_NODE = re.compile(r"(level|test|clear)area", re.I)


def size_from_i3d(z, xml_name, text):
    """Grundytan ur byggnadens modellfil när <size> saknas: utbredningen (x, z) för
    hjälppunkterna som planar marken och spärrar ytan (levelArea, testArea, clearArea)."""
    import math
    m = re.search(r"<base\b.*?<filename>\s*([^<]+?)\s*</filename>", text, re.S) or \
        re.search(r"<filename>\s*([^<]+?\.i3d)\s*</filename>", text)
    if not m:
        return None
    ref = m.group(1).replace("\\", "/").replace("$moddir$", "")
    names = {n.lower(): n for n in z.namelist()}
    hit = names.get(ref.lower().lstrip("./")) or names.get(str(PurePosixPath(xml_name).parent / ref).lower())
    if not hit:
        return None
    try:
        root = ET.fromstring(z.read(hit))
    except ET.ParseError:
        return None
    pts = []

    def walk(node, ox, oz, yaw, inside):
        for child in node:
            if child.tag not in ("TransformGroup", "Shape", "ReferenceNode", "Light", "Camera"):
                continue
            t = [float(v) for v in (child.get("translation") or "0 0 0").split()]
            r = [float(v) for v in (child.get("rotation") or "0 0 0").split()]
            c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            x, z_ = ox + t[0] * c + t[2] * s_, oz - t[0] * s_ + t[2] * c
            here = inside or bool(AREA_NODE.search(child.get("name", "")))
            if here:
                pts.append((x, z_))
            walk(child, x, z_, yaw + r[1], here)

    scene = root.find("Scene")
    if scene is None:
        return None
    walk(scene, 0.0, 0.0, 0.0, False)
    if len(pts) < 2:
        return None
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    w, l = max(xs) - min(xs), max(zs) - min(zs)
    return (round(w, 1), round(l, 1)) if w >= 1.5 and l >= 1.5 else None


def find_mods(folder):
    """Zip-filer och uppackade moddar (mappar med modDesc.xml), även i undermappar."""
    zips = sorted(folder.rglob("*.zip"))
    dirs = sorted({p.parent for p in folder.rglob("modDesc.xml")})
    return [(z.stem, z) for z in zips] + [(d.name, d) for d in dirs]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="mapp med moddarna (zip-filer eller uppackade mappar)")
    parser.add_argument("--sok", nargs="*", help="ta bara med moddar vars namn innehåller något av orden")
    parser.add_argument("--visa-ovriga", action="store_true", help="lista xml-filer som inte räknades som byggnader")
    args = parser.parse_args()
    folder = Path(args.folder).expanduser()
    mods = find_mods(folder)
    if args.sok:
        mods = [(m, p) for m, p in mods if any(w.lower() in m.lower() for w in args.sok)]
    if not mods:
        sys.exit(f"Inga moddar (zip-filer eller mappar med modDesc.xml) i {folder}.")
    print(f"{len(mods)} moddar i {folder}")
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    items = []
    archives = []
    for mod, path in mods:
        if path.is_dir():
            archives.append((mod, FolderMod(path), None))
            continue
        try:
            archives += unwrap(path)
        except zipfile.BadZipFile:
            print(f"  {path.name}: inte en zip-fil, hoppar över", file=sys.stderr)
    for mod, z, warning in archives:
        if warning:
            print(f"  OBS: {mod} {warning}")
        n_xml = n_found = 0
        with z:
            l10n = translations(z, "")
            for name in z.namelist():
                if not name.lower().endswith(".xml") or name.lower().endswith("moddesc.xml"):
                    continue
                n_xml += 1
                data = z.read(name)
                info = parse_placeable(data)
                if info is None:
                    if args.visa_ovriga:
                        tag = first_tag(data.decode("utf-8", "replace")[:50000])
                        print(f"    inte en byggnad: {name} (rotelement <{tag}>)")
                    continue
                n_found += 1
                info["size_from"] = "xml" if info["width"] else None
                if not info["width"]:
                    size = size_from_i3d(z, name, data.decode("utf-8", "replace"))
                    if size:
                        info["width"], info["length"], info["size_from"] = size[0], size[1], "i3d"
                if info["name"].startswith("$l10n_"):
                    info["name"] = l10n.get(info["name"][6:], info["name"])
                if not info["name"] or info["name"].startswith("$l10n_"):   # spelets egna textnycklar
                    info["name"] = PurePosixPath(name).stem
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
        mine = [i for i in items if i["mod"] == mod]
        print(f"  {mod}: {n_xml} xml-filer, {n_found} byggnader, {sum(1 for i in mine if i['width'])} med mått "
              f"({sum(1 for i in mine if i['size_from'] == 'i3d')} ur modellfilen), "
              f"{sum(1 for i in mine if i['thumb'])} med bild")

    cards = []
    for it in sorted(items, key=lambda i: (i["mod"], i["name"])):
        size = f"{it['width']:g} × {it['length']:g} m" if it["width"] and it["length"] else "mått saknas"
        if it.get("size_from") == "i3d":
            size += " (ur modellfilen)"
        text = " ".join(str(it[k]) for k in ("name", "mod", "category", "file", "type")).lower()
        img = (f'<img src="{it["thumb"]}" loading="lazy" alt="">' if it["thumb"]
               else '<div class="noimg">ingen bild</div>')
        cards.append(
            f'<div class="card" data-text="{html.escape(text)}">{img}<div class="body">'
            f'<div class="name">{html.escape(it["name"] or PurePosixPath(it["file"]).stem)}</div>'
            f'<div class="size">{size}</div>'
            f'<div class="meta">{html.escape(it["category"])} · pris {html.escape(it["price"])}<br>'
            f'{html.escape(it["mod"])}<br>{html.escape(it["file"])}</div></div></div>')
    (OUT / "index.html").write_text(PAGE.replace("__COUNT__", str(len(items))).replace("__MODS__", str(len(mods)))
                                    .replace("__CARDS__", "\n".join(cards)), encoding="utf-8")
    (OUT / "katalog.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {OUT.relative_to(ROOT)}/index.html ({len(items)} byggnader, "
          f"{sum(1 for i in items if i['thumb'])} med bild)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
