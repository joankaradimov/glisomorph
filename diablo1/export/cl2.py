"""A sprite's frames as a Diablo CL2, as the game reads it (plrgfx/**/*.cl2, monsters/**/*.cl2, missiles/*.cl2).

    Cl2Exporter().export(sprite, "plrgfx/warrior/wls/wlsas.cl2")

A CL2 holds one animation of one unit: its frames, in the order the game plays them, in every direction.
Players and monsters are sheets of 8 groups, one per direction (S, SW, W, NW, N, NE, E, SE: see
sprite-metadata.md), and the sprite's directions are the groups, in its order. A frame drawn once (one
cell) goes into every group. Missiles are single lists: a sprite drawn in one direction (directions=1)
is written as one, and with split, a sprite in N directions as N lists, <name>1.cl2 to <name>N.cl2, as
the game's Fireball comes in 16. A CL2 holds neither its frames' width, their timing nor the animations:
the game's tables do (sprite-metadata.md). So the sprite's animations aren't written: write one sprite
per file, its frames in the order the game plays them.

The cells must be palette indices, all present, on the canvas the game draws: as wide as its table says
for that file, with the unit at x = width / 2, 16 pixels above the bottom row (ground=16: the tile
center, where players and monsters stand). A missile is shifted by its table's width2 instead, so
ground=None leaves its pivot unchecked. Every frame keeps the whole canvas, empty rows and all, as the
game's own frames do.

The encoding is the game's. The pixels go as one stream, row by row from the bottom, left to right:
transparent pixels as skips of up to 127, which run on into the rows above, but not into rows 32, 64,
96 and 128, whose first commands each frame's header points to; three or more of one index as fills, up
to 62 (the command would hold 63, but the game's encoder never wrote it); the rest as literals of up to
65. Fills and literals stop at a row's end, but the runs of one index are found in the stream: one that
goes on into the next row is cut there, and one or two left over join the literal after them. A sheet
holds every group's frame list header first, then all the frames. So the game's own players, monsters
and missiles re-encode to their own bytes, all but a few frames (cl2.md, Writing). With check (the
default), the written file is read back with diablo1/sprites.py and compared with the cells, pixel for
pixel, and each frame's header with the rows its commands start.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from common.export.sprite import Exporter, Sprite
from diablo1.sprites import decode_cl2_frame, split_frames

MARKS = (32, 64, 96, 128)  # rows, from the bottom, whose first command a frame's header points to
GROUND = 16  # how far above the bottom row players and monsters stand (sprite-metadata.md, Placement)
FILL = 62  # the longest fill: the command holds 63, but the game's encoder never wrote more than 62


def encode_frame(cell: np.ndarray) -> bytes:
    """One frame (H, W) of palette indices, -1 transparent, as the game encodes it (see the module): the
    10-byte header, then the commands, bottom row first.

    The pixels are one stream, bottom row first, and so are the runs of one index the encoder finds: a run
    can go on past a row's end into the next. But a fill or a literal stops at the row's end. So a run of
    three or more is written as fills while three or more are left, each up to 62 and to the row's end;
    the one or two left go on as literal pixels."""
    h, w = cell.shape
    stream = np.ascontiguousarray(cell[::-1]).reshape(-1)
    out = bytearray(10)
    marks = {}
    skip, literal = 0, []

    def flush_skip():  # the transparent pixels so far, as skips of up to 127
        nonlocal skip
        while skip:
            n = min(skip, 127)
            out.append(n)
            skip -= n

    def flush_literal():  # the literal pixels so far, as literals of up to 65
        for k in range(0, len(literal), 65):
            chunk = literal[k:k + 65]
            out.append(256 - len(chunk))
            out.extend(chunk)
        literal.clear()

    def row_ends(p):  # at pixel p, a row starts: literals stop, and so do skips, before rows 32 to 128
        flush_literal()
        if p // w in MARKS and p // w < h:
            flush_skip()
            marks[p // w] = len(out)

    p = 0
    while p < len(stream):
        v = int(stream[p])
        if v < 0:
            flush_literal()
            skip += 1
            p += 1
            if p % w == 0:
                row_ends(p)
            continue
        flush_skip()
        k = 1
        while p + k < len(stream) and stream[p + k] == v:
            k += 1
        if k >= 3:
            flush_literal()
            while k >= 3:
                m = min(k, FILL, w - p % w)
                out += bytes([0xBF - m, v])
                p += m
                k -= m
                if p % w == 0:
                    row_ends(p)
        for _ in range(k):  # a run of one or two, or what's left of a longer one
            literal.append(v)
            p += 1
            if p % w == 0:
                row_ends(p)
    flush_skip()
    if any(m > 0xFFFF for m in marks.values()):
        raise ValueError("a CL2 frame's header holds 16-bit offsets: this %d x %d frame's rows start too far "
                         "into its data" % (w, h))
    struct.pack_into("<5H", out, 0, 10, *(marks.get(m, 0) for m in MARKS))
    return bytes(out)


def frame_list(frames: list[bytes]) -> bytes:
    """Frames as a CL2 frame list: their count, where each starts and where the last ends, then the frames."""
    offsets, pos = [], 4 * (len(frames) + 2)
    for f in frames:
        offsets.append(pos)
        pos += len(f)
    return struct.pack("<%dI" % (len(frames) + 2), len(frames), *offsets, pos) + b"".join(frames)


def sheet(groups: list[list[bytes]]) -> bytes:
    """Groups of frames as a CL2 sheet, laid out as the game's are: where each group's frame list starts,
    then every list's count and offsets, one after another, then all the frames, group by group. (Each
    list's offsets count from where that list starts.)"""
    starts, pos = [], 4 * len(groups)
    for g in groups:
        starts.append(pos)
        pos += 4 * (len(g) + 2)
    headers, frames = bytearray(), bytearray()
    for g, start in zip(groups, starts):
        offsets = []
        for f in g:
            offsets.append(pos + len(frames) - start)
            frames += f
        headers += struct.pack("<%dI" % (len(g) + 2), len(g), *offsets, pos + len(frames) - start)
    return struct.pack("<%dI" % len(groups), *starts) + bytes(headers) + bytes(frames)


