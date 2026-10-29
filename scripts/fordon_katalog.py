#!/usr/bin/env python3
"""Katalog över maskiner (fordon och redskap) för byggeditorns Maskiner-läge.

Läser spelets egna maskiner ur zip-filen från tools/fordon_export.ps1 (data/fordon/*.zip,
med data/vehicles/**/*.xml och butiksbilderna) och moddarnas maskiner i data/mods. För varje
maskin: fil (som kartans vehicles.xml skriver den), namn, märke, kategori, pris, mått och
butiksbild.

Resultat:
    build/fordon_katalog/katalog.json   för byggeditorn
    build/fordon_katalog/img/*.png      butiksbilderna i liten storlek

Användning:
    python scripts/fordon_katalog.py
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

from area import ROOT
from mod_katalog import FolderMod, find_image, find_mods, first_tag, regex_text, translations, unwrap

OUT = ROOT / "build" / "fordon_katalog"
GAME_DIR = ROOT / "data" / "fordon"
THUMB = 128


class SlashZip:
    """Zip-fil vars namn kan ha bakåtsnedstreck (Compress-Archive i Windows PowerShell 5)."""

    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        self.names = {n.replace("\\", "/"): n for n in self.z.namelist()}

    def namelist(self):
        return list(self.names)

    def read(self, name):
        return self.z.read(self.names[name])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.z.close()
        return False


def parse_vehicle(data):
    """Uppgifterna ur en maskins XML, eller None om filen inte är en maskin som säljs i butiken."""
    text = data.decode("utf-8", "replace")
    if first_tag(text) != "vehicle" or "<storeData" not in text:      # rotelementet, efter kommentarer
        return None
    sd = text[text.find("<storeData"):text.find("</storeData>")]
    if re.search(r"<showInStore>\s*false", sd):
        return None
    w = length = None
    m = re.search(r"<size\b[^>]*>", text[text.find("<base"):] if "<base" in text else text)
    if m:
        mw, ml = re.search(r'width="([\d.]+)"', m.group(0)), re.search(r'length="([\d.]+)"', m.group(0))
        if mw and ml:
            w, length = float(mw.group(1)), float(ml.group(1))
    return {"name": regex_text(sd, "name"), "brand": regex_text(sd, "brand"),
            "category": regex_text(sd, "category"), "price": regex_text(sd, "price"),
            "image": regex_text(sd, "image"), "width": w, "length": length}


def scan(archive, mod, prefix, items):
    """Maskinerna i ett arkiv. prefix: hur kartans vehicles.xml skriver sökvägen."""
    l10n = translations(archive, "") if mod else {}
    n = 0
    for name in archive.namelist():
        if not name.lower().endswith(".xml") or name.lower().endswith("moddesc.xml"):
            continue
        info = parse_vehicle(archive.read(name))
        if info is None:
            continue
        if info["name"].startswith("$l10n_"):
            info["name"] = l10n.get(info["name"][6:], "")
        if not info["name"]:
            info["name"] = PurePosixPath(name).stem
        thumb = None
        ref = info.pop("image")
        img = find_image(archive, name, ref.replace("$data/", "data/") if ref else ref)
        if img:
            try:
                im = Image.open(io.BytesIO(archive.read(img))).convert("RGBA")
                im.thumbnail((THUMB, THUMB))
                thumb = f"img/{len(items):05d}.png"
                im.save(OUT / thumb)
            except Exception:   # noqa: BLE001 - okänt DDS-format: utan bild
                thumb = None
        items.append({**info, "mod": mod, "file": prefix + name, "thumb": thumb})
        n += 1
    return n


def main():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    items = []
    games = sorted(GAME_DIR.glob("*.zip")) if GAME_DIR.exists() else []
    if not games:
        print(f"Ingen export av spelets maskiner i {GAME_DIR.relative_to(ROOT)}. Kör tools/fordon_export.ps1 "
              "på Windows och kopiera zip-filen dit. Tar bara med moddarnas maskiner.")
    for path in games:
        with SlashZip(path) as z:
            print(f"  spelets maskiner ({path.name}): {scan(z, None, '', items)}")
    mods = ROOT / "data" / "mods"
    found, without = set(), []
    for mod, path in find_mods(mods) if mods.exists() else []:
        archives = [(mod, FolderMod(path), None)] if path.is_dir() else []
        if not path.is_dir():
            try:
                archives = unwrap(path)
            except zipfile.BadZipFile:
                print(f"  {path.name}: inte en zip-fil, hoppar över")
                continue
        for name, archive, warning in archives:
            with archive:
                n = scan(archive, name, f"$moddir${name}/", items)
            found.add(name)
            if warning:
                print(f"  OBS: {name} {warning}")
            if n:
                print(f"  {name}: {n}")
            else:
                without.append(name)
    print(f"{len(found)} moddar i {mods.relative_to(ROOT)}, {len(without)} utan maskiner (byggnader med mera): "
          + ", ".join(sorted(without)))
    import fordon                                    # moddar som startmaskinerna kräver men som saknas här
    used = {v["file"].split("/")[0].replace("$moddir$", "") for v in fordon.read(ROOT / "maps" / "tysslinge" / "fordon.xml")
            if v["file"].startswith("$moddir$")} if (ROOT / "maps" / "tysslinge" / "fordon.xml").exists() else set()
    if used - found:
        print("Moddar i startmaskinerna som saknas i data/mods: " + ", ".join(sorted(used - found)))
    (OUT / "katalog.json").write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    cats = {}
    for i in items:
        cats[i["category"] or "?"] = cats.get(i["category"] or "?", 0) + 1
    print("Kategorier: " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items())))
    print(f"{len(items)} maskiner, {sum(1 for i in items if i['width'])} med mått, "
          f"{sum(1 for i in items if i['thumb'])} med bild. Skrev {OUT.relative_to(ROOT)}/katalog.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
