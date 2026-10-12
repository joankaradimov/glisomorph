# CL2: animated sprites

CL2 holds the directional animations: monsters, players and missiles. Which file is which, and the frame
widths the files don't store, are in [sprite-metadata.md](sprite-metadata.md).

All integers are little-endian.

## File layout

A CL2 file is either a **frame list** or a **sheet**. A sheet is a table of frame lists, one per group.
Directional sprites use one group per direction.

### Frame list

| Offset    | Type | Meaning                                                          |
|-----------|------|------------------------------------------------------------------|
| 0         | u32  | `n`, the number of frames                                        |
| 4 + 4·i   | u32  | start of frame `i` (0 ≤ i < n), relative to the start of the list |
| 4 + 4·n   | u32  | end of the last frame, which is also the size of the list        |

Frame `i` is the byte range `[offset[i], offset[i + 1])`.

### Sheet

| Offset | Type | Meaning                                                        |
|--------|------|----------------------------------------------------------------|
| 4·g    | u32  | start of group `g`'s frame list, relative to the start of the file |

There's no group count. The first frame list starts right after the table, so `groups = offset[0] / 4`.
Monster and player animations are sheets with 8 groups, one per direction, in the order given in
[sprite-metadata.md](sprite-metadata.md#directions).

### List or sheet?

The file doesn't say. The game knows from context, and DevilutionX guesses (`Cl2ToClx`,
`GetNumListsFromClxListOrSheetBuffer`): read the first u32 as a frame count `n`. If the u32 at
`4 + 4·n` equals the file size, the file is a list. Otherwise it's a sheet with `n / 4` groups.

```python
n = u32(data, 0)
is_list = 4 * n + 8 <= len(data) and u32(data, 4 * n + 4) == len(data)
```

## Frame

| Offset | Type   | Meaning                                                                                                     |
|--------|--------|-------------------------------------------------------------------------------------------------------------|
| 0      | u16    | header size, always 10                                                                                      |
| 2      | u16 ×4 | offset, from the frame start, of the command that starts row 32, 64, 96 and 128 (0 if the frame is shorter) |
| 10     | …      | pixel commands                                                                                              |

The row offsets let the renderer skip rows when clipping. A decoder can ignore them, but they make a
good consistency check. Rows are counted from the bottom.

