# FS25 Sverigekartor

Verktyg för att bygga egna kartor till Farming Simulator 25 från verkliga
platser i Sverige. Fokus ligger på svensk landsbygd som är så lik
verkligheten som möjligt.

Datakällorna täcker hela Sverige:

- **Lantmäteriet:** höjdmodell med 1 m upplösning, Marktäcke (skog, vatten,
  bebyggelse, öppen mark), ortofoto (kräver Geotorget-konto).
- **Jordbruksverket:** jordbruksblock och skiften med grödor. De verkliga
  fälten, utan inloggning.
- **OpenStreetMap:** vägar, byggnader, skog, vatten och ortnamn.

Varje karta har en egen mapp under `maps/`. Samma skript används för alla
kartor.

## Kartor

| Karta | Område | Storlek | Läge |
|---|---|---|---|
| [tysslinge](maps/tysslinge/) | Tysslinge och Södra Valla, Örebro kommun | 4×4 km | Egen modd med `build_map.py`: terräng, 179 fält, 144 farmlands. Startgård vid Södra Valla. Ska provas i spelet. |

## Ny karta, steg för steg

```bash
# 1. Skapa kartan från ett ortnamn (eller --center LAT,LON)
python scripts/new_map.py vreta --title "Vreta kloster" --place "Vreta kloster, Linköping"

# 2. Hämta OSM och bygg områdesväljaren
python scripts/pipeline.py --map vreta --only osm analys valjare

# 3. Öppna maps/vreta/omradesval.html, flytta rutan och välj storlek.
#    För in mittpunkt och storlek i maps/vreta/area.json och bygg om väljaren
#    om du ändrade något.

# 4. Kör resten av kedjan (Lantmäteriets steg kräver LM_USER och LM_PASSWORD)
export LM_USER=ditt-användarnamn
read -rsp "Lösenord: " LM_PASSWORD && echo && export LM_PASSWORD
python scripts/pipeline.py --map vreta --from falt
```

Efteråt finns detta till MapToPlay:

- `data/<namn>/lm/hojd/dtm_total.tif`: höjdmodell för hela området
  (dubbla kartstorleken), att ladda upp som DTM.
- `build/<namn>/<namn>_faltskiften.osm`: OSM-data där åkrarna är utbytta
  mot Jordbruksverkets skiften, att ladda upp som vektordata.

Med `scripts/build_map.py` (steget `karta`) byggs en färdig modd utan
MapToPlay: `build/<namn>/<mod_name>.zip`. Den bygger på
`third_party/fs25_empty_map` och innehåller terräng, fält, farmlands,
marktexturer och översiktskarta. Se [docs/fs25_kartformat.md](docs/fs25_kartformat.md).

Det här finns till GIANTS Editor:

- `build/<namn>/data/dem.png`: höjdkarta i FS25-format, med värdena i
  `build/<namn>/heightmap.json`.

Exempel på inställningar i MapToPlay: spelbar yta = kartstorleken, total
yta = dubbla kartstorleken, rotation 0, output size = kartstorleken.

## Steg i kedjan

`scripts/pipeline.py` kör stegen i ordning. Med `--only` och `--from` väljer
du vilka steg som körs.

| Steg | Skript | Resultat |
|---|---|---|
| osm | `fetch_osm.py` | `data/<namn>/raw/osm.json` |
| analys | `analyze_area.py` | `maps/<namn>/area_stats.json` och `area_features.geojson` |
| valjare | `build_area_picker.py` | `maps/<namn>/omradesval.html` |
| falt | `fetch_fields.py` | `data/<namn>/raw/jbv_skiften.geojson` och `jbv_block.geojson` |
| osmfil | `make_osm_fields.py` | `build/<namn>/<namn>_faltskiften.osm` |
| hojd | `fetch_heightmap.py` | `data/<namn>/lm/hojd/dtm_area.tif` |
| hojd_total | `fetch_heightmap.py --total` | `data/<namn>/lm/hojd/dtm_total.tif` |
| dem | `make_heightmap.py` | `build/<namn>/data/dem.png` |
| karta | `build_map.py` | `build/<namn>/<mod_name>.zip`, färdig FS25-modd |
| ortofoto | `fetch_orthophoto.py` (med `--ortofoto`) | `data/<namn>/lm/ortofoto/ortofoto.tif` |

Alla skript tar `--map <namn>`. Finns bara en karta används den
automatiskt. Det går också att sätta miljövariabeln `FS_MAP`.

## Arbetsgång för en karta

| Fas | Vad | Var det görs |
|---|---|---|
| 1 | Välj område och storlek | `maps/<namn>/omradesval.html`, `maps/<namn>/area.json` |
| 2 | Hämta data | `scripts/pipeline.py` |
| 3 | Gör om datan till FS25-format | `scripts/pipeline.py` |
| 4 | Generera grundkarta och öppna den i GIANTS Editor 10 | MapToPlay och GIANTS Editor på Windows |
| 5 | Bygg ut: terrängtexturer, fält, vägar, gårdar, skog, vatten, svenska detaljer | GIANTS Editor |
| 6 | Gör kartan spelbar: gårdar, spannmålsmottagning, försäljningsställen, PDA-karta | GIANTS Editor och XML |
| 7 | Testa i spelet, paketera som mod | FS25 |

Mer om varje fas finns i [docs/arbetsgang.md](docs/arbetsgang.md).
Datakällorna beskrivs i [docs/datakallor.md](docs/datakallor.md), och
[docs/installation.md](docs/installation.md) beskriver hur arbetet delas
mellan Debian-servern (skript och data) och Windows-datorn (FS25 och
GIANTS Editor).

## Struktur

```
maps/<namn>/            karta: area.json, områdesväljare, statistik (checkas in)
scripts/                hämtning och bearbetning, gemensamt för alla kartor
tools/                  mall för områdesväljaren
docs/                   arbetsgång, datakällor, installation, licenser
data/<namn>/            rådata per karta (checkas inte in)
build/<namn>/           färdiga filer per karta (checkas inte in)
```

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Licenser för data

- OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL.
- Lantmäteriet: CC BY 4.0. Ortofoto har extra villkor om personuppgifter.
- Jordbruksverket: öppna data.

En färdig källförteckning till modden och villkoren för ortofoto finns i
[docs/kallor_och_licenser.md](docs/kallor_och_licenser.md).
Färdiga texter för ansökningar på Geotorget, och status för varje produkt,
finns i [docs/geotorget_ansokningar.md](docs/geotorget_ansokningar.md).
