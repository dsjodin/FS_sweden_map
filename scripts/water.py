"""Vatten i FS25-kartan: vattenytor för sjöar och åar och smala vattenremsor i diken och bäckar.

Terrängen har dikena som svackor men inget vatten. Spelets egna kartor har vatten
som egna ytor (Shape) med spelets vattenshader ($data/shaders/oceanShader.xml) och
onCreate = Environment.onCreateWater, avläst från mapEU:s waterplanes.i3d. Vi bygger
ytorna själva som trianglar direkt i i3d-filen (IndexedTriangleSet) och sänker
terrängen under dem, så att vattnet syns:

- vattenytor (Marktäcke/Topografi: sjö, vattendragsyta, anlagt vatten): ytan följer
  strandens höjd, botten sänks LAKE_DEPTH under ytan
- vattendrag som linjer (Topografi 10): en remsa STREAM_WIDTH bred längs linjen med
  höjden från dikets botten (lägsta terräng intill linjen), i en ränna som sänks
  STREAM_DEPTH under vattnet
"""
import numpy as np
import shapely
from PIL import Image, ImageFilter
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import LineString

STREAM_WIDTH = 2.4       # m, vattenremsans bredd i diken och bäckar
STREAM_DEPTH = 0.7       # m från vattenytan ned till rännans botten
WATER_ABOVE_BOTTOM = 0.3 # m vatten över dikesbottnen
SNAP = 20.0              # m åt sidan där dikets botten söks (Topografi 10:s linjer har 4,5–9,5 m osäkerhet)
EDGE_CLEAR = 0.1         # m som vattnet minst ligger under terrängen strax utanför remsans kanter
CUT_RINGS = ((1.5, 1.0), (2.5, 0.5), (3.5, 0.15))   # (m från mitten, andel av STREAM_DEPTH): mjuk ränna
STREAM_STEP = 4.0        # m mellan punkterna längs remsan
ROAD_GAP = 1.5           # m utanför vägkanten där diket går i trumma (inget vatten, ingen ränna)
LAKE_DEPTH = 1.5         # m från vattenytan ned till botten i sjöar och åar
SHORE_SEARCH = 3         # px (á 2 m) runt en strandpunkt där lägsta terrängen blir vattenytan
FLIP = False             # vänd trianglarna om vattnet bara syns underifrån


def _grid(world, n):
    """Transform för spelets höjdkarta (n px, pixelmitt på kartans jämna 2 m)."""
    upp = world.size / (n - 1)
    return from_origin(world.e0 - world.half - upp / 2, world.n0 + world.half + upp / 2, upp, upp), upp


def _sample(arr, world, e, n):
    size = arr.shape[0]
    upp = world.size / (size - 1)
    c = np.clip(np.round((np.asarray(e) - world.e0 + world.half) / upp).astype(int), 0, size - 1)
    r = np.clip(np.round((world.n0 + world.half - np.asarray(n)) / upp).astype(int), 0, size - 1)
    return arr[r, c]


def _lines(geom):
    if geom.geom_type == "LineString":
        return [geom]
    return [g for part in getattr(geom, "geoms", []) for g in _lines(part)]


def _polys(geom):
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for part in getattr(geom, "geoms", []) for g in _polys(part)]


def snap_lines(game, world, waterways):
    """Flytta vattendragslinjerna till dikets botten i höjdmodellen: varje punkt till den
    lägsta terrängen inom SNAP m åt sidan, med utjämnade flyttningar längs linjen."""
    inside = world.square(10)
    offsets = np.arange(-SNAP, SNAP + 0.1, 1.0)
    out = []
    for kind, line in waterways:
        if not line.intersects(inside) or line.length < 2 * STREAM_STEP:
            out.append((kind, line))
            continue
        d = np.linspace(0, line.length, max(int(line.length / STREAM_STEP) + 1, 2))
        pts = np.array([line.interpolate(x).coords[0] for x in d])
        tang = np.gradient(pts, axis=0)
        tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-6)
        nrm = np.column_stack([-tang[:, 1], tang[:, 0]])
        cand = pts[:, None, :] + nrm[:, None, :] * offsets[None, :, None]           # (punkter, förskjutningar, 2)
        h = _sample(game, world, cand[..., 0], cand[..., 1]).astype(float)
        h += np.abs(offsets)[None, :] * 0.02                                        # närmare föredras
        best = offsets[np.argmin(h, axis=1)]
        ok = shapely.contains_xy(inside, pts[:, 0], pts[:, 1])
        best[~ok] = 0.0
        pad = np.pad(best, 2, mode="edge")
        best = np.median(np.lib.stride_tricks.sliding_window_view(pad, 5), axis=1)  # bort med enstaka hopp
        best = np.convolve(np.pad(best, 1, mode="edge"), np.ones(3) / 3, mode="valid")
        out.append((kind, LineString(pts + nrm * best[:, None])))
    return out


