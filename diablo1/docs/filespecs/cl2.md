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

## Writing CL2

- Fill in the row-offset header. Row offsets must point at the start of a command, so break runs at
  rows 32, 64, 96 and 128.
- Keep opaque runs within a row. The shipped files never cross rows, so an encoder targeting the
  original game shouldn't either.
- DevilutionX's encoder (`Source/utils/clx_encode.hpp`) emits a fill run for 3 or more repeated
  colors and literals otherwise. The two commands are interchangeable, so that choice only affects size.

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

## Sources

- DevilutionX: `Source/utils/cl2_to_clx.cpp`, `Source/utils/clx_decode.hpp`,
  `Source/utils/clx_encode.hpp`, `Source/engine/clx_sprite.hpp`.
- savagesteel's [CL2.md](https://github.com/savagesteel/d1-file-formats/blob/master/PC-Mac/CL2.md),
  which DevilutionX's source links to as its CL2 reference.
