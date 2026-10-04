# Fallout common

Things shared by Fallout (Interplay, 1997) and Fallout 2 (Black Isle Studios, 1998), the PC versions:
rules for both games, the formats they share, and references. The two games use the same engine, and
apart from the DAT archives their formats are the same, so most specs live here. Read this before a
game's own `AGENTS.md`:

- [Fallout 1](../../fallout1/docs/AGENTS.md)
- [Fallout 2](../../fallout2/docs/AGENTS.md)

Fallout Tactics, Fallout: Brotherhood of Steel and the 3D Fallouts use other engines and are out of
scope.

## This folder

It's laid out like a game folder:

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: rules, what matters for glisomorph, and references   |
| `docs/filespecs/*.md`  | specs of the formats both games share                           |
| `*.py`                 | shared parsers (none yet)                                       |

## Rules for both games

- **Never commit game data**, or anything extracted or rendered from it (sprites, PNGs, palettes, test
  fixtures cut from real files). It's Bethesda's copyrighted material (Interplay's originally). Tests
  should build synthetic inputs, or read the user's own game files at runtime and skip when they're
  absent.
- **Local game data:** ask the user where it is rather than searching the disk. Each game's
  `AGENTS.md` records what's known.
- **The source code is the reference.** alexbatalov's Community Edition (CE) and reverse-engineered (RE)
  projects reimplement each game from its executable. When a third-party document disagrees with them,
  the code wins. The specs cite files as paths inside those repositories, such as
  `fallout2-ce: src/art.cc`, and were written against these commits:

  | Repository  | Commit    | Date       |
  |-------------|-----------|------------|
  | fallout1-ce | `0609bcf` | 2025-01-15 |
  | fallout1-re | `ac9784b` | 2023-01-30 |
  | fallout2-ce | `e97087b` | 2025-02-16 |
  | fallout2-re | `b135fc4` | 2023-01-20 |

- **Mind the licenses.** This repository is MIT licensed.
  - **Can be ported, with attribution:** DarkFO and Harold (Apache-2.0; keep the notice), Falltergeist's
    dat-unpacker (MIT), the FOnline engine (MIT), Gecko (Apache-2.0), and the small MIT FRM viewers
    listed under [Tools](#tools).
  - **Dependency at most:** sfall, the Falltergeist engine and vault13 (GPL-3.0), and the yellowcake
    libraries (AGPL-3.0).
  - **Read only:** all of alexbatalov's projects and their forks (Sustainable Use License), and
    everything without a license: fodev.net's docs, RPU, Fallout Et Tu, the TeamX tools, BGforge MLS. Read
    their code to understand a format, then write an independent implementation.
  - The wiki pages (Vault-Tec Labs, the Independent Fallout Wiki) are CC BY-SA. Paraphrase them; don't
    copy their text into the specs.
- **Check claims against the data.** Every spec ends with a "Checked against the game data" section
  that says what was verified and on which files. Keep it honest: "sampled" isn't "all". Say so plainly
  when nothing was checked.
- **Byte order:** Fallout's own formats (FRM, PRO, MAP and Fallout 1's DAT) are **big-endian**, even
  though the game ran on x86. Fallout 2's DAT is little-endian. Each spec says which it is.
- **Paths inside DATs** are case-insensitive and stored with backslashes (`art\critters\hmjmpsaa.frm`).
  The specs about archives and file names ([dat.md](filespecs/dat.md), the `archives.md` pages,
  [sprite-metadata.md](filespecs/sprite-metadata.md)) write them that way, since it's how the game
  builds and stores them. The other specs use forward slashes; both mean the same path.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| DAT | [dat.md](filespecs/dat.md); which archives each game has is in [fallout1](../../fallout1/docs/filespecs/archives.md) and [fallout2](../../fallout2/docs/filespecs/archives.md) | the archives: DAT1 with LZSS (Fallout 1), DAT2 with zlib (Fallout 2) | specified, checked on every file |
| FRM, FR0–FR5 | [frm.md](filespecs/frm.md) | every sprite: critters, items, scenery, walls, tiles, UI | specified, checked on every file |
| sprite metadata | [sprite-metadata.md](filespecs/sprite-metadata.md) | art IDs, `.lst` files, critter file names, animation and weapon codes, aliases | specified, checked against every critter file |
| PAL | [pal.md](filespecs/pal.md) | `color.pal`: the palette, its inverse table, light and blend tables, color cycling | specified, checked |
| geometry | [geometry.md](filespecs/geometry.md) | the hex grid, floor tiles, the six directions and the camera they imply | specified; the camera measured on the art |
| PRO | [pro.md](filespecs/pro.md) | prototypes: what links an object to its art, light and translucency | specified, checked on every file |
| MAP | [map.md](filespecs/map.md) | maps: header, tiles, scripts, objects | specified; every map parses to its last byte |
| everything else | [other-formats.md](filespecs/other-formats.md) | GAM, MSG, scripts, ACM, MVE, fonts, saves… | listed, mostly out of scope |

## What matters for glisomorph

- **Six directions, 60° apart on the ground**, in the order NE, E, SE, SW, W, NW. There's no N or S:
  the view looks straight up the screen, halfway between NE and NW, so no direction faces the camera. E
  and W are side views. Interpolate in ground-plane angle; on screen the diagonals sit 36.87° off
  horizontal, not 60°. See [geometry.md](filespecs/geometry.md#the-six-directions).
- **The camera is known.** The 32×16 hexes and 80×36 floor tiles imply an orthographic view
  asin(√3/4) = 25.66° below the horizon: ground depth shrinks to 0.433 on screen, heights to 0.901 if
  objects were rendered in the same space. The art agrees to about ±0.5°: walk cycles give 25.3° and
  round scenery 26.1°, and 30° (Diablo's camera) is ruled out. The height squash wasn't measured. See
  [geometry.md](filespecs/geometry.md#what-3d-projection-this-implies).
- **Anchoring:** a frame's anchor is its bottom-center pixel, `(width // 2, height − 1)`. It sits on the
  hex center, plus the file's per-direction shift, plus the critter's running offset, which is the sum
  of the frame offsets so far. Align frames on that point, not on the frame box. The wiki is one pixel
  off here; the code's rule is confirmed by the art (cursor hotspots, the hex cursor). See
  [frm.md](filespecs/frm.md#where-a-frame-goes).
- **Shadows are baked in**, as in Diablo 1: critter frames include a ground shadow in the darkest greys
  (mostly index 207, which bodies use too). Treat it as a separate layer, or blending will smear it into
  the body.
- **One body per base name.** A critter's file name is a base name, a weapon letter and an animation
  code (`hmjmps` + `a` + `a` = `hmjmpsaa.frm`, the unarmed stand). All weapon letters of one base name
  are the same body holding different weapons; different armor is a different base name. Fit one model
  per base name, and leave out the aliased animations, which show another critter's art (see
  [sprite-metadata.md](filespecs/sprite-metadata.md#aliases)).
- **Rest pose:** frame 0 of the unarmed stand (`aa`), in all six directions. The rest of `aa` is an idle
  fidget the game plays now and then. Its offsets don't always sum to zero, so align fidget frames by
  their running offset too.
- **Sprites are palette indices** and index 0 is transparent; there are no skip runs, pixels are
  stored raw.
  - Indices 229–254 cycle colors (slime, monitors, fire, shoreline, the alarm). `color.pal` stores them,
    with 0 and 255, as 255s, which load as black; their colors come from the executable. Treat them as
    glowing materials: keep the indices, don't blend them. Critters hardly use them (0.01% of their
    pixels, mostly strays). Indices 1–228 are safe for ordinary colors; the game's black is 228.
  - The game maps RGB back to an index through a 32,768-entry table in `color.pal`, not by searching
    for the nearest color. With the shipped palette it only ever answers 1–228. Use it to reproduce the
    game, or a nearest-color search over 1–228 for accuracy. See
    [pal.md](filespecs/pal.md#notes-for-glisomorph).
  - Lighting darkens sprites through the palette's intensity table, and translucency comes from the
    object's PRO flags, not from the pixels.
- **Ground truth for root motion:** the sum of a walk or run cycle's frame offsets is the critter's
  on-screen travel per cycle, e.g. 69 pixels east for the male walk (2.16 hexes; cycles aren't whole
  hexes, and the game snaps the critter to its hex when a path ends). Single frame offsets are noisy,
  since they also absorb each frame's crop. The diagonal sums measure the art's foreshortening:
  0.427, against the grid's 0.433. See [frm.md](filespecs/frm.md#how-offsets-accumulate).
- **Ground truth for time interpolation:** a frame lasts `1000 / fps` ms, with fps in the file (0 means
  10). Slow animations, such as stands at the default 10 fps, leave room for in-betweens. As with Diablo,
  drop every other frame and synthesize it back.
- **Ground truth for direction interpolation:** none found yet. Critters have at most six directions,
  and nothing like Diablo's 16-direction missiles is known. Some knockdowns and deaths come as one file
  per direction (`.fr0`–`.fr5`) instead of one `.frm`; the directions are the same six.

## References

Links were checked on 2026-10-03. **Active** means changed in 2025–26, **dormant** means online but
older, and **archived** means frozen (a read-only repository) or only on the Wayback Machine. Items
specific to one game are in that game's `AGENTS.md`.

### Source code

- **alexbatalov's projects**, the reference for every spec here. All use the Sustainable Use License, so
  they're read only.
  - [fallout1-ce](https://github.com/alexbatalov/fallout1-ce) and
    [fallout2-ce](https://github.com/alexbatalov/fallout2-ce): complete reimplementations for modern
    systems. Active but quiet; their last commits are from early 2025.
  - [fallout1-re](https://github.com/alexbatalov/fallout1-re) and
    [fallout2-re](https://github.com/alexbatalov/fallout2-re): the decompilations the CE projects grew
    from, closer to the original executables. Dormant.
  - Many ports and forks reuse the CE code (PS3, PS4, original Xbox, WebAssembly, a Free Pascal port).
    They inherit its license, and none matter for format work.
- **DarkFO and Harold**, a TypeScript Fallout 2 engine with Python asset converters:
  [darkf/darkfo](https://github.com/darkf/darkfo) (archived) and its revival
  [OldGamesLab/Harold](https://github.com/OldGamesLab/Harold) (dormant). Apache-2.0, so they can be
  ported. Their `frmpixels.py` (FRM), `pal.py` (palette) and `dat2.py` (DAT2 only, no DAT1) are the most
  directly useful code here.
- [FOnline](https://github.com/cvet/fonline): an isometric MMO engine descended from a Fallout fan MMO.
  It still reads Fallout's data: a DAT reader in `Source/Common/DataSource.cpp` and FRM loaders in
  `Source/Tools/ImageBaker.cpp`. Active. MIT.
- [Falltergeist](https://github.com/falltergeist/falltergeist): a C++ reimplementation of the Fallout 2
  engine, with readers written independently of the original code. Dormant (2022). GPL-3.0.
- [vault13](https://github.com/pingw33n/vault13): a Fallout 2 engine reimplementation in Rust. Active.
  GPL-3.0.
- Smaller reimplementations, of little use: [FreeRadical](https://github.com/grepwood/FreeRadical)
  (GPL-3.0), [neofallout](https://github.com/indika-dev/neofallout) (Rust, GPL-3.0) and
  [freefall](https://github.com/ChrisNonyminus/freefall) (no license), all dormant;
  [HexWaste](https://github.com/eko1495/HexWaste), a C# Fallout 2 map viewer (active, no license).

### Format documentation

- **[Fallout 1 & 2 Docs](https://fodev.net/files/fo2/)** on fodev.net, by the Rotators: the most
  complete current reference. One page per format, plus engine structures and a curated
  [tools list](https://fodev.net/files/fo2/tools.html). Updated 2026-09. Its source,
  [rotators/fallout2-docs](https://github.com/rotators/fallout2-docs), has no license. Several specs here
  note where it disagrees with the code.
- **[Vault-Tec Labs](https://falloutmods.fandom.com/wiki/Fallout_and_Fallout_2_file_formats)**
  (falloutmods.fandom.com), CC BY-SA. Active: TeamX's documents were being imported in 2026-09.
  - The index page lists only some formats; the full set is in
    [Category:Fallout and Fallout 2 file formats](https://falloutmods.fandom.com/wiki/Category:Fallout_and_Fallout_2_file_formats).
  - The key pages: [FRM File Format](https://falloutmods.fandom.com/wiki/FRM_File_Format),
    [PAL File Format](https://falloutmods.fandom.com/wiki/PAL_File_Format),
    [DAT file format](https://falloutmods.fandom.com/wiki/DAT_file_format) (both versions, with
    Shadowbird's LZSS description) and [PRO File Format](https://falloutmods.fandom.com/wiki/PRO_File_Format).
  - [Fallout critter patches](https://falloutmods.fandom.com/wiki/Fallout_critter_patches) lists the
    MD5 of `critter.dat` and `master.dat` for each release, which tells a censored European release
    from the US one.
  - **Fandom blocks scripted fetches** with HTTP 402 or 403. The MediaWiki API works:
    `https://falloutmods.fandom.com/api.php?action=parse&page=FRM_File_Format&prop=wikitext&format=json`.
- **[The Independent Fallout Wiki](https://fallout.wiki/)** has its own copies of the format pages, for
  example [FRM File Format](https://fallout.wiki/wiki/FRM_File_Format) and
  [Game Files](https://fallout.wiki/wiki/Game_Files). Active. CC BY-SA 4.0.
- **TeamX** ([teamx.ru](https://www.teamx.ru/)), the Russian group behind most of the early format
  research. Its [site archive](https://www.teamx.ru/site_arc/index.html) is frozen at 2012 but online:
  [documents](https://www.teamx.ru/site_arc/docs/index.html) (mostly Russian; FRM, DAT, PRO, MAP, the
  critter animation list, the palette's colors) and [utilities](https://www.teamx.ru/site_arc/utils/index.html).
  No license. fodev.net keeps an
  [English mirror of the utilities](https://fodev.net/files/mirrors/teamx-utils/!_INDEX_en.html).

### Tools

- **FRM viewers and editors**, Windows programs without licenses:
  - Frame Animator, the classic FRM editor; its manual is in the TeamX documents. Archived.
  - [FRM Workshop](https://www.nexusmods.com/fallout2/mods/19): builds FRMs from BMPs and adjusts
    offsets. Archived.
  - [Titanium FRM Browser 1.3](https://fodev.net/files/archive/fo2/Titanium%20FRM%20Browser%201.3%20%28en%29.zip):
    plays FRM and RIX files. Archived.
  - The TeamX archive also has frm2bmp, frmcat, gif2frm, PAL View and Dims' FRM Editor, some with
    source.
  - [BGforge MLS](https://github.com/BGforgeNet/BGforge-MLS): a VS Code extension whose animation viewer
    converts FRM and FR0–FR5 to and from PNG. Active. Its license file is empty, so read only.
  - [msk2bmpGUI](https://github.com/QuantumApprentice/msk2bmpGUI) (world map tiles and masks, FRM preview),
    [FRMThumbnail](https://github.com/APAmk2/FRMThumbnail) (Windows thumbnails) and
    [frm_recolour_python](https://github.com/Dr-Felix116/frm_recolour_python) (palette recoloring in
    Python): active, no licenses.
- **FRM readers that can be ported**, all MIT:
  [FRM-Viewer-Online](https://github.com/Pateyta/FRM-Viewer-Online) (JavaScript),
  [frm.js](https://github.com/caasi/frm.js) and [FRMout](https://github.com/ohegba/FRMout), all dormant.
  DarkFO's `frmpixels.py` and FOnline's `ImageBaker.cpp` (above) too. Not portable:
  [frm2png](https://github.com/rotators/frm2png) (no license) and the yellowcake libraries
  [libycres](https://github.com/yellowcake-org/libycres) and
  [libycresources](https://github.com/yellowcake-org/libycresources) (AGPL-3.0).
- **DAT unpackers:**
  - [dat-unpacker](https://github.com/falltergeist/dat-unpacker), Falltergeist's command-line tool: DAT1
    with LZSS, and DAT2. MIT, dormant. The best base for a DAT1 reader.
  - [DAT Explorer II](https://github.com/rotators/fallout-tools/tree/master/DatExplorer-II), a GUI browser
    and packer in [rotators/fallout-tools](https://github.com/rotators/fallout-tools). It can't
    decompress Fallout 1's LZSS. Active, no license.
  - dat2.exe, Anchorite's console packer and unpacker: source in the TeamX archive, a binary in
    [sfall-team/Fallout_DAT2](https://github.com/sfall-team/Fallout_DAT2). No license.
  - Dims' Dat Explorer, Noid's Undat, ABel's F1 Undat and MatuX's DatMan: TeamX archive, no licenses.
- **Package registries:** nothing on PyPI, crates.io or npm reads DAT, FRM or PAL (checked
  2026-10-03). [fallout-se](https://github.com/ali-raheem/fallout-se) (Rust, Apache-2.0) reads save
  games only.
- **Art collections:** [rotators/fallout-animations](https://github.com/rotators/fallout-animations)
  holds community-made critter animations. No license; don't commit anything from it.

### Communities

- **[No Mutants Allowed](https://www.nma-fallout.com/)** (NMA): the main forum since 1997, with a
  [General Modding](https://www.nma-fallout.com/forums/fallout-general-modding.18/) board and
  [utilities](https://www.nma-fallout.com/resources/categories/utilities.7/). The old format threads,
  such as Shadowbird's on DAT and LZSS, are there. Active. It returns 403 to scripts; use a browser or the
  Wayback Machine. [Discord](https://discord.gg/9vp6zWh), about 1,100 members.
- **[BGforge](https://bgforge.net/)**: home of the Fallout 2 Restoration Project and Unofficial Patch,
  and BGforge MLS. [Forums](https://forums.bgforge.net/), [Discord](https://discord.gg/4Yqfggm) (about
  420 members). Active.
- **Rotators**, who run fodev.net and made Fallout Et Tu: [Discord](https://discord.gg/MuhRYZF), about
  110 members. Active.
- **Falltergeist**: [Discord](https://discord.gg/jxs6WRq), about 20 members. Quiet.
- **[Nexus Mods](https://www.nexusmods.com/fallout2)** and ModDB host many mods and tools; both block
  scripts. Reddit's [r/Fallout2](https://www.reddit.com/r/Fallout2/) and [r/fo2](https://www.reddit.com/r/fo2/)
  are players rather than modders.
- **Russian community:** the [fallout.ru forum](https://fforum.kochegarov.com/) has been dormant since
  2021, and TeamX's site is frozen. Russian mods (Nevada, Sonora) now appear on Discord and on
  [gitverse.ru/FalloutMods](https://gitverse.ru/FalloutMods), which also mirrors tools.
- No notable Chinese classic-Fallout modding community was found.

### Getting the game data

- **Buy the games** on GOG ([Fallout](https://www.gog.com/en/game/fallout),
  [Fallout 2](https://www.gog.com/en/game/fallout_2), or the
  [Classic bundle](https://www.gog.com/en/game/fallout_classic)), Steam
  ([Fallout](https://store.steampowered.com/app/38400/), [Fallout 2](https://store.steampowered.com/app/38410/))
  or Epic. Epic gave the Fallout Classic Collection away in December 2023 and again from 2024-08-29 to
  09-05, so many people own it there. GOG's installers unpack with `innoextract -I app setup_fallout_*.exe`,
  as the CE READMEs show.
- **Which release matters for critters.** The European releases removed the child critters (and, per
  the wiki, the German ones also the gore animations) from `critter.dat`. The UK CDs checked here lack
  only the child; every other critter file is identical to the US CDs'. Vault-Tec Labs'
  [critter patches](https://falloutmods.fandom.com/wiki/Fallout_critter_patches) page lists MD5s per
  release, though not every CD matches one (see each game's `AGENTS.md`).
- **CD images** are a good source: the DATs sit at the root of each disc's ISO 9660 file system and
  can be read in place.
- File names in an install may be all upper or all lower case, depending on the release.
