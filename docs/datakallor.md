# Datakällor

Kontrollera alltid aktuella villkor hos respektive leverantör innan data
används i en mod som publiceras.

## Lantmäteriet

Lantmäteriets data laddas ner via **Geotorget** (geotorget.lantmateriet.se).
Ett konto behövs, och det är gratis för öppna data.

### Höjdmodellen, steg för steg

1. Skapa ett konto på geotorget.lantmateriet.se.
2. Gå till produkten **Markhöjdmodell Nedladdning, API**
   (geotorget.lantmateriet.se/geodataprodukter/markhojdmodell-nedladdning-api)
   och beställ behörighet. Det är gratis, och datan är öppna data (CC BY 4.0).
   Vänta tills beställningen är godkänd.
3. Kör skriptet med samma användarnamn och lösenord som du loggar in på
   Geotorget med. Det gäller privatpersoner. En organisation använder i
   stället systemkontot som behörigheten är kopplad till. Tjänsten använder
   HTTP Basic-inloggning, och skriptet sköter det.

   ```powershell
   $env:LM_USER="ditt-användarnamn"; $env:LM_PASSWORD="ditt-lösenord"
   python scripts/fetch_heightmap.py
   ```

Skriptet hittar rätt rutor via Lantmäteriets STAC-tjänst. För vår karta
behövs rutorna 656_49, 656_50, 657_49 och 657_50, som är 10×10 km vardera.
Skriptet läser bara den del som behövs och sparar `data/lm/hojd/dtm_area.tif`.
Om skriptet svarar "401" har kontot ännu inte åtkomst till produkten.

| Datamängd | Användning | Kommentar |
|---|---|---|
| Markhöjdmodell Nedladdning, grid 1+ | Terräng (höjdkarta) | 1 m upplösning, GeoTIFF, SWEREF 99 TM. Detta är den viktigaste datamängden. |
| Ortofoto | Förlaga och PDA-karta | Visar fältgränser, gårdar och diken. |
| Topografi 10 / Fastighetskartan, vektor | Byggnader, vägar, markslag, diken | Mer komplett än OSM för byggnader och småvägar. |
| Laserdata (punktmoln) | Trädhöjder, byggnadshöjder | Valfritt, för den som vill gå längre. |

Alla datamängder ligger i referenssystemet **SWEREF 99 TM (EPSG:3006)**.
Skripten räknar i samma system. Mittpunkten i områdesväljaren visas även i
SWEREF 99 TM, så att det är lätt att beställa rätt ruta.

## Jordbruksverket

Jordbruksblock och **skiften** finns som öppna data via Jordbruksverkets
WFS-tjänst (epub.sjv.se/inspire). Ingen inloggning behövs. Hämtas med
`scripts/fetch_fields.py`.

- **Block** är sammanhängande jordbruksmark som avgränsas av vägar, diken,
  skog och liknande.
- **Skiften** är fälten inom blocken så som lantbrukarna sökt stöd för dem,
  med grödkod för året (`grdkod_mar`). De är den bästa källan till fältens
  form i spelet och till vilka grödor som ska odlas var.

Grödkoderna översätts i skriptet bara när de är bekräftade mot
Jordbruksverkets texter (till exempel 2 = vårkorn, 3 = havre, 5 = vårvete,
21 = vårraps). Övriga koder visas som siffror tills de är kontrollerade.

## OpenStreetMap

Hämtas med `scripts/fetch_osm.py`. Används för ortnamn, vägklasser och som
komplement. Licens: ODbL. Ange "© OpenStreetMap-bidragsgivare" i modden.

## Mappstruktur för rådata

```
data/raw/osm.json        OSM (fetch_osm.py)
data/lm/hojd/            Lantmäteriet höjdmodell (GeoTIFF)
data/lm/ortofoto/        Lantmäteriet ortofoto
data/lm/topografi/       Lantmäteriet vektordata
data/jbv/                Jordbruksverkets jordbruksblock
```

Rådata checkas inte in i git eftersom filerna är stora (se `.gitignore`).
