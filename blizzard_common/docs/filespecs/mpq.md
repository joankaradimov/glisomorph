# MPQ: Blizzard's archive format

Blizzard shipped the data of Diablo (1996), StarCraft (1998), Diablo II (2000) and Warcraft III
(2002) in MPQ ("Mo'PaQ") archives. This page covers the original layout, **format version 0**, with its
32-byte header; mpqfs and some other tools call it "MPQ v1". Diablo and Diablo II use it. The extended
headers, hi-block tables and HET/BET tables that World of Warcraft and StarCraft II added later are out
of scope.

Which archives each game has, which of the features below it uses, and where its listfiles come from
are in that game's `archives.md`:

- [Diablo 1](../../../diablo1/docs/filespecs/archives.md)
- [Diablo 2](../../../diablo2/docs/filespecs/archives.md)

All integers are little-endian.

## Layout

| Part        | Where                          | Size                      |
|-------------|--------------------------------|---------------------------|
| header      | archive start                  | 32 bytes                  |
| hash table  | `hash_table_offset`            | 16 bytes × `hash_table_count`, encrypted |
| block table | `block_table_offset`           | 16 bytes × `block_table_count`, encrypted |
| file data   | where each block entry points  |                           |

Offsets are relative to the archive start, which may be anywhere on a 512-byte boundary, for example
after an installer's executable stub. To find it, scan 512-byte-aligned offsets for the signature.

### Header

| Offset | Type   | Field                                                     |
|--------|--------|-----------------------------------------------------------|
| 0      | char×4 | signature `MPQ\x1A`                                       |
| 4      | u32    | header size (32)                                          |
| 8      | u32    | archive size                                              |
| 12     | u16    | format version (0)                                        |
| 14     | u16    | sector size shift: sector size = `512 << shift`           |
| 16     | u32    | hash table offset                                         |
| 20     | u32    | block table offset                                        |
| 24     | u32    | hash table entry count (a power of two)                   |
| 28     | u32    | block table entry count                                   |

### Hash table entry

| Offset | Type | Field                                                                  |
|--------|------|------------------------------------------------------------------------|
| 0      | u32  | name hash A (`hash(name, 0x100)`)                                      |
| 4      | u32  | name hash B (`hash(name, 0x200)`)                                      |
| 8      | u16  | locale (0 = neutral)                                                   |
| 10     | u8   | platform (0)                                                           |
| 11     | u8   | flags (0)                                                              |
| 12     | u32  | block index, or `0xFFFFFFFF` for empty, or `0xFFFFFFFE` for deleted    |

### Block table entry

| Offset | Type | Field                                      |
|--------|------|--------------------------------------------|
| 0      | u32  | file data offset                           |
| 4      | u32  | stored (compressed) size                   |
| 8      | u32  | file size                                  |
| 12     | u32  | flags                                      |

| Flag         | Value        | Meaning                                                   |
|--------------|--------------|-----------------------------------------------------------|
| IMPLODE      | `0x00000100` | sectors are PKWARE DCL compressed (Diablo 1)              |
| COMPRESS     | `0x00000200` | multi-method compression; each sector's first byte says which methods (StarCraft onwards) |
| ENCRYPTED    | `0x00010000` | file is encrypted                                         |
| FIX_KEY      | `0x00020000` | encryption key is adjusted by the file's offset and size  |
| SINGLE_UNIT  | `0x01000000` | stored as one unit instead of in sectors                  |
| SECTOR_CRC   | `0x04000000` | the sector offset table has one extra entry, for a table of sector checksums |
| EXISTS       | `0x80000000` | entry is in use                                           |

## Hashing and encryption

Everything uses one 1280-entry table of u32 values (`0x500`):

```python
crypt = [0] * 0x500
seed = 0x00100001
for i in range(0x100):
    for j in range(5):
        seed = (seed * 125 + 3) % 0x2AAAAB
        hi = (seed & 0xFFFF) << 16
        seed = (seed * 125 + 3) % 0x2AAAAB
        crypt[i + 0x100 * j] = hi | (seed & 0xFFFF)
```

**Hashing a name.** Normalize it first: ASCII `a–z` become upper case, `/` becomes `\`, and other
bytes are unchanged. Don't use a locale-aware `upper()`. The hash type picks a quarter of the table:
`0x000` is the hash table index, `0x100` name hash A, `0x200` name hash B, and `0x300` the encryption
key.

```python
def mpq_hash(name: str, hash_type: int) -> int:
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in normalize(name):
        s1 = crypt[hash_type + ch] ^ ((s1 + s2) & 0xFFFFFFFF)
        s2 = (ch + s1 + s2 + (s2 << 5) + 3) & 0xFFFFFFFF
    return s1
