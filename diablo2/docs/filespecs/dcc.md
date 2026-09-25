# DCC: compressed animated sprites

DCC is the format of nearly every animated sprite in Diablo II: the layers of players, monsters and
objects, plus missiles and overlays. It's heavily compressed.

- Frames of one direction share a pixel buffer of 4×4 cells.
- Each cell keeps a small palette of up to four colors.
- Unchanged cells carry over from the previous frame.

A cell can't hold more than four colors, so encoding is slightly lossy; Paul Siramy calls the loss
"almost unnoticeable". Decoding is exact.

For glisomorph, this limits what a DCC can hold. Synthesized frames with busier 4×4 cells would be
approximated if re-encoded as DCC; DC6 has no such limit.

The game decodes a DCC into the same structure as a [DC6](dc6.md) file, and the header's size fields
are sizes of that DC6 form.

The algorithm below is Bilian Belchev's description as implemented in Paul Siramy's decoder (merge_dcc),
which other decoders follow. Bit-level details come from the open-source decoders compared in
[AGENTS.md](../AGENTS.md#references).

## Bit streams

- **Bit order:** everything after the file header is read as a bit stream, least significant bit
  first. Bit `i` of the stream is `(byte[i >> 3] >> (i & 7)) & 1`, and an n-bit field is assembled
  low bit first, so it reads as little-endian.
- **Signed fields:** two's complement over n bits. A 0-bit field reads as 0.

## File header

| Offset | Type            | Field                                                      |
|--------|-----------------|------------------------------------------------------------|
| 0      | u8              | signature, `0x74`                                          |
| 1      | u8              | version, 6                                                 |
| 2      | u8              | number of directions (1–32)                                |
| 3      | u32             | frames per direction                                       |
| 7      | u32             | always 1                                                   |
| 11     | u32             | size of the whole file once converted to DC6: `Σ outsize + 4·directions·frames + 24` |
| 15     | u32[directions] | byte offset of each direction                              |

Directions are stored back to back: direction `d` runs from its offset to the next direction's offset,
or to the end of the file. The first starts at `15 + 4·directions`.

## Direction header

Each direction is its own bit stream, starting at its byte offset.

1. `outsize`, 32 bits: this direction's size as DC6 frame blocks, `Σ (32 + coded_bytes + 3)`.
2. Compression flags, 2 bits:
   - bit 0 means the EncodingType and RawPixel streams are present;
   - bit 1 means the EqualCells stream is present.
3. Seven 4-bit codes, one per frame-header field: variable0, width, height, x offset, y offset,
   optional bytes, coded bytes. Each code picks a bit width from this table:

   ```
   WIDTHS = [0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 26, 28, 30, 32]
   ```

## Frame headers

The frames' headers follow, packed with no alignment, each with these fields in order:

| Field          | Bits           | Notes                                                            |
|----------------|----------------|------------------------------------------------------------------|
| variable0      | per its code   | unknown, always 0                                                |
| width          | per its code   |                                                                  |
| height         | per its code   |                                                                  |
| x offset       | per its code   | signed                                                           |
| y offset       | per its code   | signed                                                           |
| optional bytes | per its code   | length of extra data for the frame, always 0                     |
| coded bytes    | per its code   | the frame's length as DC6 run-length data                        |
| bottom-up      | 1              | always 0                                                         |

**Frame box.** Offsets are relative to the unit's position, with y growing downward.

- **x:** the frame covers `x offset … x offset + width − 1`.
- **y (normal frames):** it covers `y offset − height + 1 … y offset`, so `(x offset, y offset)` is its
  **bottom-left pixel**.
- **y (bottom-up frames):** `y offset` would be the top row. Nothing in the game uses these, and it's
  unknown whether their pixels come in a different order.

The direction's box is the union of its frames' boxes. From here on, coordinates are relative to the
direction box's top-left corner. A decoded frame is drawn with that corner at the unit's position plus
`(box x min, box y min)`.

## Optional bytes, stream sizes, pixel values

After the frame headers:

1. **Optional bytes.** If any frame has optional bytes, skip to the next byte boundary, then skip every
   frame's optional bytes in order. Never happens in the game's files.
2. **Stream sizes,** 20 bits each, in bits:
   - EqualCells, only if flag bit 1 is set;
   - PixelMask, always;
   - EncodingType and RawPixel, only if flag bit 0 is set.
3. **Pixel values,** 256 bits. Bit `i` set means palette index `i` is used in this direction. The
   used indices, in increasing order, form the table `pv`: code `k` stands for the `k`-th used index.
   Unused codes map to 0.
4. **Streams.** They start right after, at bit granularity, back to back in this order: EqualCells,
   PixelMask, EncodingType, RawPixel, then **PixelCodeDisplacement (PCD)**. PCD is everything left in
   the direction. A stream that's absent has size 0.

## Cells

**Buffer cells.** The direction box is cut into 4×4 cells: `1 + (W − 1) / 4` columns and
`1 + (H − 1) / 4` rows. The last column and row take whatever is left, 1–4 pixels.

**Frame cells.** Each frame is cut separately, aligned to the buffer grid. On each axis, with `o` the
frame's offset within the direction box and `size` its width or height:

```python
def frame_cells(o: int, size: int) -> list[int]:
    first = 4 - o % 4                       # 1..4 pixels up to the next grid line
    if size - first <= 1:
        return [size]                       # one cell; a 1-pixel remainder is merged in
    t = size - first - 1
    n = 2 + t // 4
    if t % 4 == 0:
        n -= 1
    return [first] + [4] * (n - 2) + [size - first - 4 * (n - 2)]   # last cell: 2..5 pixels
```

A 1-pixel remainder is merged into its neighbour, so frame cells can be 5 pixels wide or tall.
Cell `(cx, cy)` of a frame belongs to buffer cell `(o_x // 4 + cx, o_y // 4 + cy)`. Frame cells are
visited row by row, top to bottom.

## Stage 1: the pixel buffer

For every frame in order, and every cell of the frame, decide the cell's colors:

```python
last_entry = [None] * buffer_cells          # most recent entry per buffer cell
entries = []
for f, frame in enumerate(frames):
    for cy, cx in frame_cells_in_row_major_order(frame):
        cur = buffer_cell_index(frame, cx, cy)
        prev = last_entry[cur]
        if prev is not None:
            if equal_cells_size and equal_cells.read(1):
                continue                    # same as before: no entry
            mask = pixel_mask.read(4)
        else:
            mask = 0xF
        count = bin(mask).count("1")
        raw = encoding_type.read(1) if count and encoding_type_size else 0
        codes, last = [], 0
        for _ in range(count):
            if raw:
                code = raw_pixel.read(8)
            else:
                code = last
                while True:                 # displacement: add 4-bit steps, 15 means "continue"
                    step = pcd.read(4)
                    code += step
                    if step != 15:
                        break
            if code == last:
                break                       # a repeated code ends the list early
            codes.append(code)
            last = code
        values = [0] * 4
        for i in range(4):                  # the newest code goes to the lowest mask bit
            if mask >> i & 1:
                values[i] = codes.pop() if codes else 0
            else:
                values[i] = prev.values[i]
        entry = Entry(frame=f, cell=cx + cy * frame_cells_wide, values=values)
        last_entry[cur] = entry
        entries.append(entry)
for e in entries:
    e.values = [pv[v] for v in e.values]   # codes → palette indices
```

All four sized streams must now be used up exactly.

## Stage 2: the frames

The PCD stream continues where stage 1 left it. It holds all the displacements first, then all the
pixel bits, which is why the stages can't be merged.

```python
bitmap = direction_sized_image(fill=0)      # persists across frames
last_cell = [None] * buffer_cells           # (x, y, w, h) last written per buffer cell
next_entry = 0
for f, frame in enumerate(frames):
    image = direction_sized_image(fill=0)
    for (x, y, w, h), (cx, cy) in frame_cells_with_positions(frame):
        b = (x // 4) + (y // 4) * buffer_cells_wide
        e = entries[next_entry] if next_entry < len(entries) else None
        if e is None or (e.frame, e.cell) != (f, cx + cy * frame_cells_wide):
            # an equal cell: reuse what the buffer cell last held
            lx, ly, lw, lh = last_cell[b] or (0, 0, -1, -1)
            if (w, h) != (lw, lh):
                clear(bitmap, x, y, w, h)
            else:
                copy(bitmap, lx, ly, w, h, to=(x, y))
                copy(bitmap, x, y, w, h, into=image)
        else:
            v = e.values
            if v[0] == v[1]:
                fill(bitmap, x, y, w, h, v[0])
            else:
                bits = 1 if v[1] == v[2] else 2
                for yy in range(h):
                    for xx in range(w):
                        bitmap[y + yy][x + xx] = v[pcd.read(bits)]
            copy(bitmap, x, y, w, h, into=image)
            next_entry += 1
        last_cell[b] = (x, y, w, h)
    frame.image = image                     # 0 = transparent
```

At the end, PCD has 0–7 bits left over: the padding to the next byte.

**Decoders disagree on equal cells.** When the cell's size is unchanged, Siramy's decoder, OpenDiablo2
and OpenD2 copy the block from where the buffer cell was last written. Worldstone leaves the bitmap as
it is, and Riiablo's newer decoder copies from the previous frame's image. The first is right: only it
reproduces the `coded bytes` the encoder stored.

Palette index 0 is transparent in the decoded frames.

## Checking a decoder

The file checks itself. Re-encoding a decoded frame as DC6 run-length data must give exactly its
`coded bytes`. Use the encoder's rules:

- runs of up to 127 pixels;
- `0x80` ends every row;
- a row's trailing transparent run is left out.

The direction's `outsize` and the file's DC6 size then follow from the formulas above. A decoder that
gets any cell wrong almost always fails this check somewhere.

## Directions

A sprite with N directions stores them in an **interleaved order, not clockwise**. The game's own
direction is one of 64 steps of 5.625°:

- 0 is facing screen-south (down);
- the values increase clockwise: 16 is west, 32 north, 48 east.
- the steps are equal angles on the ground, not on screen.

It's converted by first finding the **clockwise position** `p`, where 0 is the sector centered on south:

```python
p = ((d64 + 32 // N) // (64 // N)) % N
file_dir = DIRS[N][p]                  # the DCC / DC6 direction to draw
cof_row = p                            # the COF draw-order row: the position, not file_dir
```

```python
DIRS = {
    1:  [0],
    4:  [0, 1, 2, 3],
    8:  [4, 0, 5, 1, 6, 2, 7, 3],
    16: [4, 8, 0, 9, 5, 10, 1, 11, 6, 12, 2, 13, 7, 14, 3, 15],
    32: [4, 16, 8, 17, 0, 18, 9, 19, 5, 20, 10, 21, 1, 22, 11, 23,
         6, 24, 12, 25, 2, 26, 13, 27, 7, 28, 14, 29, 3, 30, 15, 31],
}
```

So the file's direction index means:

| Directions | File index → facing                                                               |
|-----------:|-----------------------------------------------------------------------------------|
| 8          | 0 SW, 1 NW, 2 NE, 3 SE, 4 S, 5 W, 6 N, 7 E                                        |
| 16         | 0–7 as above, then 8 SSW, 9 WSW, 10 WNW, 11 NNW, 12 NNE, 13 ENE, 14 ESE, 15 SSE   |
| 32         | 0–15 as above; 16 + j is 11.25° + 22.5°·j clockwise from south                    |

Caveats:

- **Merge_dcc's naming** follows this. Paul Siramy's tool names its output `D<p>-(<file dir>)-F<frame>`,
  which is why the PDF shows `D00-(04)` and `D02-(00)`.
- **Its 32-direction table was wrong;** the table above is the corrected one from his later DS1 editor.
- **4 directions are unsettled.** OpenDiablo2 centers file index 0 on south, and Riiablo on southwest,
  45° apart. No 4-direction file was checked.

## Checked against the game data

- **All files.** A decoder written from this page decoded every DCC in the 1.00 `d2data.mpq`,
  `d2char.mpq` and `d2exp.mpq`: 21,717 files, 271,176 directions, 3,305,132 frames.
  - **Size fields:** every frame re-encodes to exactly its `coded bytes`, and every direction's `outsize`
    and every file's DC6 size match their formulas.
  - **Streams:** in every direction, the four sized streams are used up exactly, PCD ends with 0–7
    padding bits, and every stage-1 entry is used by stage 2.
  - **Headers:** every file has signature `0x74`, version 6 and the constant 1, and the first direction
    starts right after the offset table.
  - **Unused fields:** `variable0`, the optional bytes and the bottom-up flag are 0 in every frame.
  - **Directions per file:** 1 (2,768 files), 4 (56), 8 (4,361), 16 (14,483) and 32 (49).
- **Directions:**
  - The Barbarian's `batn1hs` layers, composed in all 16 clockwise positions, turn smoothly from south
    through west, north and east. The shield is in front facing west and behind facing east. Indexing
    the COF rows by file direction instead draws the shield over his body when he faces east.
  - `missiles/arrow.dcc`, in 32 directions and drawn through the 32-direction table, turns steadily: it
    points south at position 0, west at 8, north at 16 and east at 24.

## Sources

- Bilian Belchev, "The DCC File Format Description" (2002), in Paul Siramy's `dcc_doc.zip`. The
  canonical description, for personal and non-commercial use.
- Paul Siramy's decoder (`dccinfo.c`, `merge_dcc.c`), and his DS1 editor's direction tables, as mirrored
  in d2imdev and d2-ds1-edit.
- OpenDiablo2 (`d2common/d2fileformats/d2dcc`), Riiablo (`codec/DCC.java`), Worldstone (`dcc.cpp`) and
  OpenD2, which agree with the above except where noted.
- D2MOO: the 64-direction system (`D2Common/src/Path/Step.cpp`).
