# 31 — The Terrain Node (`<TerrainTransformGroup>`)

The hardest component. This is what makes an FS25 map a *terrain*. Learned by reading real terrain nodes
(WW/mapUS); generated fresh by `tools/gen_i3d.py`. Every `$data/...` reference is a base-game engine asset
(shader/texture) — allowed, it carries no map data.

## Verified format facts (from real 16x terrain nodes)

- **DEM**: `data/map_dem.png`, **4097×4097, 16-bit** grayscale (`I;16`). World height = `value/65535 * heightScale`.
  Flat map = one constant value everywhere. (`unitsPerPixel=2` → 8192/2 = 4096, +1 for shared patch edges = 4097.)
- **Weights**: `data/*_weight.png`, **8192×8192, 8-bit**. 255 = layer fully present.
- **Densities**: `.gdm`, **16384×16384** (mapSizeLog=9), 32px chunks. Headers we must reproduce exactly:
  - `densityMap_ground.gdm`: numChannels=**11**, ranges=**1**, ntic=**0** (read by `terrainDetail`)
  - `densityMap_height.gdm`: numChannels=**12**, ranges=**2**, ntic=**0** (read by `terrainDetailHeight`)
- **Infolayers**: `.grle`. `farmland`/`fieldType` = **4096²**; collision/mask layers = **2048²**; `environment`
  is **`$data`** (`$data/maps/mapUS/data/infoLayer_environment.png`) — not generated.

## `<TerrainTransformGroup>` attributes (all required unless noted)

| attr | value (ours) | meaning |
|------|-------------|---------|
| name | `terrain` | node name the game looks for |
| static | `true` | terrain never moves |
| collisionFilterGroup / Mask | `0x100` / `0xfffff9c3` | physics: terrain is group 0x100; mask = what hits it |
| nodeId | unique int | scene-graph id |
| heightMapId | fileId→`data/map_dem.png` | the DEM |
| patchSize | `65` | vertices per mesh patch edge (LOD unit); 65 is the standard |
| heightScale | `255` | DEM value→meters scale |
| unitsPerPixel | `2` | world meters per DEM pixel (8192m / 4096 = 2) |
| maxLODDistance | `1e+07` | flat map → never drop to lowest LOD (Kansas uses this for flat) |
| lodBlendStart/End | `200`/`300` | LOD cross-fade band (m) |
| lodTextureSize | `2048` | terrain LOD atlas texture size |
| lodBlendStartDynamic/EndDynamic | `50`/`65` | near dynamic-LOD band |
| detailLodBlendDelta | `5` | detail LOD blend speed |
| materialId | fileId→terrainMaterial_mat | the terrain material |
| castShadowMap | `true` | terrain casts shadows |
| occNumLODs | `0` | occlusion culling off (correct for flat terrain) |

## Children — `<Layers>` wrapper contains, in order:

1. **`<LayerAttributes>`** — REQUIRED, fixed content. Declares the 4 per-layer attributes: `color`
   (float_linearRGB), `softness` (0–1), `materialId` (enum `field:0;dirt:1;grass:2;sand:3;sound:4;leaves:5;gravel:6;asphalt:7;`),
   `aiDriveCost` (-1..100).
2. **`<Layer>`** ×N (min 1) — a ground texture. Ours = one **grass** layer: `detail/normal/height/displacementMapId`
   → `$data/.../grass01_*.png`; `weightMapId` → `data/grass_weight.png` (local, full 255 = grass everywhere);
   `unitSize=2`; physics floats (firmness/viscosity/…); `attributes="0.155 0.082 0.037 0.5 2 8"` =
   `colorR colorG colorB softness materialId(2=grass) aiDriveCost`.
3. **`<DetailLayer name="terrainDetail">`** — the ground-state decal system (plowed/cultivated/sown/…). Reads
   `densityMap_ground.gdm` (11ch). `combinedValuesChannels="0 4 0;4 3 0;7 3 0;10 1 0"` splits the 11 channels
   into groundType(4b)/angle(3b)/spray(3b)/extra(1b). `channelOverlayTypes="groundDetail;;spray"`. Children:
   26 `<DistanceTexture match="groundType;angle;spray" fileId=…>` mapping each state to a `$data` distance
   texture (value 0 = bare, shows the base grass layer — which is all our blank map ever shows).
