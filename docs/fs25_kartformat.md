# FS25-kartformatet: källor och plan för egen generering

Målet är att generera färdiga FS25-kartor själva, utan MapToPlay, från
Lantmäteriets höjddata, Jordbruksverkets skiften och OSM.

## Källor

| Källa | Vad den ger | Pålitlighet |
|---|---|---|
| [BrewingCoder/fs25-empty-map](https://github.com/BrewingCoder/fs25-empty-map), kopierad till `third_party/fs25_empty_map/` (MIT) | Python som genererar en komplett FS25-karta från grunden, med dokumentation av varje fil: modDesc, map.xml, i3d, terrängnod, höjdkarta, viktkartor, `.gdm`, `.grle`, fält. Listar elva krav som var och en orsakade krasch när de saknades. | Tredjepart, ett enda commit. Dokumentationen bygger på provladdningar i spelet med loggar, men behöver bekräftas på vår FS25-version. |
| [GIANTS Developer Network, videoguider](https://gdn.giants-software.com/videoTutorials2.php) | 15 officiella guider för kartbygge i FS25 (maj 2025), bland annat terräng, fält, farmlands, infolager, gator, splines, försäljningsställen och procedurell placering. | Officiellt. Video, ingen skriven specifikation. |
| Spelets egen karta `$data/maps/mapUS/mapUS.i3d` | Facit för terränglager, foliage och infolager. fs25-empty-map har läst ut dem till JSON. | Officiellt, men får bara refereras, inte kopieras in i en mod. |
| Exporten från MapToPlay | En fungerande karta att jämföra med. Läses av med `scripts/inspect_export.py`. | Fungerar i spelet. |

GIANTS har ingen officiell kartmall eller skriven formatspecifikation för FS25.

## Viktiga fakta från fs25-empty-map

- En karta består av `modDesc.xml`, `maps/map.xml`, en `.i3d`-scen och
  datafiler i `maps/data/`. Shaders, marktexturer och miljöinställningar
  refereras från spelet via `$data/…`, så kartan kräver att FS25 är installerat.
- 4×4 km-karta (4096 m): höjdkarta 2049×2049 med 2 m per pixel (`unitsPerPixel`
  2), viktkartor 4096×4096, densitetskartor 8192×8192 (2 px/m), farmland och
  fieldType 2048×2048.
- Terrängnoden måste ha hela spelets uppsättning lager: 86 Layer, 37
  OverlayLayer, 43 CombinedLayer och 21 CombinedOverlayLayer. Annars kraschar
  spelet.
- `.gdm` (densitet: markstatus, grödor) och `.grle` (infolager: farmlands)
  skrivs direkt från Python. Inga verktyg från GIANTS behövs.
- Fält är noder i i3d-filen (`fields` → `fieldN` → `polygonPoints`) som
  registreras med `FieldUtil.onCreate`. Farmlands är pixlar i
  `infoLayer_farmland.grle` plus `farmlands.xml`.
- Gröda på ett fält: `densityMap_fruits.gdm`. Värdet räknas annorlunda än
  fs25-empty-map skriver, se "Växtlagren" nedan.

## Plan

1. **Testa grunden.** Bygg den tomma 4×4 km-kartan från fs25-empty-map och
   ladda den i spelet. Den ska starta utan fel och ha ett ägt vetefält i mitten.
2. **Vår terräng.** Byt den platta höjdkartan mot Lantmäteriets, 2049×2049
   med 2 m per pixel.
3. **Våra fält.** Skriv fältnoder, farmlands och markstatus från
   Jordbruksverkets skiften.
4. **Marktexturer.** Viktkartor från OSM och skiften: åker, gräs, grus,
   asfalt och skogsmark.
5. **Översiktskarta.** Den kan bygga på ortofotot, eftersom allt stannar lokalt.
6. **Grödor** enligt skiftenas grödkoder.
7. **Träd, byggnader och vägar.** Det är den svåraste delen. Där kan
   MapToPlay eller handarbete i GIANTS Editor fortfarande behövas.

## Avläst från spelets egen karta Zielonka (mapEU)

Läst ur spelets egna filer för att lära formatet. Inget är kopierat in i
modden, vi refererar bara spelets objekt via `$data/…`.

- **Träd** är `<ReferenceNode name=… translation="x y z" rotation="0 vridning 0"
  referenceId=…>` i en `trees`-grupp i scenen. Filen pekar på
  `$data/maps/trees/<art>/<art>_stageNN.i3d`, där stage01–06 är storlekar. Zielonka
  har 9 076 träd av arterna oak, aspen, beech, downyServiceBerry och apple.
- **Byggnader och försäljningsställen** står i `config/placeables.xml` som
  `<placeable filename="$data/placeables/…" position=… rotation=…>`, till exempel
  gårdsbyggnader, silor (`farma400`) och spannmålsmottagningen `grainMill`.
  Gårdshuset har barnen `<farmhouse isFreeForAll="true"/>` och `<wardrobe …/>`.
- **Köpta fordon** dyker upp vid `storeSpawnPlace1Start`, med barnet
  `storeSpawnPlace1End` 40 m bort. Callback `BaseMission.onCreateStoreSpawnPlace`.
- **Startgrödor** per fält står i `config/fields.xml`: `<field fieldId=…>` med
  `<fruit type="WHEAT" growthState="HARVESTREADY"/>` och `<ground type="HARVEST_READY"/>`,
  eller `<fruit type="UNKNOWN"/>` med `<ground type="PLOWED"/>`. Den refereras från
  map.xml med `<fields filename=…/>`.
- **Startfordon** står i `config/vehicles.xml` som `<vehicle filename="data/vehicles/…"
  farmId="1" defaultFarmProperty="true">` med en `<component>` per fordonsdel.
- Vägar, byggnader på orterna, stolpar och skyltar är egna 3D-objekt i kartans
  `.i3d.shapes`. Dem kan vi inte generera på samma sätt.

Det här används av `scripts/fs25_objects.py`.

## Rön från provspelningen (oktober 2026)

Allt här är bekräftat i spelet, i spelets logg eller i GIANTS Editor 10, om inget
annat står. Det används av `scripts/build_map.py` och `scripts/fs25_objects.py`.

### Densitetsfilerna (`.gdm`)

- **Bitarna packas per pixel.** En ruta (32 × 32 pixlar) har en palett med högst
  fyra värden. Med tre eller fyra värden används två bitar per pixel, och pixel k
  ligger i bit 2k (låg) och 2k+1 (hög), byte för byte med minst signifikant bit
  först. fs25-empty-map skrev två separata bitplan. Det märks bara i rutor med
  fler än två värden, så den bearbetade jorden och fältens inre såg rätt ut medan
  fältkanter, vägrenar och skogskanter blev omkastade i spelet. Avläst ur rutor som
  GIANTS Editor själv skrivit i en sparad `densityMap_fruits.gdm`. Rättat i
  `third_party/fs25_empty_map/tools/binfmt.py`.
- **Högst fyra värden per ruta** (`maxBpp` 2). Fler blandas ihop. `limit_palette` i
  build_map.py förenklar sådana rutor innan de skrivs, och grödorna har företräde.

### Växtlagren (`densityMap_fruits.gdm`, 10 kanaler, 5 för typen)

- **Värde = typnummer + tillstånd × 32.** Typnumret är platsen i fruits-lagrets lista
  med 1 som första (decoFoliage 1, decoBushUS 2, meadow 3, forestPlants 4,
  waterPlants 5, grass 6, wheat 7, canola 8, barley 9, …, oat 17), i samma ordning
  som `base_foliage.json`. Tillståndet är platsen i listan Layer State i GIANTS Editor,
  med 1 som första.
- Avläst i GIANTS Editors Foliage-panel. De ibockade rutorna under Foliage Channels är
  värdets bitar. Rutorna 0–4 är typen och 5–9 tillståndet.

  | Lager | Tillstånd | Värde |
  |---|---|---|
  | grass | harvestReady (4) | 134 |
  | wheat | harvestReady (8), harvested 10, dead 9 | 263 |
  | barley | harvestReady (8) | 265 |
  | oat | harvestReady (5) | 177 |
  | canola | harvestReady (9) | 296 |
  | meadow | harvestReady (4), cut 5 | 131 |
  | forestPlants | typ 4 | t.ex. deerFern (8) = 260 |

- Kommentarerna i foliage-filerna (`"0 0 0 1 - harvest ready"`) är bitarna med minst
  signifikant först och stämmer för vete, havre, raps och gräs, men **inte för korn**:
  barley.xml säger 7, editorn visar 8.
- Tillståndslistorna, i editorns ordning:
  - **forestPlants:** dry branches, clovers, starflower, bunchberry, salmonBerryBush,
    starryFalseSolomonSeal, swordFern, deerFern, grass, riceLongGrainDeco
  - **decoFoliage:** smallDenseMix, smallRumex, apera, whiteTallWeed, greenTallWeed,
    cirsium, papaverRhoeas, rumex, grassSmall, grassMedium, grassCut, coneflower,
    slenderMountainMint, wildBergamot, prairieBlazingStar
  - **waterPlants:** typhaLatifolia Small/Medium/Large, miscanthusSinensis
    Small/Medium/Large, stipaTenuissima Small/Large
  - **grass:** invisible, greenSmall, greenMiddle, harvestReady, cut, cutRolled
- **decoBush** ligger i ett eget lager (`densityMap_groundFoliage.gdm`, 4 kanaler,
  ingen typ). Vi antar att värdet är platsen i listan (Small 1, Medium 2, Big 3,
  Super Big 4, Blueberry Short–Tall 5–9, Boxwood 10–12, Hazelnut 13–15). Det är inte
  avläst än.
- `terrainDetail` (markens bearbetning) visar inga tillstånd i editorns Foliage-panel.
  Vi använder värdet 2 (kultiverad) som fs25-empty-map.

### Fält och markområden

- **Ett fält per markområde.** Fler fält på samma markområde ger `Error: FieldManager -
  There already exists field 'N' on farmland 'M'`, och de fälten försvinner. Därför är
  varje fält ett eget markområde (fält N på markområde N).
- **Mark utan markområde (id 0)** kan alla bygga på och fälla träd på (slutsats av
  provspelningen). Hela kartan täcks därför av markområden. Högst 254 markområden.
- `Warning: Missing area for FieldUpdateTask` kom för 94 av 184 fält. Orsaken är
  okänd: varken markområde, form, antal hörn eller gröda skiljer ut dem. Grannarnas
  fält får ändå ett läge efter årstiden (spelet startar i augusti), och spelets egen
  karta har bara två fält i `fields.xml`. Grödorna målas därför också direkt i
  `densityMap_fruits.gdm`.
- I den svenska översättningen heter markområden "åkermark", även när de är skog.

### map.xml, byggnader och fordon

- Utan `<storeItems filename="$data/maps/mapEU/config/storeItems.xml"/>` laddas inte
  spelets egna kartbyggnader (`not defined in store items`), och utan
  `<animals filename="$dataS/character/animals.xml">` (med `names` och `food`) laddas
  inga djurbyggnader (`Animal type 'COW' not found`). Raderna är avlästa ur mapEU.xml.
- Kartans `vehicles.xml` har samma format som sparfilens (`savegame_vehicles.xsd`).
  Fordonen kan kopieras rakt ur en sparfil med `defaultFarmProperty="true"`
  (`import_savegame.py --fordon`).
- Moddbyggnader kan placeras från kartans `placeables.xml` med `$moddir$<modd>/…`
  och modden som `<dependency>` i modDesc.xml.

### Träd ur prefab-paket

- FS25 saknar gran. Prefab-paketet `FS25_sprucepack_prefab` är en enda i3d med sex
  granar. Kartans träd är ReferenceNodes till en fil per träd, så paketet delas i en
  i3d per gran som delar `.i3d.shapes` och texturer (`prefab_trees.py`).
- Stammens `splitType="1"` är gran, så granarna går att fälla. i3d-filen pekar på
  `.png` men paketet har `.dds`, och spelet tar `.dds` automatiskt.
- Ett prefab-paket i spelets mods-mapp ger `Failed to open xml file …/modDesc.xml`.
  Det ska bara ligga i `data/mods` på servern.
