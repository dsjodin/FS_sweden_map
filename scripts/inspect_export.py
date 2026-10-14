#!/usr/bin/env python3
"""Läser av en FS25-kartexport (till exempel från MapToPlay) och skriver en
rapport över filer, bilder och XML-struktur. Rapporten visar vilka filer en
fungerande karta består av, så att vi kan generera dem själva.

Rapporten innehåller inga bilder eller modeller, bara namn, storlekar och
struktur. Den är liten nog att checka in eller klistra in.

Användning:
    python scripts/inspect_export.py SÖKVÄG_TILL_ZIP_ELLER_MAPP [--out rapport.md]

Exempel:
    python scripts/inspect_export.py ~/FS25_Tysslinge.zip --out docs/fs25_export_tysslinge.md
"""
import argparse
import io
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # rapporten går att göra utan bildinfo
    Image = None

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp"}
XML_EXT = {".xml", ".i3d"}
MAX_FULL_XML = 200  # rader; mindre XML-filer skrivs ut i sin helhet


def human(n):
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def image_info(path):
    ext = path.suffix.lower()
    try:
        if ext == ".dds":
            with open(path, "rb") as f:
                head = f.read(128)
            if head[:4] == b"DDS ":
                height, width = struct.unpack("<II", head[12:20])
                fourcc = head[84:88].decode("ascii", "replace").strip("\x00")
                return f"{width}×{height} DDS {fourcc or 'okomprimerad'}"
        if Image and ext in IMAGE_EXT:
            with Image.open(path) as im:
                return f"{im.width}×{im.height} {im.mode}"
        if ext in (".gdm", ".grle"):
            with open(path, "rb") as f:
                head = f.read(16)
            return f"GIANTS-format, huvud {head[:8].hex()}"
    except Exception as exc:
        return f"kunde inte läsas ({exc})"
    return None


def short_attrs(el, limit=12):
    items = list(el.attrib.items())
    text = " ".join(f'{k}="{v[:60]}"' for k, v in items[:limit])
    return text + (" …" if len(items) > limit else "")


def outline(el, depth=0, max_depth=3, out=None, max_children=12):
    """Trädstruktur: taggar med attribut, upprepade syskon sammanfattas."""
    out = out if out is not None else []
    out.append("  " * depth + f"<{el.tag} {short_attrs(el)}>".replace(" >", ">"))
    if depth >= max_depth:
        if len(el):
            counts = Counter(c.tag for c in el.iter() if c is not el)
            out.append("  " * (depth + 1) + "… " + ", ".join(f"{t}×{n}" for t, n in counts.most_common(8)))
        return out
    shown = Counter()
    for child in el:
        shown[child.tag] += 1
        if shown[child.tag] <= 3 and sum(shown.values()) <= max_children:
            outline(child, depth + 1, max_depth, out, max_children)
    extra = {t: n - 3 for t, n in shown.items() if n > 3}
    hidden = sum(shown.values()) - min(sum(shown.values()), max_children)
    if extra or hidden > 0:
        out.append("  " * (depth + 1) + "… fler: " + ", ".join(f"{t}×{n}" for t, n in shown.items()))
    return out


