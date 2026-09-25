# COF: how layers make an animation

A COF ("component object file", as the community calls it) describes one animation of one unit: one
mode, one weapon class. It says which layers take part, how each is drawn, and in what order the layers
are stacked in every frame of every direction. The pixels are in the layers' [DCC](dcc.md) or
[DC6](dc6.md) files. See [sprite-metadata.md](sprite-metadata.md) for how COFs and layer files are named.

Paths look like `data/global/<unit type>/<token>/cof/<token><mode><weapon class>.cof`, for example
`data/global/chars/ba/cof/batn1ss.cof`.

All integers are little-endian.

## Layout

| Offset                        | Size                           | Contents                          |
|-------------------------------|--------------------------------|-----------------------------------|
| 0                             | 28                             | header                            |
| 28                            | 9 × layers                     | layer records                     |
| 28 + 9·layers                 | frames                         | frame flags, one byte per frame   |
| 28 + 9·layers + frames        | directions × frames × layers   | draw order                        |

The file is exactly that long: `28 + 9·layers + frames + directions·frames·layers` bytes.

### Header

| Offset | Type | Field                                                                        |
|--------|------|------------------------------------------------------------------------------|
| 0      | u8   | number of layers                                                             |
| 1      | u8   | frames per direction                                                         |
| 2      | u8   | number of directions (1, 4, 8 or 16 in the game's files)                     |
| 3      | u8   | version, always 20 (`0x14`)                                                  |
| 4      | u32  | unknown; often `0x7FFDF000`, otherwise varies. Probably leftover memory      |
| 8      | i32  | bounding box: left (x min)                                                   |
| 12     | i32  | bounding box: right (x max)                                                  |
| 16     | i32  | bounding box: top (y min)                                                    |
| 20     | i32  | bounding box: bottom (y max)                                                 |
| 24     | u16  | animation speed, in 256ths of 25 fps; normally equal to AnimData.d2's        |
| 26     | u16  | zero                                                                         |

The bounding box is relative to the unit's position. It covers the animation's pixels in every frame and
direction, possibly with some margin. For `batn1ss.cof`, x runs from −68 to 60 and y from −90 to 12.
Negative y is up, so most of a character is above its origin.

### Layer record

| Offset | Type    | Field                                                                     |
|--------|---------|---------------------------------------------------------------------------|
| 0      | u8      | component: 0 `HD`, 1 `TR`, 2 `LG`, 3 `RA`, 4 `LA`, 5 `RH`, 6 `LH`, 7 `SH`, 8–15 `S1`–`S8` |
| 1      | u8      | casts a shadow (1) or not (0)                                             |
| 2      | u8      | selectable: hovering over it selects the unit                             |
| 3      | u8      | transparent: 0 draws normally; non-zero draws with the effect below      |
| 4      | u8      | draw effect, used when the layer is transparent                           |
| 5      | char[4] | weapon class of the layer's DCC, NUL-terminated (`hth`, `1ss`, …)         |

The weapon class here overrides the COF's own when naming the layer's file. See
[sprite-metadata.md](sprite-metadata.md#unit-types-and-base-paths).

**Draw effects.** The values match the game's draw modes (D2MOO, `D2Gfx/include/DrawMode.h`). Each
blended mode uses one of the lookup tables in `pal.pl2` (see [palettes.md](palettes.md)).

| Effect | Draw mode        | How it looks                                                   |
|--------|------------------|----------------------------------------------------------------|
| 0      | `TRANS25`        | 25% transparent: the layer at 75% opacity                      |
| 1      | `TRANS50`        | 50% transparent                                                |
| 2      | `TRANS75`        | 75% transparent: the layer at 25% opacity                      |
| 3      | `MODULATE`       | additive ("screen"): dark pixels vanish, bright ones glow      |
| 4      | `BURN`           | multiplicative ("luminance")                                   |
| 5      | `NORMAL`         | opaque; the value most layers carry                            |
| 6      | `TRANSHIGHLIGHT` | unclear; Paul Siramy calls it "some kind of bright screen"     |
| 7      | `HIGHLIGHT`      | unclear                                                        |

**Which way the transparency goes.** The PDF reads effect 0 as "75% translucent". The game's
decompiled blending code (in D2MOO) and the contents of the `pal.pl2` tables point the other way: the
first table keeps 75% of the sprite's color. OpenD2 and Siramy's own later code both name it "25%
transparent". Only the display differs: the value is the same, so a parser can store the number and
leave the question open.

In the game's COFs, 6,656 layers have (transparent, effect) = (0, 0) and 4,701 have (0, 5): both
opaque. 651 have (1, 3), additive auras and flames; (1, 6), (1, 1), (1, 0), (1, 2) and (1, 4) are
rare.

### Frame flags

One byte per frame, marking an event on that frame:

| Value | Event                            |
|-------|----------------------------------|
| 0     | none                             |
| 1     | attack: the blow lands           |
| 2     | missile: the projectile is released |
| 3     | sound                            |
| 4     | skill                            |

Values 0–3 occur in the files. The game reads these from [AnimData.d2](animdata.md), which carries the
same bytes.

### Draw order

For direction row `p` and frame `f`, the `layers` bytes at `(p · frames + f) · layers` list component
numbers in drawing order: the first is drawn first, so it ends up at the back. Each row is a permutation
of the COF's layers.

**The row index is the direction's clockwise position, not its file index.** Row 0 faces south and the
rows go clockwise. The layers' DCC files, on the other hand, store their directions interleaved. So to
draw position `p` of an N-direction COF, take draw-order row `p`, and from each layer's DCC take
direction `DIRS[N][p]`. See [dcc.md](dcc.md#directions) for the tables.

## COF caches: `chars_cof.d2` and `cmncof_a*.d2`

The game preloads many COFs from caches in `data/global/`:

- `chars_cof.d2` holds the players';
- `cmncof_a1.d2` … `cmncof_a7.d2` hold the ones common to each act.

The game looks there first and only then for the loose file. A cache is a sequence of records:

| Offset | Type    | Field                                   |
|--------|---------|-----------------------------------------|
| 0      | i32     | −1                                      |
| 4      | u32     | 0                                       |
| 8      | u32     | size of the COF that follows            |
| 12     | char[8] | COF name, NUL-padded (`soscbow`)        |
| 20     | i32     | −1                                      |
| 24     | …       | the COF itself                          |

The fixed words look like pointers from the game's in-memory cache, saved as-is.

## Checked against the game data

Every COF in the 1.00 `d2data.mpq`, `d2char.mpq` and `d2exp.mpq` was checked, 3,605 files in all:

- **Layout:** 3,602 have exactly the size the layout predicts. The other three are one-frame object
  COFs (`objects/f9/cof/f9*.cof`) with 3 extra bytes at the end.
- **Header:** every version byte is 20, every component is 0–15, and bytes 26–27 are always zero.
- **Draw order:** every row is a permutation of the file's layers.
- **Match with AnimData.d2:** 2,646 COFs have a record there. Frames per direction and the frame flags
  match in 2,644 of them, and the speed in 2,640.
- **Caches:** the 8 `.d2` caches parse into 524 (`chars_cof.d2`) to 1,281 records each, and end
  exactly at the end of the file. Each cache has the same 3 odd `f9` COFs.
- **Against the PDF:** `batn1ss.cof`, `faa1hth.cof` and `7hnuhth.cof` match the header values and
  layer flags shown in DRTester screenshots.
- **Draw order:** composing the Barbarian's `batn1hs` layers from their DCCs settles which way the rows
  run. With rows taken by clockwise position, the shield is in front when he faces west and behind when
  he faces east. With rows taken by DCC direction index, the shield is drawn over his body when he faces
  east.

## Sources

- Paul Siramy, *Extracting Diablo II Animations*: layers, weapon classes, draw effects, the
  `chars_cof.d2` / `cmncof_*.d2` caches, and DRTester's view of these fields.
- Layout: derived from the game files and cross-checked against the reimplementations listed in
  [AGENTS.md](../AGENTS.md#references).
