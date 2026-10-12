# StarCraft / Brood War

Notes for agents working on this game's parsers. This covers StarCraft (1998) and Brood War, the
classic PC versions up to 1.16.1, and the classic MPQs that later installs still carry. StarCraft:
Remastered (1.18 and later, 2017) keeps its data in CASC with new HD formats; it's summarized under
[Remastered](#remastered) but not specified.

Read [blizzard_common/docs/AGENTS.md](../../blizzard_common/docs/AGENTS.md) first. It has the rules
for every game (game data, licenses, checking claims) and the MPQ references.

## This folder

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file: ground rules, what matters for glisomorph, and references |
| `docs/cameras.md`      | the camera each 9-direction sprite was rendered with, as fitted and checked |
| `docs/filespecs/*.md`  | one spec per format: layout, decoding and what was checked against the real data |
| `grp.py`               | the GRP reader: frames as palette indices on the canvas          |
| `export/grp.py`        | `GrpExporter`: a sprite's frames written as a GRP (see [common/docs/AGENTS.md](../../common/docs/AGENTS.md)) |

## Game data

- **Ask the user where their copy is.** The classic data is in `StarDat.mpq`, `BrooDat.mpq` and
  `patch_rt.mpq`; `Starcraft.mpq` and `BroodWar.mpq` hold music, cinematics and campaigns. The
  install checked here, a Remastered one, still had all five beside its CASC `Data/` folder. See
  [archives.md](filespecs/archives.md).
- The repository's `blizzard_common/mpq.py` reads them as they are (everything but sound).
- **What was checked:** the checks in these docs used those MPQs, dated 2017: Brood War's data as of
  the last classic patches. StarCraft's own files in `StarDat.mpq` have the same formats with fewer
  entries (755 images against 999), and its `iscript.bin` a different header (see
  [dat.md](filespecs/dat.md#layout) and [iscript.md](filespecs/iscript.md#file-layout)).

## Ground rules

- **No reimplementation is both authoritative and portable.** OpenBW reimplements the game's logic
  and drawing faithfully, but has no license. PyMS and Chkdraft are MIT and cover the formats well,
  but are editors, not the game. Check claims against the game files; every spec says what was
  checked.
- **Licenses specific to StarCraft:**
  - **Can be ported, with attribution:**
    - PyMS (MIT since 2026-06; before that it had no license, so use a current checkout), Chkdraft,
      StormLib, CascLib and starcraft-match: MIT.
    - Animosity: Apache-2.0; keep its NOTICE.
  - **Reference only:**
    - OpenBW: no license file; treat as all rights reserved.
    - BWAPI: LGPL-3.0. Stargus: GPL-2.0.
    - Titan Reactor: no license.
    - ScmDraft 2 and DatEdit: closed freeware.

    Write independent implementations from the specs here.
  - **Never copy test fixtures from other projects.**
- **Indices, not colors.** Everything is 8-bit and drawn through a palette and lookup tables; a parser
  should hand back indices and let the caller color them.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| MPQ | [archives.md](filespecs/archives.md); the format is in [blizzard_common](../../blizzard_common/docs/filespecs/mpq.md) | the archives | specified, checked |
| GRP | [grp.md](filespecs/grp.md) | sprite frames | specified, checked on every sprite; read and written (`grp.py`, `export/grp.py`) |
| iscript.bin | [iscript.md](filespecs/iscript.md) | animation scripts: frames, timing, overlays, shadows | specified, opcode sizes checked on the whole file |
| `.dat`, LO*, `.tbl` | [dat.md](filespecs/dat.md) | units → flingy → sprites → images; overlay offsets; strings | specified, layouts checked |
| WPE, PCX remaps, draw functions | [palettes.md](filespecs/palettes.md) | palettes, player colors, shadows, glows | specified; partly checked |
| CV5, VF4, VX4, VR4, CHK | — | terrain and maps | documented in random-map-generator's `docs/starcraft/` |
| `.anim`, `.dds.grp` | — | Remastered's HD sprites | not yet; see [Remastered](#remastered) |

## What matters for glisomorph

- **Directions:** sprites have **32 directions, 11.25° apart, of which 17 are drawn** (north to
  south, clockwise) and 15 mirrored (see [grp.md](filespecs/grp.md#directions)). That's already
  finer than Diablo's 8 or 16. Synthesized directions would go between those 32, or replace the
  mirrored ones with true views, since mirroring flips lighting and asymmetric details such as the
  marine's gun hand. Dropping every other drawn direction and synthesizing it gives ground truth.
- **Time:** animations are already fast. Most frames last 1 or 2 game ticks of 42 ms (on Fastest),
  and walking advances a frame every tick (see [iscript.md](filespecs/iscript.md#timing)). In-betweens
  don't fit in the game's own timing: they need a renderer that draws between ticks, as D2DX does for
  Diablo II. The longer holds are on slower speeds and idle loops.
- **The camera differs by sprite.** Fitted 3D views of the 9-direction sprites put most Terran and
  Protoss infantry and workers at 28–38° above the ground, their vehicles and larger figures at about
  44.5°, most Zerg at 44.5–60°, and five sprites (the goliath, the Archon, the Zerg queen, guardian and
  overlord) behind a perspective camera (see [cameras.md](cameras.md)). A 3D fit needs each sprite's own
  camera.
- **Movement is often in the script.** 44 units, the infantry and the legged units among them, move
  by `move n` in their walk script, so positions advance with the frames; an in-between frame needs
  an in-between position too. Flyers, workers and the vulture glide at a speed instead.
- **Shadows are separate images**: either the unit's own frames drawn dark at an offset (flyers,
  workers, the vulture) or hand-drawn shadow GRPs that follow the unit's frame (walking units).
  Hand-drawn ones need their own in-betweens (see
  [palettes.md](filespecs/palettes.md#shadows-draw-function-10)).
- **Not every image is opaque color.** Draw function 9 images (glows, fire, explosions) are lookups
  into tables of what's already on screen, so their indices are intensities. Indices 8–15 are the
  player color ramp; synthesized pixels must keep them in that ramp.
- **Overlays per frame:** LO* files place muzzle flashes, fire and dust by frame and direction. New
  frames or directions need new LO* entries, which can be interpolated.

## Remastered

Not specified here; this is what the sources say, unchecked:

- **Storage:** CASC (readable by CascLib since build 2457, and by Chkdraft). The install checked
  here kept the classic MPQs beside it.
- **Sprites:** `.anim` files. `SD/mainSD.anim` holds all 999 images at the classic size; HD
  (`anim/main_NNN.anim`, 4× the classic size) and HD2 (2×) have one file per image. Each frame has
  up to seven layers in DXT1/DXT5 textures: diffuse, team color (a mask multiplied with the player
  color), bright, normal, specular, AO and depth, emissive. Directions and frame order are the classic
  ones, and the classic GRP still sets each frame's size and center. The team color mask can also
  be a raw bitmap.
- **Others:** `.dds.grp` (interface graphics), `anim/main.lit` (lighting), `images.rel`, skins
  (Carbot, Presale).
- Animosity's README is the best description; Chkdraft's `render/` reads and draws them.

For glisomorph, Remastered's HD art is a full-color, 4×, already-lit source, not palette indices:
a different problem from the classic sprites.

## References

Links were checked on 2026-10-03. **Active** means changed in 2025–26, **dormant** means online but
older.

### Format documentation and code

- [PyMS](https://github.com/poiuyqwert/PyMS): the StarCraft modding suite, in Python. MIT. Active
  (the `python3` branch; `master` is Python 2).
  - `PyMS/FileFormats/`: `GRP.py`, `IScriptBIN/`, `LO.py`, `DAT/*.py`, `TBL.py`, `PCX.py`; the most
    compact readable source for every format here.
  - `PyMS/Data/`: the names lists (draw functions, remappings, iscript headers) and a listfile.
- [Chkdraft](https://github.com/TheNitesWhoSay/Chkdraft): a map editor whose `src/mapping_core/`
  reads MPQ and CASC archives, `.dat` files, GRPs, iscript and Remastered `.anim`, and renders them
  (`render/`, including `game_clock.h`). MIT. Active.
- [OpenBW](https://github.com/OpenBW/openbw): a reimplementation of the game logic and drawing,
  faithful enough to replay games. `bwgame.h` holds the GRP, iscript and LO* readers and the
  direction rule; `ui/ui.h` the draw functions. No license: read only. Active.
- [Animosity](https://github.com/neivv/animosity): a Remastered `.anim` and `.dds.grp` editor;
  its README documents the layers and scales. Apache-2.0. Active.
- [staredit.net's wiki](https://wiki.staredit.net/wiki/Modding_Files_Overview): "GRP Image Format",
  "Modding Files Overview", "IceCC Animations", "Game speed". The old iscript and `images.dat` pages
  are gone; the old `/wiki/index.php/` links redirect.
- random-map-generator's `docs/starcraft/`: terrain, palettes and remap tables, measured over the
  shipped maps. Its notes cite "StarSource", a decompilation of 1.17, which couldn't be found publicly.
- [starcraft-match](https://github.com/nicodlz/starcraft-match): a matching decompilation of 1.16.1,
  partial. MIT. Active.
- Dead: Stormcoast Fortress's "File Specs" pages, and farty1billion's site.

### Engines and tools

- [BWAPI](https://github.com/bwapi/bwapi): the bot API; its docs give the game speeds. LGPL-3.0.
  Active.
- [StormLib](https://github.com/ladislav-zezula/StormLib) and
  [CascLib](https://github.com/ladislav-zezula/CascLib): MPQ and CASC readers. MIT. Active.
- [ScmDraft 2](http://www.stormcoast-fortress.net/cntt/software/scmdraft/): the standard map editor.
  Closed freeware.
- [Titan Reactor](https://github.com/alexpineda/titan-reactor): a 3D replay viewer for Remastered
  assets, on OpenBW. No license. Dormant.
- [Stargus](https://github.com/Wargus/stargus): StarCraft data on the Stratagus engine. GPL-2.0.
  Active.
- [Magnetar](https://github.com/joankaradimov/Magnetar): a Brood War mod and reimplementation, in
  C++. MIT. Dormant.

### Listfiles

- The archives' own listfiles are incomplete (see
  [archives.md](filespecs/archives.md#file-names)); `images.tbl`, `sfxdata.tbl` and `portdata.tbl`
  name most game files.
- PyMS's `PyMS/Data/Listfile.txt` has about 6,100 paths. MIT.
- Zezula's MPQ Editor ships listfiles too.
