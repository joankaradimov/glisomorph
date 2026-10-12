"""StarCraft GRP sprites (unit/**/*.grp). See starcraft/docs/filespecs/grp.md.

read() decodes the run-length GRPs, as every sprite on the map is: each frame comes back on the whole canvas,
as palette indices (int16), -1 where transparent. The few uncompressed interface GRPs aren't handled.
Directions aren't the GRP's business: in a turning image, frames come in steps of 17 (grp.md, Directions).
"""

import struct
from dataclasses import dataclass

import numpy as np


@dataclass
class Grp:
    width: int
    height: int
    frames: list[np.ndarray]  # each (height, width) int16, -1 transparent


def read(data: bytes) -> Grp:
    count, width, height = struct.unpack_from("<3H", data)
    frames = []
    for f in range(count):
        x, y, w, h, offset = struct.unpack_from("<4BI", data, 6 + 8 * f)
        if x + w > width or y + h > height:
            raise ValueError("frame %d's box %s reaches outside the %dx%d canvas" % (f, (x, y, w, h), width, height))
        cell = np.full((height, width), -1, np.int16)
        for r in range(h):
            p = offset + struct.unpack_from("<H", data, offset + 2 * r)[0]
            row = []
            while len(row) < w:
                c = data[p]
                p += 1
                if c & 0x80:  # 1nnnnnnn: n transparent pixels
                    row += [-1] * (c & 0x7F)
                elif c & 0x40:  # 01nnnnnn: the next byte, n times
                    row += [data[p]] * (c & 0x3F)
                    p += 1
                else:  # 00nnnnnn: the next n bytes
                    row += list(data[p:p + c])
                    p += c
            if len(row) != w:
                raise ValueError("frame %d, row %d: runs fill %d pixels of a %d-pixel box" % (f, r, len(row), w))
            cell[y + r, x:x + w] = row
        frames.append(cell)
    return Grp(width, height, frames)
