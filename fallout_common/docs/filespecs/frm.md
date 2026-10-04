# FRM: sprites and animations

FRM holds every image in Fallout 1 and Fallout 2: critter animations, items, scenery, walls, floor
tiles, the interface, talking heads and their backgrounds. One file is one animation, with up to 6
directions and the same number of frames in each. Fallout 1 and 2 use the same format and the same
reader.

Which file is which, what the directions and animation codes mean, and how the game picks a file, are
in [sprite-metadata.md](sprite-metadata.md).

All integers are **big-endian**.

## Layout

| Offset | Type       | Field                                                                         |
|--------|------------|-------------------------------------------------------------------------------|
| 0      | u32        | version: 4 in every shipped file but one (Fallout 1's `art/inven/oknife.frm` has 3). The game ignores it |
| 4      | i16        | frames per second; 0 means 10                                                 |
| 6      | i16        | action frame: the frame on which an attack hits, a door opens, etc.           |
| 8      | i16        | frames per direction (the same for every direction)                           |
| 10     | i16 × 6    | shift x, one per direction                                                    |
| 22     | i16 × 6    | shift y, one per direction                                                    |
| 34     | u32 × 6    | start of each direction's first frame, relative to the end of the header (62) |
| 58     | u32        | size of the frame data that follows the header: the file size − 62, except in split files (see below) |
| 62     | …          | frames                                                                        |

The header is 62 bytes. The game's reader is `artReadHeader` and `artRead` (`fallout2-ce: src/art.cc`),
`art_readFrameData` and `load_frame_into` in Fallout 1 (`fallout1-ce: src/game/art.cc`).

**Directions** are numbered 0–5 in the order NE, E, SE, SW, W, NW: clockwise on screen, starting
up-right (`fallout2-ce: src/obj_types.h`, the `ROTATION_*` enum). See
[sprite-metadata.md](sprite-metadata.md#directions) for the screen and ground vectors.

### Frames

Each direction is `frames per direction` frames, one after another:

| Offset | Type | Field                                                             |
|--------|------|-------------------------------------------------------------------|
| 0      | i16  | width                                                             |
| 2      | i16  | height                                                            |
| 4      | u32  | size of the pixel data, normally `width × height`                 |
| 8      | i16  | offset x: how far this frame moves the object from the previous one |
| 10     | i16  | offset y                                                          |
| 12     | u8 × size | pixels                                                       |

The next frame starts right after the pixels; there's no padding in the file. (The game pads each frame
to 4 bytes when it loads it into memory, and the in-memory `Art` struct has a `padding[6]` array the
file doesn't have. Ignore both.)

## Pixels

Raw palette indices, one byte per pixel, row by row from the **top** row down, left to right. There's
no compression.

- **Index 0 is transparent.** Every transparent blitter skips it (`transSrcCopy`,
  `fallout2-ce: src/draw.cc`), and critters are drawn through darkening blitters that skip it too
  (`_dark_trans_buf_to_buf`, called from `_obj_render_object`, `src/object.cc`). There's no other way to
  mark transparency, so black has to be some other index.
- The palette is separate (`color.pal`). Indices 229–254 are color-cycled by the engine, so those
  pixels animate even on a still frame (see [pal.md](pal.md#color-cycling)).
- **Shadows are baked in.** Critter frames include the critter's ground shadow, drawn in the darkest
  greys (mostly index 207, which bodies use too). The floating eye bot (`mafeye`) has only its shadow
  in its bottom rows.
- The file names no palette. The world is always drawn with `color.pal`; a few full-screen pictures
  get a different palette because the code that shows them loads one by name (see
  [pal.md](pal.md#which-palettes-exist)).

## Directions shared and split

**Shared blocks.** The reader walks the 6 directions in order. Direction `d` is read from the stream
only if `d` is 0 or its data offset differs from direction `d − 1`'s; otherwise it reuses the previous
block (`artRead`). So a file with one direction stores one block and repeats offset 0 six times.
Items, scenery and anything without a facing are like that. The shifts are still read per direction,
so in principle the same pixels can sit at 6 different shifts.

In the shipped data every file has either 1 block or 6:

| Files                                   | Blocks                                                       |
|-----------------------------------------|--------------------------------------------------------------|
| critter `.frm`                          | 6, except 123 in Fallout 1 and 48 in Fallout 2 with 1: mostly the called-shot pictures (`na`) and Fallout 1's stairs animations (`ag`–`aj`), plus the stands of a few critters that never turn (`mamstr`, `nmgzmo`, `nmover`, `madegg`) |
| critter `.fr0`–`.fr5`                   | always 1                                                     |
| `art/misc`, `art/items`                 | 1, except projectiles and thrown weapons (`rocket.frm`, `spear.frm`, `knife.frm`, `molotov.frm` and the like), which have 6 |
| everything else                         | 1                                                            |

**Shifts in one-block files.** Most repeat one shift in all six entries. About 600 per game store a
different shift in entry 0 than in entries 1–5 (`art/items/desk1.frm` has (−21, 17), then (61, 32)
five times), and 60–70 set only entry 0. The renderer takes the entry for the object's rotation
(`art->xOffsets[rotation]`), so in those files the shift depends on how the map turns the object.

The game reads the blocks sequentially and uses the offsets only to place them in memory. A well-formed
file stores the blocks in direction order with no gaps, so seeking to `62 + offset` gives the same
result. A decoder that seeks is more forgiving; one that follows the game should check that the two
agree.

**Split files: `.fr0`–`.fr5`.** A critter's knockdown and death animations can also come as one file per
direction, `<name>.fr0` (NE) to `<name>.fr5` (NW), next to or instead of the combined `<name>.frm`. Which
one the game opens is decided when the FID is built (see
[sprite-metadata.md](sprite-metadata.md#fid-the-art-id)): the per-direction file if it exists, else
`.fr0`, else `.frm`. The frame is then still looked up by the critter's direction inside whatever file
was opened. A split file with one block (all 6 offsets equal) serves every direction; a combined
`.frm` must have all 6 blocks, or every direction shows the same pixels.

In the shipped data, only knockdowns and deaths come split (`ba`–`bp`, though never `bn`, as the rule
predicts), in 495 animations per game, and no split animation also has a `.frm`. In Fallout 1, six of
them ship only an `.fr0` (`malieubl`, `mamstrba`, `mamstrbl`, `nmgzmoba`, `nmgzmobl`, `nmovr2ba`),
which the fallback then shows for every direction.

**Missing data.** `fallout2-ce` sets `data size` to the file size when it's 0 (a comment blames
malformed files in the *Nevada* mod). The original game has no such fix.

**`data size` in split files.** As the falloutmods wiki notes, `.fr0`–`.fr5` files store the total for
all 6 directions, although they hold one: the sum of the six files' frame data. That holds for 2,929 of
Fallout 1's 2,940 split files; the other 11 (`hmlthrbd`, and five of `masphnbh`'s) store a larger,
apparently stale total. The game only uses the field to size the buffer it reads the frames into, so a
value larger than the frames is harmless. Every combined `.frm` stores its own size exactly.

## Where a frame goes

`_obj_render_object` and `objectGetRect` (`fallout2-ce: src/object.cc`; `obj_render_object` and
`obj_bound` in Fallout 1) place a frame of an object standing on a hex like this:

1. `tileToScreenXY` gives the top-left corner of the hex's 32×16 box. Add (16, 8) to get the hex's
   center `(cx, cy)`.
2. Add the file's shift for the object's direction: `(shift_x[d], shift_y[d])`.
3. Add the object's accumulated offset `(ox, oy)` (see below).

That gives the anchor `(ax, ay)`. Then

```
left   = ax - width // 2
top    = ay - (height - 1)
bottom = ay
```

So the anchor is the frame pixel `(width // 2, height - 1)`: the center column of the **bottom row**.
For an even width it's the right-hand one of the two middle columns. Frames of different sizes line up
on that point.

Third-party docs (the falloutmods wiki's *FRM File Format* page, the fodev.net FRM page) say
`top = anchor_y - height`, which puts the bottom row one pixel above the anchor. The game's code puts
it on the anchor.

**The art agrees with the code.** Critter frames can't tell the two rules apart, since both move every
frame by the same pixel. Art drawn to point at something can:

- Mouse cursors use the same rule for their hotspot: `(width / 2 − shift_x, height − 1 − shift_y)`
  (`gameMouseSetCursor`, `fallout2-ce: src/game_mouse.cc`). With it, the shipped shifts land exactly
  on the arrow's tip (0, 0) in `stdarrow.frm`, the crosshair's center (10, 10), the center of the
  `plus` cursor (8, 8), and the tips of the `scrnorth` (15, 0) and `scrsouth` (16, 25) scroll arrows.
  With `height` instead of `height − 1`, every hotspot is one pixel low, and `scrsouth`'s falls off
  the picture.
- The hex cursor `msef000.frm` (32×16, shift (0, 7)) covers the hex's box exactly under the code's rule,
  and one pixel high under the wiki's. `block2.frm` (31×14) is centered in the box only under the code's
  rule.

**Frames are cropped tight.** In stand frame 0, the bottom row has opaque pixels in 568 of Fallout 2's
576 critter directions; the exceptions have larger shifts that make up for it. The feet's lowest pixel
lands `shift_y` below the hex center: a median of 4 pixels, 2–5 for humans, up to 24 for big
monsters. Horizontally, human bodies are centered within 2.5 pixels of the hex center in all six
directions.

Objects that aren't on a hex (interface pieces, the cursor, inventory pictures) are drawn from their
top-left corner instead, and use the shifts and offsets in their own ways. The hex cursor, for one,
uses its frame offset (16, 14) as a placement offset, not as motion (`_gmouse_3d_move_to`).

## How offsets accumulate

The object keeps a running offset `(ox, oy)`. Placing it on a hex (`objectSetLocation`, `obj_move_to_tile`
in Fallout 1) resets it to 0.

**Playing an animation** (`_object_animate`, `fallout2-ce: src/animation.cc`):

- On the first tick, the game switches to the new FRM, sets frame 0 and adds
  **the outgoing FRM's shift for the current direction plus frame 0's offset** to `(ox, oy)`. The
  outgoing shift is added on top of the new file's own shift, which the renderer applies anyway. Fallout
  1 does the same. It looks like a quirk of the original code; it only matters when the outgoing file's
  shift isn't zero.
- Each later tick advances one frame and adds that frame's offset. Frame `i` of an animation started
  from rest is therefore drawn at `hex center + shift[d] + Σ offset[0..i]` (plus the quirk above).
- Played in reverse, each step back subtracts the offset of the frame it leaves.
- The offset stays after the animation ends, until the object is put on a hex again. That's how a
  critter knocked back keeps its displaced position until the game moves it to the hex it landed on.

**Walking and running** (`_object_move`) work differently, because the critter actually travels:

- At the start the critter is placed on its hex (offset reset), turned and set to frame 0; frame 0's
  offset is added.
- Each tick adds the next frame's offset, wrapping from the last frame to frame 0, so the cycle repeats.
- When the running offset reaches one hex step in the walking direction (in either axis), the critter
  moves to the next hex and the step is subtracted from the offset. The steps are
  NE (16, −12), E (32, 0), SE (16, 12), SW (−16, 12), W (−32, 0), NW (−16, −12) (`_off_tile` and
  `dword_51D984`, `fallout2-ce: src/tile.cc`; `off_tile` in Fallout 1).

So the sum of a walk cycle's offsets is how far the critter moves per cycle, in screen pixels. That's a
measured root motion for free. **It isn't a whole number of hexes**:

| File                     | Frames | Sum, E    | Sum, NE    | Hexes per cycle, E |
|--------------------------|-------:|-----------|------------|-------------------:|
| `hmjmpsab` (male walk)   | 8      | (69, 0)   | (34, −25)  | 2.16               |
| `hfjmpsab` (female walk) | 8      | (60, 0)   | (30, −22)  | 1.88               |
| `hmjmpsat` (male run)    | 10     | (128, 0)  | (64, −47)  | 4.00               |
| `maclawab` (deathclaw)   | 8      | (102, 0)  | (51, −39)  | 3.19               |
| `mamantab` (mantis)      | 8      | (28, 0)   | (14, −10)  | 0.88               |

No unarmed walk in either game is a whole number of hexes in all six directions, and runs are whole only
in E and W, in 38 of 170 cases. The step rule copes: the remainder carries over, so `hmjmps` moves 2 or
3 hexes per cycle as the extra pixels build up. On the diagonals the art's y/x ratio averages 0.739
against the grid's 0.75, so x triggers each step and the critter lags a little sideways, 6 pixels over
20 hexes for the median walk. The lag is dropped when the path ends and `objectSetLocation` puts the
critter on its hex: it snaps.

Single frame offsets are noisier than the sums. Frames are cropped tight, so each frame's offset also
absorbs the change in its crop: the male walk's E offsets vary from 6 to 11 pixels. Only a cycle's sum
is clean root motion.

The four diagonals mirror each other and W is −E for all but 8 critters, which are off by 1–6 pixels
(`hmmetlab`, `malieuab`, `nmlosrab`, `nmovr2ab`, `navgulab`; runs `hmmaxxat`, `nfpeasat`, `maroboat`).

**Stands.** Frame 0's offset is (0, 0) in 555 of Fallout 2's 576 stand directions. A stand's offsets
don't always sum to zero (they don't in 215 of 576), so an idle fidget can leave a critter displaced
until it's placed on a hex again. A few look broken: `nmlosraa` NE sums to (288, 289), and `nfbrlpaa` E
(52, 0) and `nmovr2aa` E (51, 0) move like walks.

`_dude_stand` (returning to the stand with a weapon out) builds its offset from the sum of all the
take-out animation's frame offsets plus the unarmed stand's shift, then places the critter on its hex
and applies it. Armed stands are therefore not necessarily drawn where the unarmed one is.

## Timing

- A frame lasts `1000 / fps` milliseconds, with fps 0 read as 10 (`artGetFramesPerSecond`,
  `animationComputeTicksPerFrame`; `art_frame_fps`, `compute_tpf` in Fallout 1).
- In combat, walks (not runs) get the *combat speed* preference added to their fps.
- The action frame is the frame at which the game fires the animation's effect (the hit, the shot). It
  isn't used for drawing.

In Fallout 2's critter `.frm` files the fps is 10 in 64%, 0 (also 10) in 20%, 8 in 10%, and 9, 13 or 20
in most of the rest. Static art (scenery, tiles, inventory pictures) mostly stores 1 or 0.

## Decoding

```python
import struct

HEADER_SIZE = 62
DIRECTIONS = ("NE", "E", "SE", "SW", "W", "NW")


def read_frm(data: bytes) -> dict:
    """Decodes an FRM. Each direction is a list of frames; equal adjacent offsets share one list."""
    version, fps, action_frame, frame_count = struct.unpack_from(">IhhH", data, 0)
    shift_x = struct.unpack_from(">6h", data, 10)
    shift_y = struct.unpack_from(">6h", data, 22)
    offsets = struct.unpack_from(">6I", data, 34)
    (data_size,) = struct.unpack_from(">I", data, 58)

    directions: list[list[dict]] = []
    for d in range(6):
        if d > 0 and offsets[d] == offsets[d - 1]:
            directions.append(directions[-1])  # the same block, as the game does
            continue
        pos = HEADER_SIZE + offsets[d]
        frames = []
        for _ in range(frame_count):
            width, height, size, off_x, off_y = struct.unpack_from(">hhIhh", data, pos)
            pixels = data[pos + 12:pos + 12 + size]
            rows = [list(pixels[y * width:(y + 1) * width]) for y in range(height)]  # top to bottom
            frames.append({"width": width, "height": height, "offset": (off_x, off_y), "rows": rows})
            pos += 12 + size
        directions.append(frames)

    return {
        "version": version,
        "fps": fps or 10,
        "action_frame": action_frame,
        "shift": list(zip(shift_x, shift_y)),
        "directions": directions,
        "distinct_directions": len({id(frames) for frames in directions}),
    }


def anchor_in_frame(width: int, height: int) -> tuple[int, int]:
    """The frame pixel that sits on the anchor point. Index 0 pixels are transparent."""
    return width // 2, height - 1
```

## Writing FRM

- Store the directions in order, contiguously, and give repeated directions the same offset as the one
  before them. Don't make a later direction point back at an earlier, non-adjacent block: the game
  would read the next block from the stream instead.
- Keep index 0 for transparency only.
- Set `size` to `width × height` and `data size` to the total length of the frame data.

## Notes on the wiki

The falloutmods wiki's *FRM File Format* page agrees on the layout, the big-endian integers, the
direction order (`.fr0` is NE, clockwise to `.fr5` NW) and index 0 being transparent, with these
differences:

- **Signedness.** It marks fps, action frame, frame count, width and height as unsigned. The game
  reads them into `short`s (`artReadHeader`, `artReadFrameData`). The values are small, so either
  reading works for real files.
- **Pixel values.** It gives the pixel bytes' range as 0–63. Pixels are palette indices, 0–255; 0–63
  is the range of the palette's color components.
- **Per-FRM palettes.** It says an FRM may have its own palette, `<name>.pal` next to it, and gives
  `helpscrn.frm` with `helpscrn.pal` as the example. The art loader never looks for one. The help
  screen, the death screen and the ending slides load their palettes by name in the code that shows
  them (`fallout2-ce: src/game.cc`, `src/main.cc`, `src/endgame.cc`). Only the ending slides derive
  the palette's name from the FRM's.
- **The anchor.** `top = center_y - frame_height`; see [Where a frame goes](#where-a-frame-goes).
- **Values it lists.** fps 8 to 22 (`0x08`–`0x16`) "possibly more", and 1 to 255 frames per
  direction, as observed values rather than limits.

## Checked against the game data

The format comes from the code of fallout2-ce, fallout1-ce, fallout1-re and fallout2-re. It was
checked on 2026-10-03 against every FRM, `.fr0`–`.fr5` included, of four CD releases: 10,394 files in
Fallout 1 US, 10,386 in the European release, 15,190 in Fallout 2 US and 15,085 in the UK release.

- **Every file parses as specified.** In all 51,055 files every direction's offset matches a
  sequential read, every frame's size is width × height, and the last frame ends exactly at the end of
  the file. The header's version and data size are as described in [Layout](#layout) and
  [Directions shared and split](#directions-shared-and-split).
- **Directions:** the block counts, the shifts of one-block files and the split files, all files
  (see [Directions shared and split](#directions-shared-and-split)).
- **Anchoring:** the code's rule, shown right by the cursors and the hex cursor; stand frames of
  Fallout 2's critters in all six directions, and Fallout 1's (see [Where a frame goes](#where-a-frame-goes)).
- **Offsets:** every walk and run of both US releases, and every stand (see
  [How offsets accumulate](#how-offsets-accumulate)). The step rule was simulated on the walks.
- **Timing:** the fps values of all files (see [Timing](#timing)). The action frames weren't
  examined.

Renders made for the check (stands in six directions on the hex grid, walk cycles with their hex
changes, the hex cursor under both rules) aren't kept in the repository, since they're made from
game data.

## Sources

- fallout2-ce (commit `e97087b`): `src/art.cc` (`artReadHeader`, `artRead`, `artReadFrameData`,
  `artGetFrame`, `artGetFramesPerSecond`, `buildFid`), `src/object.cc` (`_obj_render_object`,
  `objectGetRect`, `_obj_offset`, `objectSetLocation`), `src/animation.cc` (`_object_animate`,
  `_object_move`, `_dude_stand`, `animationComputeTicksPerFrame`), `src/tile.cc` (`tileToScreenXY`,
  `_off_tile`), `src/draw.cc` (`transSrcCopy`).
- fallout1-ce (commit `0609bcf`): `src/game/art.cc` (`load_frame_into`, `art_readFrameData`,
  `frame_ptr`, `art_frame_fps`), `src/game/object.cc`, `src/game/anim.cc` (`compute_tpf`),
  `src/game/tile.cc`. Same format and same logic as Fallout 2.
- fallout1-re (`ac9784b`) and fallout2-re (`b135fc4`): the original-code reconstructions the CE ports
  come from; they agree on everything above (`art_id`, the readers).
- The fodev.net FRM page (<https://fodev.net/files/fo2/frm.html>): header layout, version 4, the
  color-cycled range.
- [falloutmods wiki, FRM File Format](https://falloutmods.fandom.com/wiki/FRM_File_Format), read
  through the MediaWiki API (`api.php?action=parse&prop=wikitext`), since plain page fetches return
  HTTP 402: header layout, version 4, the `.fr0`–`.fr5` suffixes, the positioning formula, the
  `data size` note for split files.
