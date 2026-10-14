# 60 — The 100ha owned wheat field

A single 100ha (1000×1000m) field dead-center: player-owned at start, workable area 1m inside the boundary,
planted with harvest-ready wheat. This is the template for adding fields/crops to any map.

## i3d (`gen_i3d.py`)
A `fields` group + one `field1`, in the Scene:
```
TransformGroup "fields"  (UserAttribute onCreate = FieldUtil.onCreate)   <- registers the field system
  TransformGroup "field1" translation="0 32 0"  (UserAttribute: the field's attributes)
    TransformGroup "polygonPoints"        <- child index 0 (polygonIndex="0")
      TransformGroup "p" translation="-500 0 -500"   (the 4 corners, relative to field1)
      ... x4 (square)
    TransformGroup "nameIndicator"        <- child index 1 (nameIndicatorIndex="1", ALSO teleportIndicatorIndex="1")
```
`field1`'s UserAttribute (from mapUS): `angle`(float 0), `missionAllowed`(bool true — lets contracts spawn),
`missionOnlyGrass`(bool false), `nameIndicatorIndex`(string 1), `polygonIndex`(string 0),
`teleportIndicatorIndex`(string 1 — reuses the nameIndicator; no separate teleport node needed).

Like the sun and spawn point, the field system is found via the **`onCreate` scriptCallback** (`FieldUtil.onCreate`),
not by name — see 30_i3d.md.

## Data (`gen_data.py`, painted via the from-scratch `binfmt.paint_gdm` / `paint_grle`)
The map is 8192m; densities are 16384² (2 px/m), farmland is 4096² (0.5 px/m). Center pixel = resolution/2.
- **`densityMap_fruits`** (10ch, 2 ranges split at 5, ntic 5): the workable area (`_sq(16384, 500, inset=1)` =
  px 7194–9190) = **wheat**. Fruits value is packed `typeIdx | (state << numTypeIndexChannels)`:
  wheat typeIdx **6**, harvest-ready state **7** → `6 | (7<<5) = 230`. **Type indices are 0-BASED** — the index in
  the fruits FML's FoliageType list (decoFoliage=0, decoBushUS=1, meadow=2, forestPlants=3, waterPlants=4,
  grass=5, **wheat=6**, canola=7, barley=8, maize=9, potato=10, …; see base_foliage.json). Using 7 gives canola.
  Verified: crops DO render on this correctly-structured from-scratch map (WW never managed this).
- **`densityMap_ground`** (11ch, 1 range): same workable area = **groundType 7 (sown)** — the tilled dirt look.
- **`infoLayer_farmland`** (4096²): the field square (`_sq(4096, 500)` = px 1798–2298) = **1**; rest = **2**.

## Config (`gen_configs.py`)
`farmlands.xml`: `<farmland id="1" defaultFarmProperty="true"/>` (owned, no npcName) +
`<farmland id="2" npcName="FORESTER"/>` (buyable). Farmland 1's pixels are the field, so the player owns the
planted field at start.

## To change the crop / growth / size
- crop: change `WHEAT` typeIdx in gen_data (index in base_foliage.json fruits list).
- growth: change the state (e.g. a mid growing stage instead of 7).
- size: change `FIELD_HALF` (metres) and the polygonPoints corners in gen_i3d together.
