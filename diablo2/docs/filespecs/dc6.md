# DC6: uncompressed sprites

DC6 is Diablo II's simple sprite format. Pixels are stored raw; only transparent runs are compressed.
It's used for the UI, fonts and inventory pictures (`data/global/items/inv*.dc6`), items' drop animations
(`flp*.dc6`), and a few animations too big or too special for [DCC](dcc.md): Mephisto, Tyrael, the
Maggot Queen's death and Mephisto's Hell Gate, for example.

All integers are little-endian.

## Layout

| Offset | Type                  | Field                                                   |
|--------|-----------------------|---------------------------------------------------------|
| 0      | u32                   | version, always 6                                       |
| 4      | u32                   | flags, always 1 in the game's files                     |
| 8      | u32                   | encoding, always 0                                      |
| 12     | u8×4                  | termination bytes: usually `EE EE EE EE`, sometimes `CD CD CD CD` or zero |
| 16     | u32                   | number of directions                                    |
| 20     | u32                   | frames per direction                                    |
| 24     | u32 × directions × frames | offset of each frame, direction by direction        |

Each frame:

| Offset | Type | Field                                                                   |
|--------|------|-------------------------------------------------------------------------|
| 0      | u32  | flip: 0 means the rows are stored bottom-up, non-zero top-down          |
| 4      | u32  | width                                                                   |
| 8      | u32  | height                                                                  |
| 12     | i32  | x offset: the frame's left edge, relative to the unit's position        |
| 16     | i32  | y offset: its bottom edge (negative is up); see below                   |
| 20     | u32  | always 0                                                                |
| 24     | u32  | a leftover pointer from the tool that wrote the file; meaningless       |
| 28     | u32  | length of the pixel data                                                |
| 32     | …    | pixel data (`length` bytes), then 3 termination bytes                   |

Frames are packed: the next one starts at `offset + 32 + length + 3`.

**Where the frame goes.** Decoders disagree by one pixel. Siramy's DS1 editor and Riiablo's older code
put the frame's bottom row at the y offset, as in [DCC](dcc.md#frame-headers). OpenDiablo2 and Riiablo's
newer code put it one row higher. Nothing in the files settles which is right.

**Directions** use the same interleaved order as DCC (see [dcc.md](dcc.md#directions)).

## Pixel data

Palette indices, one row after another. The first stored row is the **bottom** row unless `flip` is set.

| Byte `c`      | Meaning                                             |
|---------------|-----------------------------------------------------|
| `0x80`        | end of the row; the rest of it is transparent       |
| `0x81–0xFF`   | skip `c & 0x7F` transparent pixels                  |
| `0x00–0x7F`   | `c` literal pixels; their colors are the next `c` bytes |

Every row, the last one included, ends with `0x80`, so the number of `0x80` bytes is the height. Runs
never cross a row, and nothing needs the width to decode. As in Diablo 1, transparency exists only as
skip runs; index 0 is an ordinary color.

```python
def decode_dc6_frame(data: bytes, width: int, height: int, flip: int) -> list[list[int | None]]:
    """Returns rows top to bottom; None marks a transparent pixel."""
    rows, row, pos = [], [], 0
    while pos < len(data):
        c = data[pos]
        pos += 1
        if c == 0x80:
            rows.append(row + [None] * (width - len(row)))
            row = []
        elif c & 0x80:
            row += [None] * (c & 0x7F)
        else:
            row += data[pos:pos + c]
            pos += c
    return rows if flip else rows[::-1]
```

## Checked against the game data

Every DC6 in the 1.00 `d2data.mpq`, `d2char.mpq` and `d2exp.mpq` was checked: 1,651 files and 26,312
frames.

- **Header:** version 6, flags 1 and encoding 0 in every file. The termination bytes are `EE`×4 in
  1,193 files, `CD`×4 in 400 and zero in 58.
- **Rows:** every frame has exactly `height` rows, and no row is wider than `width`.
- **Packing:** each frame starts 3 bytes after the previous one's pixel data ends.
- **Flip:** only 140 frames have it, all in the generic inventory pictures (`items/inv1x1.dc6`,
  `inv1x2.dc6`, `inv2x2.dc6`, `inv2x3.dc6`). Rendering confirms the row order: a healing potion (no flip)
  is upright when drawn bottom-up, and a dagger (flip) when drawn top-down.

## Sources

- Paul Siramy, *Extracting Diablo II Animations*: where DC6 is used, and that DCC decodes into
  the same structure.
- D2MOO: the cell struct `D2GfxCellStrc` (flip, width, height, x and y offset) in
  `source/D2Gfx/include/D2Gfx.h`.
- Layout details: the game files.
