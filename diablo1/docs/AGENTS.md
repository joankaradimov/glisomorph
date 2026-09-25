# Diablo 1 / Hellfire

Notes for agents working on this game's parsers. This covers Diablo (Blizzard North, 1996) and its
expansion Hellfire (Synergistic, 1997), PC versions. The PlayStation and Mac versions store data
differently and are out of scope.

Read [blizzard_common/docs/AGENTS.md](../../blizzard_common/docs/AGENTS.md) first. It has the rules
for every game (game data, licenses, checking claims) and the MPQ references.

## This folder

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: ground rules, what matters for glisomorph, and references |
| `docs/filespecs/*.md`  | one spec per format: layout, decoding and what was checked against the real data |
| `*.py`                 | parsers (none yet)                                              |

## Game data

- Diablo's data is `DIABDAT.MPQ`. Hellfire adds `hellfire.mpq`, `hfmonk.mpq`, `hfmusic.mpq` and
  `hfvoice.mpq`. Only `DIABDAT.MPQ`, `hellfire.mpq` and `hfmonk.mpq` contain sprites. See
  [archives.md](filespecs/archives.md).
- Local convention: a sibling folder `../DevilutionX-data/` (relative to the repository root) holds the
  MPQs, and `../DevilutionX/` is a DevilutionX checkout.

## Ground rules

- **DevilutionX is the reference** for how the game reads its data. When a third-party document
  disagrees with DevilutionX's code, the code wins. Cite files as `Source/...` paths relative to the
  DevilutionX repository. These docs were written against commit `6f26339f4` (2026-09-23); files may
  have moved since.
- **Licenses specific to Diablo 1:**
  - DevilutionX and the Diablo 1 Graphics Tool use the Sustainable Use License. It isn't open source
    and isn't compatible with MIT. Read their code to understand a format, then write an independent
    implementation.
  - clx-conversion-tools, d1-file-formats and sanctuary/formats are Unlicense or public domain, so
    they can be ported.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| MPQ | [archives.md](filespecs/archives.md); the format is in [blizzard_common](../../blizzard_common/docs/filespecs/mpq.md) | archives that hold all the data | specified, checked |
| CL2 | [cl2.md](filespecs/cl2.md) | animated directional sprites (monsters, players, missiles) | specified, checked |
| CEL | [cel.md](filespecs/cel.md) | other sprites, UI, and dungeon tiles | sprites specified and checked; tiles outlined |
| CLX | [clx.md](filespecs/clx.md) | DevilutionX's runtime and asset sprite format | specified |
| PAL | [pal.md](filespecs/pal.md) | 256-color palettes | specified, checked |
| TRN | [trn.md](filespecs/trn.md) | palette index remaps (recolors) | specified |
| sprite metadata | [sprite-metadata.md](filespecs/sprite-metadata.md) | widths, directions and animations that the sprite files don't store | specified |
| MIN, TIL, DUN, SOL, AMP | — | level geometry and tile tables | not yet |
| PCX | — | standard ZSoft PCX, used by the original UI | not yet |
| WAV, SMK | — | sound and video | out of scope |

## What matters for glisomorph

