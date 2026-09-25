# CEL: sprites and tiles

CEL is the older of the two sprite formats. The game uses it for:

- item drop animations (`items/*.cel`),
- objects (`objects/*.cel`),
- town NPCs (`towners/**/*.cel`),
- inventory and cursor graphics (`data/inv/objcurs.cel`),
- UI pieces (`ctrlpan/`, `data/`),
- a few 8-direction sheets (`towners/animals/cow.cel`),
- dungeon tiles (`levels/*data/*.cel`), which use a different frame encoding (see
  [Level tile CELs](#level-tile-cels)).

Which sprite uses which width is in [sprite-metadata.md](sprite-metadata.md).

All integers are little-endian.

## File layout

The layout is the same as [CL2](cl2.md#file-layout): either a frame list, or a sheet of frame lists.
CEL uses the same list-or-sheet test. `towners/animals/cow.cel`, for example, is an 8-group sheet.

For CEL sheets, DevilutionX (`CelToClx`) uses the offset table only to find where the first group
starts, then reads the groups back to back. In `cow.cel` the table's offsets are also correct, so
either approach works.

## Frame

A frame may start with the same 10-byte header as CL2: `u16` header size (10), then the offsets of
rows 32, 64, 96 and 128. Unlike CL2, the header is optional, and whether it's there depends on the
file:

- **With headers:** the item drop animations, `data/inv/objcurs.cel` and `towners/animals/cow.cel`.
- **Without headers:** the UI graphics, whether they have one frame or several (`data/pentspin.cel`,
  `ctrlpan/p8but2.cel`, `items/duricons.cel`, `ctrlpan/panel8.cel`, `data/textbox.cel`). Level tile
  CELs don't have them either.

DevilutionX (`CelToClx`) treats a frame as having a header when its first `u16` is 10. That's a
heuristic: a headerless frame that starts with a 10-pixel literal run whose first pixel is color 0
would be misread. It works on the game data, although the single-frame debug graphic `data/square.cel`
is ambiguous.

When the header is present and the frame is taller than 32 rows, the commands before the row-32 offset
normally decode to exactly `32 × width` pixels. That's a handy check on the width tables, but not a
reliable source of widths: see [cl2.md](cl2.md#frame).

## Pixel commands

Rows go bottom to top, like CL2. The meaning of the high bit is the **opposite** of CL2's, and there's
no fill command:

| Command byte `c` | Meaning                                                      |
|------------------|--------------------------------------------------------------|
| `0x00–0x7F`      | literal: `c` pixels, whose colors are the next `c` bytes     |
| `0x80–0xFF`      | skip `256 − c` transparent pixels                            |

- Runs never cross a row boundary. DevilutionX's converter relies on this.
- **Width** isn't stored. It can also differ per frame: `data/inv/objcurs.cel` holds cursors and
  inventory items of several sizes. The original game hard-coded those widths. DevilutionX ships them as
  `assets/data/inv/objcurs-widths.txt`.
- **Height** is `pixels decoded / width`.

```python
def decode_cel_frame(frame: bytes, width: int) -> list[list[int | None]]:
    """Returns rows top to bottom; None marks a transparent pixel."""
    pos = 10 if u16(frame, 0) == 10 else 0
    stream: list[int | None] = []
    while pos < len(frame):
        c = frame[pos]
        pos += 1
        if c < 0x80:
            stream += frame[pos:pos + c]
            pos += c
        else:
            stream += [None] * (256 - c)
    rows = [stream[y:y + width] for y in range(0, len(stream), width)]
    return rows[::-1]
```

## Level tile CELs

`levels/l1data/l1.cel` and its siblings hold 32×32 pieces of dungeon tiles. The frame encoding depends
on a **tile type**, which is stored in the level's MIN file rather than in the CEL:

| Type              | Bytes    | Shape and encoding                                                                   |
|-------------------|----------|--------------------------------------------------------------------------------------|
| Square            | 1024     | 32×32, raw pixels                                                                    |
| TransparentSquare | variable | 32×32, run-length encoded like a sprite CEL frame (runs don't cross rows)            |
| LeftTriangle      | 544      | 32×31, varying-width rows, with 2 padding bytes before every even row                |
| RightTriangle     | 544      | the mirror image of LeftTriangle, with the padding after every even row              |
| LeftTrapezoid     | 800      | 32×32: the bottom part of LeftTriangle in its encoding, then raw pixels for the top 32×16 rectangle |
| RightTrapezoid    | 800      | the same, with RightTriangle for the bottom part                                     |

These frames have no header. Tiles aren't animated sprites, so this is as far as these docs go for now.
The exact row widths are in DevilutionX's `Source/levels/dun_tile.hpp`.

## Checked against the game data

On the retail `DIABDAT.MPQ`:

- `data/inv/objcurs.cel` (179 frames), `items/armor2.cel` (15 frames) and `towners/animals/cow.cel`
  (8 groups × 12 frames) have the 10-byte header on every frame.
- In `items/armor2.cel` and `cow.cel`, the header's row offsets match the decoded data, no run crosses a
  row boundary, and every frame decodes to a whole number of rows.
- The UI CELs listed under [Frame](#frame) have no frame headers.
- `levels/l1data/l1.cel` (1119 frames) has no frame headers. Its frame sizes are 544 bytes (477
  frames), 1024 (219) and 800 (132), and the rest vary, which matches the tile types above.

## Sources

- DevilutionX: `Source/utils/cel_to_clx.cpp`, `Source/levels/dun_tile.hpp`,
  `Source/cursor.cpp` (the objcurs widths).
- savagesteel's [d1-file-formats](https://github.com/savagesteel/d1-file-formats).
