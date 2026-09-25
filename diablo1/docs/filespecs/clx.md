# CLX: DevilutionX's sprite format

CLX isn't one of Diablo's own formats. DevilutionX introduced it, and uses it for:

- **Every sprite at runtime.** It converts CEL and CL2 to CLX as it loads them
  (`Source/utils/cel_to_clx.cpp`, `Source/utils/cl2_to_clx.cpp`), and PCX too
  (`Source/utils/pcx_to_clx.cpp`).
- **Its own assets**: `devilutionx.mpq` and `fonts.mpq`, built from the `assets/` folder of the
  DevilutionX repository (`assets/data/*.clx`, `assets/ui_art/*.clx`, `assets/fonts/**/*.clx`, and so
  on).
- **Unpacked game data.** A build with `UNPACKED_MPQS` expects the MPQs extracted and converted by
  [devilutionx-asset-optimizer](https://github.com/diasurgical/devilutionx-asset-optimizer), formerly
  devilutionx-mpq-tools, so the sprites on disk are `.clx`. For example, `Source/engine/assets.cpp` checks
  for `plrgfx/monk/mha/mhaas.clx`.

[clx-conversion-tools](https://github.com/diasurgical/clx-conversion-tools) converts single files:
`cel2clx`, `cl22clx`, `pcx2clx` and `clx2pcx`.

CLX is [CL2](cl2.md) with a self-describing frame header. That makes it the easiest of the three to
parse, and a convenient interchange format.

All integers are little-endian.

## File layout

The same frame list or sheet as [CL2](cl2.md#file-layout), with the same list-or-sheet test
(`GetNumListsFromClxListOrSheetBuffer` in `Source/engine/clx_sprite.hpp`).

## Frame

| Offset | Type | Meaning                               |
|--------|------|---------------------------------------|
| 0      | u16  | header size (6 in files DevilutionX writes) |
| 2      | u16  | width                                 |
| 4      | u16  | height                                |
| *header size* | … | pixel commands, exactly as in [CL2](cl2.md#pixel-commands) |

Readers should skip `header size` bytes rather than assume 6.

Compared with CL2:

- Width and height are stored.
- There are no row offsets.
- Opaque runs can wrap rows as well as skip runs. `Cl2ToClx` merges consecutive opaque pixels across
  row boundaries. A linear-stream decoder, like the one in [cl2.md](cl2.md), handles this without
  changes.

## Sources

- DevilutionX: `Source/engine/clx_sprite.hpp` (the format description), `Source/utils/clx_encode.hpp`,
  `Source/utils/clx_decode.hpp`, `Source/utils/cel_to_clx.cpp`, `Source/utils/cl2_to_clx.cpp`.
