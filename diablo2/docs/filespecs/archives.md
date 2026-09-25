# Diablo II's archives

The MPQ format itself is described in [blizzard_common's mpq.md](../../../blizzard_common/docs/filespecs/mpq.md).
This page covers what's specific to Diablo II and Lord of Destruction.

## Archives

| Archive         | Disc              | Contents                                                        |
|-----------------|-------------------|-----------------------------------------------------------------|
| `d2data.mpq`    | Install           | most game data: monsters, objects, missiles, UI, tiles, tables, palettes |
| `d2char.mpq`    | Play              | the five classic player characters                              |
| `d2sfx.mpq`     | Install           | sound effects                                                   |
| `d2speech.mpq`  | Install           | speech                                                          |
| `d2music.mpq`   | Play              | music                                                           |
| `d2video.mpq`   | Cinematics        | cinematics                                                      |
| `d2exp.mpq`     | Lord of Destruction | the expansion's data, including the Druid and the Assassin    |
| `d2xmusic.mpq`, `d2xtalk.mpq`, `d2xvideo.mpq` | Lord of Destruction | the expansion's music, speech and cinematics |
| `patch_d2.mpq`  | created by patches | patch data                                                     |

When the same path is in several archives, the higher priority wins (D2MOO,
`source/D2Win/src/D2WinArchive.cpp`, patch 1.10f):

| Priority | Archives                                                                  |
|---------:|---------------------------------------------------------------------------|
| 5000     | `patch_d2.mpq`                                                            |
| 3000     | `d2exp.mpq`, `d2xmusic.mpq`, `d2xtalk.mpq`, `d2xvideo.mpq` (Lord of Destruction only) |
| 1000     | `d2data.mpq`, `d2char.mpq`, `d2sfx.mpq`, `d2speech.mpq`, `d2music.mpq`, `d2video.mpq`, and the optional `d2delta.mpq` and `d2kfixup.mpq` |

Paul Siramy's PDF gives the same advice: look in `patch_d2.mpq` first, then `d2exp.mpq`, then
`d2data.mpq`.

Patches ship as executables (`LODPatch_113d.exe`, `LODPatch_114d.exe`) with an MPQ embedded at a
512-byte boundary. Its files have flat names (`armor.txt`, `A5L28.DC6`), and the patcher installs them.

`SETUP.MPQ` (the installer's) and `PLAYD2.MPQ`, also on the discs, aren't game data.

## Features used

All the game archives are format version 0 with 4096-byte sectors. Unlike Diablo 1, they use the
multi-method COMPRESS flag rather than IMPLODE, and graphics aren't encrypted:

| Archive        | Hash entries | Blocks | Block flags                                                            |
|----------------|-------------:|-------:|------------------------------------------------------------------------|
| `d2data.mpq`   | 65536        | 10815  | 10783 COMPRESS, 2 stored, 1 COMPRESS+ENCRYPTED+FIX_KEY                  |
| `d2char.mpq`   | 16384        | 10013  | 10008 COMPRESS, 1 COMPRESS+ENCRYPTED+FIX_KEY                            |
| `d2exp.mpq`    | 65536        | 9888   | 6914 stored, 2354 COMPRESS, 585 COMPRESS+ENCRYPTED+FIX_KEY              |
| `d2sfx.mpq`    | 8192         | 2329   | all COMPRESS+ENCRYPTED+FIX_KEY                                          |
| `d2speech.mpq` | 8192         | 1566   | all COMPRESS+ENCRYPTED+FIX_KEY                                          |

- **Graphics and data** (DCC, DC6, COF, DT1, DS1, `.txt`, `.bin`, `.dat`, `.pl2`, `.d2`) use method
  mask `0x08`, PKWARE DCL, and nothing else.
- **`d2exp.mpq`'s DCC files, all 6,914 of them, are stored uncompressed.**
- **WAV files** are encrypted with FIX_KEY. Their first sector uses PKWARE (mask `0x08`), and the
  audio sectors Huffman plus mono ADPCM (`0x41`).
- **For sprites**, a reader needs PKWARE under the COMPRESS flag, plus stored files. Encryption,
  Huffman and ADPCM only matter for sound.
- **Patches may differ.** One implementer reports that the 1.14d `patch_d2.mpq` installed by Battle.net
  stores some files with the older IMPLODE flag
  ([blacha/diablo2#7](https://github.com/blacha/diablo2/issues/7); not checked here). A reader should
  accept both flags.

## File names

Every game archive has a `(listfile)` that names all of its files; `d2data.mpq`'s has 10,785 names.
`SETUP.MPQ` and `PLAYD2.MPQ` have none. Paul Siramy's PDF says that in the version he used, the
listfile of `d2sfx.mpq` lacked the `.wav` names. The 1.00 disc's has all of them.

The listed paths use mixed case (`data\global\palette\ACT1\Pal.PL2`); the MPQ name hash ignores case.

`patch_d2.mpq` can be incomplete: a 2005 forum thread shows about 50 unnamed entries in the 1.09 and 1.10
ones. Lectem's "Diablo2UberListfile" names about 40,700 paths across betas, versions and patches (see
[AGENTS.md](../AGENTS.md#listfiles)).

## Checked against the game data

Everything in the tables above was read from the original Diablo II (1.00) and Lord of Destruction disc
images. Every name in each archive's listfile was found in its hash table. Sampling files by extension,
all decompressed with the methods listed. The patch executables' embedded archives were opened too.

## Sources

- The game discs.
- D2MOO: `source/D2Win/src/D2WinArchive.cpp` (archive priorities, 1.10f).
- Paul Siramy, *Extracting Diablo II Animations*: archive precedence, `d2sfx.mpq`'s listfile.
- StormLib's source notes that method `0x08` is Diablo II's; Zezula notes that Diablo II's listfiles
  are complete.
