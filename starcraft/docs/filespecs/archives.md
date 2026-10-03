# StarCraft's archives

The MPQ format itself is described in [blizzard_common's mpq.md](../../../blizzard_common/docs/filespecs/mpq.md).
This page covers what's specific to StarCraft and Brood War before Remastered. Remastered keeps its
data in CASC instead; see [AGENTS.md](../AGENTS.md#remastered).

## Archives

| Archive | Contents |
|---------|----------|
| `StarDat.mpq` | StarCraft's data: sprites, tilesets, tables, scripts, sounds |
| `BrooDat.mpq` | Brood War's data, which overrides and extends StarDat's |
| `patch_rt.mpq` | the patch's game data (`rt` = runtime) |
| `patch_ed.mpq` | the patch's editor data, for StarEdit |
| `Starcraft.mpq`, `BroodWar.mpq` | the CDs' archives: music and cinematics, and in `Starcraft.mpq` the campaigns. The MPQ starts partway into each file (at 259,584 and 294,912 bytes), and its files use the older IMPLODE flag |

A path is looked up in `patch_rt.mpq` first, then `BrooDat.mpq`, then `StarDat.mpq`. Of the files
this project cares about, the patch replaces `iscript.bin` (Brood War's but for 6 bytes no script
reaches), `units.dat`, `flingy.dat`, `weapons.dat`, `stat_txt.tbl` and seven of the GRPs
`images.dat` names.

## Features used

All three data archives are format version 0 with 4,096-byte sectors:

| Archive | Hash entries | Blocks | Flags of the files |
|---------|-------------:|-------:|--------------------|
| `StarDat.mpq` | 4,096 | 2,925 | 2,412 COMPRESS + ENCRYPTED + FIX_KEY; 478 stored (all SMK videos); 28 COMPRESS + SECTOR_CRC; 7 ENCRYPTED + FIX_KEY, stored |
| `BrooDat.mpq` | 4,096 | 931 | 805 COMPRESS + ENCRYPTED + FIX_KEY; 117 stored (SMK videos); 7 ENCRYPTED + FIX_KEY, stored (`.tbl`); 2 COMPRESS + SECTOR_CRC |
| `patch_rt.mpq` | 16,384 | 181 | 180 COMPRESS, not encrypted |

- **Unlike Diablo II, the data is encrypted**, with FIX_KEY. The key comes from the file's name, so
  `mpq.py` needs the name to read a file.
- **Graphics and data** are compressed with PKWARE DCL (method byte `0x08`), under the COMPRESS
  flag.
- **Sound** (`.wav`) uses Huffman plus IMA ADPCM, mono (`0x41`) or stereo (`0x81`).
- **Videos** (`.smk`) are stored.

The repository's `blizzard_common/mpq.py` reads everything but the sound.

## File names

Each archive has a `(listfile)`, but they're far from complete:

| Archive | Names in its listfile | Files |
|---------|----------------------:|------:|
| `StarDat.mpq` | 27 | 2,925 blocks |
| `BrooDat.mpq` | 903 | 931 blocks |
| `patch_rt.mpq` | 60 | 181 blocks |

The game's own string tables name most of what matters: `arr/images.tbl` names every GRP and LO*
file under `unit/`, and recovers 720 names in `StarDat.mpq` that its listfile lacks.
`arr/sfxdata.tbl` names the sounds under `sound/` and `arr/portdata.tbl` the portraits. For the
rest, use a community listfile (see [AGENTS.md](../AGENTS.md#listfiles)).

## Checked against the game data

Read with `blizzard_common/mpq.py` from the classic MPQs of an install, dated 2017:

- The headers, tables and flag counts above, and the CD archives' offsets and flags.
- The method byte: of the 215 compressed, multi-sector files `BrooDat.mpq`'s listfile names, sound
  aside, 211 start with a `0x08` sector and 4 with a stored one.
- Every file the listfiles or `images.tbl` name in the three data archives, except sound, decompresses
  to its stated size. 204 of the 206 `.wav` files in `BrooDat.mpq` stop at Huffman and ADPCM, with the
  method bytes above.
- Which archive wins was taken from the sources, not tested in the game.

## Sources

- [Ladislav Zezula's MPQ pages](http://www.zezula.net/en/mpq/mpqformat.html) for the compression
  methods.
- [staredit.net's "Modding Files Overview"](https://wiki.staredit.net/wiki/Modding_Files_Overview)
  for the archive order.
- StormLib's `SCompression.cpp`: StarCraft uses PKWARE DCL with a variable dictionary size, unlike
  Diablo 1's fixed one.
