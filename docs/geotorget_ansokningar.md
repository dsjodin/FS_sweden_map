# Ansökningar på Geotorget

Lantmäteriets produkter som innehåller personuppgifter kräver en ansökan med
samma formulär varje gång: behandling, personuppgiftsansvar, var datan lagras
och tre fritextfält med teckengränser. Här finns färdiga texter att klistra in,
så att ansökningarna blir lika och stämmer med hur skripten faktiskt använder
datan.

## Status

| Produkt | Används till | Ansökan | Status |
|---|---|---|---|
| Markhöjdmodell Nedladdning (grid 1+) | Terräng | Ingen ansökan om personuppgifter | Beviljad, används |
| Ortofoto Nedladdning | Förlaga, översiktskarta | Texter under [Ortofoto](#ortofoto-nedladdning) | Ansökt |
| Topografi 10 Nedladdning, vektor | Vattendrag, marktyper, vägar, byggnader | Texter under [Topografi 10](#topografi-10-nedladdning-vektor) | Ansökt |
| Marktäcke Nedladdning, vektor | Skog, åker, sankmark, vatten | Mallen nedan | Beställd. Täcks troligen av Topografi 10 |
| Byggnad Nedladdning, vektor | Byggnader | Mallen nedan | Beställd. Täcks troligen av Topografi 10 |
| Hydrografi Nedladdning | Vattendrag | Går inte att få | Avslagen: bara för myndigheter, tillståndsärenden och forskning |

Uppdatera tabellen när en ansökan beviljas.

## Fält som är lika för alla produkter

**Behandling** (om det är ett fritextfält):
> Datan lagras och bearbetas på mina egna datorer i Sverige.
> Den används enbart som underlag i ett privat hobbyprojekt.

**Personuppgiftsansvar:** kryssa i rutan. Som privatperson som själv bestämmer
hur datan används är du personuppgiftsansvarig.

**Var sker lagring/bearbetning:** Inom EU/EES.

**Geografiskt område** (128 av 200 tecken):
> Hela Sverige. Kartor görs för valfria landsbygdsområden i landet, cirka 8×8 km per karta, med början i Tysslinge, Örebro kommun.

Välj **Sverige** som geografiskt urval i beställningen, så att det stämmer med
texten.

## Personuppgiftsansvar och undantaget för privat bruk

GDPR gäller inte när en privatperson behandlar personuppgifter för privat
bruk utan att sprida dem (artikel 2.2 c). Lantmäteriet prövar om det
undantaget gäller utifrån motiveringen. Texterna är skrivna för att det ska
gå att bedöma:

- **Privat bruk:** en hobby utan kommersiellt syfte. Datan används bara av
  mig, på mina egna datorer hemma.
- **Ingen spridning av personuppgifter:** varken datan eller utsnitt ur den
  sprids. En publicerad modd innehåller bara egen spelgrafik, utan personer,
  fordon, namn, ägare eller adresser.

Det som skulle kunna tolkas som spridning är modden. Därför får modden aldrig
innehålla bilder eller utsnitt ur ortofoton, inte heller som översiktskarta.
`build_map.py` ritar översiktskartan från kartans egna marktyper, vägar och
byggnader, och den ska fortsätta göra det.

## Mall för nya produkter

Byt `[DATA]` mot vad produkten innehåller och `[ANVÄNDNING]` mot vad den ska
användas till i spelet. Håll texten under 900 tecken.

**Hur informationen kommer att användas:**
> Datan ska användas som underlag när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Jag använder [DATA] för att [ANVÄNDNING]. För varje karta används bara ett begränsat område på cirka 8×8 km. Datan bearbetas på mina egna datorer. Jag använder inga uppgifter om ägare eller adresser och gör ingen analys av personer eller fastigheter. Eventuella personuppgifter i datan behandlas inte särskilt. Projektet är en privat hobby utan kommersiellt syfte.

**Om informationen kommer att spridas:**
> Själva datan sprids inte. Den lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den bara spelgrafik och förenklade former som jag skapat utifrån datan. Inga uppgifter om personer, ägare eller adresser följer med. Källan anges som "[PRODUKTNAMN], © Lantmäteriet, bearbetad, CC BY 4.0".

## Topografi 10 Nedladdning, vektor

Beställning: engångsuttag, SWEREF 99 TM, GeoPackage, urval Sverige. Avgift 0 kr.

**Hur informationen kommer att användas** (732 av 900 tecken):
> Datan ska användas som underlag när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Jag använder vattendrag, marktyper (skog, åker, sankmark, vatten), vägar och byggnadernas läge och form för att placera dessa rätt i spelet. För varje karta används bara ett begränsat område på cirka 8×8 km. Datan bearbetas på mina egna datorer. Jag använder inga uppgifter om ägare eller adresser och gör ingen analys av personer eller fastigheter. Eventuella personuppgifter i datan behandlas inte särskilt. Projektet är en privat hobby utan kommersiellt syfte.

**Om informationen kommer att spridas** (462 av 900 tecken):
> Själva datan sprids inte. Den lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den bara spelgrafik och förenklade former som jag skapat utifrån datan, till exempel var skog, vattendrag och vägar finns. Inga attribut som namn på byggnader, ägare eller adresser följer med. Källan anges som "Topografi 10, © Lantmäteriet, bearbetad, CC BY 4.0".

## Ortofoto Nedladdning

Klistra in **en** text per fält. Geografiskt område: samma text som under
"Fält som är lika för alla produkter".

**Hur informationen kommer att användas** (757 av 900 tecken):
> Ortofotona ska användas som förlaga när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Bilderna används för att se var åkerkanter, diken, vägar, gårdar och träd ligger, så att kartorna blir verklighetstrogna. För varje karta hämtas bara ett begränsat område på cirka 8×8 km, som skalas ned till 0,5 m upplösning. Bilderna bearbetas på mina egna datorer och används bara av mig. Jag gör ingen analys av personer, fastigheter eller fordon. Eventuella personuppgifter i bilderna behandlas inte särskilt. Behandlingen sker för privat bruk, i en hobby utan kommersiellt syfte.

**Om informationen kommer att spridas** (575 av 900 tecken):
> Ortofotona och eventuella personuppgifter i dem sprids inte. Bilderna lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den inga ortofoton och inga utsnitt ur dem, inte heller i översiktskartan. Den innehåller bara spelgrafik som jag själv har skapat med bilderna som förlaga, till exempel var åkrar, vägar och skog finns. Inga personer, fordon, namn eller adresser följer med. Källan anges som "Ortofoto Nedladdning, © Lantmäteriet, bearbetad, CC BY 4.0".

## Det här lovar ansökningarna, och skripten följer det

Det som står i ansökningarna är också det som gäller enligt Lantmäteriets
användningsvillkor (se [kallor_och_licenser.md](kallor_och_licenser.md)):

- Datan används bara för att bygga kartor till FS25.
- Bara kartans område används, cirka 8×8 km. Skripten läser bara ut det
  området ur Lantmäteriets filer.
- Datan lagras bara på egna datorer i Sverige. **Den laddas inte upp
  till MapToPlay eller andra molntjänster.**
- Inga uppgifter om ägare, adresser eller personer används eller följer med
  i modden.
- Modden innehåller inga ortofoton eller utsnitt ur dem. Översiktskartan
  ritas från kartdatan, inte från ortofoton.
- Källan anges i modden (`modDesc.xml`) med produktnamn, © Lantmäteriet,
  bearbetad och CC BY 4.0.
- Lantmäteriet kan göra stickprov. Avviker användningen från ansökan kan
  behörigheten dras in.
