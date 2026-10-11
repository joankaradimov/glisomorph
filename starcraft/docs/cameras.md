# Cameras

StarCraft's unit sprites were rendered from 3D models, but not all with one camera. Fitting a sprite's drawn
directions as views of one 3D shape, and checking the fit by rebuilding a drawn direction it didn't see, finds
the camera each sprite was rendered with. This page lists what was found for the classic Terran, Protoss and
Zerg sprites that draw 9 of their 17 directions (see [grp.md](filespecs/grp.md#directions)).

## The camera

- **Turning**: the camera turns about a vertical axis through the unit, 11.25° from one direction to the next,
  clockwise from north.
- **Elevation**: the camera's angle above the ground: 0° looks from the side, 90° straight down. An
  orthographic camera draws a circle on the ground as an ellipse whose height is its width times
  sin(elevation).
- **Projection**: orthographic, or a perspective camera at distance D from the rotation axis, in pixels at the
  sprite's scale. A perspective camera draws a point p at (p·right, p·up) · D / (D + p·forward).
- **Axis offset**: where the rotation axis falls relative to the canvas center, the image's position (see
  [grp.md](filespecs/grp.md#placement)), in pixels, x right and y down.

## How it was measured

- **The fit**: every animation step is fitted on its own as a still 3D shape (Gaussians), seen from the 9
  drawn directions through the camera. The axis offset is found by carving the silhouettes' visual hull and
  keeping the offset whose hull covers the silhouettes best.
- **Perspective**: a wrong camera carves away parts that the silhouettes show. Over camera distance (down to
  60 px) and elevation, the goliath (legs and turret), the Archon's figure and the Zerg queen, guardian and
  overlord covered clearly better with a near camera. The other large sprites covered best orthographic. Small
  sprites are covered fully under any camera, so the hull can't tell for them.
- **Elevation**: one drawn direction (east, direction 8) is left out of every step, rebuilt from the others,
  and compared with the game's frame. The scores are silhouette overlap (IoU), the share of exactly matching
  palette indices, and the RGB error.
  - Each sprite was searched at 26°, 30°, 34°, 38° and 44.5° on up to four sample steps, and higher, up to
    60°, while the score was still rising.
  - A best angle away from the default 44.5° was refitted and tested on every step. It was kept only where it
    beat the previous camera on all three scores. So was a perspective camera, with its elevation found from
    the silhouettes.
- **Precision**: a few degrees. The search steps were 4–6°. Near ties stayed at 44.5°: the medic and the high
  templar at 50° each scored better on two measures and worse on one. The probe and scarab have one step each,
  so their scores are noisier.

## Results

IoU and exact are the scores for direction 8 rebuilt, over every step. The nearest drawn directions are
22.5° away in this test, against 11.25° for a direction between two drawn ones, so the scores understate how
well new directions match.

| Sprite | GRP | Elevation | Projection | Axis offset | IoU | Exact |
|---|---|--:|---|---|--:|--:|
| Marine | `terran/marine.grp` | 44.5° | orthographic | 0, 0 | 0.940 | 21.6% |
| Firebat | `terran/firebat.grp` | 34° | orthographic | 0.5, −2 | 0.942 | 24.8% |
| Ghost | `terran/ghost.grp` | 34° | orthographic | −0.5, 0 | 0.903 | 16.4% |
| Medic | `terran/medic.grp` | 44.5° | orthographic | 0.5, −2 | 0.929 | 19.5% |
| Sarah Kerrigan | `terran/ughost.grp` | 33° | orthographic | 1.5, 0 | 0.927 | 17.6% |
| Civilian | `neutral/civilian.grp` | 30° | orthographic | −1, −2 | 0.927 | 36.8% |
| SCV | `terran/SCV.grp` | 37° | orthographic | 0.5, −2 | 0.952 | 30.6% |
| Vulture | `terran/Vulture.grp` | 44.5° | orthographic | 0, −2 | 0.940 | 29.0% |
| Goliath, legs | `terran/goliath.grp` | 40.5° | perspective, 85 px | 0, −2 | 0.917 | 19.0% |
| Goliath, turret | `terran/goliathT.grp` | 43° | perspective, 85 px | 0, −2 | 0.960 | 20.4% |
| Siege tank, tank-mode body | `terran/tank.grp` | 44.5° | orthographic | 0, 0 | 0.965 | 15.3% |
| Siege tank, tank-mode turret | `terran/tankt.grp` | 44.5° | orthographic | −1, −2 | 0.941 | 28.5% |
| Siege tank, siege-mode turret | `terran/stankt.grp` | 44.5° | orthographic | 0.5, 0 | 0.964 | 30.1% |
| Science vessel, turning part | `terran/wesselt.grp` | 44.5° | orthographic | 1, −2 | 0.926 | 46.0% |
| Zealot | `protoss/zealot.grp` | 37.5° | orthographic | 1.5, 2 | 0.905 | 19.8% |
| High templar | `protoss/templar.grp` | 44.5° | orthographic | 0.5, −2 | 0.889 | 19.2% |
| Dark templar | `protoss/dtemplar.grp` | 44.5° | orthographic | 0, 0 | 0.927 | 33.5% |
| Reaver | `protoss/trilob.grp` | 44.5° | orthographic | −1, 0 | 0.912 | 15.8% |
| Probe | `protoss/probe.grp` | 28° | orthographic | 0.5, 0 | 0.913 | 15.9% |
| Scarab | `protoss/sapper.grp` | 44.5° | orthographic | −0.5, −2 | 0.928 | 25.0% |
| Archon, figure | `protoss/archonT.grp` | 47.5° | perspective, 120 px | 0.5, 2 | 0.914 | 19.7% |
| Dark archon, figure | `protoss/darchnT.grp` | 44.5° | orthographic | 0.5, −2 | 0.908 | 42.4% |
| High templar, glow | `thingy/pteglow.grp` | 44.5° | orthographic | 0.5, −2 | 0.888 | 44.1% |
| Zergling | `zerg/zergling.grp` | 44.5° | orthographic | 0, 2 | 0.879 | 21.6% |
| Hydralisk | `zerg/hydra.grp` | 44.5° | orthographic | −0.5, 2 | 0.825 | 20.2% |
| Lurker | `zerg/Zlurker.grp` | 44.5° | orthographic | 0, −2 | 0.943 | 22.5% |
| Ultralisk | `zerg/ultra.grp` | 44.5° | orthographic | 0.5, 0 | 0.945 | 17.3% |
| Drone | `zerg/drone.grp` | 50° | orthographic | 0, −2 | 0.890 | 19.4% |
| Larva | `zerg/larva.grp` | 44.5° | orthographic | −0.5, 2 | 0.917 | 26.1% |
| Broodling | `zerg/brood.grp` | 60° | orthographic | 0, 0 | 0.851 | 22.6% |
| Defiler | `zerg/defiler.grp` | 44.5° | orthographic | 0.5, −2 | 0.919 | 23.9% |
| Infested terran | `zerg/bugguy.grp` | 34° | orthographic | 0.5, −2 | 0.918 | 14.7% |
| Infested Kerrigan | `zerg/uikerr.grp` | 34° | orthographic | −1, 2 | 0.894 | 22.0% |
| Queen | `zerg/queen.grp` | 53.5° | perspective, 120 px | 2, −2 | 0.958 | 24.5% |
| Mutalisk | `zerg/mutalid.grp` | 44.5° | orthographic | 0, −2 | 0.943 | 23.1% |
| Scourge | `zerg/avenger.grp` | 55° | orthographic | 0.5, −2 | 0.954 | 21.9% |
| Guardian | `zerg/guardian.grp` | 50° | perspective, 200 px | 0.5, −2 | 0.948 | 25.6% |
| Devourer | `zerg/devour.grp` | 44.5° | orthographic | −1, −2 | 0.940 | 16.1% |
| Overlord | `zerg/overlord.grp` | 42.5° | perspective, 150 px | 0, 0 | 0.899 | 20.8% |

## What it shows

- **Most infantry and workers were rendered from lower down**, 28–38°: the ghost, firebat, Kerrigan and
  civilian at 30–34°, the SCV and zealot at about 37°, and the probe at 28°. Their scores peak there and fall
  off toward 44.5°.
- **The marine and medic are exceptions.** The marine scores about the same from 44.5° to 50°, and the medic
  peaks near 50°.
- **Vehicles and the larger Protoss figures** peak at about 44.5°: the siege tank and its turrets, the
  vulture, both templars, the reaver and the dark archon. Lower angles score clearly worse, and 50° about the
  same or worse.
- **Most Zerg units were rendered from 44.5° or higher**: the zergling, hydralisk, lurker, ultralisk, larva,
  defiler, mutalisk and devourer at 44.5°, the drone at 50°, the scourge at 55° and the broodling at 60°.
- **The infested terran and Infested Kerrigan** peak at 34°, like the Terran infantry they were drawn from.
- **Five sprites were rendered in perspective**, all from close: the goliath (85 px from the axis), the
  Archon (120 px), and the Zerg queen (120 px), overlord (150 px) and guardian (200 px).

## Not measured

- The neutral units other than the civilian.
- Images whose new directions are drawn in 2D rather than fitted: shadows, glows and other effects.
- The nuclear missile looks alike from most directions, so its camera can't be measured.
