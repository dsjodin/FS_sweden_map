# Datakällor

Kontrollera alltid aktuella villkor hos respektive leverantör innan data
används i en mod som publiceras.

## Lantmäteriet

Lantmäteriets data laddas ner via **Geotorget** (geotorget.lantmateriet.se).
Ett konto behövs, och det är gratis för öppna data. Beställ för ett område som
täcker kartrutan plus cirka 500 m marginal.

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

**Jordbruksblock** (blockdatabasen) finns som öppna data och visar
åkermarkens verkliga avgränsning. Den används för att ta fram fälten i spelet.

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
