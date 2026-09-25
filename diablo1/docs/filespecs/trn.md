# TRN: palette translations

A TRN file recolors a sprite without touching its pixels. It maps palette indices to palette indices,
and it's applied when the sprite is drawn, before lighting.

## Format

256 bytes, no header. Byte `i` is the index to draw in place of index `i`:

```python
recolored = [trn[i] if i is not None else None for i in pixels]
```

A TRN works on indices, not colors, so recoloring means pointing one ramp's indices at another ramp
(see [pal.md](pal.md)). Unused entries are usually left as the identity: `plrgfx/infra.trn` keeps 129
of its 256 entries and `plrgfx/stone.trn` keeps 144.

## Where they're used

| TRN | When it's applied | Purpose | Found in |
|-----|-------------------|---------|----------|
| `monsters/<trnFile>.trn`, e.g. `monsters/zombie/bluered.trn` | at load, to every animation of the type | color variants that share one set of sprites; `trnFile` is a column of `monstdat.tsv` | `DIABDAT.MPQ` (66 files) |
| `monsters/monsters/<trn>.trn` | at draw time, in place of lighting | unique monsters, their corpses and their missiles; `trn` is a column of `unique_monstdat.tsv` | `DIABDAT.MPQ` (31 files) |
| `plrgfx/infra.trn` | at draw time | a red tint: actors in unlit areas or seen through infravision, and unusable items in the inventory and stores | `DIABDAT.MPQ` |
| `plrgfx/stone.trn` | at draw time | Stone Curse (petrified monsters) | `DIABDAT.MPQ` |
| `<player sprite path>.trn`, e.g. `plrgfx/warrior/whu/whufm.trn` | at load, to that one file | fixes for individual sprites | `devilutionx.mpq` |
| `plrgfx/<trn>.trn` | at load, to all of a class's sprites | optional per-class recolor; `trn` comes from the class's `sprites.tsv` | none shipped; for mods |
| `gendata/pause.trn` | at draw time | tints the whole view red (`RedBack` in `Source/control/control_panel.cpp`) | `devilutionx.mpq` |

Before applying a monster type's TRN, DevilutionX replaces entries equal to 255 with 0. It doesn't
translate the walk animation of the Counselor family. The loaders are in `Source/monster.cpp`,
`Source/engine/trn.cpp` and `Source/lighting.cpp`.

## Notes for glisomorph

- When comparing or interpolating, work on the untranslated sprite. Apply the TRN only for display.
- Frames glisomorph synthesizes get the same TRNs as the originals at runtime. Their pixels need to stay
  in the ramps the TRNs expect, or the recolor will miss them. See
  [pal.md](pal.md#notes-for-glisomorph).
