#!/usr/bin/env python3
"""Hittar träd utanför skogen i ortofotot: åkerholmar, trädrader längs diken och
åar, alléer och träd runt gårdar. Sådant finns inte i Marktäcke eller Topografi 10.

Metoden lär sig hur träd ser ut i just den här flygningen (årstid, ljus) i
stället för att använda fasta gränsvärden:
1. Exempel på träd: pixlar långt inne i Marktäckes skogar.
   Exempel på annat: pixlar inne i fält, öppen mark, vägar, byggnader och vatten.
2. Varje pixel beskrivs med färg, ljushet och textur (trädkronor är ojämna,
   gräs och åker släta). En enkel statistisk modell (QDA) skiljer klasserna åt.
3. Modellen används bara utanför skog, fält, vägar, byggnader och vatten.
   Trädkronorna blir ytor, och i dem sätts träd med cirka 7 m mellanrum.

Ortofotot lämnar aldrig servern. Resultatet är bara trädpositioner:
    data/<namn>/lm/ortofoto/trad.json        trädpositioner (SWEREF 99 TM), läses av build_map.py
    build/<namn>/kontroll_trad.jpg           kontrollbild: ortofoto med funna träd i rött.
                                             Bara för dig att titta på, skicka den inte vidare.

Kräver: fetch_orthophoto.py, fetch_fields.py, fetch_osm.py och helst Marktäcke
eller Topografi 10 för kartan.

Användning:
    python scripts/detect_trees.py [--map tysslinge] [--troskel 0.9]
"""
import argparse
import json
import sys

import numpy as np
import rasterio
import shapely
from PIL import Image, ImageFilter
from rasterio.features import rasterize, shapes
from rasterio.windows import from_bounds
from shapely.geometry import shape
from shapely.ops import unary_union

import build_map as bm
from area import add_map_argument, open_map

STRIP = 1024            # rader per bearbetat band
PAD = 8                 # px överlapp för texturfiltren
SAMPLES = 200_000       # träningspixlar per klass
MIN_CROWN = 12.0        # m², mindre fläckar räknas som brus
TREE_SPACING = 7.0      # m mellan träd i en trädgrupp
MAX_TREES = 8000
POS, NEG = 1, 2         # träningsetiketter


def box_mean(a, k):
    """Medelvärde i ett k×k-fönster (k udda) med integralbild, samma storlek som a."""
    p = k // 2
    s = np.pad(a, p + 1, mode="edge").cumsum(0).cumsum(1)
    return (s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k])[: a.shape[0], : a.shape[1]] / (k * k)


def features(rgb):
    """Pixelvärden (n, 6): kromaticitet r och g, ljushet, grönhet, textur i 1,5 och 4,5 m."""
    r, g, b = (rgb[i].astype(np.float32) for i in range(3))
    tot = r + g + b + 1.0
    bright = tot / 765.0
    out = [r / tot, g / tot, bright, (2 * g - r - b) / tot]
    for k in (3, 9):
        m = box_mean(bright, k)
        out.append(np.sqrt(np.maximum(box_mean(bright * bright, k) - m * m, 0)))
    return np.stack(out, axis=-1)


class QDA:
    def fit(self, pos, neg):
        self.params = []
        for x in (pos, neg):
            mu = x.mean(0)
            cov = np.cov(x, rowvar=False) + np.eye(x.shape[1]) * 1e-6
            self.params.append((mu, np.linalg.inv(cov), np.linalg.slogdet(cov)[1]))
        return self

    def logodds(self, x, batch=1_000_000):
        out = np.empty(len(x), np.float32)
        for i in range(0, len(x), batch):
            ll = []
            for mu, icov, logdet in self.params:
                d = x[i:i + batch] - mu
                ll.append(-0.5 * (np.einsum("ij,jk,ik->i", d, icov, d) + logdet))
            out[i:i + batch] = ll[0] - ll[1]
        return out