- **Sprites are palette indices**, not RGB, and transparency comes only from run-length skip runs.
  - Interpolation happens in RGB, so the results have to go back into the palette's shared sprite range
    (128–254), ramp by ramp. See [pal.md](filespecs/pal.md#notes-for-glisomorph).
  - Index 0 (black) is mostly shadow, drawn as opaque pixels baked into the frames. That's how
    DevilutionX describes it. Treat shadows as a separate layer, or blending will smear them into the
    body.
- **Frame widths aren't in the files.** They come from the game's tables, collected in
  [sprite-metadata.md](filespecs/sprite-metadata.md). Heights vary from frame to frame and fall out of
  decoding.
- **Anchoring:** a frame is drawn from its bottom-left corner, shifted left by `(width − 64) / 2`. The
  actor's tile center is therefore at `x = width / 2`, 16 px above the bottom row. Align frames on that
  point when comparing or blending them, including frames from animations of different widths.
- **Directions:** players and monsters have 8, one group per direction, in the order S, SW, W, NW, N,
  NE, E, SE. They're 45° apart on the ground, even though the 2:1 projection makes the on-screen angles
  unequal. Interpolate across directions in ground-plane angle, not screen angle.
- **Ground truth for direction interpolation:** a handful of missiles (Fireball, the fire and lightning
  arrows, Holy Bolt, acid, and 5 Hellfire ones) come in 16 directions. Drop every other one, synthesize
  it, and compare.
  - A few monster and player sheets repeat direction groups, and some have other known art flaws. Leave
    them out of any ground truth; they're listed in
    [sprite-metadata.md](filespecs/sprite-metadata.md#direction-groups-that-repeat).
- **Ground truth for time interpolation:** animations run at 20 ticks per second. Each frame lasts a
  whole number of ticks, its delay. Slow animations, such as a Zombie standing at 4 ticks per frame,
  leave room for in-between frames. Real in-betweens to compare against don't exist. The nearest thing
  is to drop every other frame of a smooth animation and synthesize it back.

## References

Links were checked on 2026-09-25. **Active** means changed in 2025–26, **dormant** means online but
older, and **archived** means frozen or only on the Wayback Machine.

### Source code

- [DevilutionX](https://github.com/diasurgical/DevilutionX): the port of Diablo and Hellfire, and the
  reference for every format here, including CLX. Active. Sustainable Use License.
- [devilution](https://github.com/diasurgical/devilution): the decompilation DevilutionX grew from,
  Hellfire included. Dormant.
- [pionere/devilutionX](https://github.com/pionere/devilutionX): an active hard fork with its own
  releases.
- [freeablo](https://github.com/wheybags/freeablo) (archived), [diabloweb](https://github.com/d07RiV/diabloweb)
  (a WebAssembly build of devilution, dormant) and [DGEngine](https://github.com/dgcor/DGEngine) (a
  data-driven engine rewrite, low activity): independent implementations, handy for cross-checking.

### Format documentation

- [savagesteel/d1-file-formats](https://github.com/savagesteel/d1-file-formats): the best written specs.
  It covers PAL, TRN, CEL (including level tiles and multi-group files), CL2, MIN, TIL, DUN and the PSX
  formats. Its MPQ page is empty, and SOL and AMP are unfinished. Dormant. Unlicense. DevilutionX's
  code links to its CL2 page.
- The DevilutionX source is the only spec for CLX (`Source/engine/clx_sprite.hpp`), SOL
  (`Source/levels/dun_tile_data.cpp`) and AMP (`Source/automap.cpp`). Its
  [`assets/txtdata`](https://github.com/diasurgical/DevilutionX/tree/master/assets/txtdata) holds the
  sprite tables.
- sanctuary/formats: Go decoders for CEL, CL2, PAL, TRN, MIN, TIL and DUN, public domain. The GitHub
  repository is gone, but a 2020 snapshot is still on the
  [Go module proxy](https://proxy.golang.org/github.com/sanctuary/formats/@v/v0.0.0-20200419174750-c646ccdb5a40.zip).
  Its `image/cel/config` lists every file's frame sizes, palette and TRN, plus notes on broken
  animations.
- [doggan/diablo-file-formats](https://github.com/doggan/diablo-file-formats): JavaScript parsers for
  CEL, CL2 (partial), PAL, DUN, TIL, MIN and SOL. Dormant.
- [Unofficial Diablo CEL Image Specification](https://web.archive.org/web/20091027162419/http://geocities.com/fantasydiablo/cel_spec.html):
  Joel Molin, 2004, public domain. Archived. The live geocities.ws copy redirects to an unrelated page.
- MPQ documentation is listed in [blizzard_common](../../blizzard_common/docs/AGENTS.md#references).
  [mpqfs](https://github.com/diasurgical/mpqfs), MIT licensed, is DevilutionX's own MPQ library.

### Tools

- [Diablo 1 Graphics Tool](https://github.com/diasurgical/d1-graphics-tool): the standard viewer and
  editor for CEL, CL2, PAL, TRN, MIN, TIL, SOL and AMP, with PNG export. Low activity. Sustainable Use
  License. Development continues in [pionere's fork](https://github.com/pionere/d1-graphics-tool), which
  is active.
- [clx-conversion-tools](https://github.com/diasurgical/clx-conversion-tools), formerly
  devilutionx-graphics-tools: `cel2clx`, `cl22clx`, `pcx2clx` and `clx2pcx`. Unlicense. Dormant.
- [devilutionx-asset-optimizer](https://github.com/diasurgical/devilutionx-asset-optimizer), formerly
  devilutionx-mpq-tools: `unpack_and_minify_mpq`, which produces the data for `UNPACKED_MPQS` builds. Its
  `data/` folder has the best listfiles, and `diabdat-clx.txt`, which gives the width of every CEL and
  CL2 in `DIABDAT.MPQ`. Active.
- MPQ tools and Python MPQ libraries are covered in
  [blizzard_common](../../blizzard_common/docs/AGENTS.md#mpq-tools). Two notes specific to Diablo 1:
  - DevilutionX builds `devilutionx.mpq` with smpq.
  - mpqcli can create Diablo-style archives (`create -g diablo1`).

### Listfiles

Diablo's MPQs contain no `(listfile)`, so you need a list of paths to find anything.

- [devilutionx-asset-optimizer `data/`](https://github.com/diasurgical/devilutionx-asset-optimizer/tree/main/data)
  has one list per archive. They name 100% of the files in `DIABDAT.MPQ`, `hellfire.mpq`, `hfmonk.mpq`
  and `hfmusic.mpq`.
- Zezula's [`listfiles.zip`](http://www.zezula.net/download/listfiles.zip) also covers 100% of
  `DIABDAT.MPQ`, `hellfire.mpq` and `hfmonk.mpq`.
- diabloweb's [`ListFile.txt`](https://github.com/d07RiV/diabloweb/blob/master/src/mpqcmp/ListFile.txt)
  covers 2,908 of `DIABDAT.MPQ`'s 2,910 files, and no Hellfire files.

### Communities

- **DevilutionX:**
  - [Discord](https://discord.gg/YQKCAYQ) (the invite opens in #modding);
  - [devilutionx.com](https://devilutionx.com);
  - the wiki's [Modding](https://github.com/diasurgical/DevilutionX/wiki/Modding) and
    [Community Mods](https://github.com/diasurgical/DevilutionX/wiki/Community-Mods) pages.

  All active. This is where Diablo 1 modding happens now.
- **The Hell**, a long-running overhaul mod by Mordor: [ModDB](https://www.moddb.com/mods/diablo-the-hell-4)
  and [Discord](https://discord.gg/AN9NukZFbN). Active.
- **Belzebub and its multiplayer successor Tchernobog**, by Noktis: [site](https://mod.diablo.noktis.pl/).
  Active.
- **Infernity**, by qndel: [GitHub](https://github.com/qndel/Infernity). Dormant.
- **[The Horadrim](https://discord.gg/AckTPMu)**, a Discord for unmodded multiplayer. Active.
- **ModDB hubs** for [Diablo](https://www.moddb.com/games/diablo/mods) and
  [Hellfire](https://www.moddb.com/games/diablo-hellfire/mods). Active.
- **The Phrozen Keep's [Diablo I Modding](https://d2mods.info/forum/viewforum.php?f=208) board.**
  Dormant: its newest topic is from 2023.
- **[forum.diablo1.ru](http://forum.diablo1.ru/)**, a Russian forum with a mods board. Low activity.
- **[Jarulf's Guide](https://wheybags.gitlab.io/jarulfs-guide/)**, the classic reference on game
  mechanics.
- **Lurker Lounge**, a long-standing Diablo site. It's been unreachable since about 2026-09-22.

### Getting the game data

- Buy Diablo + Hellfire on [GOG](https://www.gog.com/en/game/diablo). The DevilutionX wiki explains how to
  [extract the MPQs from the installer](https://github.com/diasurgical/devilutionX/wiki/Extracting-MPQs-from-the-GoG-installer).
  It's also sold on [Battle.net](https://us.shop.battle.net/en-us/product/diablo).
- The shareware version is free from Blizzard as
  [`diablosw.exe`](http://ftp.blizzard.com/pub/demos/diablosw.exe). `smpq -x diablosw.exe spawn.mpq`
  extracts its `spawn.mpq`.
  - The copies of `spawn.mpq` that DevilutionX and diabloweb link to are repacked. They use zlib or
    multi-method compression instead of implode, and DevilutionX's copy isn't encrypted. They won't
    exercise an implode decoder.
  - Its license only allows private use, and whether it may be redistributed is unclear, so don't commit
    it either.
