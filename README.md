# FS25 Tysslinge

Egen karta till Farming Simulator 25 byggd på den verkliga landsbygden runt
Tysslinge och Södra Valla i Örebro kommun. Målet är att kartan ska vara så lik
verkligheten som möjligt, med spannmålsodling i fokus och en tydlig känsla av
svensk landsbygd.

Repot innehåller allt som behövs för att ta fram kartan: konfiguration för
området, skript som hämtar och bearbetar data, verktyg och dokumentation. Själva
kartmodden (i3d, texturer, XML) läggs i `map/` när vi kommer dit.

## Läge just nu

**Fas 1: Välj område.** Öppna `tools/omradesval.html` i en webbläsare. Dra
rutan och jämför 2×2, 4×4 och 8×8 km. När du har bestämt dig, kopiera
mittpunkten och storleken och uppdatera `config/area.json`.

Första analysen med mittpunkten mellan Tysslinge och Södra Valla:

| Storlek | Åker | Skog | Åkerskiften i OSM | Gårdsplaner | Byggnader | Med i rutan |
|---|---|---|---|---|---|---|
| 2×2 km | 281 ha (67 %) | 23 ha | 27 | 0 | 29 | Stora Valla, Osvalla. Varken Tysslinge eller Södra Valla får plats. |
| 4×4 km | 881 ha (53 %) | 127 ha | 75 | 3 | 449 | Tysslinge, kyrkan, Södra Valla, Latorpsbruk, Stora Valla, Rumboholm |
| 8×8 km | 2 507 ha (37 %) | 1 575 ha | 282 | 14 | 1 726 | Även Garphyttan, Vintrosa och E18/E20 |

Rekommendation: **4×4 km** (FS25 "4x"). Rutan rymmer båda platserna och nästan
bara jordbruksbygd. 8×8 km tar med motorväg och tätorter och blir ett mycket
stort projekt för en första karta.

## Arbetsgång

| Fas | Vad | Var det görs |
|---|---|---|
| 1 | Välj område och storlek | `tools/omradesval.html`, `config/area.json` |
| 2 | Hämta data: höjdmodell, ortofoto och fastighetskarta från Lantmäteriet, jordbruksblock från Jordbruksverket, OSM | skript i `scripts/` |
| 3 | Gör om datan till FS25-format: höjdkarta, fältmasker, väg- och skogsmasker | skript i `scripts/`, eller Maps4FS med egen höjdmodell |
| 4 | Generera grundkarta och öppna den i GIANTS Editor 10 | Maps4FS och GIANTS Editor (Windows/Mac) |
| 5 | Bygg ut: terrängtexturer, fält, vägar, gårdar, skog, vatten, svenska detaljer | GIANTS Editor |
| 6 | Gör kartan spelbar: gårdar att köpa, spannmålsmottagning, försäljningsställen, PDA-karta, trafik | GIANTS Editor och XML |
| 7 | Testa i spelet, paketera som mod | FS25 |

Mer om varje fas finns i [docs/arbetsgang.md](docs/arbetsgang.md) och
datakällorna beskrivs i [docs/datakallor.md](docs/datakallor.md).

## Kom igång med skripten

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/fetch_osm.py           # hämtar OSM-data till data/raw/
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
docs/                   arbetsgång och datakällor
```

## Licenser för data

- OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL.
- Lantmäteriet och Jordbruksverket: se villkoren för respektive datamängd i
  [docs/datakallor.md](docs/datakallor.md).
