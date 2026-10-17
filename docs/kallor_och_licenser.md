# Källor och licenser

Texten nedan ska följa med den publicerade modden, till exempel i
`modDesc.xml` (beskrivningen) och som en textfil i modden.

## Text till modden

> Kartan bygger på verkliga data för området kring Tysslinge, Örebro kommun.
> Alla data har bearbetats för att passa spelet.
>
> - Höjddata: Markhöjdmodell Nedladdning, grid 1+, © Lantmäteriet, bearbetad, CC BY 4.0
> - Flygbilder som förlaga: Ortofoto Nedladdning, © Lantmäteriet, bearbetad, CC BY 4.0
> - Fältgränser: Jordbruksblock och jordbruksskiften, © Jordbruksverket, bearbetad
> - Vägar, byggnader, skog och vatten: © OpenStreetMap-bidragsgivare, ODbL
>   (openstreetmap.org/copyright)
> - Grundkarta genererad med MapToPlay (källangivelser i `maptoplay.json`)
>
> CC BY 4.0: creativecommons.org/licenses/by/4.0/

Raden om ortofoto tas bara med om ortofotot faktiskt har använts.
Kontrollera Jordbruksverkets licens för blockdatabasen innan publicering.

## Villkor för Lantmäteriets ortofoto

Ortofoto Nedladdning innehåller personuppgifter och omfattas av
Lantmäteriets "Användningsvillkor för värdefulla datamängder som innehåller
personuppgifter" (dnr LM2025/009269, version 1.1). Det innebär:

- Bilderna får bara användas för det ändamål som angavs i ansökan, alltså
  som förlaga till den här kartan.
- Bara det område som behövs hämtas: 8×8 km kring kartans mittpunkt.
  `fetch_orthophoto.py` hämtar exakt det området.
- Bilderna lagras och bearbetas bara på egna datorer i Sverige.
  **De laddas inte upp till MapToPlay eller andra molntjänster.**
- Bilderna sprids inte, varken hela eller som utsnitt. Modden innehåller
  inga ortofoton, inte heller i översiktskartan.
- Lantmäteriet kan göra stickprovskontroller.

Höjdmodellen innehåller inga personuppgifter men kräver samma källangivelse
enligt CC BY 4.0.
