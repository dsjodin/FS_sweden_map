# 32 — The terrain layer block (the standard ground layers)

The `<Layers>` element inside the terrain node is **not** just a list of ground textures — it's a structure the
terrain shader + cache build **require in full**. A minimal 1-Layer terrain builds the geometry quadtree but then
**crashes the terrain cache build** (occluders/nmap/weights caches). Base-game maps all carry the full set.

## What the base game has (from `mapUS.i3d`, the ground truth)

| element | count | what it is | has weightMapId? | textures |
|---------|-------|-----------|------------------|----------|
| `LayerAttribute` | 4 | declares the per-layer attrs: color / softness / materialId(enum) / aiDriveCost | — | — |
| `Layer` | 86 | a ground texture (grass01, asphalt01, dirt…) | **yes** (where it appears) | `$data` detail/normal/height/displacement |
| `OverlayLayer` | 37 | crop-state visuals (cultivated, sown, harvestReady, spray) | no (driven by the density) | `$data` |
| `CombinedLayer` | 43 | a *named group* of Layers, e.g. `layers="asphalt01;asphalt02"` | no | none (just references) |
| `CombinedOverlayLayer` | 21 | a named group of OverlayLayers | no | none |

Then (as before): 2 `DetailLayer` (terrainDetail, terrainDetailHeight), 1 `DisplacementLayer`, `FoliageSystem`
(we omit — no crops), 9 `InfoLayer`.

**Every one of the 492 layer textures is a base-game `$data` asset** — so we reproduce the whole block referencing
`$data`, and it carries no map data.

## How we generate it (nothing copied)
- `tools/base_terrain_layers.json` — the layer *definitions* (names, attributes, `$data` texture paths) extracted
  from mapUS **as the reference the format demands**. This is the base-game standard ground set, not mod content.
- `gen_i3d.emit_layer_block()` reads it and emits every element, but swaps the `Layer` weights for OUR OWN:
  **`grass01` → `data/grass_weight.png` (255 = grass everywhere)**, **every other of the 86 Layers → one shared
  `data/blank_weight.png` (0 = hidden)**. So the structure is complete but the map is uniform empty grass.
- Sharing one blank weight across 85 layers is legitimate (WW does the same with `ww_weight_blank`).

## The height material
`terrainDetailHeight` uses `groundDetailHeight_mat`. Use **mapUS's** definition:
`customShaderId → $data/shaders/groundHeightShader.xml`, `diffuseColor="0 0 0 0"`, and a single
`<Custommap name="heightNoiseMap" → $data/shared/groundHeightNoise.dds>`. **No Texture/Normalmap/Glossmap** — WW's
copy added `$data/fillPlanes/dummyFillplane_specular.dds`, which the base game does not ship → load crash.

## Why "look at the base game, not a mod"
WW/Kansas are mapUS derivatives that added/renamed/broke things (WW's whole crop-render saga is why this project
exists). `mapUS.i3d` is the authoritative source of the standard terrain structure.
