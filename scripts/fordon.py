"""Startgårdens maskiner: läsa maps/<namn>/fordon.xml och tillämpa byggeditorns ändringar.

fordon.xml kommer från import_savegame.py --fordon och har samma format som en sparfils
vehicles.xml: <vehicle filename uniqueId ...> med en <component index position rotation> per
del, och övriga element (till exempel attachments) som knyter ihop påkopplade maskiner.

Byggeditorns Maskiner-läge sparar ändringarna i maps/<namn>/fordon_andringar.json:
    {"flytt": {grupp: {"dx": m österut, "dy": m norrut, "rot": grader moturs}},
     "bort": [uniqueId, ...],
     "nya": [{"file", "mod", "name", "x", "y", "rot", "w", "l"}, ...]}
En grupp är en maskin med allt som är kopplat till den, och nyckeln är gruppens första
maskin. Gruppen vrids runt den maskinens första del.

Spelets vridning "rx ry rz" (grader) motsvarar matrisen Rz · Ry · Rx (avläst: en traktor i
spelets egen karta, "137.54 -86.29 -136.14", står bara plant med den ordningen). En vridning
θ moturs sett ovanifrån är Ry(θ) i spelets koordinater (x österut, z söderut).
"""
import hashlib
import math
import xml.etree.ElementTree as ET

import numpy as np


def rot_matrix(rx, ry, rz):
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def euler(M):
    """rx, ry, rz (grader) för M = Rz · Ry · Rx."""
    ry = math.asin(max(-1.0, min(1.0, -M[2, 0])))
    rx = math.atan2(M[2, 1], M[2, 2])
    rz = math.atan2(M[1, 0], M[0, 0])
    return tuple(math.degrees(v) for v in (rx, ry, rz))


def yaw(rotation):
    """Spelets y-vridning (grader) för maskinens framåtriktning (lokal +z)."""
    f = rot_matrix(*rotation) @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.atan2(f[0], f[2]))


def floats(s):
    return [float(v) for v in (s or "0 0 0").split()]


def groups(root):
    """{uniqueId: gruppens nyckel}: maskiner som nämns i samma element (kopplingar) hör ihop."""
    ids = [v.get("uniqueId") for v in root.findall("vehicle")]
    parent = {i: i for i in ids}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for el in root:
        if el.tag == "vehicle":
            continue
        refs = [v for sub in el.iter() for v in sub.attrib.values() if v in parent]
        for r in refs[1:]:
            a, b = find(refs[0]), find(r)
            if a != b:
                parent[max(a, b, key=ids.index)] = min(a, b, key=ids.index)   # den första blir nyckel
    return {i: find(i) for i in ids}


def read(path):
    """Maskinerna för byggeditorn: id, fil, grupp, första delens läge (x österut, y norrut från
    kartans mitt) och vridning (spelets y-vridning, som byggnaderna)."""
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    group = groups(root)
    out = []
    for v in root.findall("vehicle"):
        comp = v.find("component")
        if comp is None:
            continue
        x, _y, z = floats(comp.get("position"))
        out.append({"id": v.get("uniqueId"), "file": v.get("filename", ""), "group": group[v.get("uniqueId")],
                    "x": round(x, 2), "y": round(-z, 2), "rot": round(yaw(floats(comp.get("rotation"))), 1)})
    return out


def apply(text, edits, ground):
    """fordon.xml med ändringarna. ground(x, z) = markens höjd i spelets koordinater; maskiner som
    flyttas behåller sin höjd över marken."""
    root = ET.fromstring(text)
    group = groups(root)
    gone = set(edits.get("bort", []))
    for v in list(root.findall("vehicle")):
        if v.get("uniqueId") in gone:
            root.remove(v)
    for el in list(root):                        # kopplingar till borttagna maskiner
        if el.tag != "vehicle" and any(val in gone for sub in el.iter() for val in sub.attrib.values()):
            root.remove(el)
    pivots = {}
    for v in root.findall("vehicle"):
        g = group.get(v.get("uniqueId"))
        if g == v.get("uniqueId") and v.find("component") is not None:
            x, _y, z = floats(v.find("component").get("position"))
            pivots[g] = (x, z)
    for v in root.findall("vehicle"):
        g = group.get(v.get("uniqueId"))
        e = edits.get("flytt", {}).get(g)
        if not e or g not in pivots:
            continue
        px, pz = pivots[g]
        th = math.radians(e.get("rot", 0))
        Ry = rot_matrix(0, e.get("rot", 0), 0)
        for comp in v.findall("component"):
            x, y, z = floats(comp.get("position"))
            rx_, rz_ = x - px, z - pz
            nx = px + math.cos(th) * rx_ + math.sin(th) * rz_ + e.get("dx", 0)
            nz = pz - math.sin(th) * rx_ + math.cos(th) * rz_ - e.get("dy", 0)
            ny = y - ground(x, z) + ground(nx, nz)
            comp.set("position", f"{nx:.3f} {ny:.3f} {nz:.3f}")
            comp.set("rotation", "%.3f %.3f %.3f" % euler(Ry @ rot_matrix(*floats(comp.get("rotation")))))
    for i, n in enumerate(edits.get("nya", [])):
        x, z = n["x"], -n["y"]
        v = ET.SubElement(root, "vehicle", {"filename": n["file"], "uniqueId": "vehicle" + hashlib.md5(f"{i} {n['file']}".encode()).hexdigest(),
                                            "age": "0", "price": "0", "farmId": "1", "propertyState": "OWNED",
                                            "defaultFarmProperty": "true"})
        if n.get("mod"):
            v.set("modName", n["mod"])
        ET.SubElement(v, "component", {"index": "1", "position": f"{x:.3f} {ground(x, z) + 0.5:.3f} {z:.3f}",
                                       "rotation": f"0 {n.get('rot', 0):.2f} 0"})
    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