def masks(project, world, grid):
    """Etiketter för träning och yta där träd får sökas, som rasterbilder på grid."""
    osm, _ = bm.load_land(project, world)
    areas, roads, waterways, _rail, buildings, _pl = osm
    cut = bm.obstacles(roads, waterways, world, areas)
    fields = [g for g, _, _ in bm.load_fields(project, world, cut)]
    transform, shp = grid
    road_geoms = [ln.buffer(bm.ROAD_STYLE[c][1] / 2 + 1) for c, ln in roads]
    forest = [g for c, g in areas if c == "forest"]
    water = [g for c, g in areas if c == "water"]
    meadow = [g for c, g in areas if c == "meadow"]

    def burn(geoms, value=1):
        geoms = [g for g in geoms if not g.is_empty]
        if not geoms:
            return np.zeros(shp, np.uint8)
        return rasterize(((g, value) for g in geoms), out_shape=shp, transform=transform, dtype="uint8")

    label = np.zeros(shp, np.uint8)
    label[burn([g.buffer(-8) for g in forest]) > 0] = POS
    neg = burn([g.buffer(-5) for g in fields] + [g.buffer(-6) for g in meadow] + road_geoms
               + buildings + water)
    label[(neg > 0) & (label == 0)] = NEG
    # Skogskanten får redan träd av build_map, och strandkanter ger falsk textur: håll avstånd.
    blocked = burn([g.buffer(1) for g in fields] + road_geoms + [b.buffer(1) for b in buildings]
                   + [g.buffer(2) for g in water] + [g.buffer(4) for g in forest])
    return label, blocked == 0, forest, waterways, buildings


def strips(src, window_bounds, shp):
    """(rad0, rgb-band med PAD rader extra på varje sida, pad_ovan) över hela kartrutan."""
    x0, y0, x1, y1 = window_bounds
    full = from_bounds(x0, y0, x1, y1, src.transform).round_offsets()
    for r0 in range(0, shp[0], STRIP):
        r1 = min(r0 + STRIP, shp[0])
        a, b = max(r0 - PAD, 0), min(r1 + PAD, shp[0])
        win = rasterio.windows.Window(full.col_off, full.row_off + a, shp[1], b - a)
        yield r0, r1, src.read([1, 2, 3], window=win, boundless=True, fill_value=0), r0 - a


