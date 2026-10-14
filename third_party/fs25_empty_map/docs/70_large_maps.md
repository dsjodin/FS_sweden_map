# 70 — Large maps (64x): the resolution ceiling

Not everything scales linearly with map size. **Above 16x, the density and weight resolutions must be CAPPED** or
the GPU runs out of memory building the density textures. Verified against base mapUS and **FS25_WestEnd** (a
shipping "West End 64x map by Levis") — the reference for known-good 64x numbers.

## The ceiling (what `mapcfg.Cfg` caps)
| resolution | ≤16x (8192 m) | 64x (16384 m) | why |
|---|---|---|---|
| density (.gdm) | 2 px/m (16384²) | **1 px/m (16384², capped)** | 32768² density textures OOM: *"Failed to allocate ImageResource for DensityTexture, probably out of memory"* (crashed a first 64x build at ~55%) |
| weights (.png) | 1 px/m (= map_m) | **0.5 px/m (8192², capped)** | West End caps weights at 8192² too |
| DEM | 2 m/px (map_m/2+1) | 2 m/px (8193²) | scales freely — same terrain-mesh detail per metre |
| overview | map-sized | map-sized (16384²) | must stay map-sized (it's the PDA image) |

Caps in `Cfg.__init__`: `density_res = min(map_m*2, 16384)`, `weight_res = min(map_m, 8192)`. Everything else
(infolayers, DisplacementLayer size) derives from `density_res`, so they cap automatically.

## Terrain LOD — a latent bug the 64x exposed
Base mapUS uses `maxLODDistance=750`, `occMaxLODDistance=300`. Ours were `1e7 / 512000` — effectively **no LOD**
(full terrain detail to the horizon). Harmless at 4x/16x, but a no-LOD 64x is 4× the area of full-detail geometry,
compounding the memory pressure. Now set to the mapUS values (750/300); West End confirms 750 for a 64x.

## The trade-off (what 1 px/m density costs)
A 64x has **half the linear density/weight resolution** of a 16x: cultivation / field-edge / crop / foliage detail
on a **1 m grid instead of 0.5 m**, and slightly softer texture-layer transitions. The terrain **mesh** (DEM) and
the ground **textures** ($data) are unaffected. It's invisible in play and is exactly what every shipping 64x does.
If you need 2 px/m density, use a *smaller* map — you can't buy it back on a 64x without exceeding VRAM.

## `.gdm` version byte
West End's density magic is `!MDF` (0x21); ours is `"MDF` (0x22) — a format-version byte. Both load fine.

## Editing a 64x in GIANTS Editor
Separate concern (the viewport culling blackout). Scale the AlwaysLoaded culling script: box ±8192, clip ~18000.
See memory `fs25-large-map-gotchas` #4.
