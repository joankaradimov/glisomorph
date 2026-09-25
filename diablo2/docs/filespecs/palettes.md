# Palettes and color maps

Diablo II's sprites are 8-bit palette indices, like Diablo 1's. Each act has its own palette, with
lighting, blending and recoloring done through 256-entry tables of palette indices.

All integers are little-endian.

## `pal.dat`: the act palette

`data/global/palette/<act>/pal.dat`, for `act1` … `act5` plus menu, loading, sky and other screens:
768 bytes, 256 entries of **blue, green, red**, in that order. There's no header and no alpha.
Transparency lives in the sprite encodings.

## `pal.pl2`: the palette plus precomputed tables

`data/global/palette/<act>/pal.pl2` holds the same palette followed by every lookup table the renderer
uses: 443,175 bytes. Each table is 256 bytes that map a palette index to another. The layout, with
D2MOO's names (`D2PL2FileStrc`) and OpenDiablo2's in brackets where they differ:

| Offset    | Size           | Contents                                                        |
|-----------|----------------|-----------------------------------------------------------------|
| `0x00000` | 256 × 4        | the palette as **red, green, blue, unused**                     |
| `0x00400` | 32 × 256       | `shadows`: 32 lighting levels [LightLevelVariations]            |
| `0x02400` | 16 × 256       | `light` [InvColorVariations]                                    |
| `0x03400` | 256            | `gamma` [SelectedUnitShift]                                     |
| `0x03500` | 3 × 256 × 256  | `trans`: translucent blending at three strengths, `table[level][top][bottom]` [AlphaBlend] |
| `0x33500` | 256 × 256      | `screen` [AdditiveBlend]                                        |
| `0x43500` | 256 × 256      | `luminance` [MultiplicativeBlend]                               |
| `0x53500` | 128 × 256      | `states`: recolors for skills and states [hue variations, red/green/blue tones and others] |
| `0x5B500` | 256 × 256      | `darkBlend` [MaxComponentBlend]                                 |
| `0x6B500` | 256            | `darkenPalette` [DarkenedColorShift]                            |
| `0x6B600` | 13 × 3         | `standardColors`: text colors, 3 bytes each [TextColors]        |
| `0x6B627` | 13 × 256       | `standardShifts` [TextColorShifts]                              |

The blend tables are why COF layers can be translucent in an 8-bit game: instead of mixing colors, the
renderer looks up the result. How the tables were computed, as the decoder comparison found by checking
the file against formulas (`c` is a color component, `a` the screen's and `b` the sprite's, 0–255):

| Tables              | Result                                                                  |
|---------------------|-------------------------------------------------------------------------|
| `shadows[i]`        | nearest color to `c × (i + 1) / 32`; table 31 is the identity           |
| `light[i]`          | nearest color to `c + (i + 1) × (255 − c) / 16`                         |
| `trans[k][a][b]`    | nearest color to `a × r + b × (1 − r)`, with `r` = 64, 128 or 192 / 255 for `k` = 0, 1, 2 |
| `screen[a][b]`      | `min(a + b, 255)`                                                       |
| `luminance[a][b]`   | `a × b / 255`                                                           |
| `darkenPalette`     | `c − c / 3`                                                             |

The game's decompiled blending code looks up `table[screen pixel][sprite pixel]`. With the formula above,
`trans[0]` keeps 75% of the sprite: it's "25% transparent", the `TRANS25` draw mode.

Some tools count tables differently:

- Tools and forum posts often number the 256-byte tables after the palette: 0–31 `shadows`, 32–47
  `light`, 48 `gamma`, 49–816 `trans`, and so on.
- Paul Siramy's DS1 editor counts from the start of the file, which adds 4.
- DRTester's colormap "index" (306 and 562 in the PDF) is one of these numbers.

## Color maps

These are 256-byte tables like the ones in `pal.pl2`, applied to a layer's pixels before drawing
(`out = map[in]`), as with Diablo 1's TRN files. How items and monsters pick one is in
[sprite-metadata.md](sprite-metadata.md#color-maps).

| File                                            | Maps    | Use                                                         |
|-------------------------------------------------|---------|-------------------------------------------------------------|
| `data/global/items/palette/grey.dat`, `grey2.dat`, `greybrown.dat`, `brown.dat`, `gold.dat` | 21 each | tints of items drawn on characters. An item type's `Transform` picks the file, the item's color the map (0–20) |
| `data/global/items/palette/invgrey.dat`, `invgrey2.dat`, `invgreybrown.dat` | 21 each | the same tints for inventory pictures                   |
| `data/global/monsters/<token>/cof/palshift.dat` | 8       | a monster type's color variants; the game uses maps 3–8     |
| `data/global/monsters/randtransforms.dat`       | 30      | extra variants for super uniques from 1.10; the game uses maps 1–22 |

An item type's `Transform` (and `InvTrans`, for the inventory picture) picks the file:

| Value | File         | Value | File              |
|------:|--------------|------:|-------------------|
| 1     | `grey.dat`   | 5     | `greybrown.dat`   |
| 2     | `grey2.dat`  | 6     | `invgrey.dat`     |
| 3     | `brown.dat`  | 7     | `invgrey2.dat`    |
| 4     | `gold.dat`   | 8     | `invgreybrown.dat` |

The order comes from Riiablo, and D2MOO's character-select code agrees on 7 and 8. D2MOO
(`ITEMS_GetColor`) packs an item's color as `color + 32 × Transform`, valid when `Transform` is 1–8 and
the color is under 21. Unlike `palshift.dat`, the first map of an item file isn't the identity.

## Checked against the game data

In the 1.00 `d2data.mpq`:

- **`pal.dat`:** all 17 are 768 bytes. Rendering a healing potion with the act 1 palette gives red
  when read as blue-green-red, and blue when read the other way.
- **`pal.pl2`:** 14 of the 15 are 443,175 bytes, the sum of the table above. Their palettes are the
  byte-reversed `pal.dat` entries, padded to 4 bytes. `loading/pal.pl2` is 259 bytes shorter: it has
  one text color (3 bytes) and one text-color table (256 bytes) fewer, as Riiablo also handles.
- **Color maps:** the item files are 5,376 bytes (21 × 256), every `palshift.dat` in `d2data.mpq`
  (55 of them) is 2,048 bytes (8 × 256), and `randtransforms.dat` is 7,680 bytes (30 × 256).
- **`palshift.dat` identities:** in 69 of the 70 files in `d2data.mpq` and `d2exp.mpq`, the first two
  maps are the identity. That would explain why the game starts counting at the third.

## Sources

- D2MOO: `source/D2Win/src/D2WinPalette.cpp` (loading, byte order, `D2PL2FileStrc`),
  `source/D2Common/src/Items/Items.cpp` (`ITEMS_GetColor`).
- OpenDiablo2's PL2 reader, for the alternative table names.
- Paul Siramy, *Extracting Diablo II Animations*: palshift and randtransforms usage.
