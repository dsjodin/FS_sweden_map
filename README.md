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

### Träd ur laserdata och kontrollkarta

```bash
python scripts/laser_trees.py --map tysslinge    # krontak och träd utanför skogen ur Laserdata Skog
python scripts/build_map.py --map tysslinge
python scripts/kontrollkarta.py --map tysslinge  # build/tysslinge/kontrollkarta/index.html
```

Kontrollkartan visar ortofotot, laserns trädkronor, de utplacerade träden och
Marktäckes skogar. Den innehåller ortofoto och ska bara visas på egna datorer.

FS25 saknar gran. Lägg prefab-paketet `FS25_sprucepack_prefab.zip` i `data/mods`,
så kopierar `build_map.py` in granarna i kartan (`scripts/prefab_trees.py`). De blir
huvudträdet i barr- och blandskogen och kan väljas i byggeditorns Träd-läge. Spelaren
behöver ingen extra modd. Utan paketet blir det tall i stället. Granarna kan fällas och
säljs som gran. Se `python scripts/i3d_info.py <zip>` för hur ett paket är uppbyggt.

### Fastighetsgränser som markområden

Lägg fastighetsområdena som GeoJSON i `data/<namn>/fastigheter.geojson` (polygoner med
beteckningen i `TITEL` och typen i `BESKRIVNING`). FS25 tillåter bara ett fält per
markområde, så varje fält blir ett köpbart markområde, och resten av fastigheten (skog,
gårdsplan) går till dess närmaste fält. Fastigheter utan fält blir egna markområden, fält
som ligger på två fastigheter delas längs gränsen, och fälten på fastigheten närmast
startpunkten ägs från start. Samfälligheter, vägar och
tomter under 0,5 ha går till grannarna. Beteckningarna kommer inte med i modden
(se `scripts/fastigheter.py`). Utan filen används Jordbruksverkets block.

### Byggeditor: moddbyggnader på de verkliga byggnaderna

```bash
python scripts/mod_katalog.py data/mods          # katalog över byggnaderna i dina moddar
python scripts/byggeditor.py --map tysslinge     # öppna http://ClaudeVM:8080 i webbläsaren
```

Klicka på en verklig byggnad (Topografi 10), välj en moddbyggnad, dra och vrid
den. Placeringarna sparas i `maps/<namn>/byggnader.json` och blir byggnader i
kartan när `build_map.py` körs (knappen "Bygg kartan"). Moddarna blir beroenden.

Läget **Måla mark** ritar ytor (gräs, åker, gårdsplan, asfaltyta, skog, sudda
vägar, inga träd) och vägar (grus eller asfalt, valfri bredd). Läget **Träd**
sätter ut träd av vald art och storlek. Ritningarna sparas i
`maps/<namn>/ritningar.json` och läggs ovanpå datan av `build_map.py`
(se `scripts/drawings.py`).

### Bygga i spelet i stället för i GIANTS Editor

Placera byggnader och objekt i spelets byggläge, kopiera sparfilen till
servern och för in dem i kartan:

```bash
scp -r "$env:USERPROFILE\Documents\My Games\FarmingSimulator2025\savegame1" root@ClaudeVM:~/FS_sweden_map/data/tysslinge/   # från Windows
python scripts/import_savegame.py --map tysslinge data/tysslinge/savegame1
python scripts/build_map.py --map tysslinge
```

Placeringarna sparas i `maps/<namn>/placeringar.json` och följer med i varje
ombyggnad. Objekt från andra moddar blir beroenden i kartans `modDesc.xml`.

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
| marktacke | `fetch_landcover.py --produkt marktacke` | `data/<namn>/lm/vektor/marktacke_<kommun>/` |
| trad | `laser_trees.py` | `data/<namn>/lm/laser/krontak.tif` och `data/<namn>/lm/trad.json` |
| karta | `build_map.py` | `build/<namn>/<mod_name>.zip`, färdig FS25-modd |
| kontroll | `kontrollkarta.py` | `build/<namn>/kontrollkarta/index.html` |
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