def i3d_report(path, lines):
    root = ET.parse(path).getroot()
    lines.append(f"Rot: `<{root.tag} {short_attrs(root)}>`\n")
    files = root.find("Files")
    if files is not None:
        names = [f.get("filename", "") for f in files]
        lines.append(f"**Files:** {len(names)} st")
        by_dir = Counter(str(Path(n).parent) for n in names)
        for d, n in by_dir.most_common(25):
            lines.append(f"- `{d}/` {n}")
        local = [n for n in names if not n.startswith("$")]
        lines.append("\nLokala filer (inte från spelets $data):")
        lines += [f"- `{n}`" for n in local[:80]]
        if len(local) > 80:
            lines.append(f"- … och {len(local) - 80} till")
        lines.append("")
    for tag in ("TerrainTransformGroup", "Layers", "InfoLayer", "FoliageMultiLayer", "FoliageType", "DetailLayer"):
        found = list(root.iter(tag))
        if found:
            lines.append(f"**{tag}:** {len(found)} st")
            lines.append("```xml")
            lines += outline(found[0], max_depth=2)
            lines.append("```")
    scene = root.find("Scene")
    if scene is not None:
        lines.append("**Scene, översta nivån:**")
        lines.append("```xml")
        for child in scene:
            counts = Counter(c.tag for c in child.iter())
            lines.append(f"<{child.tag} {short_attrs(child, 4)}>  ({', '.join(f'{t}×{n}' for t, n in counts.most_common(5))})")
        lines.append("```")
    user_attrs = root.find("UserAttributes")
    if user_attrs is not None:
        lines.append(f"**UserAttributes:** {len(user_attrs)} st")
        lines.append("```xml")
        lines += outline(user_attrs, max_depth=2)
        lines.append("```")


def xml_report(path, lines):
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = text.splitlines()
    if len(rows) <= MAX_FULL_XML:
        lines.append("```xml")
        lines += rows
        lines.append("```")
    else:
        root = ET.fromstring(text)
        lines.append(f"{len(rows)} rader, visar struktur:")
        lines.append("```xml")
        lines += outline(root, max_depth=3)
        lines.append("```")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="zip-fil eller uppackad mapp")
    parser.add_argument("--out", help="skriv rapporten till fil (annars skärmen)")
    args = parser.parse_args()

    src = Path(args.source).expanduser()
    tmp = None
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp.name)
        base = Path(tmp.name)
    elif src.is_dir():
        base = src
    else:
        sys.exit(f"Hittar inte {src} (ange en zip-fil eller en mapp).")

    files = sorted(p for p in base.rglob("*") if p.is_file())
    lines = [f"# Rapport över FS25-export: {src.name}", ""]
    lines.append(f"{len(files)} filer, totalt {human(sum(p.stat().st_size for p in files))}.\n")

    # Översikt per mapp.
    per_dir = defaultdict(lambda: [0, 0, Counter()])
    for p in files:
        d = per_dir[str(p.parent.relative_to(base))]
        d[0] += 1
        d[1] += p.stat().st_size
        d[2][p.suffix.lower() or "(ingen)"] += 1
    lines.append("## Mappar\n")
    lines.append("| Mapp | Filer | Storlek | Filtyper |")
    lines.append("|---|---|---|---|")
    for d, (n, size, exts) in sorted(per_dir.items()):
        lines.append(f"| `{d}` | {n} | {human(size)} | {', '.join(f'{e}×{c}' for e, c in exts.most_common(6))} |")

    # Alla filer utom stora modell- och texturbibliotek, med bildinfo.
    lines.append("\n## Filer\n")
    lines.append("| Fil | Storlek | Info |")
    lines.append("|---|---|---|")
    for p in files:
        rel = p.relative_to(base)
        if per_dir[str(rel.parent)][0] > 60 and p.suffix.lower() not in XML_EXT:
            continue  # stora mappar med modeller/texturer sammanfattas ovan
        lines.append(f"| `{rel}` | {human(p.stat().st_size)} | {image_info(p) or ''} |")

    # XML och i3d.
    lines.append("\n## XML och i3d\n")
    for p in files:
        if p.suffix.lower() not in XML_EXT:
            continue
        rel = p.relative_to(base)
        if per_dir[str(rel.parent)][0] > 60 and "map" not in rel.parts[:2]:
            continue
        lines.append(f"### `{rel}`\n")
        try:
            if p.suffix.lower() == ".i3d" and p.stat().st_size > 200_000:
                i3d_report(p, lines)
            else:
                xml_report(p, lines)
        except ET.ParseError as exc:
            lines.append(f"Kunde inte tolkas som XML: {exc}")
        lines.append("")

    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"Skrev {args.out} ({human(len(report.encode()))})")
    else:
        sys.stdout.write(report)
    if tmp:
        tmp.cleanup()


if __name__ == "__main__":
    main()
