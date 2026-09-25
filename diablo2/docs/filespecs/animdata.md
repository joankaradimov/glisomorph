# AnimData.d2: frame counts, speeds and events

`data/global/animdata.d2` gives every COF-based animation of players, monsters and missiles its number
of frames per direction, its speed and its per-frame events. Objects don't use it: `Objects.txt` has
their speeds (see [sprite-metadata.md](sprite-metadata.md#speed)). The file is in `d2data.mpq`, and
`d2exp.mpq` has a newer copy.

All integers are little-endian.

## Layout

A hash table of 256 buckets, stored one after another. Bucket `i` is a `u32` record count followed by
that many 160-byte records. There's no index: to find bucket `i`, walk the buckets before it.

| Offset | Type      | Field                                                    |
|--------|-----------|----------------------------------------------------------|
| 0      | char[8]   | COF name, NUL-padded (`BATN1SS`)                         |
| 8      | u32       | frames per direction                                     |
| 12     | u32       | speed, in 256ths of 25 fps (256 = 25 fps)                |
| 16     | u8[144]   | frame events: one byte per frame, the rest zero          |

A name's bucket is the sum of its upper-cased characters, modulo 256:

```python
def bucket(cof_name: str) -> int:
    return sum(cof_name.upper().encode("ascii")) & 0xFF
```

## Speed

The game runs at 25 frames per second. An animation advances by `speed / 256` frames each game frame:
`fps = 25 × speed / 256`. The Barbarian's `BATN1SS` has speed 80, about 7.8 fps. Paul Siramy's PDF
lists the values the game uses, from 24 to 512. The file also has a few records with speed 0.

## Frame events

| Value | Event on that frame                  |
|-------|--------------------------------------|
| 0     | none                                 |
| 1     | attack: the blow lands               |
| 2     | missile: the projectile is released  |
| 3     | sound                                |
| 4     | skill                                |

Values 0–3 occur in the 1.00 file. The meanings come from Riiablo, Worldstone and OpenDiablo2, and match
the event numbers of D2MOO's animation sequences. The game copies the flag of each frame it passes into
the unit's action-frame field (D2MOO, `UNITS_SetAnimActionFrame`).

## Lookup

The game compares all 8 bytes of the name, so names must be NUL-padded. When a COF has no record, D2MOO
falls back to 2,048 frames at speed 256.

## How the game plays an animation

A unit keeps its position in the animation as an 8.8 fixed-point number of frames. Every game tick
(40 ms) it adds the speed. The frame shown is the integer part, and the animation ends when the
position passes `frames × 256`. (D2MOO, `D2Common/src/Units/Units.cpp`.)

The speed isn't always the file's:

- **Players and monsters:** the game scales the base speed by attack speed, cast rate, hit recovery,
  block and run/walk bonuses. Player walking and running use fixed base speeds of 213 and 101.
- **Attacks:** some start a frame or two in. The Amazon and the Sorceress get a "frame bonus" with
  certain weapons.
- **Objects:** `Objects.txt` gives the speed, jittered by up to ±1/16 unless the object is synchronized.
- **Missiles:** they use their `animrate` from `Missiles.txt`.

So the same frames can be shown at many rates. That's useful for glisomorph: in-between frames help
most at slow rates.

## Checked against the game data

The 1.00 `d2data.mpq` copy has 2,563 records and parses to exactly its 411,104 bytes. Every record is in
the bucket the hash above predicts. No record has an event beyond its frame count. The frame counts,
speeds and events agree with the COF files (see [cof.md](cof.md#checked-against-the-game-data)).

## Sources

- D2MOO: `D2Common/include/DataTbls/AnimTbls.h` and `src/DataTbls/AnimTbls.cpp` (layout, hash,
  fallback), `src/Units/Units.cpp` (playback and speed modifiers).
- Paul Siramy, *Extracting Diablo II Animations*: the meaning of the speed, and the Animdata_edit tool.
- Riiablo, Worldstone and OpenDiablo2: the event values.
