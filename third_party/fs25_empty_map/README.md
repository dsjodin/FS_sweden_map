# FS25 Empty Flat 16x Starter Map — 100% generated from scratch

A complete, loadable Farming Simulator 25 **16x map (8192m × 8192m)**, generated **entirely by Python** — no
part is copied, transplanted, or templated from another map. It loads with **zero errors**, spawns the player,
displays correctly, and ships a **100ha owned, pre-planted wheat field** dead-center.

This is the reusable starting point for all future 16x maps and FS22→FS25 conversions: start here, then add.

## What it produces
`out/FS25_Empty16x/` — a full mod:
- flat terrain (even ~31m), uniform grass, the full base-game standard terrain layer/foliage structure
- a **100ha field** (1000×1000m) dead-center: farmland-1 (player-owned at start), workable area 1m inset,
  planted with harvest-ready **wheat**; the rest of the map is farmland-2 (buyable)
- an 8192×8192 overview image, correct sun/lighting, a valid spawn point

## Build & deploy (deterministic — same output every run)
```
python tools/build.py 16   # 16x (8192 m, default) -> out/FS25_Empty16x/
python tools/build.py 4    # 4x  (4096 m)          -> out/FS25_Empty4x/
python tools/build.py 64   # 64x (16384 m)         -> out/FS25_Empty64x/    (density/weights capped - see docs/70)
```
Deploy to the game (junction so edits are live), from PowerShell:
```
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\My Games\FarmingSimulator2025\mods\FS25_Empty16x" `
         -Target "$(Resolve-Path .\out\FS25_Empty16x)"
```
Then start a **new game** on "Empty 16x". (GIANTS overwrites `log.txt` every launch, so copy it out after a run if
you want to keep a load log for comparison.)

## Generators (`tools/`)
| file | produces |
|------|----------|
| `binfmt.py` | the GIANTS binary formats from scratch: `flat_dem`, `uniform_weight`, `blank_gdm`/`paint_gdm` (density `"MDF`), `blank_grle`/`paint_grle` (info layer) |
| `gen_i3d.py` | the whole scene + terrain node (Files/Materials/Scene/UserAttributes), the layer block, foliage system, and the field |
| `gen_data.py` | DEM, weights, densities (+ painted field ground/wheat), infolayers (+ painted farmland) |
| `gen_configs.py` | map.xml, modDesc, farmlands.xml, overview.png, empty start configs, icon |
| `build.py` | runs them all into `out/FS25_Empty16x/` and checks every local file ref resolves |

## Base-game reference data (extracted, NOT map content)
`base_terrain_layers.json`, `base_foliage.json`, `base_infolayers.json` are the **standard terrain structure**
extracted from base-game `mapUS.i3d` (`$data/maps/mapUS/mapUS.i3d`) — the layer/foliage/infolayer *definitions*
(names, attributes, `$data` texture paths). The generators reproduce this standard structure with **our own**
weights/densities. To re-extract them, the extraction snippets are in the git history / docs. All textures/shaders
they reference are base-game `$data` (the engine — carries no map data).

## Docs (`docs/`) — the format + every requirement, so it can be rebuilt understanding each piece
`00_overview.md` (anatomy + the load-requirement corpus), `10_moddesc`, `20_mapxml`, `30_i3d`, `31_terrain_node`,
`32_terrain_layers`, `33_infolayers`, `40_dem`, `41_weights`, `50_gdm`, `51_grle`, `60_field`.

## The corpus (every one cost an in-game crash to find — see 00_overview.md / memory `fs25-scratch-map-load-corpus`)
Reference the **base game (mapUS), never a mod** — WW/Kansas are derivatives that broke/renamed things.
1. modDesc `iconFilename` in two places (per-`<map>` a child element) → map appears in list
2. map.xml `<filename>` → the i3d, else "Loading map: nil" crash
3. `<OccluderLods>` child present → no non-manifold-edges crash
4. full base-game layer block (86 Layers + overlays + combined) → terrain cache build survives
5. height material = base-game spec (no specular DDS) → no missing-dds crash
6. multi-range `.gdm` writes the interior split byte → no "wrong compression channel" crash
7. `<FoliageSystem>` present → terrain build survives
8. special nodes register via `onCreate` UserAttributes: sun=`Environment.onCreateSunLight`, spawn=`Mission00.onCreateStartPoint`, fields=`FieldUtil.onCreate`
9. overview image, map-sized (8192²) → non-black in-game map (the game overlays fields onto it; AD Editor reads it)
10. infolayer .grle resolutions match base game (tip/indoor 16384², nav 8192², placement/farmland/fieldType 4096²)
11. farmland infolayer painted (not blank) → farmland defined → player has land → spawn works

## Mandate
100% PY-generated; nothing copied/templated from another map. `$data`/`$dataS` engine refs are allowed (shaders,
ground textures, sub-configs) — they carry no map data. Every component has a doc explaining what each element means.
