"""Diablo 1 sprite files: CEL and CL2. See diablo1/docs/filespecs/cel.md and cl2.md.

Frames decode to a width, a height and one palette index per pixel, top row first, with None for
transparent pixels. The width isn't stored in the files; sprite-metadata.md says where it comes from.
"""

import struct
from dataclasses import dataclass


@dataclass
class Frame:
    width: int
    height: int
    pixels: list[int | None]  # row-major, top row first

    def row(self, y: int) -> list[int | None]:
        return self.pixels[y * self.width:(y + 1) * self.width]


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def split_frames(data: bytes) -> list[list[bytes]]:
    """Splits a frame list or a sheet into groups of raw frames. A list is one group."""
    count = _u32(data, 0)
    if 4 * count + 8 <= len(data) and _u32(data, 4 * count + 4) == len(data):
        starts = [0]
    else:
        starts = [_u32(data, 4 * g) for g in range(count // 4)]
    groups = []
    for start in starts:
        frames = _u32(data, start)
        offsets = struct.unpack_from("<%dI" % (frames + 1), data, start + 4)
        groups.append([data[start + offsets[i]:start + offsets[i + 1]] for i in range(frames)])
    return groups


def _to_frame(stream: list[int | None], width: int) -> Frame:
    if len(stream) % width:
        raise ValueError("frame data doesn't fill whole rows of width %d" % width)
    height = len(stream) // width
    rows = [stream[y * width:(y + 1) * width] for y in range(height)]
    return Frame(width, height, [p for row in reversed(rows) for p in row])  # stored bottom row first


def decode_cl2_frame(frame: bytes, width: int) -> Frame:
    pos = _u16(frame, 0)  # skip the frame header
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
    return _to_frame(stream, width)


def decode_cel_frame(frame: bytes, width: int) -> Frame:
    pos = 10 if len(frame) >= 2 and _u16(frame, 0) == 10 else 0  # optional frame header
    stream: list[int | None] = []
    while pos < len(frame):
        c = frame[pos]
        pos += 1
        if c < 0x80:
            stream += frame[pos:pos + c]
            pos += c
        else:
            stream += [None] * (256 - c)
    return _to_frame(stream, width)


def load_cl2(data: bytes, width: int) -> list[list[Frame]]:
    """All groups (directions) of a CL2 file; a plain list comes back as one group."""
    return [[decode_cl2_frame(f, width) for f in group] for group in split_frames(data)]


def load_cel(data: bytes, width: int) -> list[list[Frame]]:
    return [[decode_cel_frame(f, width) for f in group] for group in split_frames(data)]