def road_banks(game, world, transform, water_polys, roads):
    """Där en väg korsar en vattenyta (höjdmodellen saknar broar) byggs en vägbank i vägens
    höjd strax utanför vattnet, så att vägen går att köra på."""
    for width, line in roads:
        for poly in water_polys:
            if not line.intersects(poly):
                continue
            outside = line.difference(poly.buffer(2)).intersection(poly.buffer(25))
            pts = [q.coords[0] for part in _lines(outside) for q in
                   (part.interpolate(d) for d in np.arange(0, part.length + 0.1, 2.0))]
            if not pts:
                continue
            pts = np.array(pts)
            level = float(np.median(_sample(game, world, pts[:, 0], pts[:, 1])))
            bank = line.buffer(width / 2 + 1.5).intersection(poly.buffer(3))
            if bank.is_empty:
                continue
            m = rasterize([(bank, 1)], out_shape=game.shape, transform=transform, dtype="uint8") > 0
            game[m] = np.maximum(game[m], level)


def build_water(game, world, areas, waterways, roads=()):
    """Sänker terrängen (game, spelets höjder) under vattnet och returnerar vattenytorna som
    [(namn, vertices [(e, n, höjd)], trianglar [(i, j, k)])]. roads = [(bredd, linje)]:
    under vägar blir det varken vatten eller ränna (trummor och broar)."""
    n = game.shape[0]
    transform, _upp = _grid(world, n)
    road_zone = shapely.union_all([ln.buffer(w / 2 + ROAD_GAP) for w, ln in roads]) if roads else None
    if road_zone is not None:
        shapely.prepare(road_zone)
    inner_sq = world.square(4)
    road_banks(game, world, transform,
               [p for c, g in areas if c == "water" for p in _polys(g.intersection(inner_sq)) if p.area > 50],
               [(w, ln) for w, ln in roads if ln.intersects(inner_sq)])
    low = np.array(Image.fromarray(game.astype(np.float32)).filter(ImageFilter.MinFilter(2 * SHORE_SEARCH + 1)))
    bed = np.array(Image.fromarray(game.astype(np.float32)).filter(ImageFilter.MinFilter(3)))   # dikesbotten
    inner = world.square(4)
    meshes, cut_shapes, lakes = [], [], []

    # Sjöar och breda åar
    water_polys = [p for c, g in areas if c == "water" for p in _polys(g.intersection(inner)) if p.area > 50]
    if road_zone is not None:   # vattnet slutar vid vägbanken
        water_polys = [q for p in water_polys for q in _polys(p.difference(road_zone)) if q.area > 50]
    for i, poly in enumerate(water_polys):
        poly = poly.simplify(1.5)
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        tris = [t for t in shapely.get_parts(shapely.constrained_delaunay_triangles(poly)) if t.area > 0.01]
        verts, index, faces = [], {}, []
        for t in tris:
            ids = []
            for x, y in list(t.exterior.coords)[:3]:
                key = (round(x, 2), round(y, 2))
                if key not in index:
                    index[key] = len(verts)
                    verts.append([key[0], key[1], 0.0])
                ids.append(index[key])
            faces.append(tuple(ids))
        if not faces:
            continue
        v = np.array(verts)
        v[:, 2] = _sample(low, world, v[:, 0], v[:, 1])
        meshes.append((f"water{i + 1:03d}", v.tolist(), faces))
        lakes.append(poly.buffer(-1.0))

    # Diken och bäckar, utanför vattenytorna
    surface = shapely.union_all(water_polys).buffer(1.0) if water_polys else None
    for i, (kind, line) in enumerate(waterways):
        geom = line.intersection(inner)
        if road_zone is not None:
            geom = geom.difference(road_zone)    # trumma under vägen
        if surface is not None:
            geom = geom.difference(surface)
        for part in _lines(geom):
            if part.length < 2 * STREAM_STEP:
                continue
            d = np.linspace(0, part.length, max(int(part.length / STREAM_STEP) + 1, 2))
            pts = np.array([part.interpolate(x).coords[0] for x in d])
            tang = np.gradient(pts, axis=0)
            tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-6)
            unit = np.column_stack([-tang[:, 1], tang[:, 0]])
            normal = unit * STREAM_WIDTH / 2
            # Vattnet får aldrig ligga över marken strax utanför kanterna (annars svävar det i en slänt).
            reach = unit * (STREAM_WIDTH / 2 + 0.8)
            banks = np.minimum(_sample(game, world, *(pts + reach).T), _sample(game, world, *(pts - reach).T))
            limit = banks.astype(float) - EDGE_CLEAR
            h = _sample(bed, world, pts[:, 0], pts[:, 1]).astype(float) + WATER_ABOVE_BOTTOM
            h = np.convolve(np.pad(np.minimum(h, limit), 2, mode="edge"), np.ones(5) / 5, mode="valid")
            h = np.minimum(h, limit)
            left, right = pts + normal, pts - normal
            verts = []
            for k in range(len(pts)):
                verts += [[left[k, 0], left[k, 1], h[k]], [right[k, 0], right[k, 1], h[k]]]
            faces = []
            for k in range(len(pts) - 1):
                a, b, c, e = 2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 3
                faces += [(a, b, c), (b, e, c)]
            meshes.append((f"stream{i + 1:03d}_{len(meshes)}", verts, faces))
            for k in range(len(pts) - 1):
                line_k = LineString([pts[k], pts[k + 1]])
                for radius, share in CUT_RINGS:
                    seg = line_k.buffer(radius)
                    if road_zone is not None and road_zone.intersects(seg):
                        seg = seg.difference(road_zone)
                    cut_shapes.append((seg, float(min(h[k], h[k + 1])) - STREAM_DEPTH * share, radius))

    lake_mask = rasterize(((g, 1) for g in lakes if not g.is_empty), out_shape=game.shape, transform=transform,
                          dtype="uint8") > 0 if lakes else np.zeros(game.shape, bool)
    game[lake_mask] = np.minimum(game[lake_mask], np.maximum(low[lake_mask] - LAKE_DEPTH, 0.5))   # följer fallet
    if cut_shapes:
        # Yttre ringar först, så att de djupare inre vinner där de överlappar.
        cut_shapes.sort(key=lambda t: -t[2])
        bottom = rasterize(((g, v) for g, v, _r in cut_shapes if not g.is_empty), out_shape=game.shape,
                           transform=transform, fill=np.nan, dtype="float32")
        sel = ~np.isnan(bottom)
        game[sel] = np.minimum(game[sel], np.maximum(bottom[sel], 0.5))
    return meshes


