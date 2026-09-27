# glisomorph

**Gli**ssando + **Isom**etric + **Morph**

Just as a **gl**issando glides between two musical notes, **iso**metric sprites can **morph**
smoothly between two frames. glisomorph synthesizes the frames in between, along two axes:

- **Time**: between consecutive animation frames, for smoother motion.
- **Space**: between adjacent facing directions, e.g. turning 8 directions into 16.

```text
direction ↓   time →
              f0      f1      f2
  S           ■   □   ■   □   ■
              □   □   □   □   □
  SW          ■   □   ■   □   ■
              □   □   □   □   □
  W           ■   □   ■   □   ■

  ■ original frame    □ interpolated frame
```

## Status

A proof of concept for Diablo 1, in [`poc/`](poc/README.md) (Python, PyTorch, gsplat). For each sprite, it:

1. **Reconstructs** the model in 3D from its 8 directions: as voxels, or as 3D Gaussians. An
   animation gets one set of Gaussians, moved from frame to frame.
2. **Renders** the new directions and frames from that reconstruction.
3. **Copies the artist's pixels** into them: each new pixel takes its palette index from the
   originals that see the same surface point, relit, so the output stays in the game's palette.
4. **Adds the baked shadow** the way the originals were made: the outline, squashed and sheared.

The game data readers are in `blizzard_common` (MPQ archives) and `diablo1` (palettes, CL2
sprites). Results and open problems are in [poc/README.md](poc/README.md).
