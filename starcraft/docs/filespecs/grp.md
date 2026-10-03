# GRP: sprites

Every unit, building, doodad, missile and effect StarCraft draws on the map is a GRP under `unit/`.
A GRP is a set of frames that share one canvas size. It holds no palette, no timing, no directions
and no animations. Those come from [images.dat](dat.md) and the [iscript](iscript.md). This page
covers the classic game, 1.00 to 1.16.1; Remastered's SD GRPs are the same format (see
[AGENTS.md](../AGENTS.md#remastered)).

## Layout

All values are little-endian.

| Offset | Size | Field |
|-------:|------|-------|
| 0 | u16 | frame count |
| 2 | u16 | canvas width |
| 4 | u16 | canvas height |
| 6 | 8 per frame | frame headers |

A frame header:

| Offset | Size | Field |
|-------:|------|-------|
| 0 | u8 | x: left edge of the frame's box within the canvas |
| 1 | u8 | y: top edge of the box |
| 2 | u8 | box width |
| 3 | u8 | box height |
| 4 | u32 | offset of the frame's data, from the start of the file |

Only the box is stored; the rest of the canvas is transparent. Frames whose headers give the same
offset share their data.

## Frame data

The usual encoding is run-length, one row at a time. The frame's data starts with a row table: a u16
per row of the box, each the offset of that row's runs **from the start of the row table**. A row is
a sequence of runs that together fill the box's width exactly, each opened by one byte:

| Control byte | Run |
|--------------|-----|
| `1nnnnnnn` | `n` transparent pixels |
| `01nnnnnn` | the next byte, repeated `n` times |
| `00nnnnnn` | the next `n` bytes, copied as they are |

Rows never carry over: a row ends when its runs reach the box width.

A few interface GRPs are instead **uncompressed**: the frame's data is the box's pixels, row after
row, `width × height` bytes with no row table. Nothing in the file says which encoding it uses. The
uncompressed ones are the dialog borders (`dlgs/*.grp`, `glue/PalNl/Dlg.grp`) and the score-screen
icons (`glue/Score*/iScore.grp`). Every GRP that `images.dat` names, and so every sprite drawn on the
map, is run-length encoded. A reader for sprites can assume it; a general reader has to know the file.

## Pixels

Every pixel is a palette index. Transparent pixels are only those skipped by `1nnnnnnn` runs; index 0
inside a run is drawn (black). The colors depend on what's drawing the image:

- the palette is the map's tileset `.wpe`. Units draw almost entirely in the entries every tileset
  shares, so they look the same on every tileset; the siege tank, the geyser and a few neutral
  buildings are exceptions, and the doodads under `unit/thingy/tileset/` deliberately draw in the
  tileset's own colors;
- indices 8–15 are the **player color**, swapped through `game/tunit.pcx` before drawing;
- an image's draw function can ignore the indices entirely (shadows, cloaking), or blend through a
  lookup table (glows, explosions).

See [palettes.md](palettes.md).

## Directions

A GRP doesn't know about directions; the image does. When `images.dat` marks an image as turning
(its "graphics turns" byte is 1), each **animation step is 17 consecutive frames**: directions 0 to 16
of 32, starting at north (facing up, away from the viewer) and going clockwise to south (16). The
other 15 directions are drawn by **mirroring** frames 15 down to 1 left to right:

| Direction | 0 | 1 … 15 | 16 | 17 … 31 |
|-----------|---|--------|----|---------|
| Frame | `base + 0` | `base + 1` … `base + 15` | `base + 16` | `base + 15` … `base + 1`, mirrored |

So `frame = base + d` for `d ≤ 16`, else `base + 32 − d`, flipped. The iscript names steps by their
`base`, always a multiple of 17 in the turning part of a GRP. A unit's facing is 0–255 in the game
logic, and the image direction is `(facing + 4) / 8`, rounded down, so the 32 image directions are
11.25° apart and each covers the facings centered on it; facings 252–255 come out as 32, which is
direction 0 (OpenBW, `set_image_heading`).

Mirroring flips the whole canvas, not just the box: a mirrored box starts at
`x' = canvas width − x − box width`.

**Turning GRPs can end in non-turning frames.** A marine is 229 frames: 13 steps of 17, then 8 death
frames that play in one direction only. The marine, ghost, medic, zealot, dragoon, high templar,
zergling, hydralisk, ultralisk, infested terran and the critters all do this, and so do some of
their shadow GRPs.

## Placement

An image is drawn with its canvas centered on its position: the sprite's position plus the image's
own offset, which the iscript sets (`setpos`, the offsets of `imgol` and the like). A frame's box goes
at

```
left = position.x + x − width / 2                 (mirrored: position.x + width / 2 − (x + box width))
top  = position.y + y − height / 2
```

with `width` and `height` the canvas's, divided rounding down. Overlays such as muzzle flashes and
fire are placed per frame from [LO* files](dat.md#lo-overlay-offsets).

## Checked against the game data

Checked on the MPQs of a 2017 classic install (`StarDat.mpq`, `BrooDat.mpq`, `patch_rt.mpq`):

- **All 833 GRPs** that `images.dat`'s 999 images name decode as run-length frames: every row fills
  its box exactly, and every box lies inside its canvas.
- Of the 34 other GRPs the archives' listfiles name, 24 are run-length and 10 are uncompressed (the
  ones listed above); in those, every frame's offset plus `width × height` fits in the file.
- 159 images turn. 109 of their 128 GRPs have a frame count divisible by 17; the other 19 are the
  ones with trailing single-direction frames. In 143 of the 159 images, every `playfram` in the
  image's iscript is a multiple of 17; the other 16 are those same units and their extra frames.
- The mirroring rule was checked by eye on the marine's walk and the mutalisk's flight, rendered in
  all 32 directions: the sheet is symmetric about direction 16 and turns smoothly.
- That direction 0 faces north and the directions run clockwise, from the attack and carry
  overlays: where the defiler, drone, guardian, archon, SCV, siege tank turret and wraith fire from
  or carry things is above the center in frame 0, to its right in frame 8 and below it in frame 16.

## Sources

- [staredit.net's "GRP Image Format"](https://wiki.staredit.net/wiki/GRP_Image_Format) and PyMS's
  `FileFormats/GRP.py` (MIT) for the layout and the uncompressed variant.
- OpenBW (`bwgame.h`: `read_grp`, `set_image_heading`, and where an image's position is worked out)
  for the 17-of-32 mirroring, the rounding and the placement. No license: read only.
- Everything above was checked against the data as listed.