def add_to_i3d(root, meshes, world, nid, add_file):
    """Lägg vattenytorna i i3d-filen: material, trianglar och noder med onCreateWater."""
    import xml.etree.ElementTree as ET

    if not meshes:
        return
    shader = add_file("$data/shaders/oceanShader.xml")
    normal = add_file("$data/maps/textures/shared/water_normal.png")
    mats = root.find("Materials")
    mat_id = str(max(int(m.get("materialId")) for m in mats) + 1)
    mat = ET.SubElement(mats, "Material", {"name": "waterSimPonds_mat", "materialId": mat_id,
                                           "diffuseColor": "1 1 1 1", "specularColor": "1 1 1",
                                           "customShaderId": shader})
    ET.SubElement(mat, "Refractionmap", {"type": "planar", "coeff": "1", "bumpScale": "0.01", "withSSRData": "true"})
    ET.SubElement(mat, "CustomParameter", {"name": "depthScale", "value": "0.025"})
    ET.SubElement(mat, "CustomParameter", {"name": "underwaterFogDepth", "value": "1 1 2 1"})
    ET.SubElement(mat, "Normalmap", {"fileId": normal})

    shapes = root.find("Shapes")
    if shapes is None:
        shapes = ET.Element("Shapes")
        root.insert(list(root).index(mats) + 1, shapes)
    scene, uas = root.find("Scene"), root.find("UserAttributes")
    group = ET.SubElement(scene, "TransformGroup", {"name": "waterPlanes", "nodeId": nid()})
    for shape_id, (name, verts, faces) in enumerate(meshes, start=len(shapes) + 1):
        v = np.array(verts, dtype=float)
        x = v[:, 0] - world.e0          # spelets x österut
        z = world.n0 - v[:, 1]          # spelets z söderut
        y = v[:, 2]
        cx, cy, cz = float(x.mean()), float(y.min()), float(z.mean())
        its = ET.SubElement(shapes, "IndexedTriangleSet", {"name": name, "shapeId": str(shape_id)})
        vs = ET.SubElement(its, "Vertices", {"count": str(len(v)), "normal": "true", "uv0": "true"})
        for xi, yi, zi in zip(x, y, z):
            ET.SubElement(vs, "v", {"p": f"{xi - cx:.2f} {yi - cy:.3f} {zi - cz:.2f}", "n": "0 1 0",
                                    "t0": f"{xi / 10:.3f} {zi / 10:.3f}"})
        ts = ET.SubElement(its, "Triangles", {"count": str(len(faces))})
        for a, b, c in faces:
            # Normalen (b - a) × (c - a) ska peka uppåt (+y) i spelets koordinater.
            ny = (z[b] - z[a]) * (x[c] - x[a]) - (x[b] - x[a]) * (z[c] - z[a])
            if (ny < 0) != FLIP:
                b, c = c, b
            ET.SubElement(ts, "t", {"vi": f"{a} {b} {c}"})
        subs = ET.SubElement(its, "Subsets", {"count": "1"})
        ET.SubElement(subs, "Subset", {"firstVertex": "0", "numVertices": str(len(v)),
                                       "firstIndex": "0", "numIndices": str(3 * len(faces))})
        node = nid()
        ET.SubElement(group, "Shape", {
            "name": name, "translation": f"{cx:.2f} {cy:.3f} {cz:.2f}", "shapeId": str(shape_id),
            "static": "true", "collisionFilterGroup": "0x80000000", "collisionFilterMask": "0x1",
            "castsShadows": "false", "receiveShadows": "true", "materialIds": mat_id,
            "clipDistance": "1500", "nodeId": node})
        ua = ET.SubElement(uas, "UserAttribute", {"nodeId": node})
        ET.SubElement(ua, "Attribute", {"name": "onCreate", "type": "scriptCallback",
                                        "value": "Environment.onCreateWater"})
