"""Lantmäteriets vektordata för build_map.py: marktyper, vattendrag, vägar och byggnader.

Källor, i den ordning de används:
- Marktäcke Nedladdning, vektor: hämtas per kommun med fetch_landcover.py till
  data/<namn>/lm/vektor/marktacke_<kommun>/.
- Topografi 10 Nedladdning, vektor: en leverans per län, uppackad till
  data/topografi10/ln<län>/<tema>_ln<län>.gpkg (gemensam för alla kartor).
  Ger vattendrag (hydro), vägar (kommunikation), byggnader (byggnadsverk) och,
  om Marktäcke saknas, marktyper (mark).

Ytorna får samma klassnamn som analyze_area.load_features ger OSM-datan
(forest, water, ...; vägklasserna i build_map.ROAD_STYLE), så att de kan
ersätta OSM rakt av. Klasserna är avlästa från leveranserna (fältet objekttypnr
eller objekttyp).
"""
from area import ROOT

TOPO_DIR = ROOT / "data" / "topografi10"

MARK_CLASSES = {
    2645: "forest",       # Barr- och blandskog
    2646: "forest",       # Lövskog
    2642: "farmland",     # Åker
    2643: "farmland",     # Fruktodling
    2640: "meadow",       # Öppen mark
    2632: "water",        # Sjö
    2633: "water",        # Vattendragsyta
    2634: "water",        # Anlagt vatten
    2636: "residential",  # Sluten bebyggelse
    2637: "residential",  # Hög bebyggelse
    2638: "residential",  # Låg bebyggelse
    2639: "residential",  # Industri- och handelsbebyggelse
    2641: "residential",  # Torg
}
# OSM-klasser som Marktäcke ersätter. Gårdsplaner (farmyard) finns inte i Marktäcke och tas från OSM.
REPLACES = {"forest", "water", "residential", "meadow", "farmland", "wetland"}

# Topografi 10, kommunikation: vägtyp -> vägklass i build_map.ROAD_STYLE. Saknas = används inte.
ROAD_CLASSES = {
    "Motorväg": "motorväg/riksväg", "Motortrafikled": "motorväg/riksväg", "Mötesfri väg": "motorväg/riksväg",
    "Landsväg": "länsväg", "Huvudgata": "länsväg",
    "Landsväg liten": "länsväg",   # numrerade länsvägar, till exempel T732
    "Småväg": "småväg", "Lokalgata stor": "småväg", "Lokalgata liten": "småväg",
    "Infartsväg/Utfartsväg": "småväg", "Kvartersväg": "småväg", "Parkeringsområdesväg": "småväg",
    "Leveransväg": "småväg",
    "Småväg enkel standard": "grusväg/brukningsväg", "Traktorväg": "grusväg/brukningsväg",
}
WATERWAY_KIND = "vattendrag"   # Topografi 10 skiljer inte bäck från dike; bredden sätts i build_map


def marktacke_files(project):
    return sorted((project.lm / "vektor").glob("marktacke_*/**/*.gpkg"))


def topo_files(theme):
    return sorted(TOPO_DIR.glob(f"ln*/{theme}_ln*.gpkg"))


def has_topo():
    return bool(topo_files("kommunikation") or topo_files("hydro"))


def read_layer(paths, layer, area, columns):
    """[(geometri, {kolumn: värde})] inom area ur alla filer, utan z-värden och dubbletter.
    Filer vars utbredning inte når area hoppas över (länsfiler utanför kartan)."""
    import pyogrio  # pip install pyogrio
    import shapely

    out, seen = [], set()
    for path in paths:
        if layer not in [name for name, _ in pyogrio.list_layers(path)]:
            continue
        info = pyogrio.read_info(path, layer=layer, force_total_bounds=True)
        x0, y0, x1, y1 = info["total_bounds"]
        ax0, ay0, ax1, ay1 = area.bounds
        if x1 < ax0 or x0 > ax1 or y1 < ay0 or y0 > ay1:
            continue
        if info["crs"] and info["crs"] != "EPSG:3006":
            raise ValueError(f"{path.name} har koordinatsystemet {info['crs']}, väntade SWEREF 99 TM (EPSG:3006).")
        cols = ["objektidentitet"] + [c for c in columns if c in info["fields"]]
        _meta, _fids, wkb, data = pyogrio.raw.read(path, layer=layer, bbox=area.bounds, columns=cols)
        values = dict(zip(cols, data))
        for i, geom in enumerate(shapely.from_wkb(wkb)):
            oid = values["objektidentitet"][i]
            if geom is None or oid in seen:      # samma objekt kan finnas i två kommuners eller läns filer
                continue
            seen.add(oid)
            geom = shapely.make_valid(shapely.force_2d(geom)).intersection(area)   # filerna har z-värden
            if not geom.is_empty:
                out.append((geom, {c: values[c][i] for c in cols}))
    return out


def lines(geom):
    """LineString-delar ur en geometri (klippning kan ge MultiLineString eller samlingar)."""
    if geom.geom_type == "LineString":
        return [geom]
    return [g for part in getattr(geom, "geoms", []) for g in lines(part)]


def load_marktacke(project, area):
    """[(klass, polygon)] för marktyperna inom area: Marktäcke, annars Topografi 10:s marklager."""
    paths = marktacke_files(project) or topo_files("mark")
    out = []
    for geom, attrs in read_layer(paths, "mark", area, ["objekttypnr"]):
        typ = attrs["objekttypnr"]
        cls = MARK_CLASSES.get(int(typ)) if typ is not None else None
        if cls:
            out.append((cls, geom))
    return out


def load_waterways(area):
    """[(WATERWAY_KIND, linje)] för Topografi 10:s vattendrag inom area."""
    return [(WATERWAY_KIND, ln) for geom, _ in read_layer(topo_files("hydro"), "hydrolinje", area, [])
            for ln in lines(geom)]


def load_roads(area):
    """[(vägklass, linje)] för Topografi 10:s vägar (vaglinje och ovrig_vag) inom area."""
    out = []
    for layer in ("vaglinje", "ovrig_vag"):
        for geom, attrs in read_layer(topo_files("kommunikation"), layer, area, ["objekttyp"]):
            cls = ROAD_CLASSES.get(attrs.get("objekttyp"))
            if cls:
                out += [(cls, ln) for ln in lines(geom)]
    return out


def load_buildings(area):
    """[(polygon, {objekttyp, andamal1, huvudbyggnad})] för Topografi 10:s byggnader inom area."""
    out = []
    for geom, attrs in read_layer(topo_files("byggnadsverk"), "byggnad", area,
                                  ["objekttyp", "andamal1", "huvudbyggnad"]):
        for poly in ([geom] if geom.geom_type == "Polygon" else getattr(geom, "geoms", [])):
            if poly.geom_type == "Polygon":
                out.append((poly, attrs))
    return out
