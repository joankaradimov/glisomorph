# Fallout

Notes for agents working on this game's parsers. This covers Fallout: A Post Nuclear Role Playing Game
(Interplay, 1997), the PC version, and its official patches.

Read [fallout_common/docs/AGENTS.md](../../fallout_common/docs/AGENTS.md) first. It has the rules for
both games (game data, licenses, checking claims), the formats Fallout 1 shares with Fallout 2, what
matters for glisomorph, and most references.

## This folder

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: what's specific to Fallout 1                         |
| `docs/filespecs/*.md`  | specs of what differs from Fallout 2                            |
| `*.py`                 | parsers (none yet)                                              |

## Game data

- The data is `master.dat`, `critter.dat` and a `data` folder of loose files that override them. Both
  DATs are DAT1: big-endian, with LZSS compression. There's no `patch000.dat`. See
  [archives.md](filespecs/archives.md).
- **Critter sprites are only in `critter.dat`** (or `data\`). The game keeps two separate databases and
  never looks for critter art in `master.dat`, or for anything else in `critter.dat`.
- The digital releases ship both DATs in full; on the original CD, the smaller installs
  left them on the CD.
- **Local game data:** ask the user. Images of the original CDs work well: the DATs sit at the root
  of the ISO 9660 file system, each one contiguous, so a reader can open them in place.
- **What was checked:** the docs were checked against the US CD, the European CD (the UK "GSP White
  Label" release) and patch 1.1. GOG and Steam releases weren't checked.

## Ground rules

- **fallout1-ce is the reference**, with fallout1-re as a cross-check closer to the original executable.
  Both use the Sustainable Use License. The commits the specs were written against are in
  [fallout_common](../../fallout_common/docs/AGENTS.md#rules-for-both-games). Cite files as
  `fallout1-ce: src/game/art.cc`; Fallout 1's sources keep the game code under `src/game/` and the
  library under `src/plib/`, unlike fallout2-ce's flat `src/`.
- **Differences from Fallout 2 that matter for sprites:**
  - `critters.lst` lines are `name,alias`, without Fallout 2's third field (the run flag). A line with no
    alias uses list entry 0 as its alias; Fallout 2 uses `hmwarr`. See
    [sprite-metadata.md](../../fallout_common/docs/filespecs/sprite-metadata.md#fallout-1-and-2).
  - MAP files are version 19 (Fallout 2's are 20), and critter PROs are 412 bytes (Fallout 2's are 416).
  - The FRM, PAL and color-cycling formats, the animation and weapon codes, and the geometry are the
    same.
- **European releases.** The European CD's `critter.dat` lacks the child critter, `nachld`, apart from
  the files other critters borrow through aliases. Every other critter file is identical to the US
  CD's, gore included. Its `master.dat` adds French and Spanish interface art, which only the European
  executable reads (see [archives.md](filespecs/archives.md)).
  - The European CD matches the "UK (GSP White Label)" MD5s on the wiki's
    [critter patches](https://falloutmods.fandom.com/wiki/Fallout_critter_patches) page. The US CD
    checked here matches neither of that page's US hashes, so more than one US build exists.
  - According to GOG's forums the digital Fallout 1 is the European build; that wasn't checked.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| DAT1 | [archives.md](filespecs/archives.md); the format is in [fallout_common](../../fallout_common/docs/filespecs/dat.md#dat1-fallout-1) | the archives, and which one a file comes from | specified, checked on every file |
| FRM, PAL, PRO, MAP, … | [fallout_common](../../fallout_common/docs/AGENTS.md#formats) | everything else, shared with Fallout 2 | see there |

## References

The shared references are in [fallout_common](../../fallout_common/docs/AGENTS.md#references). These
are specific to Fallout 1; links were checked on 2026-10-03.

- [fallout1-ce](https://github.com/alexbatalov/fallout1-ce) (active but quiet) and
  [fallout1-re](https://github.com/alexbatalov/fallout1-re) (dormant): the reference. Sustainable Use
  License. Unlike Fallout 2, there's no community fork that took over.
- **Engine extensions**, for the original executables: sfall1, Crafty's Fallout 1 counterpart of sfall
  (copies such as [Ytfarc/sfall1](https://github.com/Ytfarc/sfall1), GPL-2.0, dormant), and
  [F1DP](https://github.com/Edw590/F1DP), for the DOS executable (GPL-3.0, active).
- [Fallout Et Tu](https://github.com/rotators/Fo1in2) (Fo1in2): Fallout 1 rebuilt as a Fallout 2 mod,
  using the player's own Fallout 1 data. Active, no license.
- [F1Undat-UI](https://github.com/FalloutTeamX/F1Undat-UI): a Fallout 1 DAT unpacker. Archived, no
  license. Falltergeist's MIT [dat-unpacker](https://github.com/falltergeist/dat-unpacker) is the one to
  port from for DAT1 and its LZSS.
- **The 1997 demo** is on the Internet Archive as [FalloutDemo](https://archive.org/details/FalloutDemo)
  (`falldemo.zip`, 20 MB). It has one `FALLDEMO.DAT`, a DAT1 archive, instead of `master.dat` and
  `critter.dat`. Read on 2026-10-03: 4,354 files, including 303 critter files for 9 base names (the
  player's looks, `mabrom`, `maddog`, `nmlosr`). It was built from a beta: of its critter FRMs, 189
  are identical to the US release, 43 differ and 70 aren't in the release at all. It carries no
  permission to redistribute, so don't commit it.
