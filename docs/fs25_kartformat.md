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
- Gröda på ett fält: `densityMap_fruits.gdm` med värdet `typIndex | (status << 5)`,
  till exempel vete = typIndex 6.

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
