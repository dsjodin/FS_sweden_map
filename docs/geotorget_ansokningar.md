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
| Ortofoto Nedladdning | Förlaga för detaljer | Texter under [Ortofoto](#ortofoto-nedladdning) | Ansökt, väntar på prövning |
| Topografi 10 Nedladdning, vektor | Vattendrag, marktyper, vägar, byggnader | Texter under [Topografi 10](#topografi-10-nedladdning-vektor) | Ansökt, väntar på prövning |
| Marktäcke Nedladdning, vektor | Skog, åker, sankmark, vatten | Texter under [Marktäcke](#marktäcke-nedladdning-vektor) | Beviljad direkt (automatiskt godkänd) |
| Byggnad Nedladdning, vektor | Byggnader och deras ändamål | Texter under [Byggnad](#byggnad-nedladdning-vektor) | Ansökt, väntar på prövning |
| Hydrografi Nedladdning | Vattendrag | Går inte att få | Avslagen: bara för myndigheter, tillståndsärenden och forskning |

Uppdatera tabellen när en ansökan beviljas.

Topografi 10 och Marktäcke/Byggnad överlappar, men de levereras olika.
Topografi 10 är ett engångsuttag av hela Sverige. Marktäcke och Byggnad
hämtas per kommun via Lantmäteriets API, och `fetch_landcover.py` hämtar dem
automatiskt för varje ny karta, alltid i senaste versionen. Byggnad har
dessutom byggnadens ändamål (bostad, ekonomibyggnad med flera), som behövs
för att välja rätt sorts byggnad i spelet. Därför beställs alla tre.


## Fält som är lika för alla produkter

**Behandling** (om det är ett fritextfält):
> Datan lagras och bearbetas på mina egna datorer i Sverige.
> Den används enbart som underlag i ett privat hobbyprojekt.

**Personuppgiftsansvar:** kryssa i rutan. Som privatperson som själv bestämmer
hur datan används är du personuppgiftsansvarig.

**Var sker lagring/bearbetning:** Inom EU/EES.

**Geografiskt område** (128 av 200 tecken):
> Hela Sverige. Kartor görs för valfria landsbygdsområden i landet, cirka 8×8 km per karta, med början i Tysslinge, Örebro kommun.

Texten beskriver vad behörigheten ska gälla. Själva uttaget kan vara mindre:

- **Produkter som hämtas via API** (Marktäcke, Byggnad, Ortofoto,
  Markhöjdmodell): välj urval **Sverige**. Skripten hämtar ändå bara de
  rutor eller kommuner som kartan berör.
- **Produkter som levereras som fil** (Topografi 10): välj några få län där
  kartor är aktuella, inte hela Sverige. Det blir en mindre fil, och
  skripten använder ändå bara kartans område ur den. Beställ ett nytt uttag
  om en karta ska göras i ett annat län.

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

Beställning: engångsuttag, SWEREF 99 TM, GeoPackage. Urval: några få län där
kartor är aktuella, alltid Örebro län för Tysslinge. Avgift 0 kr.

**Geografiskt område** (169 av 200 tecken). Ändra listan om du väljer
andra län, så att texten stämmer med uttaget:
> Örebro, Östergötlands, Västra Götalands och Skåne län. Kartor görs för landsbygdsområden om cirka 8×8 km per karta inom dessa län, med början i Tysslinge, Örebro kommun.

**Hur informationen kommer att användas** (732 av 900 tecken):
> Datan ska användas som underlag när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Jag använder vattendrag, marktyper (skog, åker, sankmark, vatten), vägar och byggnadernas läge och form för att placera dessa rätt i spelet. För varje karta används bara ett begränsat område på cirka 8×8 km. Datan bearbetas på mina egna datorer. Jag använder inga uppgifter om ägare eller adresser och gör ingen analys av personer eller fastigheter. Eventuella personuppgifter i datan behandlas inte särskilt. Projektet är en privat hobby utan kommersiellt syfte.

**Om informationen kommer att spridas** (462 av 900 tecken):
> Själva datan sprids inte. Den lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den bara spelgrafik och förenklade former som jag skapat utifrån datan, till exempel var skog, vattendrag och vägar finns. Inga attribut som namn på byggnader, ägare eller adresser följer med. Källan anges som "Topografi 10, © Lantmäteriet, bearbetad, CC BY 4.0".

## Marktäcke Nedladdning, vektor

Villkor: Användningsvillkor för värdefulla datamängder, utan personuppgifter.
Texterna nedan behövs bara om formuläret ändå frågar efter motivering.

Beställning: SWEREF 99 TM, urval Sverige. Avgift 0 kr. Hämtas med `fetch_landcover.py` när behörigheten är klar.

**Hur informationen kommer att användas** (784 av 900 tecken):
> Datan ska användas som underlag när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Jag använder marktyperna (skog, åker, sankmark, vatten, bebyggelse) för att lägga rätt marktextur och placera skog och vatten på rätt ställen i spelet. För varje karta används bara ett begränsat område på cirka 8×8 km. Datan bearbetas på mina egna datorer och används bara av mig. Jag använder inga uppgifter om ägare eller adresser och gör ingen analys av personer eller fastigheter. Eventuella personuppgifter i datan behandlas inte särskilt. Behandlingen sker för privat bruk, i en hobby utan kommersiellt syfte.

**Om informationen kommer att spridas** (504 av 900 tecken):
> Själva datan och eventuella personuppgifter i den sprids inte. Datan lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den bara spelgrafik och förenklade former som jag skapat utifrån datan, till exempel var skog, åker och vatten finns. Inga uppgifter om personer, ägare eller adresser följer med. Källan anges som "Marktäcke Nedladdning, vektor, © Lantmäteriet, bearbetad, CC BY 4.0".

## Byggnad Nedladdning, vektor

Beställning: SWEREF 99 TM, urval Sverige. Avgift 0 kr. Hämtas med `fetch_landcover.py` när behörigheten är klar.

**Hur informationen kommer att användas** (788 av 900 tecken):
> Datan ska användas som underlag när jag bygger egna kartor (moddar) till datorspelet Farming Simulator 25 över verkliga platser på svensk landsbygd i olika delar av landet. Den första kartan gäller Tysslinge i Örebro kommun, och fler kartor ska göras på andra platser. Jag använder byggnadernas läge, form och ändamål (till exempel bostad eller ekonomibyggnad) för att placera passande byggnader från spelet på rätt ställen. För varje karta används bara ett begränsat område på cirka 8×8 km. Datan bearbetas på mina egna datorer och används bara av mig. Jag använder inga uppgifter om ägare eller adresser och gör ingen analys av personer eller fastigheter. Eventuella personuppgifter i datan behandlas inte särskilt. Behandlingen sker för privat bruk, i en hobby utan kommersiellt syfte.

**Om informationen kommer att spridas** (503 av 900 tecken):
> Själva datan och eventuella personuppgifter i den sprids inte. Datan lagras bara på mina egna datorer i Sverige och laddas inte upp till molntjänster. Om en färdig kartmodd publiceras, till exempel gratis på spelets moddsidor, innehåller den bara spelgrafik och förenklade former som jag skapat utifrån datan, till exempel var det finns hus och ladugårdar. Inga uppgifter om personer, ägare eller adresser följer med. Källan anges som "Byggnad Nedladdning, vektor, © Lantmäteriet, bearbetad, CC BY 4.0".

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
