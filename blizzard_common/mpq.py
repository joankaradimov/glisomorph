"""Read-only access to MPQ archives, format version 0 (Diablo, Diablo II).

See blizzard_common/docs/filespecs/mpq.md. Supports IMPLODE and COMPRESS (PKWARE, zlib, bzip2),
encryption with or without FIX_KEY, SINGLE_UNIT and SECTOR_CRC. Huffman and ADPCM, which only
occur in WAV files, raise UnsupportedCompression.
"""

import bz2
import struct
import zlib
from typing import BinaryIO

from .pkware import explode

IMPLODE = 0x00000100
COMPRESS = 0x00000200
ENCRYPTED = 0x00010000
FIX_KEY = 0x00020000
SINGLE_UNIT = 0x01000000
SECTOR_CRC = 0x04000000
EXISTS = 0x80000000

_HASH_EMPTY = 0xFFFFFFFF
_HASH_DELETED = 0xFFFFFFFE
_MASK32 = 0xFFFFFFFF


class UnsupportedCompression(Exception):
    pass


def _crypt_table() -> list[int]:
    table = [0] * 0x500
    seed = 0x00100001
    for i in range(0x100):
        for j in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            high = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            table[i + 0x100 * j] = high | (seed & 0xFFFF)
    return table


_CRYPT = _crypt_table()
# ASCII a-z become upper case and '/' becomes '\'; every other byte stays as it is.
_NORMALIZE = bytes(c - 32 if 0x61 <= c <= 0x7A else 0x5C if c == 0x2F else c for c in range(256))


def hash_name(name: str, hash_type: int) -> int:
    """The Storm string hash; hash_type is 0x000, 0x100, 0x200 or 0x300."""
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for c in name.encode("latin-1").translate(_NORMALIZE):
        s1 = _CRYPT[hash_type + c] ^ ((s1 + s2) & _MASK32)
        s2 = (c + s1 + s2 + (s2 << 5) + 3) & _MASK32
    return s1


def decrypt(words, key: int) -> list[int]:
    seed = 0xEEEEEEEE
    out = []
    for word in words:
        seed = (seed + _CRYPT[0x400 + (key & 0xFF)]) & _MASK32
        plain = word ^ ((key + seed) & _MASK32)
        out.append(plain)
        key = ((((~key) << 21) + 0x11111111) & _MASK32) | (key >> 11)
        seed = (plain + seed + (seed << 5) + 3) & _MASK32
    return out


def _decrypt_bytes(data: bytes, key: int) -> bytes:
    n = len(data) // 4  # trailing bytes aren't encrypted
    words = decrypt(struct.unpack_from("<%dI" % n, data), key)
    return struct.pack("<%dI" % n, *words) + data[4 * n:]


class MpqArchive:
    """An MPQ archive inside a file, found at `offset` or by scanning 512-byte boundaries."""

    def __init__(self, path: str, offset: int | None = None):
        self._file: BinaryIO = open(path, "rb")
        self.offset = self._find_header() if offset is None else offset
        self._file.seek(self.offset)
        header = self._file.read(32)
        (signature, _header_size, _archive_size, self.version, sector_shift, hash_offset, block_offset,
         hash_count, block_count) = struct.unpack("<4sIIHHIIII", header)
        if signature != b"MPQ\x1a":
            raise ValueError("no MPQ header at offset %d" % self.offset)
        self.sector_size = 512 << sector_shift
        self._hashes = self._read_table(hash_offset, hash_count, "(hash table)")
        self._blocks = self._read_table(block_offset, block_count, "(block table)")

    def close(self) -> None:
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _find_header(self) -> int:
        offset = 0
        while True:
            self._file.seek(offset)
            signature = self._file.read(4)
            if len(signature) < 4:
                raise ValueError("no MPQ header found")
            if signature == b"MPQ\x1a":
                return offset
            offset += 512

    def _read_table(self, offset: int, count: int, name: str) -> list[tuple[int, int, int, int]]:
        self._file.seek(self.offset + offset)
        words = struct.unpack("<%dI" % (4 * count), self._file.read(16 * count))
        words = decrypt(words, hash_name(name, 0x300))
        return [tuple(words[4 * i:4 * i + 4]) for i in range(count)]

    def _find_block(self, name: str):
        count = len(self._hashes)
        index = hash_name(name, 0x000) % count
        name_a, name_b = hash_name(name, 0x100), hash_name(name, 0x200)
        for _ in range(count):
            hash_a, hash_b, _locale_platform, block = self._hashes[index]
            if block == _HASH_EMPTY:
                return None
            if block != _HASH_DELETED and hash_a == name_a and hash_b == name_b:
                return self._blocks[block]
            index = (index + 1) % count
        return None

    def __contains__(self, name: str) -> bool:
        return self._find_block(name) is not None

    def read(self, name: str) -> bytes:
        """Returns the file's contents; raises KeyError if it isn't in the archive."""
        block = self._find_block(name)
        if block is None:
            raise KeyError(name)
        offset, stored_size, size, flags = block
        self._file.seek(self.offset + offset)
        raw = self._file.read(stored_size)
        key = 0
        if flags & ENCRYPTED:
            key = hash_name(name.replace("/", "\\").rsplit("\\", 1)[-1], 0x300)
            if flags & FIX_KEY:
                key = ((key + offset) & _MASK32) ^ size
        compressed = bool(flags & (IMPLODE | COMPRESS))
        if flags & SINGLE_UNIT:
            data = _decrypt_bytes(raw, key) if key else raw
            return self._decompress(data, size, flags) if compressed else data
        sectors = (size + self.sector_size - 1) // self.sector_size
        if not compressed:
            chunks = [raw[i * self.sector_size:(i + 1) * self.sector_size] for i in range(sectors)]
            return b"".join(_decrypt_bytes(c, (key + i) & _MASK32) if key else c for i, c in enumerate(chunks))
        entries = sectors + 1 + (1 if flags & SECTOR_CRC else 0)
        table = struct.unpack_from("<%dI" % entries, raw)
        if key:
            table = decrypt(table, (key - 1) & _MASK32)
        out = bytearray()
        for i in range(sectors):
            chunk = raw[table[i]:table[i + 1]]
            if key:
                chunk = _decrypt_bytes(chunk, (key + i) & _MASK32)
            expected = min(self.sector_size, size - i * self.sector_size)
            out += self._decompress(chunk, expected, flags)
        if len(out) != size:
            raise ValueError("%s: decompressed to %d bytes, expected %d" % (name, len(out), size))
        return bytes(out)

    @staticmethod
    def _decompress(chunk: bytes, expected: int, flags: int) -> bytes:
        if len(chunk) == expected:
            return chunk  # stored uncompressed
        if flags & IMPLODE:
            return explode(chunk)
        methods, data = chunk[0], chunk[1:]
        if methods == 0x08:
            return explode(data)
        if methods == 0x02:
            return zlib.decompress(data)
        if methods == 0x10:
            return bz2.decompress(data)
        raise UnsupportedCompression("compression methods 0x%02x" % methods)

    def listfile(self) -> list[str] | None:
        """The archive's own (listfile), if it has one."""
        if "(listfile)" not in self:
            return None
        text = self.read("(listfile)").decode("latin-1")
        return [line.strip() for line in text.replace(";", "\n").splitlines() if line.strip()]