4. **`<DetailLayer name="terrainDetailHeight">`** — the fill/heap-height decals. Reads `densityMap_height.gdm`
   (12ch, 2 ranges); `materialId`→`groundDetailHeight_mat`; `heightFirstChannel=6 heightNumChannels=6 maxHeight=4`.
5. **`<DisplacementLayer name="terrainDisplacement">`** — runtime rut/furrow mesh displacement. No file ref
   (`densityMapShaderNames="terrainDisplacementMap"`, runtime). `size=16384 tileSize=16 numChannels=6 cellSize=2 maxHeight=0.2`.
6. **`<InfoLayer>` ×9** — runtime metadata grids, each `runtime="true"` with `<Group>/<Option>` value labels:
   `environment`(4ch,$data), `farmlands`(8ch), `indoorMask`(1), `navigationCollision`(1,no group),
   `tipCollision`(1), `tipCollisionGenerated`(2), `placementCollision`(1), `placementCollisionGenerated`(1),
   `fieldType`(1). All local ones blank.

## Materials (2)
- **`terrainMaterial_mat`** → `customShaderId` = `$data/shaders/terrainShader.xml`. No children.
- **`groundDetailHeight_mat`** → `$data/shaders/groundHeightShader.xml` + `<Texture>/<Normalmap>/<Glossmap>` =
  `$data/fillPlanes/dummyFillplane_*.dds` + `<Custommap name="heightNoiseMap">` = `$data/shared/groundHeightNoise.dds`.

## Omitted for an empty map
- **`terrainDetailHeight` + `groundDetailHeight_mat`** — the fill/heap-height decal system (grain heaps, dug
  ground). Unused on an empty map, AND its material's `<Glossmap>` points at `$data/fillPlanes/dummyFillplane_specular.dds`
  which **the base game does not ship** → `Error: Missing dds file` → **load crash**. (Real maps carry the material
  but never trigger the load because their `terrainDetailHeight` referenced a different/dangling material id.)
  So we drop the layer, its material, and `densityMap_height.gdm`.
- **`<OverlayLayer>`** (crop-stage overlays) — no crops.
- **`<FoliageSystem>`** (3D grass/crop *blades*) — our "grass" is the ground *texture* (a `<Layer>`), not foliage.
- **`<Shape>` / `.i3d.shapes`** — no meshes at all on an empty flat map.

## GOTCHA — `terrainDetailHeight maxHeight` must stay > 0 (else FREEZE on drive/mow)

`gen_i3d.py` has a `micro_displacement=False` post-process (default) that zeroes terrain-layer `maxHeight` to kill
**washboard/diamond corrugation** on non-flat terrain. That corrugation comes ONLY from the micro-tessellation
**`DisplacementLayer`** (`terrainDisplacement`) — so zero *that* one. Do **NOT** zero the **`terrainDetailHeight`
DetailLayer**: it is the fill/height layer (densityMap_height) that the engine's **`tireTrackSystem` and `SnowSystem`
read**. If `terrainDetailHeight maxHeight="0"`:
- `g_currentMission.tireTrackSystem` is never created → nil.
- `SnowSystem.lua:524 updateSnowShader` divides by the zero max-height → **Divide by zero** every frame.
- `SnowSystem.lua:286` / `DensityMapHeightUtil.lua:448` index the nil `tireTrackSystemId` every frame.

The moment a **mower/vehicle drives on terrain**, these fire per-`update` → tens of thousands of log errors →
the game **freezes**. A blank height-density map adds 0 height regardless of `maxHeight`, so keeping it at `4`
(mapUS's value) causes **no** visual corrugation — only the DisplacementLayer does. Fixed 2026-07-06: the zeroing
loop now touches `DisplacementLayer` only; `terrainDetailHeight` keeps `maxHeight="4"`.