They usually give away the width too. If a frame is taller than 32 rows, the commands before the
row-32 offset normally decode to exactly `32 × width` pixels (a trick from savagesteel's CL2.md). But
that's a hint, not a source. In the Warrior's three bow-attack files
(`plrgfx/warrior/w{l,m,h}b/w?bat.cl2`), the offsets were computed for a width of 128, while the frames
are really 96 wide, as the width table says. Don't use the offsets to seek to a row either: they're
wrong in those files.

## Pixel commands

Pixels are palette indices (see [pal.md](pal.md)). The command stream fills the frame starting at the
**bottom-left** corner: left to right along a row, then the row above.

| Command byte `c` | Meaning                                                                   |
|------------------|---------------------------------------------------------------------------|
| `0x00–0x7F`      | skip `c` transparent pixels                                               |
| `0x80–0xBE`      | fill: `0xBF − c` pixels (1–63), all of the color in the next byte         |
| `0xBF–0xFF`      | literal: `256 − c` pixels (1–65); their colors are the next `256 − c` bytes |

- **Width** isn't stored. It comes from the game's tables ([sprite-metadata.md](sprite-metadata.md)).
- **Height** isn't stored either: it's `pixels decoded / width`. Frames always end on a row boundary.
- **Transparency** exists only as skip runs. There's no color key, and index 0 is opaque black.
- **Runs can wrap rows.** Skip runs often continue onto the next row. In the game's files, fill and
  literal runs never cross a row boundary. DevilutionX's decoder doesn't rely on that, and its
  [CLX](clx.md) encoder does write opaque runs that wrap. Decode the frame as one linear stream and cut it
  into rows afterwards; that handles every case.

```python
def decode_cl2_frame(frame: bytes, width: int) -> list[list[int | None]]:
    """Returns rows top to bottom; None marks a transparent pixel."""
    pos = u16(frame, 0)  # skip the frame header
    stream: list[int | None] = []
    while pos < len(frame):
        c = frame[pos]
        pos += 1
        if c < 0x80:
            stream += [None] * c
        elif c < 0xBF:
            stream += [frame[pos]] * (0xBF - c)
            pos += 1
        else:
            stream += frame[pos:pos + 256 - c]
            pos += 256 - c
    rows = [stream[y:y + width] for y in range(0, len(stream), width)]
    return rows[::-1]
```

## Reading and writing

`diablo1/sprites.py` reads CL2 files into frames of palette indices. `diablo1/export/cl2.py` writes
them; see [common/docs/AGENTS.md](../../../common/docs/AGENTS.md) for the sprite it takes.

### Writing

The game's files were all written one way, nearly to the byte, and `export/cl2.py` writes them that way:

- **Frames** keep the whole canvas, empty rows and all, so every frame of a file is as tall as the others.
  The Warrior's stand is 96 × 96, with 11 to 29 empty rows at the top of each frame.
- **Commands**, with the pixels as one stream, row by row from the bottom, left to right:
  - transparent pixels as skips of up to 127. They run on into the rows above, but not into rows 32, 64,
    96 and 128, so that each of those rows starts with a command of its own, for the header to point at;
  - three or more of one index as fills, of up to 62 each. The command would hold 63, but no file has
    one;
  - everything else as literals of up to 65.
- **Runs across rows:** fills and literals stop at a row's end, but the encoder found runs of one index
  in the stream, past a row's end. So a run is written as fills while three or more of it are left, each
  as long as it can be within its row. The one or two left join the literal after them. A run of three
  that starts at a row's last pixel is a fill of 1, then two literal pixels in the next row.
- **Header:** 10, then where the commands for rows 32, 64, 96 and 128 start, 0 for rows the frame
  doesn't have.
- **Sheets:** the table of where each group's frame list starts, then every list's count and offsets,
  one after another, then all the frames, group by group. A list's offsets count from where the list
  starts. A frame list alone (a missile) is its count and offsets, then its frames.
- **Check:** after writing, the file is read back and compared with the frames, pixel for pixel, and each
  frame's header with where its commands start those rows.

The fill rule is the one DevilutionX's CLX encoder (`Source/utils/clx_encode.hpp`) uses too: a fill for
3 or more repeats, literals otherwise.

## Checked against the game data

Every player, monster and missile CL2 file in the retail `DIABDAT.MPQ`, `hellfire.mpq` and
`hfmonk.mpq` was decoded with the widths from [sprite-metadata.md](sprite-metadata.md):

| Family   | Files | Frames  | Layout                                                    |
|----------|------:|--------:|-----------------------------------------------------------|
| players  | 1056  | 108,760 | all 8-group sheets                                        |
| monsters | 306   | 30,240  | 8-group sheets, except 2 single lists (the Golem's)      |
| missiles | 245   | 2,975   | all single lists (multi-direction missiles use one file per direction) |

In all of them:

- every frame has the 10-byte header;
- every frame decodes to a whole number of rows;
- no fill or literal run crosses a row, while skip runs often do;
- the row offsets match the decoded data, except in the Warrior's three bow-attack files (384 frames;
  see [Frame](#frame)).

`monsters/darkmage/dmagew.cl2` is a 96-byte stub and can't be decoded. The monster type that would use
it is never spawned.

`export/cl2.py` re-encoded every one of those files, 128,573 frames, named and sized by DevilutionX's
tables (`assets/txtdata`):

- 1,386 of the 1,390 files come out byte for byte the same, sheet layouts and headers included, and so
  do 128,187 of the frames;
- the Warrior's three bow-attack files differ in all 384 frames. Their headers point at rows counted 128
  pixels wide (see [Frame](#frame)), and their skips are cut at those rows. Re-encoded at their true
  width of 96, they decode to the same pixels;
- the fireman's attack (`monsters/fireman/firema.cl2`) differs in 2 of 160 frames. There, its encoder
  didn't cut a run of one index at a row's end: two pixels at the end of a row went into a literal,
  where every other file has them as a fill (see [Writing](#writing)).

Every rule in [Writing](#writing) was found by comparing these bytes: the fills of at most 62, the one
or two left over, the runs across rows and the sheet layout. Each fixed every frame it was about.

The writer was also tried on a sheet glisomorph made, a Warrior's stand in 8 directions at twice the
frames (20). It read back pixel for pixel. That was checked with the reader here, not by loading the
file in the game.

## Sources

- DevilutionX: `Source/utils/cl2_to_clx.cpp`, `Source/utils/clx_decode.hpp`,
  `Source/utils/clx_encode.hpp`, `Source/engine/clx_sprite.hpp`.
- savagesteel's [CL2.md](https://github.com/savagesteel/d1-file-formats/blob/master/PC-Mac/CL2.md),
  which DevilutionX's source links to as its CL2 reference.
