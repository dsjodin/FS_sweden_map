"""Lantmäteriets Marktäcke Nedladdning, vektor som ytor för build_map.py.

Ytorna får samma klassnamn som analyze_area.load_features ger OSM-ytorna
(forest, water, ...), så att de kan ersätta OSM:s marktäcke rakt av.
Filerna hämtas med fetch_landcover.py till data/<namn>/lm/vektor/marktacke_<kommun>/.

Klasserna är avlästa från leveransen (lagret mark, fältet objekttypnr).
"""
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


def marktacke_files(project):
    return sorted((project.lm / "vektor").glob("marktacke_*/**/*.gpkg"))


def load_marktacke(project, area):
    """[(klass, polygon i SWEREF 99 TM)] för Marktäckes ytor inom area (en shapely-yta)."""
    import pyogrio  # pip install pyogrio
    import shapely

    out, seen = [], set()
    for path in marktacke_files(project):
        meta, _fids, wkb, (ids, types) = pyogrio.raw.read(
            path, layer="mark", bbox=area.bounds, columns=["objektidentitet", "objekttypnr"])
        if meta["crs"] and meta["crs"] != "EPSG:3006":
            raise ValueError(f"{path.name} har koordinatsystemet {meta['crs']}, väntade SWEREF 99 TM (EPSG:3006).")
        for oid, typ, geom in zip(ids, types, shapely.from_wkb(wkb)):
            cls = MARK_CLASSES.get(int(typ)) if typ is not None else None
            if cls is None or geom is None or oid in seen:   # samma yta kan finnas i två kommuners filer
                continue
            seen.add(oid)
            geom = shapely.make_valid(shapely.force_2d(geom)).intersection(area)   # filerna har z-värden
            if not geom.is_empty:
                out.append((cls, geom))
    return out
