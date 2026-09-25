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

Early days: no code yet.
