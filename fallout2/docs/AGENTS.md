# Fallout 2

Notes for agents working on this game's parsers. This covers Fallout 2: A Post Nuclear Role Playing Game
(Black Isle Studios, 1998), the PC version, patched to 1.02.

Read [fallout_common/docs/AGENTS.md](../../fallout_common/docs/AGENTS.md) first. It has the rules for
both games (game data, licenses, checking claims), the formats Fallout 2 shares with Fallout 1, what
matters for glisomorph, and most references.

## This folder

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: what's specific to Fallout 2                         |
| `docs/filespecs/*.md`  | specs of what differs from Fallout 1                            |
| `*.py`                 | parsers (none yet)                                              |

## Game data

- The data is `master.dat`, `critter.dat`, `patch000.dat` and a `data` folder of loose files. The DATs
  are DAT2: little-endian, with zlib compression. See [archives.md](filespecs/archives.md).
- **One search list for everything.** Unlike Fallout 1, any file can come from any archive. For
  unmodified data the order is `patch000.dat`, `data\`, `critter.dat`, `master.dat`. Note that
  `patch000.dat` wins over loose files.
- Critter sprites are all in `critter.dat`. The official 1.02 patch's `patch000.dat` replaces none;
  mods may.
- **Local game data:** ask the user. Images of the original CDs work well: the DATs sit at the root
  of the ISO 9660 file system, so a reader can open them in place. The 1.02 patch (`f2patch.exe`) is a
  self-extracting zip; `patch000.dat` can be read straight out of it.
- **What was checked:** the docs were checked against the US and UK CDs and the US 1.02 patch. GOG and
  Steam releases weren't checked.

## Ground rules

- **fallout2-ce is the reference**, with fallout2-re as a cross-check closer to the original executable.
  Both use the Sustainable Use License. The commits the specs were written against are in
  [fallout_common](../../fallout_common/docs/AGENTS.md#rules-for-both-games). Cite files as
  `fallout2-ce: src/art.cc`.
  - Development has moved to the community fork
    [fallout2-ce/fallout2-ce](https://github.com/fallout2-ce/fallout2-ce), which adds sfall
    compatibility. Check it when a behavior looks like a CE bug fix or an sfall extension.
  - CE adds things the original game doesn't have, such as reading `f2_res.dat` and accepting FRMs whose
    data size is 0. The specs say when a behavior is CE-only.
- **Differences from Fallout 1 that matter for sprites:**
  - `critters.lst` lines are `name,alias,run`; the third field only tells the combat AI it may make the
    critter run. Whether a critter can run depends on whether its run file exists. A line with no alias
    uses `hmwarr`. See
    [sprite-metadata.md](../../fallout_common/docs/filespecs/sprite-metadata.md#fallout-1-and-2).
  - Fallout 2 adds critters, but no new animation or weapon codes.
  - MAP files are version 20 (Fallout 1's are 19), and critter PROs are 416 bytes (Fallout 1's are 412;
    two of Fallout 2's, Sentry Bot and Weak Brahmin, are 412 too, which the game accepts).
- **Mods** (the Restoration Project, Nevada, Sonora, …) add their own `patchNNN.dat` files or loose
  files, and can replace critter art. glisomorph should read the unmodified data.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| DAT2 | [archives.md](filespecs/archives.md); the format is in [fallout_common](../../fallout_common/docs/filespecs/dat.md#dat2-fallout-2) | the archives, and which one wins | specified, checked on every file |
| FRM, PAL, PRO, MAP, … | [fallout_common](../../fallout_common/docs/AGENTS.md#formats) | everything else, shared with Fallout 1 | see there |

## References

The shared references are in [fallout_common](../../fallout_common/docs/AGENTS.md#references). These
are specific to Fallout 2; links were checked on 2026-10-03.

- [fallout2-ce](https://github.com/alexbatalov/fallout2-ce) (active but quiet) and
  [fallout2-re](https://github.com/alexbatalov/fallout2-re) (dormant): the reference. The community fork
  [fallout2-ce/fallout2-ce](https://github.com/fallout2-ce/fallout2-ce) is active
  ([site](https://fallout2-ce.github.io/)). All Sustainable Use License.
- [sfall](https://github.com/sfall-team/sfall): the engine extension for the original executable, which
  most mods assume. [Docs](https://sfall-team.github.io/sfall/). Active. GPL-3.0.
- **The Restoration Project, updated** ([BGforgeNet/Fallout2_Restoration_Project](https://github.com/BGforgeNet/Fallout2_Restoration_Project))
  and the [Unofficial Patch](https://github.com/BGforgeNet/Fallout2_Unofficial_Patch): mods (scripts,
  maps, some art), not engines. They continue killap's original project ([killap.net](http://killap.net/),
  dormant). Active, no license.
- **Map editors:** the BIS mapper (Interplay's own, with docs translated by TeamX; fodev.net links a
  patched build under [mapping tools](https://fodev.net/files/fo2/tools.html#mapping)), Dims Mapper
  ([source](https://github.com/FalloutTeamX/F2_Mapper_Dims), no license) and
  [Gecko](https://github.com/JanSimek/gecko), a modern editor that reads DAT and FRM (active,
  Apache-2.0, can be ported).
- [fo2dat](https://github.com/adamkewley/fo2dat): a DAT2 extractor and packer in Rust. Archived, no
  license.
- **No official demo** of Fallout 2 could be found.
- **Releases and the children.** The UK CD's `critter.dat` lacks the child critter, `nachld`, except
  its called-shot picture; every other critter file is identical to the US CD's. The community's
  `f2children.zip` restores the missing files as loose files, byte for byte the US ones. The US CD's
  `critter.dat` has the US MD5 on the wiki's
  [critter patches](https://falloutmods.fandom.com/wiki/Fallout_critter_patches) page
  (`9b16e92ac88d168e81126b72e6f9ab3c`). That page's UK entry doesn't describe the UK CD checked here.
- **The digital releases** (GOG, Steam) are patched to 1.02, so they include `patch000.dat`.
  According to GOG's forums they include the child critters. Not checked.
