# Källa

Kopia av [BrewingCoder/fs25-empty-map](https://github.com/BrewingCoder/fs25-empty-map),
commit `b19e4e145c1075b4c69d5fbb1219fb2f4f6bde9c` (2026-07-08), MIT-licens (se `LICENSE`).

Projektet genererar en laddningsbar FS25-karta helt från Python och dokumenterar
filformaten (`docs/`): modDesc, map.xml, i3d och terrängnoden, höjdkarta,
viktkartor, densitetskartor (`.gdm`), infolager (`.grle`) och fält.

Vi använder det som grund för att generera egna kartor utan MapToPlay. Ändringar
görs i våra egna skript under `scripts/`, inte här, så att det går att uppdatera
kopian från källan.

Testbygge av en tom 4×4 km-karta:

    python third_party/fs25_empty_map/tools/build.py 4
    # -> third_party/fs25_empty_map/out/FS25_Empty4x/
