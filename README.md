# FS25 Tysslinge

Egen karta till Farming Simulator 25 byggd på den verkliga landsbygden runt
Tysslinge och Södra Valla i Örebro kommun. Målet är att kartan ska vara så lik
verkligheten som möjligt, med spannmålsodling i fokus och en tydlig känsla av
svensk landsbygd.

Repot innehåller allt som behövs för att ta fram kartan: konfiguration för
området, skript som hämtar och bearbetar data, verktyg och dokumentation. Själva
kartmodden (i3d, texturer, XML) läggs i `map/` när vi kommer dit.

## Läge just nu

**Fas 1 är klar.** Kartan blir 4×4 km (4096 m, FS25 "4x") med mittpunkt
59.26756, 15.01856 (SWEREF 99 TM N 6 569 846, E 501 058). Rutan går från
E 499 010 till 503 106 och N 6 567 798 till 6 571 894. Den rymmer
Tysslinge med kyrkan, Södra Valla, Stora Valla, Latorpsbruk och Rumboholm.

Enligt OSM innehåller rutan 917 ha åker (55 %), 109 ha skog och 429 byggnader.
`tools/omradesval.html` visar rutan.

**Fas 2 pågår: hämta data.**

- [x] OpenStreetMap (`scripts/fetch_osm.py`)
- [x] Jordbruksverkets block och skiften 2025, med grödor
  (`scripts/fetch_fields.py`): 279 block och 371 skiften i rutan med 300 m
  marginal. Ingen inloggning behövs.
- [x] Lantmäteriets höjdmodell, 1 m (`scripts/fetch_heightmap.py`). Höjden
  varierar mellan 37,6 och 93,5 m över havet, en skillnad på 56 m.
- [ ] Ortofoto som förlaga.

**Fas 3 har börjat.**

- [x] Höjdkarta `build/data/dem.png`, 4097×4097, 16 bitar
  (`scripts/make_heightmap.py`). Värdena till GIANTS Editor skrivs till
  `build/heightmap.json`.
- [x] Grundkarta från MapToPlay, 4096 m spelbar yta och 8192 m total yta,
  med vår höjdmodell `dtm_8km.tif`.
- [ ] Verkliga fält: `scripts/make_osm_fields.py` bygger
  `build/tysslinge_faltskiften.osm`. Där är OSM:s åkrar utbytta mot 514
  åkrar och 88 ängar från Jordbruksverkets skiften. Filen laddas upp som
  vektordata i MapToPlay.

## Arbetsgång

| Fas | Vad | Var det görs |
|---|---|---|
| 1 | Välj område och storlek | `tools/omradesval.html`, `config/area.json` |
| 2 | Hämta data: höjdmodell, ortofoto och fastighetskarta från Lantmäteriet, jordbruksblock från Jordbruksverket, OSM | skript i `scripts/` |
| 3 | Gör om datan till FS25-format: höjdkarta, fältmasker, väg- och skogsmasker | skript i `scripts/` |
| 4 | Generera grundkarta och öppna den i GIANTS Editor 10 | Kartmall (MapToPlay eller egen) och GIANTS Editor på Windows |
| 5 | Bygg ut: terrängtexturer, fält, vägar, gårdar, skog, vatten, svenska detaljer | GIANTS Editor |
| 6 | Gör kartan spelbar: gårdar att köpa, spannmålsmottagning, försäljningsställen, PDA-karta, trafik | GIANTS Editor och XML |
| 7 | Testa i spelet, paketera som mod | FS25 |

Mer om varje fas finns i [docs/arbetsgang.md](docs/arbetsgang.md) och
datakällorna beskrivs i [docs/datakallor.md](docs/datakallor.md).
[docs/installation.md](docs/installation.md) beskriver hur arbetet delas
mellan Debian-servern (skript och data) och Windows-datorn (FS25 och GIANTS
Editor).

## Kom igång med skripten

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/fetch_osm.py           # hämtar OSM-data till data/raw/
python scripts/fetch_fields.py        # Jordbruksverkets block och skiften
python scripts/fetch_heightmap.py     # Lantmäteriets höjdmodell (kräver LM_USER/LM_PASSWORD)
python scripts/make_heightmap.py      # höjdkarta i FS25-format till build/
python scripts/make_osm_fields.py     # OSM-fil med Jordbruksverkets skiften som åkrar
python scripts/analyze_area.py        # statistik per kartstorlek + data till väljaren
python scripts/build_area_picker.py   # bygger tools/omradesval.html
```

`analyze_area.py --center 59.27,15.02` räknar på en annan mittpunkt.

## Struktur

```
config/area.json        område: mittpunkt, storlek, platser
scripts/                hämtning och bearbetning av data
tools/                  områdesväljaren (HTML)
data/                   genererad data (rådata under data/raw/ checkas inte in)
build/                  färdiga kartfiler, t.ex. dem.png (checkas inte in)
docs/                   arbetsgång och datakällor
```

## Licenser för data

- OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL.
- Lantmäteriet och Jordbruksverket: se villkoren för respektive datamängd i
  [docs/datakallor.md](docs/datakallor.md).
