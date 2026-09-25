"""PKWARE Data Compression Library "explode" (decompression).

This is a Python port of blast.c, altered from the original:

    blast.c -- Copyright (C) 2003, 2012, 2013 Mark Adler

    This software is provided 'as-is', without any express or implied
    warranty.  In no event will the author be held liable for any damages
    arising from the use of this software.

    Permission is granted to anyone to use this software for any purpose,
    including commercial applications, and to alter it and redistribute it
    freely, subject to the following restrictions:

    1. The origin of this software must not be misrepresented; you must not
       claim that you wrote the original software. If you use this software
       in a product, an acknowledgment in the product documentation would be
       appreciated but is not required.
    2. Altered source versions must be plainly marked as such, and must not be
       misrepresented as being the original software.
    3. This notice may not be removed or altered from any source distribution.

    Mark Adler    madler@alumni.caltech.edu

See blizzard_common/docs/filespecs/mpq.md for how MPQ archives use it.
"""

_MAXBITS = 13


class _Huffman:
    """Canonical code from blast.c's compact "repeat count, length" encoding."""

    def __init__(self, rep: list[int]):
        lengths: list[int] = []
        for byte in rep:
            lengths += [byte & 15] * ((byte >> 4) + 1)
        self.count = [0] * (_MAXBITS + 1)
        for length in lengths:
            self.count[length] += 1
        offsets = [0] * (_MAXBITS + 1)
        for length in range(1, _MAXBITS):
            offsets[length + 1] = offsets[length] + self.count[length]
        self.symbol = [0] * len(lengths)
        for symbol, length in enumerate(lengths):
            if length:
                self.symbol[offsets[length]] = symbol
                offsets[length] += 1


_LITERALS = _Huffman([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173])
_LENGTHS = _Huffman([2, 35, 36, 53, 38, 23])
_DISTANCES = _Huffman([2, 20, 53, 230, 247, 151, 248])
_LENGTH_BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
_LENGTH_EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]


class _BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.buffer = 0
        self.count = 0

    def bits(self, need: int) -> int:
        while self.count < need:
            if self.pos >= len(self.data):
                raise ValueError("PKWARE stream ends early")
            self.buffer |= self.data[self.pos] << self.count
            self.pos += 1
            self.count += 8
        value = self.buffer & ((1 << need) - 1)
        self.buffer >>= need
        self.count -= need
        return value

    def decode(self, code: _Huffman) -> int:
        value = first = index = 0
        for length in range(1, _MAXBITS + 1):
            value |= self.bits(1) ^ 1  # codes are stored bit-inverted
            count = code.count[length]
            if value < first + count:
                return code.symbol[index + (value - first)]
            index += count
            first = (first + count) << 1
            value <<= 1
        raise ValueError("invalid PKWARE code")


def explode(data: bytes) -> bytes:
    """Decompresses one PKWARE DCL stream."""
    reader = _BitReader(data)
    coded_literals = reader.bits(8)
    dictionary_bits = reader.bits(8)
    if coded_literals > 1 or not 4 <= dictionary_bits <= 6:
        raise ValueError("invalid PKWARE header")
    out = bytearray()
    while True:
        if reader.bits(1):
            symbol = reader.decode(_LENGTHS)
            length = _LENGTH_BASE[symbol] + reader.bits(_LENGTH_EXTRA[symbol])
            if length == 519:
                return bytes(out)
            extra = 2 if length == 2 else dictionary_bits
            distance = (reader.decode(_DISTANCES) << extra) + reader.bits(extra) + 1
            if distance > len(out):
                raise ValueError("PKWARE distance too far back")
            start = len(out) - distance
            for i in range(length):  # the copy may overlap its own output
                out.append(out[start + i])
        else:
            out.append(reader.decode(_LITERALS) if coded_literals else reader.bits(8))
