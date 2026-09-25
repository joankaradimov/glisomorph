# Diablo II / Lord of Destruction

Notes for agents working on this game's parsers. This covers Diablo II (Blizzard North, 2000) and its
expansion Lord of Destruction (2001), the classic PC versions, patches 1.00 to 1.14d. Diablo II:
Resurrected (2021) keeps its data in CASC storage with new formats, and is out of scope.

Read [blizzard_common/docs/AGENTS.md](../../blizzard_common/docs/AGENTS.md) first. It has the rules
for every game (game data, licenses, checking claims) and the MPQ references.

## This folder

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: ground rules, what matters for glisomorph, and references |
| `docs/filespecs/*.md`  | one spec per format: layout, decoding and what was checked against the real data |
| `*.py`                 | parsers (none yet)                                              |

## Game data

- The data is in MPQ archives. Sprites are in `d2data.mpq`, `d2char.mpq` and `d2exp.mpq`, plus
  `patch_d2.mpq` once patched. See [archives.md](filespecs/archives.md).
- **Disc images:** ask the user where their copy of the game is. Images of the original discs
  (Install, Play, Cinematics and Lord of Destruction) work well.
  - They're plain ISO 9660, so each MPQ is one contiguous extent. An MPQ reader can open it at its offset
    inside the image; there's no need to mount or extract anything.
  - Patch executables (`LODPatch_113d.exe`, …) embed their own MPQ.
- **What was checked:** the checks in these docs used the original discs, which carry the 1.00 data.
  Patch 1.10 changed the data tables considerably, but not the graphics formats.

## Ground rules

- **There's no DevilutionX for Diablo II.** No single reimplementation is authoritative:
  - D2MOO reimplements the game's logic DLLs faithfully, but not the graphics side;
  - the open-source engines decode the formats, but were written from community specs.
  Check claims against the game files; every spec says what was checked.
- **Licenses specific to Diablo II:**
  - **Can be ported, with attribution:**
    - D2MOO, Diablerie, AbyssEngine and d2animdata: MIT. D2MOO's README also asks for non-commercial
      use.
    - Riiablo: Apache-2.0; keep its NOTICE.
  - **Reference only:**
    - OpenDiablo2 (and its HellSpawner), Worldstone, OpenD2 and SixDice: GPL.
    - Paul Siramy's tool sources, the OpenDiablo2 split packages and CE_Database: no license.
    - Bilian Belchev's DCC document: personal, non-commercial use.

    Write independent implementations from the specs here.
  - **Never copy test fixtures from other projects.** Worldstone and libd2 include real Blizzard files.
- **Versions:** file formats didn't change between patches, but tables and their columns did, a lot, in
  1.10. Say which version a table fact comes from.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| MPQ | [archives.md](filespecs/archives.md); the format is in [blizzard_common](../../blizzard_common/docs/filespecs/mpq.md) | the archives | specified, checked |
| DCC | [dcc.md](filespecs/dcc.md) | compressed animated sprites: units, missiles, overlays | specified, checked on every file |
| DC6 | [dc6.md](filespecs/dc6.md) | uncompressed sprites: UI, inventory, a few animations | specified, checked |
| COF | [cof.md](filespecs/cof.md) | how layers stack into an animation | specified, checked |
| AnimData.d2 | [animdata.md](filespecs/animdata.md) | frame counts, speeds, frame events | specified, checked |
| PAL, PL2, color maps | [palettes.md](filespecs/palettes.md) | palettes and 256-entry lookup tables | specified, checked |
| sprite metadata | [sprite-metadata.md](filespecs/sprite-metadata.md) | tokens, layers, modes, weapon classes, color variants, speed | specified from the PDF and D2MOO |
| DT1, DS1 | — | floor and wall tiles, map presets | not yet |
| `.txt` / `.bin` tables | — | the game's data tables | not yet; see sprite-metadata.md for the columns that matter |

## What matters for glisomorph

- **Units are layered.** A character is up to 16 layers, each its own sprite file. The order they're
  stacked in changes per direction and frame (see [cof.md](filespecs/cof.md)). Interpolate each layer
  on its own, then compose; don't blend composites.
- **Palette indices again.** Interpolated pixels have to go back to palette indices. Color maps
  recolor layers by index, so keep synthesized pixels in the same color ramps as their sources, or tints
  and variants will break (see [palettes.md](filespecs/palettes.md)).
- **Shadows and blending are the renderer's job.** Unlike Diablo 1, sprites have no baked shadows: the
  game projects them from the layers. Translucent and additive layers are marked in the COF, so their
  pixels shouldn't be blended as if opaque.
- **Time:** animations advance by `speed / 256` frames per 40 ms game tick, in 8.8 fixed point, so most
  animations already spend several ticks on each frame. That makes room for in-betweens (see
  [animdata.md](filespecs/animdata.md)).
