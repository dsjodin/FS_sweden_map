"""Startgårdens maskiner: läsa maps/<namn>/fordon.xml och tillämpa byggeditorns ändringar.

fordon.xml kommer från import_savegame.py --fordon och har samma format som en sparfils
vehicles.xml: <vehicle filename uniqueId ...> med en <component index position rotation> per
del, och övriga element (till exempel attachments) som knyter ihop påkopplade maskiner.

Byggeditorns Maskiner-läge sparar ändringarna i maps/<namn>/fordon_andringar.json:
    {"flytt": {id: {"a": grader moturs, "tx": m, "ty": m}},   ny plats = R(a) · gammal + (tx, ty)
     "bort": [id, ...],
     "nya": [{"id", "file", "mod", "name", "x", "y", "rot"}, ...],
     "lankar": [[id, id], ...], "lossa": [id, ...]}
Flytten sparas per maskin (x österut, y norrut från kartans mitt), så att maskiner kan kopplas
ihop och isär i editorn utan att något hoppar. Grupperna (påkopplade redskap, maskiner lastade
på en vagn, egna kopplingar) används bara i editorn för att flytta och vrida flera på en gång.
Äldre filer med flytt per grupp ({"dx", "dy", "rot"} runt gruppens första maskin) räknas om av
normalize.

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
    """Maskinerna för byggeditorn: id, fil, grupp (påkopplade redskap), första delens läge
    (x österut, y norrut från kartans mitt), höjd h och vridning (spelets y-vridning, som byggnaderna)."""
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    group = groups(root)
    out = []
    for v in root.findall("vehicle"):
        comp = v.find("component")
        if comp is None:
            continue
        x, y, z = floats(comp.get("position"))
        out.append({"id": v.get("uniqueId"), "file": v.get("filename", ""), "group": group[v.get("uniqueId")],
                    "x": round(x, 2), "y": round(-z, 2), "h": round(y, 2),
                    "rot": round(yaw(floats(comp.get("rotation"))), 1)})
    return out


def normalize(edits, vehicles):
    """Ändringarna med flytt per maskin. vehicles: read() (för äldre filer med flytt per grupp)."""
    edits = dict(edits or {})
    by_id = {v["id"]: v for v in vehicles}
    flytt = {}
    for key, e in (edits.get("flytt") or {}).items():
        if "dx" not in e:
            flytt[key] = e
            continue
        p = by_id.get(key)
        if p is None:
            continue
        a = math.radians(e.get("rot", 0))
        px, py = p["x"], p["y"]          # vridning runt gruppens första maskin, sedan förflyttning
        t = (px - (math.cos(a) * px - math.sin(a) * py) + e.get("dx", 0),
             py - (math.sin(a) * px + math.cos(a) * py) + e.get("dy", 0))
        for v in vehicles:
            if v["group"] == key:
                flytt[v["id"]] = {"a": e.get("rot", 0), "tx": t[0], "ty": t[1]}
    edits["flytt"] = flytt
    for i, n in enumerate(edits.get("nya", [])):
        n.setdefault("id", f"ny{i}")
    return edits


def apply(text, edits, ground):
    """fordon.xml med ändringarna. ground(x, z) = markens höjd i spelets koordinater; maskiner som
    flyttas behåller sin höjd över marken (en maskin på en vagn står kvar på vagnen)."""
    root = ET.fromstring(text)
    edits = normalize(edits, read_root(root))
    gone = set(edits.get("bort", []))
    for v in list(root.findall("vehicle")):
        if v.get("uniqueId") in gone:
            root.remove(v)
    for el in list(root):                        # kopplingar till borttagna maskiner
        if el.tag != "vehicle" and any(val in gone for sub in el.iter() for val in sub.attrib.values()):
            root.remove(el)

    def move(comp, e, base_ground=None):
        x, y, z = floats(comp.get("position"))
        a = math.radians(e.get("a", 0))
        mx, my = x, -z                            # kartans koordinater
        nx = math.cos(a) * mx - math.sin(a) * my + e.get("tx", 0)
        ny_ = math.sin(a) * mx + math.cos(a) * my + e.get("ty", 0)
        nz = -ny_
        h = y - (ground(x, z) if base_ground is None else base_ground) + ground(nx, nz)
        comp.set("position", f"{nx:.3f} {h:.3f} {nz:.3f}")
        comp.set("rotation", "%.3f %.3f %.3f" % euler(rot_matrix(0, e.get("a", 0), 0)
                                                     @ rot_matrix(*floats(comp.get("rotation")))))
    for v in root.findall("vehicle"):
        e = edits["flytt"].get(v.get("uniqueId"))
        if e:
            for comp in v.findall("component"):
                move(comp, e)
    for n in edits.get("nya", []):
        if n["id"] in gone:
            continue
        x, z = n["x"], -n["y"]
        v = ET.SubElement(root, "vehicle", {"filename": n["file"],
                                            "uniqueId": "vehicle" + hashlib.md5(f"{n['id']} {n['file']}".encode()).hexdigest(),
                                            "age": "0", "price": "0", "farmId": "1", "propertyState": "OWNED",
                                            "defaultFarmProperty": "true"})
        if n.get("mod"):
            v.set("modName", n["mod"])
        comp = ET.SubElement(v, "component", {"index": "1", "position": f"{x:.3f} {ground(x, z) + 0.5:.3f} {z:.3f}",
                                              "rotation": f"0 {n.get('rot', 0):.2f} 0"})
        if n["id"] in edits["flytt"]:
            move(comp, edits["flytt"][n["id"]])
    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def read_root(root):
    """read() för ett redan inläst rotelement."""
    group = groups(root)
    out = []
    for v in root.findall("vehicle"):
        comp = v.find("component")
        if comp is not None:
            x, y, z = floats(comp.get("position"))
            out.append({"id": v.get("uniqueId"), "group": group[v.get("uniqueId")], "x": x, "y": -z})
    return out
