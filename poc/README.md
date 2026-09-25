# Proof of concept: in-between directions for Diablo 1 sprites

Reconstruct a sprite in 3D from its 8 (or 16) directions, then render the directions in between.
Only Diablo 1, only still frames.

## How it works

1. **Views.** Each direction of one animation frame is an orthographic view of the same model,
   turned by a known yaw: 45° steps for 8 directions, 22.5° for 16 (`views.py`).
2. **Calibration.** Search the camera elevation, a pivot offset and the sense of rotation for the
   visual hull that best explains every direction's silhouette (`fit.py`).
   - Diablo 1's camera sits about 24–28° above the horizon.
   - The directions share one rotation axis: `registration.py` finds no per-direction shifts.
   - The mirrored rotation is always clearly worse.
3. **Reconstruction.** A voxel radiance field in plain PyTorch (`field.py`), started from the visual
   hull and confined to it. It's fitted to the palette colors and silhouettes of the known directions.
   Baked shadows (index 0) count as transparent, because the model doesn't cover them.
4. **Rendering a new direction.**
   - The field gives the silhouette and the surface.
   - Colors are *reprojected* (`reproject.py`): each pixel takes the palette index that the nearest
     original direction shows at that surface point, if that direction can see it.
   - This keeps the artist's pixels, instead of re-quantizing blended colors.

```
python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset warrior --split all
python -m poc.zoom out/warrior-all-h0 --mpq PATH/TO/DIABDAT.MPQ --views 1 3
```

**Splits:**
- `all` uses every direction.
- `alternate` trains on every other direction; it's the real task for the 16-direction missiles.
- `holdout:K` hides direction K.

**Outputs** go to `out/` (gitignored: they're derived from game data):
- `metrics.json`;
- `compare.png`: truth, field colors and reprojected colors, for every direction;
- `in_between.png`: originals with a synthesized direction between each pair;
- `turntable.gif`: 32 directions.

## Results

**Metrics** (all on held-out directions):
- *Exact*: pixels whose palette index matches.
- *Ramp*: pixels in the same shade ramp.
- *IoU*: silhouette overlap.

The baseline reuses the nearest known direction unchanged.

| Test | IoU | Exact | Ramp | Baseline IoU / exact |
|------|----:|------:|-----:|---------------------:|
| Arrow, 16 directions, even → odd (the real 22.5° task) | 0.63 | 37% | 56% | 0.09 / 13% |
| Warrior, SW held out (45° from 7 others) | 0.86 | 22% | 56% | 0.40 / 6% |
| Zombie, SW held out | 0.86 | 22% | 71% | 0.32 / 14% |

On the directions they were trained on, the same fits get 95–99% of palette indices exactly right
where the silhouettes overlap. The representation isn't the limit; predicting unseen pixels is. (The
arrow ran with 0.6-pixel voxels, `--voxel 0.6`, for its 1-pixel shaft.)

**Pixel-perfect output isn't possible.** Even with the geometry right, an unseen direction's exact
pixels depend on things the other directions don't pin down:

- sub-pixel placement of edges and of thin parts, such as the arrow's 1-pixel shaft;
- texture detail at the scale of single pixels;
- shading from lights fixed to the camera: the warrior's shadow falls left of him in every direction;
- the original renderer's quantization to the palette.

**Does it look right? Mostly, at game scale.** The synthesized directions have the right silhouette,
pose and colors, and slot into the rotation plausibly. Up close there's speckle, thin parts such as
blades break up, and there are no shadows yet.

## Next steps

- **Shadows:** regenerate them by projecting the model onto the ground along the light, which is fixed
  relative to the camera and can be measured from the original shadows.
- **Cleaner surfaces:** a surface representation (2D Gaussian splatting or an SDF) instead of free
  voxels. Now that the cameras are calibrated, gsplat can be tried directly.
- **Texture:** blend reprojection from both neighbours by visibility and angle, and fill the holes.
- **Lighting:** model the camera-fixed light explicitly (albedo, normals and one light), so shading
  moves physically instead of being averaged.
- **Evaluation:** only the missiles have real in-between directions. Characters can only be scored
  by hiding a direction, which is a harder, 45°, version of the task.