```

**Decrypting** a sequence of u32 words with a key:

```python
def decrypt(words: list[int], key: int) -> list[int]:
    seed = 0xEEEEEEEE
    out = []
    for w in words:
        seed = (seed + crypt[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        plain = w ^ ((key + seed) & 0xFFFFFFFF)
        out.append(plain)
        key = ((((~key) << 21) + 0x11111111) & 0xFFFFFFFF) | (key >> 11)
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF
    return out
```

The keys are:

- hash table: `mpq_hash("(hash table)", 0x300)` = `0xC3AF3770`
- block table: `mpq_hash("(block table)", 0x300)` = `0xEC83B3A3`
- a file: `mpq_hash(basename, 0x300)`, where `basename` is the part after the last `\`. With FIX_KEY,
  the key becomes `(key + block_offset) ^ file_size`.

## Finding a file

```python
i = mpq_hash(path, 0x000) % hash_table_count
while hash_table[i].block_index != 0xFFFFFFFF:           # empty ends the probe chain
    e = hash_table[i]
    if e.block_index != 0xFFFFFFFE and (e.hash_a, e.hash_b) == (mpq_hash(path, 0x100), mpq_hash(path, 0x200)):
        return block_table[e.block_index]
    i = (i + 1) % hash_table_count
```

Archives store hashes, not names. Some carry a text file called `(listfile)` naming their contents,
but it can be missing or incomplete, so tools rely on external listfiles. The encryption key is derived
from the file name, so an encrypted file whose name you don't know can't even be decrypted.

## Reading a file

A file is split into sectors of `sector_size` bytes; the last one is shorter.

- **Compressed** (IMPLODE or COMPRESS, not SINGLE_UNIT): the data starts with a sector offset table of
  `sectors + 1` u32 values, relative to the file data offset. SECTOR_CRC adds one more entry. The first
  value equals the table's own size, which makes a good sanity check. If the file is encrypted, the
  table is decrypted with `key − 1`.
- **Stored** (neither flag): sector `i` is simply at `offset + i · sector_size`.
- **SINGLE_UNIT:** the whole file is one sector, with no offset table.
- **Encryption:** sector `i` is decrypted with `key + i`. Only whole u32 words are encrypted; 1–3
  trailing bytes are left as they are.
- **Decompression:** a sector whose stored size equals its expected size is stored raw. Otherwise:
  - IMPLODE: the whole sector is a PKWARE DCL stream.
  - COMPRESS: the sector's first byte is a mask of the methods used, and the stream follows it.

### Methods in the COMPRESS mask

| Bit    | Method                          | Typical use                              |
|--------|---------------------------------|------------------------------------------|
| `0x01` | Huffman (Storm's adaptive Huffman) | WAV audio, together with ADPCM        |
| `0x02` | zlib (deflate)                  | Warcraft III onwards, repacked archives  |
| `0x08` | PKWARE DCL implode              | general data                             |
| `0x10` | bzip2                           | Warcraft III onwards                     |
| `0x20` | sparse                          | StarCraft II                             |
| `0x40` | IMA ADPCM, mono                 | WAV audio                                |
| `0x80` | IMA ADPCM, stereo               | WAV audio                                |

`0x12` isn't a combination of bits: it means LZMA (StarCraft II). When several bits are set, StormLib
(`SCompDecompress`) undoes them in this fixed order: bzip2, PKWARE, zlib, Huffman, ADPCM stereo, ADPCM
mono, sparse. A WAV sector marked `0x41`, for example, is Huffman-decoded first, then ADPCM-decoded.
Sprites never use Huffman or ADPCM, so a reader aimed at graphics can report those as unsupported.

### PKWARE DCL "explode"

This is an LZ77 variant with fixed Shannon–Fano code tables and an LSB-first bit stream. The first two
bytes are the literal mode (0 = raw 8-bit literals, 1 = coded literals) and the dictionary size
(4, 5 or 6, meaning 1, 2 or 4 KiB). A length code of 519 ends the stream. Implementations worth
porting:

- Mark Adler's `blast.c` in zlib's `contrib/blast`, under the zlib license. It's small and easy to
  port to Python.
- `src/mpq_explode.h` in [mpqfs](https://github.com/diasurgical/mpqfs), under the MIT license.
- StormLib's `src/pklib/explode.c`, MIT.

## Checked against the game data

A Python reader written from this page (hash, decrypt, sector table and a `blast.c` port) was run on
the retail archives. The per-game results are in each game's `archives.md`.

- **Diablo 1:** it read every file. That covers IMPLODE, ENCRYPTED and stored sectors.
- **Diablo II:** it read the graphics, palettes and data files of the original discs' archives. That
  covers COMPRESS with PKWARE, and ENCRYPTED with FIX_KEY: each archive's `(listfile)` is stored that
  way.
- **The archive start:** the header search found the MPQs embedded in the Diablo II patch executables.
- **Not exercised:** Huffman and ADPCM (seen only in WAV sectors, mask `0x41`), zlib, bzip2, SINGLE_UNIT
  and SECTOR_CRC.

## Sources

- [mpqfs](https://github.com/diasurgical/mpqfs) (MIT): `src/mpq_archive.h`, `src/mpq_crypto.c`,
  `src/mpq_stream.c`, `src/mpq_explode.h`.
- [StormLib](https://github.com/ladislav-zezula/StormLib) (MIT): `src/SCompression.cpp` (the method
  order), `src/pklib/`, `src/huffman/`, `src/adpcm/`.
- Ladislav Zezula's [MPQ format](http://www.zezula.net/en/mpq/mpqformat.html) and
  [fundamentals](http://www.zezula.net/en/mpq/techinfo.html) pages.