def header_rows(frame: bytes, width: int) -> list[int]:
    """The offsets a frame's header should hold: for rows 32, 64, 96 and 128, where the command that starts
    the row is (0 where the frame is shorter). Raises ValueError where a command runs into such a row."""
    want = {m * width: m for m in MARKS}
    found = {}
    pos, pixels = struct.unpack_from("<H", frame, 0)[0], 0
    while pos < len(frame):
        if pixels in want:
            found[want[pixels]] = pos
        c = frame[pos]
        n = c if c < 0x80 else 0xBF - c if c < 0xBF else 256 - c
        crossed = [m for p, m in want.items() if pixels < p < pixels + n]
        if crossed:
            raise ValueError("a command runs into row %d, so the header can't point at it" % crossed[0])
        pixels += n
        pos += 1 if c < 0x80 else 2 if c < 0xBF else 1 + n
    return [found.get(m, 0) for m in MARKS]


class Cl2Exporter(Exporter):
    """A sprite as a CL2 (see the module). Options:

    check: read the written file back and compare it with the cells (default on).
    directions: how many the game draws the unit in: 8 for players and monsters (the default), 1 for a
        missile drawn the same every way. Each frame has that many cells, or one, drawn the same in all.
    ground: how many pixels above the bottom row the sprite's pivot stands, at x = width / 2 (16, the
        tile center, for players and monsters); None doesn't check (missiles: their table shifts them).
    split: one frame list per direction, <name>1.cl2 to <name><directions>.cl2, as the game's
        16-direction missiles come; otherwise one file, a sheet (a list with one direction)."""

    suffixes = (".cl2",)

    def __init__(self, check: bool = True, directions: int = 8, ground: int | None = GROUND, split: bool = False):
        self.check = check
        self.directions = directions
        self.ground = ground
        self.split = split

    def groups(self, sprite: Sprite) -> list[list[np.ndarray]]:
        """Each direction's frames, in order, after checking the sprite can be a CL2."""
        h, w = sprite.canvas
        if sprite.scale != 1:
            raise ValueError("the game draws a CL2 pixel for pixel: this sprite is at %d times its size" % sprite.scale)
        if self.ground is not None and sprite.anchor != (w // 2, h - self.ground):
            raise ValueError("the game draws a frame from its bottom-left corner, with the unit at x = width / 2, "
                             "%d pixels above the bottom row: the pivot has to be (%d, %d), not %s" % (
                                 self.ground, w // 2, h - self.ground, sprite.anchor))
        groups = [[] for _ in range(self.directions)]
        for f, cells in enumerate(sprite.cells):
            if len(cells) not in (1, self.directions):
                raise ValueError("frame %d has %d cells: a CL2 frame is drawn in %d direction%s, or once in all" % (
                    f, len(cells), self.directions, "s" if self.directions > 1 else ""))
            for d, cell in enumerate(cells):
                if cell is None or cell.ndim != 2:
                    raise ValueError("frame %d, direction %d: a CL2 holds palette indices in every cell" % (f, d))
                if cell.max(initial=-1) > 255 or cell.min(initial=0) < -1:
                    raise ValueError("frame %d, direction %d: indices run 0-255, -1 transparent" % (f, d))
            for d in range(self.directions):
                groups[d].append(sprite.cell(f, d).astype(np.int16))
        return groups

    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        path = self.check_suffix(path)
        h, w = sprite.canvas
        groups = self.groups(sprite)
        encoded = [[encode_frame(cell) for cell in group] for group in groups]
        if self.split:
            files = {path.with_name("%s%d%s" % (path.stem, d + 1, path.suffix)): ([cells], frame_list(data))
                     for d, (cells, data) in enumerate(zip(groups, encoded))}
        elif self.directions == 1:
            files = {path: (groups, frame_list(encoded[0]))}
        else:
            files = {path: (groups, sheet(encoded))}
        for out, (cells, data) in files.items():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            if self.check:
                self.verify(out, cells, w)
        return list(files)

    @staticmethod
    def verify(path: Path, groups: list[list[np.ndarray]], width: int):
        """Reads a written CL2 back and compares it with the cells it was written from."""
        back = split_frames(path.read_bytes())
        if [len(g) for g in back] != [len(g) for g in groups]:
            raise AssertionError("%s reads back as %d groups of %s frames, not as written" % (
                path, len(back), sorted({len(g) for g in back})))
        for d, (raw_group, cells) in enumerate(zip(back, groups)):
            for f, (raw, cell) in enumerate(zip(raw_group, cells)):
                frame = decode_cl2_frame(raw, width)
                pixels = np.array([-1 if p is None else p for p in frame.pixels], np.int16).reshape(frame.height, width)
                if not np.array_equal(pixels, cell):
                    raise AssertionError("%s: frame %d of direction %d doesn't read back as written" % (path, f, d))
                if list(struct.unpack_from("<4H", raw, 2)) != header_rows(raw, width):
                    raise AssertionError("%s: frame %d of direction %d has a header that doesn't point at "
                                         "rows 32, 64, 96 and 128" % (path, f, d))