def main():
    parser = argparse.ArgumentParser()
    add_map_argument(parser)
    parser.add_argument("--troskel", type=float, default=0.9,
                        help="hur säker modellen ska vara (0–1) för att en pixel ska räknas som träd")
    args = parser.parse_args()
    project = open_map(args.map)
    world = bm.World(project)
    ortho = project.lm / "ortofoto" / "ortofoto.tif"
    if not ortho.exists():
        sys.exit(f"Hittar inte {project.rel(ortho)}. Kör fetch_orthophoto.py först.")

    rng = np.random.default_rng(1)
    with rasterio.open(ortho) as src:
        res = src.res[0]
        sq = world.square(-20)
        x0, y0, x1, y1 = sq.bounds
        shp = (int(round((y1 - y0) / res)), int(round((x1 - x0) / res)))
        transform = rasterio.transform.from_origin(x0, y1, res, res)
        print("Etiketter och spärrytor ...")
        label, allowed, forest, waterways, buildings = masks(project, world, (transform, shp))
        if (label == POS).sum() < 1000:
            sys.exit("För lite skog i kartrutan att lära sig trädens utseende från.")

        print("Lär modellen hur träd ser ut i den här flygningen ...")
        pos, neg = [], []
        share = {POS: SAMPLES / max((label == POS).sum(), 1), NEG: SAMPLES / max((label == NEG).sum(), 1)}
        for r0, r1, rgb, top in strips(src, (x0, y0, x1, y1), shp):
            f = features(rgb)[top: top + (r1 - r0)]
            lab = label[r0:r1]
            for cls, bucket in ((POS, pos), (NEG, neg)):
                idx = np.flatnonzero((lab == cls).ravel())
                take = idx[rng.random(idx.size) < share[cls]]
                bucket.append(f.reshape(-1, f.shape[-1])[take])
        pos, neg = np.concatenate(pos), np.concatenate(neg)
        split_p, split_n = int(len(pos) * 0.8), int(len(neg) * 0.8)
        rng.shuffle(pos), rng.shuffle(neg)
        model = QDA().fit(pos[:split_p], neg[:split_n])
        limit = np.log(args.troskel / (1 - args.troskel))
        hit_p = (model.logodds(pos[split_p:]) > limit).mean()
        hit_n = (model.logodds(neg[split_n:]) <= limit).mean()
        print(f"  Kontroll på sparade exempel: {hit_p:.0%} av skogspixlarna och {hit_n:.0%} av övriga rätt.")

        print("Söker träd utanför skogen ...")
        mask = np.zeros(shp, np.uint8)
        for r0, r1, rgb, top in strips(src, (x0, y0, x1, y1), shp):
            ok = allowed[r0:r1]
            if not ok.any():
                continue
            f = features(rgb)[top: top + (r1 - r0)]
            band = np.zeros(ok.shape, np.uint8)
            band[ok] = (model.logodds(f[ok]) > limit).astype(np.uint8)
            mask[r0:r1] = band

    # Rensa brus: öppning med 3×3 (1,5 m), så att enstaka pixlar försvinner.
    img = Image.fromarray(mask * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    mask = (np.array(img) > 0).astype(np.uint8)

    crowns = [shape(g) for g, v in shapes(mask, mask=mask > 0, transform=transform) if v == 1]
    crowns = [c for c in crowns if c.area >= MIN_CROWN]
    points = []
    for c in crowns:
        minx, miny, maxx, maxy = c.bounds
        ge, gn = np.meshgrid(np.arange(minx + TREE_SPACING / 2, maxx, TREE_SPACING),
                             np.arange(miny + TREE_SPACING / 2, maxy, TREE_SPACING))
        keep = shapely.contains_xy(c, ge.ravel(), gn.ravel())
        inside = list(zip(ge.ravel()[keep], gn.ravel()[keep]))
        if not inside:                       # liten krona: ett träd mitt i
            p = c.representative_point()
            inside = [(p.x, p.y)]
        points += [(round(float(e), 1), round(float(n), 1)) for e, n in inside]
    if len(points) > MAX_TREES:
        points = [points[i] for i in sorted(rng.choice(len(points), MAX_TREES, replace=False))]

    canopy = unary_union(crowns) if crowns else None
    water_zone = unary_union([ln.buffer(20) for _, ln in waterways]) if waterways else None
    near_water = canopy.intersection(water_zone).area / canopy.area if canopy and water_zone else 0
    print(f"\nTrädkronor utanför skogen: {sum(c.area for c in crowns) / 10_000:.1f} ha i {len(crowns)} grupper "
          f"({sum(c.area < 60 for c in crowns)} enstaka träd).")
    print(f"  {near_water:.0%} av ytan ligger inom 20 m från ett vattendrag.")
    print(f"  {len(points)} träd att sätta ut.")

    out = project.lm / "ortofoto" / "trad.json"
    out.write_text(json.dumps({
        "kalla": "Trädpositioner härledda ur Ortofoto Nedladdning, © Lantmäteriet",
        "troskel": args.troskel, "points": points}), encoding="utf-8")
    print(f"Skrev {project.rel(out)}")

    # Kontrollbild, 2 m per pixel. Stannar på servern.
    with rasterio.open(ortho) as src:
        w = from_bounds(*sq.bounds, src.transform)
        small = (shp[0] // 4, shp[1] // 4)
        rgb = src.read([1, 2, 3], window=w, out_shape=(3,) + small, boundless=True).transpose(1, 2, 0)
    m = np.array(Image.fromarray(mask * 255).resize(small[::-1], Image.BOX)) > 64
    rgb = rgb.copy()
    rgb[m] = (0.4 * rgb[m] + 0.6 * np.array([255, 0, 0])).astype(np.uint8)
    project.build.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(project.build / "kontroll_trad.jpg", quality=85)
    print(f"Kontrollbild: {project.rel(project.build / 'kontroll_trad.jpg')} (bara för dig, skicka den inte vidare)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
