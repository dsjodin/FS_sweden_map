# Arbetsgång från verklig plats till FS25-karta

Den här guiden är skriven för den som aldrig byggt en FS25-karta. Varje fas
avslutas med något konkret som går att titta på innan nästa fas börjar.

## Program som behövs

| Program | Till vad | Kostnad |
|---|---|---|
| Farming Simulator 25 | Testa kartan | Har du redan |
| GIANTS Editor 10 | Huvudverktyget för att bygga kartan | Gratis via GIANTS Developer Network (gdn.giants-software.com), kräver konto |
| Maps4FS | Genererar en grundkarta (terräng, fält, vägar, skog) från geodata | Gratis, öppen källkod |
| QGIS | Titta på och klippa geodata | Gratis |
| GIMP eller Paint.NET | Redigera masker och texturer | Gratis |
| Python 3.11 eller senare | Skripten i det här repot | Gratis |
| Blender med GIANTS I3D-exporter | Egna 3D-modeller, till exempel en röd ladugård. Behövs först i fas 5 | Gratis |

GIANTS Editor finns för Windows och macOS. Skripten i repot fungerar överallt.

## Fas 1: Välj område och storlek

- Öppna `tools/omradesval.html`, flytta rutan och jämför storlekarna.
- Bestäm mittpunkt och storlek, och för in dem i `config/area.json`.
- FS25 stöder kartstorlekarna 2048, 4096, 8192 och 16384 m. En meter i
  verkligheten blir en meter i spelet.

**Klart när:** `config/area.json` har rätt mittpunkt och storlek.

## Fas 2: Hämta data

Se [datakallor.md](datakallor.md). Kortfattat:

1. **Höjdmodell** från Lantmäteriet (Markhöjdmodell, 1 m grid). Den blir
   kartans terräng.
2. **Ortofoto** från Lantmäteriet. Används som förlaga när fält, vägar och gårdar
   ritas, och som jämförelse.
3. **Topografi/fastighetskarta** från Lantmäteriet i vektorformat. Ger
   markslag, byggnader, vägar, diken och stenmurar.
4. **Jordbruksblock** från Jordbruksverket. Ger de verkliga åkrarnas gränser,
   vilket är bättre än OSM.
5. **OpenStreetMap** som komplement (redan hämtat).

**Klart när:** all rådata ligger i `data/raw/` och `data/lm/`, klippt till
området med lite marginal.

## Fas 3: Gör om datan till FS25-format

Skript som ska skrivas i den här fasen:

- `make_heightmap.py`: höjdmodell till 16-bitars PNG i kartans upplösning.
  Höjdskalan väljs så att terrängen inte blir trappstegad.
- `make_masks.py`: åker, skog, vägar, vatten och gårdsplan som svartvita
  masker. Maskerna används för terrängtexturer och för att placera skog.
- `make_fields.py`: fältgränser från jordbruksblocken, förenklade så att de
  går att köra på i spelet.

Alternativet är att låta Maps4FS göra en stor del av detta och bara ge den vår
egen höjdmodell. Vi provar Maps4FS först och skriver egna skript där resultatet
inte räcker.

**Klart när:** höjdkarta och masker ser rätt ut jämfört med ortofotot.

## Fas 4: Grundkarta i GIANTS Editor

- Generera kartan med Maps4FS (eller kopiera in egna höjdkartor och masker i en
  tom FS25-kartmall).
- Öppna `map.i3d` i GIANTS Editor och kontrollera terrängen.
- Starta kartan i spelet tidigt, redan innan den är snygg. Då märks fel i
  grundinställningarna innan mycket arbete lagts på dem.

**Klart när:** du kan köra en traktor på den tomma terrängen i spelet.

## Fas 5: Bygg ut kartan

Ungefär i den här ordningen:

1. **Terrängtexturer:** åker, gräs, grus, skogsmark.
2. **Fält:** fältdefinitioner och farmlands (köpbara markområden).
3. **Vägar:** asfaltsvägar och grusvägar som splines, med diken.
4. **Gårdar:** byggnader på de verkliga gårdsplanerna. Börja med spelets egna
   objekt och byt till svenska modeller efter hand.
5. **Skog och vegetation:** gran och tall i skogsdungarna, lövträd längs
   bäckar och åkerholmar.
6. **Vatten:** bäckarna och dammarna.
7. **Svenska detaljer:** röda ladugårdar med vita knutar, gärdsgårdar och
   stenmurar, rundbalar i vit plast, brevlådor, Tysslinge kyrka.

## Fas 6: Gör kartan spelbar

- Startgård med maskinhall och spannmålssilo.
- Spannmålsmottagning och försäljningsställen. Kan vara fiktiva eller
  inspirerade av verkliga platser i närheten.
- PDA-kartan (översiktskartan) från ortofoto eller masker.
- Trafik och fotgängare längs vägarna (AI-splines).

## Fas 7: Test och paketering

- `modDesc.xml` med namn, version och beskrivning.
- Zippa som `FS25_Tysslinge.zip` och lägg i mods-mappen.
- Kontrollera loggen (`log.txt`) efter fel och varningar.
