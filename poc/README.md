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

## Lighting model

`--lighting phong` (or `lambert`) replaces the field's plain colors with shading (`LitVoxelField` in
`field.py`):

- **Albedo:** a color per voxel.
- **Normals:** minus the gradient of the smoothed density.
- **Lights:** one or two directional lights (`--lights`). Each is a learned direction in *camera*
  space, with a learned strength, plus an ambient term and a Blinn–Phong highlight.

Diablo's sprites were rendered with lights fixed relative to the camera while the model turned. For
each view, the lights therefore become world directions through that view's camera basis. Shading
is deferred: albedo, normal and specular strength are accumulated along each ray, then shaded once
per pixel.

**Relit reprojection.** With a lighting model, a reprojected pixel's color is multiplied by the
target view's shading divided by the source view's shading at that surface point, then snapped back to
the palette. That corrects for the light having moved relative to the model between the two
directions.

**Results** on held-out directions. "Field" is the field's own colors quantized to the palette; RGB
error is the mean absolute difference, 0–255.

| Test | Silhouette IoU | Field: exact / RGB error | Best colors: exact / RGB error |
|------|---------------:|--------------------------|--------------------------------|
| Warrior, unlit | 0.864 | 14.5% / 20.9 | reprojected: 21.6% / 16.8 |
| Warrior, lit   | 0.867 | 18.3% / 18.2 | relit: 20.5% / 16.8 |
| Zombie, unlit  | 0.860 | 17.2% / 19.8 | reprojected: 22.1% / 17.1 |
| Zombie, lit    | 0.862 | 23.5% / 14.8 | relit: 24.1% / 15.3 |
| Arrow, unlit (22.5°) | 0.633 | 15.0% / 19.2 | reprojected: 37.1% / 13.2 |
| Arrow, lit (22.5°)   | 0.633 | 16.5% / 19.4 | reprojected: 38.1% / 12.6 |

- **The light is recovered consistently.** Fitted to each sprite separately, the single light comes
  out almost the same every time. In camera space (x right, y up, z toward the camera) it's about
  (0.4, 0.75, 0.5): upper right and in front. That matches the baked shadows, which always fall to the
  left, and confirms that the lights were fixed to the camera.
- **Normals mustn't reshape the geometry.** When shading gradients flowed into the density through
  the normals, the optimizer bent the shape to fake shading, and character silhouettes dropped from
  0.86 to 0.77–0.80 IoU. Normals are now computed from the density without passing gradients back
  (`--coupled-normals` restores the old behaviour).
- **The gain is moderate.** Lighting clearly improves the field's own colors, and relit reprojection
  is as good as or a little better than plain reprojection. The remaining roughness comes from noisy
  surfaces, not from lighting.

## Sub-pixel accuracy

`poc/diagnose.py` showed the largest share of held-out error was placement. Many pixels have the wrong
color family, but the right one is within a pixel. Two options target that:

- `--refine-camera`: after 300 iterations, the calibrated elevation and pivot offset are refined by
  gradient along with the field.
- `--supersample 2`: each pixel is rendered as the average of 2 x 2 sub-pixel rays (area sampling,
  like an anti-aliased render that was downsampled).

**Results** (reprojected colors, held-out directions):

| Test | Exact | Wrong ramp | Exact within 1 px | Silhouette IoU |
|------|------:|-----------:|------------------:|---------------:|
| Warrior, before | 22% | 44% | 51% | 0.864 |
| Warrior, refined + area-sampled | 20% | 44% | 55% | 0.87 |
| Zombie, before | 22% | 29% | 66% | 0.860 |
| Zombie, refined + area-sampled | 22% | 33% | 68% | 0.86 |
| Arrow, before | 37% | — | — | 0.633 |
| Arrow, refined + area-sampled | 38% | — | — | 0.732 |

- **The camera was already right.** Refinement moved the elevation by 0.3–0.8° and the pivot by at
  most 0.1 pixel.
- **Area sampling helps thin parts.** It lifted the arrow's silhouette overlap by 10 points, and does
  little for characters.
- **What misplaces pixels on characters:**
  - *Surface depth error.* At 45°, a depth error of about 1.4 voxels moves a reprojected pixel by a
    whole pixel, and the voxel field's surfaces are soft at that scale.
  - *Resampling itself.* Turning a texture to a new angle makes each output pixel pick one source
    pixel. That limits exact matches even with perfect geometry, so part of the gap is a ceiling for
    any method.

## Next steps

- **Shadows:** regenerate them by projecting the model onto the ground along the recovered light.
- **Cleaner surfaces:** a surface representation (2D Gaussian splatting or an SDF) instead of free
  voxels, for more accurate depth. The cameras are calibrated, so gsplat can be tried directly.
- **Coherent warps:** smooth the reconstructed depth before reprojecting, so that neighbouring pixels
  fetch from neighbouring source pixels. That targets the speckle rather than the exact-match score.
- **A ceiling:** render a known 3D model into 8 + 8 directions and run the pipeline on it. That would
  show how many exact pixels are achievable at all.
- **Texture:** blend reprojection from both neighbours by visibility and angle, and fill the holes.
- **Lighting:** tried; see above. The recovered light could also drive shadow regeneration, and could
  be fitted once for the whole game and then held fixed.
- **Evaluation:** only the missiles have real in-between directions. Characters can only be scored
  by hiding a direction, which is a harder, 45°, version of the task.
