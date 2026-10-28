#!/usr/bin/env python3
"""Visa uppbyggnaden av en i3d-fil: filer, material och nodträdet med de attribut
som avgör hur modellen kan användas i kartan (shapeId, splitType, kollision, LOD,
synavstånd) och nodernas UserAttributes.

Tar en i3d-fil eller en zip (alla i3d-filer i den visas). Läser bara, ändrar inget.

Användning:
    python scripts/i3d_info.py data/mods/FS25_sprucepack_prefab.zip
    python scripts/i3d_info.py modell.i3d [--djup 6]
"""
import argparse
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NODES = ("TransformGroup", "Shape", "ReferenceNode", "Light", "Camera", "Dynamic", "Terrain")
SHOWN = ("shapeId", "referenceId", "splitType", "static", "dynamic", "kinematic", "compound", "compoundChild",
         "collision", "collisionMask", "collisionFilterGroup", "collisionFilterMask", "trigger",
         "clipDistance", "lodDistance", "castsShadows", "receiveShadows", "nonRenderable", "visibility",
         "materialIds", "translation", "rotation", "scale", "density", "objectMask")


def show(name, data, depth):
    root = ET.fromstring(data)
    print(f"=== {name} ({len(data) // 1024} kB) ===")
    files = {f.get("fileId"): f.get("filename") for f in root.iter("File")}
    print("Filer:")
    for fid, fn in files.items():
        print(f"  {fid}: {fn}")
    print("Material:")
    for m in root.iter("Material"):
        refs = {c.tag: files.get(c.get("fileId"), c.get("fileId")) for c in m}
        print(f"  {m.get('materialId')}: {m.get('name')}  "
              + "  ".join(f"{k}={v}" for k, v in refs.items()))
    shapes = root.find("Shapes")
    if shapes is not None:
        print("Shapes:", shapes.get("externalShapesFile") or f"{len(shapes)} st i filen")
    attrs = {}
    for ua in root.iter("UserAttribute"):
        attrs[ua.get("nodeId")] = {a.get("name"): a.get("value") for a in ua}
    print("Scen:")

    def walk(node, level):
        for child in node:
            if child.tag not in NODES:
                continue
            extra = "  ".join(f"{k}={child.get(k)}" for k in SHOWN if child.get(k) is not None)
            print(f"{'  ' * (level + 1)}{child.tag} '{child.get('name')}' [{child.get('nodeId')}]  {extra}")
            if child.get("nodeId") in attrs:
                print(f"{'  ' * (level + 2)}UserAttribute: {attrs[child.get('nodeId')]}")
            if level + 1 < depth:
                walk(child, level + 1)
            elif len(child):
                print(f"{'  ' * (level + 2)}... {sum(1 for _ in child.iter()) - 1} noder till")
    scene = root.find("Scene")
    if scene is not None:
        walk(scene, 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--djup", type=int, default=6, help="hur många nivåer av nodträdet som visas")
    args = parser.parse_args()
    if zipfile.is_zipfile(args.path):
        with zipfile.ZipFile(args.path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".i3d")]
            if not names:
                sys.exit("Inga i3d-filer i zip-filen.")
            for n in names:
                show(n, z.read(n), args.djup)
    else:
        show(args.path.name, args.path.read_bytes(), args.djup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
