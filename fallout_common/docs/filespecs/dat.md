# DAT: Fallout's archive format

Fallout (1997) and Fallout 2 (1998) keep nearly all their data in `.dat` archives. The two games use
different formats under the same extension:

- **DAT1** (Fallout 1): big-endian, a list of directories, then each directory's files. Files are
  stored raw or compressed with LZSS.
- **DAT2** (Fallout 2): little-endian, one flat file list at the end of the archive. Files are stored
  raw or compressed with zlib.

Neither has a magic number. A reader can tell them apart by trying DAT2's footer first (see
[Telling them apart](#telling-them-apart)).

Which archives each game has, and which one wins, are in that game's `archives.md`:

- [Fallout 1](../../../fallout1/docs/filespecs/archives.md)
- [Fallout 2](../../../fallout2/docs/filespecs/archives.md)

## DAT1 (Fallout 1)

All integers are big-endian.

The game reads the directory as two levels of the same "assoc" structure, a sorted list of names with
an optional fixed-size record after each name (`fallout1-ce: src/plib/assoc/assoc.cc`, `assoc_load`).
The first level lists the directories; the second, one per directory, lists its files.

### Layout

| Part              | Size                                                       |
|-------------------|------------------------------------------------------------|
| directory header  | 16 bytes                                                   |
| directory names   | `directory_count` names                                    |
| file lists        | one per directory, in the same order as the names          |
| file data         | where each file entry points                               |

### Assoc header

Both levels start with the same 16-byte header.

| Offset | Type | Field                                                                     |
|--------|------|---------------------------------------------------------------------------|
| 0      | u32  | number of names (directories, or files in this directory)                 |
| 4      | u32  | capacity the writer allocated; at least the count, otherwise meaningless  |
| 8      | u32  | size of the record after each name: 0 for the directory list, 16 for file lists |
| 12     | u32  | a pointer left over from the writer's memory; meaningless                 |

The game reads the record size from the file and trusts it. The directory list has none, so its names
follow each other directly.

Community docs call the fields at 4, 8 and 12 "unknown", "flags" and "timestamp". The Kaitai spec
(`fallout_dat.ksy`) and the falloutmods wiki say the field at 4 is usually `0x0A`, and `0x5E` in
`master.dat`. That fits a capacity. The code reads the field at 12 and discards it
(`fallout1-ce: src/plib/assoc/assoc.cc`, `assoc_read_assoc_array`, notes that it is the list pointer).

In the shipped archives the directory header's capacity is 94 (`0x5E`) in `master.dat` and 10 in
`critter.dat`, its record size is 0, and every file list's record size is 16. The pointer field holds
arbitrary large values.

The capacity matters in one way: `assoc_load` allocates that many slots and then reads `count` names
into them. A capacity of 0 or less allocates nothing and reads no names, which leaves the rest of the
directory unparsed; a capacity below the count writes past the allocation. The wiki reports that
Fallout crashes when the value is below 1, which fits. A writer should store at least the count.

### Names

A name is one length byte, then that many ASCII bytes, with no terminator. Directory names are full
paths with `\` between parts, e.g. `ART\CRITTERS`. File names are bare, e.g. `HMJMPSAA.FRM`.

Both lists must be sorted, because the game finds names by binary search with a case-insensitive
compare (`assoc_find`). Since the game upper-cases paths before looking them up, the stored case doesn't
matter. The shipped names are all upper case.

**The sort order folds to lower case.** The original's `stricmp` compares lower-cased characters, so
`_` (`0x5F`) sorts before the letters (`0x61` and up): `DI_UP2.FRM` comes before `DIPLOMAT.FRM`. The
shipped lists are in that order. Compared in upper case, `_` would sort after `Z`, and 5 pairs of
neighbours in the US `master.dat` (12 in the European one) are out of order. A binary search has to fold
case the same way, or it misses names.

### File entry

After each file name come 16 bytes:

| Offset | Type | Field                                                            |
|--------|------|------------------------------------------------------------------|
| 0      | u32  | attributes: how the file is stored (below)                       |
| 4      | u32  | offset of the data from the start of the archive                 |
| 8      | u32  | unpacked size                                                    |
| 12     | u32  | packed size                                                      |

| Attributes  | Meaning                                                                     |
|-------------|-----------------------------------------------------------------------------|
| `0x20`      | stored: `unpacked size` raw bytes at `offset`. The packed size is 0 in the shipped archives |
| `0x40`      | LZSS in blocks (below). `packed size` counts the blocks, headers included   |
| `0x10` or 0 | one LZSS stream of `packed size` bytes. The code supports it; the shipped archives never use it |

The shipped archives use only `0x20` and `0x40`.

The game looks only at `attributes & 0xF0`, after turning 0 into `0x10` (`fallout1-ce:
src/plib/db/db.cc`, `db_read_to_buf`, `db_fopen`). Any other value fails to open.

### Blocks (`0x40`)

The data is a sequence of blocks. Each starts with a u16 (big-endian, like everything else):

| Header bit 15 | Block                                                                       |
|---------------|-----------------------------------------------------------------------------|
| set           | stored: the next `header & 0x7FFF` bytes are output as they are              |
| clear         | LZSS: the next `header` bytes are an LZSS stream, decoded on its own        |

Blocks follow each other until `unpacked size` bytes have been produced. Each block decodes into a
16 KiB buffer (`db_preload_buffer`), so no block produces more than `0x4000` bytes. Every LZSS block
starts with a fresh dictionary.

In the shipped archives every block but a file's last produces exactly `0x4000` bytes, the last one
ends exactly at `unpacked size`, and the blocks end exactly at `packed size`. Stored blocks do occur:
6,592 of them, in 725 of Fallout 1's 19,247 compressed files.

The game doesn't stop on a zero header. fodev.net's page says a zero block ends the stream, and the
falloutmods wiki's LZSS walkthrough does the same, but in the code a zero header just makes no progress, and only the output count ends the loop. A reader should
stop on the count, and treat a zero header as an error rather than loop forever.

### LZSS

This is Haruhiko Okumura's classic LZSS (`fallout1-ce: src/plib/db/lzss.cc`):

| Property            | Value                                                            |
|---------------------|------------------------------------------------------------------|
| dictionary          | 4096-byte ring buffer                                            |
| initial contents    | bytes 0–4077 are spaces (`0x20`)                                 |
| initial write index | 4078 (4096 − 18)                                                 |
| flag byte           | one per 8 items, read from bit 0 (LSB) up                        |
| flag bit 1          | literal: one byte, output and written to the dictionary          |
| flag bit 0          | match: two bytes `lo`, `hi`                                      |
| match position      | `lo | (hi & 0xF0) << 4`, an absolute index into the ring buffer  |
| match length        | `(hi & 0x0F) + 3`, so 3–18                                       |
| end                 | when the input runs out; the decoder counts input bytes, not output |

Match bytes are copied one at a time and each is written back to the dictionary as it is copied, so a
match may overlap the bytes it is producing.

The game resets only the first 4078 bytes of the ring buffer. The last 18 keep whatever the previous
file left there (zeros at start-up). A stream from Okumura's encoder never reads them before writing
them, so a reader can fill them with anything.

```python
def lzss_decode(src: bytes) -> bytes:
    ring = bytearray(b" " * 4096)
    r = 4078
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        flags = src[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if flags >> bit & 1:                      # literal
                b = src[i]
                i += 1
                out.append(b)
                ring[r] = b
                r = (r + 1) & 0xFFF
            else:                                     # match
                if i + 1 >= n:
                    break
                lo, hi = src[i], src[i + 1]
                i += 2
                pos = lo | (hi & 0xF0) << 4
                for k in range((hi & 0x0F) + 3):
                    b = ring[(pos + k) & 0xFFF]
                    out.append(b)
                    ring[r] = b
                    r = (r + 1) & 0xFFF
    return bytes(out)


def read_blocks(data: bytes, offset: int, unpacked_size: int) -> bytes:
    out = bytearray()
    pos = offset
    while len(out) < unpacked_size:
        header = int.from_bytes(data[pos:pos + 2], "big")
        pos += 2
        if header == 0:
            raise ValueError("zero block header")
        n = header & 0x7FFF
        chunk = data[pos:pos + n]
        out += chunk if header & 0x8000 else lzss_decode(chunk)
        pos += n
    return bytes(out[:unpacked_size])
```

### Reading the directory

```python
import struct

def read_dat1(data: bytes) -> dict[str, tuple[int, int, int, int]]:
    """Maps 'DIR\\NAME' (upper case) to (attributes, offset, unpacked, packed)."""
    pos = 0

    def u32() -> int:
        nonlocal pos
        (v,) = struct.unpack_from(">I", data, pos)
        pos += 4
        return v

    def name() -> str:
        nonlocal pos
        n = data[pos]
        s = data[pos + 1:pos + 1 + n].decode("ascii")
        pos += 1 + n
        return s

    count, _capacity, record_size, _pointer = u32(), u32(), u32(), u32()
    dirs = []
    for _ in range(count):
        dirs.append(name())
        pos += record_size                            # 0 in practice
    files = {}
    for d in dirs:
        count, _capacity, record_size, _pointer = u32(), u32(), u32(), u32()
        assert record_size == 16
        for _ in range(count):
            f = name()
            key = f if d == "." else d + "\\" + f
            files[key.upper()] = (u32(), u32(), u32(), u32())
    return files
```

### Finding a file

The game upper-cases the path, uses `\` as the separator and drops a leading `.\`
(`db_find_dir_entry`). It splits the path at the last `\`: the part before is looked up in the directory
list, the part after in that directory's files. A path with no `\` goes straight to directory 0, without
a name lookup. Fallout 1's `master.dat` does have a root directory named `.` as its first entry, as
fodev.net's page and the falloutmods wiki say. It holds `COLOR.PAL` and the fonts (`FONT*.AAF`,
`FONT*.FON`); the wiki warns that its one-character name is easy to skip by mistake. `critter.dat` has a
single directory, `ART\CRITTERS`, and no root. Both lookups ignore case.

## DAT2 (Fallout 2)

All integers are little-endian.

### Layout

| Part        | Where                                     | Size                    |
|-------------|-------------------------------------------|-------------------------|
| file data   | from the data base onwards                |                         |
| file count  | `file_size − 8 − tree_size`               | u32                     |
| file list   | right after the count                     | `file_count` entries    |
| footer      | the last 8 bytes                          | 8 bytes                 |

### Footer

| Offset from the end | Type | Field                                                            |
|---------------------|------|------------------------------------------------------------------|
| −8                  | u32  | tree size: the file count plus the file list, in bytes           |
| −4                  | u32  | data size: the archive's size, counted from the data base        |

The data base is `file_size − data_size`. Normally `data_size` equals the file's size and the base is
0. The code allows extra bytes before the archive (`fallout2-ce: src/dfile.cc`, `dbaseOpen`).

### File entry

| Offset | Type   | Field                                                        |
|--------|--------|--------------------------------------------------------------|
| 0      | u32    | name length `n`                                              |
| 4      | char×n | path, e.g. `art\critters\<name>.frm`; no terminator         |
| 4+n    | u8     | compressed: 1 means zlib, anything else means stored         |
| 5+n    | u32    | unpacked size                                                |
| 9+n    | u32    | packed size: the bytes stored in the archive                 |
| 13+n   | u32    | offset of the data, from the data base                       |

Paths are full, with `\` as the separator. The wiki says names follow DOS 8.3; nothing in the reader
enforces it. The list is sorted in ascending order, since the game finds a path by binary
search with a case-insensitive compare (`dfileOpenInternal`). As in DAT1, the order folds to lower
case (`_` before letters). The stored case is mixed: `critter.dat` uses lower case, while `master.dat`
mixes lower, upper and mixed case, even within one name (`art\intrface\eG_VCT02.pal`). A binary search
that folds to upper case misses 77 of the 23,120 paths in `master.dat`. A reader is safer with a
dictionary keyed by the lower-cased path: CE's compare (`SDL_strcasecmp`) and the original's
(`stricmp`) needn't fold case the same way.

**Compression.** Only the byte decides. The game tests `compressed == 1` and calls zlib's `inflateInit`
(`fallout2-ce: src/dfile.cc`), so the data is a zlib stream: a 2-byte header (usually `78 DA` or
`78 9C`), deflate, and an Adler-32 trailer. It isn't raw deflate or gzip. Don't infer compression from
the sizes. A stored file has packed size equal to unpacked size, but a compressed file could too, and
the game never compares them.

Community docs call this byte the "type". If a file has a value other than 0 or 1, the game reads it as
stored.

In the shipped archives the byte is only ever 0 or 1. Every compressed entry starts with `78 DA` and
its zlib stream ends exactly at `packed size`. Stored entries have packed size equal to unpacked size;
they're protos, `.txt` and `.msg` text, ACM sounds and a few others. No compressed entry has the two
sizes equal. `data_size` equals the file size, so the data base is 0.

```python
import struct, zlib

def read_dat2(data: bytes) -> dict[str, tuple[int, int, int, int]]:
    """Maps the lower-cased path to (compressed, unpacked, packed, absolute offset)."""
    tree_size, data_size = struct.unpack_from("<II", data, len(data) - 8)
    base = len(data) - data_size
    pos = len(data) - 8 - tree_size
    (count,) = struct.unpack_from("<I", data, pos)
    pos += 4
    files = {}
    for _ in range(count):
        (n,) = struct.unpack_from("<I", data, pos)
        path = data[pos + 4:pos + 4 + n].decode("ascii")
        compressed, unpacked, packed, offset = struct.unpack_from("<BIII", data, pos + 4 + n)
        pos += 4 + n + 13
        files[path.lower()] = (compressed, unpacked, packed, base + offset)
    return files

def read_file(data: bytes, entry: tuple[int, int, int, int]) -> bytes:
    compressed, unpacked, packed, offset = entry
    raw = data[offset:offset + packed]
    return zlib.decompress(raw) if compressed == 1 else raw
```

### Finding a file

The game passes paths with `\` separators, relative to the game folder (`art\critters\...`), and compares
them case-insensitively with the stored ones. There is no directory level.

## Telling them apart

Try DAT2 first: read the footer, and check that `tree_size + 8 ≤ file_size`, that `data_size ≤
file_size`, and that the file list parses exactly up to the footer. A DAT1 archive fails that: its first
u32, read big-endian, is a small directory count, and its record-size field at offset 8 is 0.

## Text files

Both games' readers drop `\r` before `\n` when a file is opened in text mode (`"rt"`). This doesn't
change the stored data, and binary files such as sprites are opened with `"rb"`.

## Notes on the wiki

The falloutmods wiki's *DAT file format* page (Shadowbird's DAT1 and LZSS notes, MatuX's DAT2
document) agrees with the code on the layouts, with these differences:

- **DAT1 header fields.** It calls the fields at 4, 8 and 12 unknowns. Its observations fit the code:
  the field at 8 is "always 0" in the directory header and "always 0x10" in the file lists, which is
  the record size (0 and 16).
- **Packed size of stored files.** It says the packed size is 0 when attributes are `0x20`. That's
  true of the shipped archives; the code reads `unpacked size` bytes for those and never looks at the
  packed size.
- **Block headers.** Its LZSS walkthrough reads the block header as a signed 16-bit number: negative
  means stored, with the absolute value as the length, and 0 ends the file. The code clears bit 15
  and uses the low 15 bits as the length (`db_preload_buffer`, `db_read_to_buf`). The two agree only
  for a header of `0x8000`; for a stored block of 5 bytes (`0x8005`) the signed reading gives 32,763.
  Follow the code. The "0 ends the file" rule is fodev.net's claim again (see [Blocks](#blocks-0x40)).
- **DAT2 directory address.** It gives the tree's start as `DataSize − TreeSize − 4` and calls
  `TreeSize` the size of the entries. With `data_size` equal to the file size, that formula lands on the
  first entry, after the file count, so it matches the code's `file_size − 8 − tree_size` for the count.
  Its table, which puts the count outside `TreeSize`, doesn't. The code (`dbaseOpen`) counts the
  count's 4 bytes in the tree size.
- **DAT2 sort order.** It says the entries are sorted "in a descendent direction". The game finds them
  with `bsearch` and a case-insensitive compare, which needs ascending order, and the shipped lists
  are ascending.
- **DAT2 compression.** It calls the type byte a boolean (1 compressed, 0 not) and says compressed data
  starts with `78 DA`. That fits the code; the code doesn't check the signature.

## Checked against the game data

Checked on 2026-10-03 against every archive of four CD releases: Fallout 1 US and European (the UK
"GSP White Label" release, by the MD5s on the wiki's *Fallout critter patches* page), Fallout 2 US and
UK, plus the `patch000.dat` inside Fallout 2's official 1.02 patch (`f2patch.exe`). The readers were the
Python above, unchanged.

- **All files decode.** 23,840 files (Fallout 1 US), 25,243 (European), 30,240 (Fallout 2 US), 30,137
  (UK) and 489 (`patch000.dat`). Every one decoded to exactly its unpacked size, with no errors.
- **DAT1:** everything in [Assoc header](#assoc-header), [File entry](#file-entry) and
  [Blocks](#blocks-0x40) above: the record sizes, the capacities, the attribute values, packed size 0
  for stored files, block sizes and ends, no zero block headers, the `.` root. Text files such as
  `critters.lst` decode to readable text.
- **DAT2:** the footer, the tree size including the count (the list parses to exactly the footer),
  the compression byte, the zlib headers and stream ends, and the sizes, as described in
  [File entry](#file-entry-1).
- **Sorting:** all lists, in all archives, are in ascending order with a lower-case fold; see
  [Names](#names) and [File entry](#file-entry-1).
- Not checked: the `0x10` single-stream mode, which no shipped file uses, and modded or digital-store
  releases.

## Sources

- fallout1-ce (commit 0609bcf): `src/plib/db/db.cc` (`db_init_database`, `db_find_dir_entry`,
  `db_read_to_buf`, `db_fopen`, `db_preload_buffer`), `src/plib/db/lzss.cc`, `src/plib/assoc/assoc.cc`.
- fallout1-re (commit ac9784b): `src/plib/db/db.c`, `src/plib/db/lzss.c`; the same logic.
- fallout2-ce (commit e97087b): `src/dfile.cc` (`dbaseOpen`, `dfileOpenInternal`).
- fallout2-re (commit b135fc4): `src/plib/xfile/dfile.c`; the same logic, with `stricmp`.
- [fodev.net's DAT page](https://fodev.net/files/fo2/dat.html): the `.` root directory, the LZSS
  parameters, the zero-block claim.
- [Kaitai Struct's `fallout_dat`](https://formats.kaitai.io/fallout_dat): DAT1 field names and the
  attribute values `0x20` and `0x40`.
- [falloutmods wiki, DAT file format](https://falloutmods.fandom.com/wiki/DAT_file_format), which
  covers both DAT1 and DAT2 (there's no separate DAT2 page), and
  [Master.dat](https://falloutmods.fandom.com/wiki/Master.dat). Read through the MediaWiki API
  (`api.php?action=parse&prop=wikitext`), since plain page fetches return HTTP 402.
