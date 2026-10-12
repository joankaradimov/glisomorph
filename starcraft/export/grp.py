"""A sprite's frames as a StarCraft GRP, as the game reads it (unit/**/*.grp).

    GrpExporter().export(sprite, "unit/terran/marine.grp")

Frames go in order, each frame's directions together. A turning frame's 17 cells (directions 0 to 16 of
32; the game draws the rest by mirroring) become 17 consecutive GRP frames, an animation step. A frame
drawn once (one cell) becomes one, as the death frames at the end of a turning GRP. A GRP holds neither
timing nor animations (the iscript does), so the sprite's animations aren't written.

The cells must be palette indices, all present, on the canvas the GRP gets, with the unit at its center
(the sprite's pivot left at the default, or set there): a GRP has no position of its own, and the game
centers its canvas on the unit. Each frame is stored as the smallest box holding what it draws, which
grp.md's frame header limits to 255 pixels each way.

The encoding is the run-length one every sprite uses. In each row: transparent pixels in runs of up to
127, three or more of one index as a repeat run of up to 63, and the rest copied as is, up to 63 at a time.
Identical frames share their data, as in the game's own GRPs. The game's encoder made other choices in
places, so a rebuilt GRP decodes to the same pixels without being the same bytes. With check (the
default), the written file is read back and compared with the cells, pixel for pixel.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from common.export.sprite import Exporter, Sprite
from starcraft.grp import read

DIRECTIONS = 17  # a turning frame's cells: directions 0 to 16 of 32


def encode_frame(cell: np.ndarray) -> tuple[tuple[int, int, int, int], bytes]:
    """A frame (H, W) of palette indices, -1 transparent: its box (x, y, width, height) and its data."""
    ys, xs = np.nonzero(cell >= 0)
    if len(ys) == 0:  # nothing drawn: a 1x1 box with its one pixel transparent
        return (0, 0, 1, 1), struct.pack("<H", 2) + bytes([0x81])
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    if max(x0, y0, x1 - x0, y1 - y0) > 255:
        raise ValueError("a GRP frame's box is at most 255 pixels from the canvas's corner and 255 across; "
                         "this one is %d x %d at (%d, %d)" % (x1 - x0, y1 - y0, x0, y0))
    rows = []
    for row in cell[y0:y1, x0:x1]:
        out, i, w = bytearray(), 0, len(row)
        while i < w:
            j = i
            if row[i] < 0:  # transparent
                while j < w and row[j] < 0 and j - i < 127:
                    j += 1
                out.append(0x80 | (j - i))
            else:
                while j < w and row[j] == row[i] and j - i < 63:
                    j += 1
                if j - i >= 3:  # repeated
                    out += bytes([0x40 | (j - i), int(row[i])])
                else:  # copied, up to the next gap or run of three
                    j = i
                    while j < w and row[j] >= 0 and j - i < 63:
                        if j + 2 < w and row[j] == row[j + 1] == row[j + 2]:
                            break
                        j += 1
                    j = max(j, i + 1)
                    out += bytes([j - i]) + bytes(int(v) for v in row[i:j])
            i = j
        rows.append(bytes(out))
    table, data = bytearray(), bytearray()
    for r in rows:
        table += struct.pack("<H", 2 * len(rows) + len(data))  # from the start of the row table
        data += r
    return (x0, y0, x1 - x0, y1 - y0), bytes(table + data)


def encode(width: int, height: int, frames: list[np.ndarray]) -> bytes:
    """A whole GRP: the frames, in order, on a width x height canvas. Identical frames share their data."""
    shared = {}
    for cell in frames:
        if cell.tobytes() not in shared:
            shared[cell.tobytes()] = encode_frame(cell)
    header = bytearray(struct.pack("<3H", len(frames), width, height))
    body, offsets = bytearray(), {}
    start = 6 + 8 * len(frames)
    for cell in frames:
        box, data = shared[cell.tobytes()]
        if cell.tobytes() not in offsets:
            offsets[cell.tobytes()] = start + len(body)
            body += data
        header += struct.pack("<4BI", *box, offsets[cell.tobytes()])
    return bytes(header + body)


class GrpExporter(Exporter):
    """A sprite as a GRP (see the module). Options:

    check: read the written file back and compare it with the cells (default on)."""

    suffixes = (".grp",)

    def __init__(self, check: bool = True):
        self.check = check

    def frames(self, sprite: Sprite) -> list[np.ndarray]:
        """The GRP's frames in order, after checking the sprite can be one."""
        h, w = sprite.canvas
        if sprite.anchor != (w // 2, h // 2):
            raise ValueError("a GRP is drawn centered on the unit: the pivot has to be the canvas center "
                             "(%d, %d), not %s" % (w // 2, h // 2, sprite.anchor))
        out = []
        for f, cells in enumerate(sprite.cells):
            if len(cells) not in (1, DIRECTIONS):
                raise ValueError("frame %d has %d cells: a GRP frame is drawn once (1) or turns (%d)" % (
                    f, len(cells), DIRECTIONS))
            for d, cell in enumerate(cells):
                if cell is None or cell.ndim != 2:
                    raise ValueError("frame %d, direction %d: a GRP holds palette indices in every cell" % (f, d))
                if cell.max(initial=-1) > 255 or cell.min(initial=0) < -1:
                    raise ValueError("frame %d, direction %d: indices run 0-255, -1 transparent" % (f, d))
                out.append(cell.astype(np.int16))
        return out

    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        path = self.check_suffix(path)
        h, w = sprite.canvas
        frames = self.frames(sprite)
        data = encode(w, h, frames)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if self.check:
            back = read(path.read_bytes())
            if (back.width, back.height, len(back.frames)) != (w, h, len(frames)):
                raise AssertionError("%s doesn't read back as written" % path)
            for f, (a, b) in enumerate(zip(back.frames, frames)):
                if not np.array_equal(a, b):
                    raise AssertionError("%s: frame %d doesn't read back as written" % (path, f))
        return [path]
