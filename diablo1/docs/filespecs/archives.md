# Diablo 1's archives

The MPQ format itself is described in [blizzard_common's mpq.md](../../../blizzard_common/docs/filespecs/mpq.md).
This page covers what's specific to Diablo 1 and Hellfire: which archives exist, which one wins, the
MPQ features they use, and where to get file names.

## Archives and precedence

DevilutionX searches the archives in priority order, highest first (`Source/engine/assets.cpp`,
`Source/engine/assets.hpp`). A path found in a higher-priority archive hides the same path in lower ones.

| Archive                          | Contents                                                | Priority |
|----------------------------------|---------------------------------------------------------|---------:|
| mods                             | loaded mods                                             | ≥ 10000  |
| `fonts.mpq`                      | extra fonts (DevilutionX)                               | 9200     |
| `<language code>.mpq`            | translations (DevilutionX)                              | 9100     |
| `devilutionx.mpq`                | DevilutionX's own assets, built from its `assets/` folder | 9000   |
| `hfvoice.mpq`                    | Hellfire voices                                         | 8500     |
| `hfmusic.mpq`                    | Hellfire music                                          | 8200     |
| `hfbarb.mpq`, `hfbard.mpq`       | optional data for Hellfire's hidden Barbarian and Bard classes | 8120, 8110 |
| `hfmonk.mpq`                     | Hellfire's Monk class                                   | 8100     |
| `hellfire.mpq`                   | Hellfire                                                | 8000     |
| `DIABDAT.MPQ` or `spawn.mpq`     | Diablo (retail), or the shareware subset                | 1000     |

For sprites, the archives that matter are `DIABDAT.MPQ`, `hellfire.mpq` and `hfmonk.mpq`.

## File names

Diablo's archives have no `(listfile)`. File names come from the game code, DevilutionX's data tables,
or community listfiles. The listfiles in devilutionx-asset-optimizer name every file in the retail
archives (see [AGENTS.md](../AGENTS.md#listfiles)).

## Checked against the game data

| Archive        | Sector size | Hash entries | Blocks | Block flags                                                                 |
|----------------|------------:|-------------:|-------:|------------------------------------------------------------------------------|
| `DIABDAT.MPQ`  | 4096        | 4096         | 2910   | 1752 IMPLODE+ENCRYPTED, 1148 ENCRYPTED (stored), 10 neither                  |
| `hellfire.mpq` | 4096        | 2048         | 584    | 582 IMPLODE+ENCRYPTED, 2 neither                                             |
| `hfmonk.mpq`   | 4096        | 1024         | 336    | 336 IMPLODE+ENCRYPTED                                                        |

None of them uses COMPRESS, FIX_KEY, SINGLE_UNIT or SECTOR_CRC, and every hash entry has locale 0. A
reader that covers IMPLODE, ENCRYPTED and stored sectors can read everything in them; the Python reader
written from the MPQ spec did.

`spawn.mpq` wasn't checked. The copies DevilutionX and diabloweb link to are repacked: they use zlib
or multi-method compression (COMPRESS) instead of implode, and DevilutionX's copy isn't encrypted. A
reader meant to handle those needs the COMPRESS path as well. The original shareware `spawn.mpq` only
exists inside Blizzard's `diablosw.exe` (see [AGENTS.md](../AGENTS.md#getting-the-game-data)).

## Sources

- DevilutionX: `Source/engine/assets.cpp` and `Source/engine/assets.hpp` (archive priorities),
  `Source/mpq/`.
