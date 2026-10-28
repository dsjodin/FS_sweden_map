"""Träd ur prefab-paket som kopieras in i kartan, för arter som FS25 saknar (gran).

Ett prefab-paket är en i3d-fil med flera träd bredvid varandra, med en gemensam
.i3d.shapes-fil och texturer (avläst ur FS25_sprucepack_prefab.zip med i3d_info.py):

    Scene / TransformGroup 'spruce' / TransformGroup 'spruceVar01_stage01' / Shape 'LOD0' (splitType=1) ...

Kartans träd är ReferenceNodes som pekar på en i3d-fil per träd (fs25_objects.add_trees).
En referens till paketets fil skulle sätta ut alla träden på en gång, så install delar
paketet i en i3d-fil per träd, med trädet flyttat till origo. Alla filerna pekar på samma
shapes-fil och texturer, som kopieras bredvid:

    maps/trees/spruce/spruce_var01_stage01.i3d ... sprucepack.i3d.shapes, textures/

Stammen har splitType 1 (gran), så träden kan fällas och säljas som gran.
Paketen läggs i data/mods (eller en undermapp där), precis som moddarna.
"""
import copy
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath

from area import ROOT

MODS = ROOT / "data" / "mods"
TREE_NODE = re.compile(r"(?i)var_?0*(\d+)_stage0*(\d+)$")


def find_pack(zip_name):
    hits = sorted(MODS.rglob(zip_name)) if MODS.exists() else []
    return hits[0] if hits else None


def stage_name(art, node_name):
    """'spruceVar01_stage02' -> 'spruce_var01_stage02', eller None om namnet inte är ett träd."""
    m = TREE_NODE.search(node_name or "")
    return f"{art}_var{int(m.group(1)):02d}_stage{int(m.group(2)):02d}" if m else None


def split_pack(data, art):
    """{filnamn utan .i3d: i3d-fil (bytes)} med ett träd per fil, ur paketets i3d-fil."""
    root = ET.fromstring(data)
    scene = root.find("Scene")
    trees = [(stage_name(art, n.get("name")), n) for n in scene.iter("TransformGroup")]
    out = {}
    for name, node in trees:
        if not name:
            continue
        one = copy.deepcopy(root)
        one_scene = one.find("Scene")
        for child in list(one_scene):
            one_scene.remove(child)
        tree = copy.deepcopy(node)
        tree.set("translation", "0 0 0")
        one_scene.append(tree)
        keep = {n.get("nodeId") for n in tree.iter()}
        uas = one.find("UserAttributes")
        if uas is not None:
            for ua in list(uas):
                if ua.get("nodeId") not in keep:
                    uas.remove(ua)
        out[name] = ET.tostring(one, encoding="iso-8859-1", xml_declaration=True)
    return out


def install(maps_dir, packs):
    """Kopierar in de paket som finns i data/mods. packs: {art: {"zip": ..., "stages": [...]}}.
    Returnerar de arter som kom med; för övriga skrivs varför."""
    installed = set()
    for art, pack in packs.items():
        target = maps_dir / "trees" / art
        shutil.rmtree(target, ignore_errors=True)
        path = find_pack(pack["zip"])
        if path is None:
            print(f"  {pack['zip']} finns inte i data/mods: {art} ersätts med tall")
            continue
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            i3d = [n for n in names if n.lower().endswith(".i3d")]
            if len(i3d) != 1:
                print(f"  {path.name}: väntade en i3d-fil, hittade {len(i3d)}. {art} ersätts med tall")
                continue
            base = PurePosixPath(i3d[0]).parent
            files = split_pack(z.read(i3d[0]), art)
            missing = [s for s in pack["stages"] if f"{art}_{s}" not in files]
            if missing:
                print(f"  {path.name}: saknar {', '.join(missing)}. {art} ersätts med tall")
                continue
            target.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                (target / f"{name}.i3d").write_bytes(text)
            for n in names:                       # shapes-filen och texturerna, med samma sökvägar som i paketet
                p = PurePosixPath(n)
                if n.endswith("/") or p.suffix.lower() == ".i3d" or ".." in p.parts or not p.is_relative_to(base):
                    continue
                rel = p.relative_to(base)
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(n))
        installed.add(art)
        print(f"  {art}: {len(files)} träd ur {path.name}")
    return installed