- **Directions:** units face one of 64 internal directions, 5.625° apart, drawn with the nearest of the
  sprite's 1, 4, 8, 16 or 32 directions. How the files order their directions is in
  [dcc.md](filespecs/dcc.md#directions). Counts in the 1.00 data:

  | Unit      | Directions                                        |
  |-----------|---------------------------------------------------|
  | players   | 16 in every mode (848 COFs; only 2 have 8)        |
  | monsters  | mostly 8 (954 COFs); 1 (299), 16 (28), 4 (13)    |
  | objects   | 1 (1,460 COFs; one has 4)                         |
  | missiles  | 1 (211 DCCs), 4 (34), 8 (54), 16 (43), 32 (49)    |

  Players' 16 directions, and the 32-direction missiles, make natural ground truth for direction
  interpolation: drop every other direction, synthesize it, and compare.

## References

Links were checked on 2026-09-25. **Active** means changed in 2025–26, **dormant** means online but
older, and **archived** means frozen.

### Required reading

- Paul Siramy, [*Extracting Diablo II Animations*](https://paul-siramy.pages-perso.free.fr/_divers2/Extracting%20Diablo%20II%20Animations.pdf)
  (PDF, 54 pages, written for patches 1.09d and 1.10).
  - What it covers: how the game composes animations: layers, COFs, weapon classes, armor components,
    item and monster color maps, animation speed, blend modes, shadows and object modes, worked through
    a Barbarian, a Fallen, the Countess and a teleport pad.
  - What it doesn't: the DCC bitstream. For that it points to Bilian Belchev's DCC document.
  - Most of [sprite-metadata.md](filespecs/sprite-metadata.md) comes from it.
- [D2MOO](https://github.com/ThePhrozenKeep/D2MOO): The Phrozen Keep's reimplementation of the game DLLs
  for patch 1.10f, from decompilation. MIT. Active.
  - Authoritative on: AnimData.d2, animation timing, `pal.pl2`, the COF header and naming, weapon-class
    rules, and the 64 internal directions.
  - Missing: DCC/DC6 decoding, and the mapping from game direction to file direction.
  - Its D2Win composite code is commented-out decompilation, so treat it as a hint.
- [CE_Database](https://github.com/ThePhrozenKeep/CE_Database): export ordinals, names and prototypes
  of the 1.10f DLLs, plus IDA scripts. There are no structure definitions.
  - Useful for finding functions. `D2CMP.dll`'s direction converters are listed there, such as
    `CelGameDirToFileDir` (#10018) and `CelConvertDir` (#10019).
  - No license. Dormant since 2023.

### Format documentation

- **Paul Siramy's site**, [paul-siramy.pages-perso.free.fr](https://paul-siramy.pages-perso.free.fr/).
  Static; the newest material is from 2014. The menus are French, the documents English. The directory
  listings [`/_divers/`](https://paul-siramy.pages-perso.free.fr/_divers/) and
  [`/_divers2/`](https://paul-siramy.pages-perso.free.fr/_divers2/) are the easiest way in.
  - [`dcc_doc.zip`](https://paul-siramy.pages-perso.free.fr/_divers/dcc_doc.zip) holds **Bilian
    Belchev's "The Dcc File Format Description"** (2002), the canonical DCC spec, with Paul's notes and a
    small C decoder. Personal, non-commercial use only.
  - [DT1 format](https://paul-siramy.pages-perso.free.fr/_divers/dt1_doc/): floor and wall tiles.
    Detailed, but a 2018 Phrozen Keep article says parts are missing or wrong.
  - ["New monster color variations from scratch"](https://paul-siramy.pages-perso.free.fr/_divers2/tmptutcmap/):
    colormap theory, and every colormap file with its size.
  - Old d2mods.com links on the site are gone; use d2mods.info.
- **The Phrozen Keep**:
  - its [knowledge base](https://d2mods.info/forum/kb/index);
  - the File Guides: the column-by-column reference for the data tables, per version. For 1.10–1.14,
    see [`?c=4`](https://d2mods.info/forum/kb/index?c=4);
  - "[Colormaps Explained](https://d2mods.info/forum/kb/viewarticle?a=423)";
  - Paul Siramy's [index thread](https://d2mods.info/forum/viewtopic.php?t=724) on the COF, D2, DC6,
    DS1, DT1 and TBL formats.
- **Code that works as a spec:**
  - [Riiablo `codec/`](https://github.com/collinsmith/riiablo/tree/master/core/src/main/java/com/riiablo/codec):
    DCC, DC6, COF, PL2 and palettes. Apache-2.0.
  - [Diablerie `D2Formats/`](https://github.com/mofr/Diablerie/tree/master/Assets/Scripts/Diablerie/Engine/IO/D2Formats):
    DCC, DC6, COF, AnimData, DT1, DS1 and palettes. MIT.
  - [Worldstone](https://github.com/Lectem/Worldstone): DCC, DC6, COF and PL2. GPL-3.0.
- **Compiled `.bin` tables** have no written spec. D2MOO's data-table structures describe 1.10f.

### Engines and reimplementations

- [OpenDiablo2](https://github.com/OpenDiablo2/OpenDiablo2): a Go engine with decoders for every
  format. GPL-3.0; archived in 2021.
- [Riiablo](https://github.com/collinsmith/riiablo): a Java/LibGDX remake, not playable yet. Apache-2.0;
  dormant.
- [OpenD2](https://github.com/eezstreet/OpenD2): a C rewrite whose DCC decoder is a port of Siramy's.
  GPL-3.0; dormant.
- [Diablerie](https://github.com/mofr/Diablerie): a Unity recreation. MIT; dormant.
- [AbyssEngine](https://github.com/AbyssEngine/AbyssEngine): a clean-room engine, OpenDiablo2's
  successor. MIT; dormant.
- [D2DX](https://github.com/bolrog/d2dx): a graphics wrapper whose "motion prediction" smooths unit
  positions between the game's 25 ticks a second. It never blends sprite frames or directions, so it's
  the closest prior art to glisomorph, not a replacement. GPL-3.0; dormant.

### Tools

- **DR Tester** (Sloan Roy): the COF, DCC and DC6 viewer the PDF uses, with palettes and palette
  shifts. Closed source; [v0.22](https://paul-siramy.pages-perso.free.fr/_divers/DRTest_11_16_08.zip).
- **Paul Siramy's tools**, freeware with C sources and no license. All are under
  [`/_divers/`](https://paul-siramy.pages-perso.free.fr/_divers/):
  - `merge_dcc.zip`: flattens COF animations into frames;
  - `dccinfo.zip`: dumps DCC headers;
  - `dc6con.zip`: DC6 to PCX and back;
  - `animdata_edit_v2_1.zip`: AnimData.d2 to text and back;
  - `cofinfo.zip`;
  - and the DS1 editor, continued as [d2-ds1-edit](https://github.com/bethington/d2-ds1-edit), which
    is active.
- [SixDice](https://bahj.com/sixdice/): a DCC/DC6 converter. Its source was released in 2021 under
  GPL-3.0 as [rjnienaber/SixDice](https://github.com/rjnienaber/SixDice), with a warning about codec bugs.
- [HellSpawner](https://github.com/OpenDiablo2/HellSpawner): OpenDiablo2's editor for DC6, DCC, COF,
  DT1, DS1, palettes, PL2 and AnimData. GPL-3.0; dormant.
- **Python:** there's no maintained DCC or COF decoder.
  - [d2animdata](https://github.com/pastelmind/d2animdata) converts AnimData.d2 to and from JSON. MIT;
    archived.
  - [`mpq`](https://pypi.org/project/mpq/) binds StormLib and reads Diablo II's archives.

### Listfiles

- Every game MPQ has a complete `(listfile)`. `patch_d2.mpq` may not (see
  [archives.md](filespecs/archives.md#file-names)).
- Lectem's [Diablo2UberListfile](https://d2mods.info/forum/download/file.php?id=1306) has about 40,700
  paths, covering betas, shareware, 1.00–1.14d and installers.
  ([thread](https://d2mods.info/forum/viewtopic.php?t=65218))

### Communities

- **[The Phrozen Keep](https://d2mods.info/):** the hub of classic Diablo II modding, active in 2026.
  - [forums](https://d2mods.info/forum/): Tools, Multimedia, Code Editing;
  - [Discord](https://discord.gg/NvfftHY), where D2MOO is developed.
- **Big mods:**
  - [Project Diablo 2](https://www.projectdiablo2.com/) ([Discord](https://discord.gg/projectdiablo2));
  - [Path of Diablo](https://pathofdiablo.com/);
  - Median XL, whose site's 2025–26 activity couldn't be checked.
- **[Mod DB](https://www.moddb.com/games/diablo-2-lod):** about 120 LoD mods, many updated in 2026.
- **[The Arreat Summit](https://classic.battle.net/diablo2exp/):** Blizzard's own game-data reference.

### Getting the game data

- **Buying it:** Blizzard still sells [Diablo II](https://us.shop.battle.net/en-us/product/diablo-ii) and
  [Lord of Destruction](https://us.shop.battle.net/en-us/product/diablo-ii-lord-of-destruction) as
  classic games.
- **Installing it:** Blizzard's [install guide](https://us.support.blizzard.com/en/help/article/13867)
  covers existing CD keys.
- **Patching it:** the installers put down 1.14b, and Battle.net patches to 1.14d. The 1.14d patches are
  on Blizzard's FTP.
- **Diablo II: Resurrected** doesn't include the classic game or its MPQs. Its data is in CASC, with
  `.sprite` textures (`SpA1`) instead of DCC, so it's out of scope.
