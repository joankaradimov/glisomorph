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
4. **Rendering a new direction** (`evaluate.py`).
   - The field gives the silhouette and the surface.
   - Colors are *reprojected* (`reproject.py`): each pixel takes the palette index that an original
     direction shows at that surface point, from a direction that can see it.
   - This keeps the artist's pixels, instead of re-quantizing blended colors.
   - The warp is kept coherent, so that neighbouring pixels fetch neighbouring source pixels, from
     the same direction (see [Coherent warps](#coherent-warps)).
   - Each pixel's material comes from the nearest source pixel, and its shade is interpolated
     between source pixels of that material (see [Shades](#shades)).
   - Characters get a baked shadow, cast by the reconstruction (see [Shadows](#shadows)).

```
python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset warrior --split all
python -m poc.evaluate out/warrior-all-phong1 --mpq PATH/TO/DIABDAT.MPQ --warp plain --out out/warrior-plain
python -m poc.zoom out/warrior-all-phong1 --mpq PATH/TO/DIABDAT.MPQ --views 1 3
```

`fit.py` saves the fitted scene and then runs `evaluate.py` on it. Running `evaluate.py` by hand
renders a saved fit again, for example with other reprojection settings, without fitting again.

**Splits:**
- `all` uses every direction.
- `alternate` trains on every other direction; it's the real task for the 16-direction missiles.
- `holdout:K` hides direction K.

**Outputs** go to `out/` (gitignored: they're derived from game data):
- `scene.pt`: the fitted field and its cameras;
- `metrics.json`;
- `views.npz`: the palette indices of every direction (truth, field colors, reprojected colors), and
  the shadows;
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
blades break up, and shadows were missing (see [Shadows](#shadows)).

## Lighting model

`--lighting phong` (the default; `lambert` leaves out the highlight, and `none` fits plain colors)
replaces the field's plain colors with shading (`LitVoxelField` in `field.py`):

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
  (0.4, 0.75, 0.5): upper right and in front. It confirms that the lights were fixed to the camera, as
  do the baked shadows, which fall the same way in every direction. (The shadows come from another
  light, though: see [Shadows](#shadows).)
- **Normals mustn't reshape the geometry.** When shading gradients flowed into the density through
  the normals, the optimizer bent the shape to fake shading, and character silhouettes dropped from
  0.86 to 0.77–0.80 IoU. Normals are now computed from the density without passing gradients back
  (`--coupled-normals` restores the old behaviour).
- **The gain is moderate.** Lighting clearly improves the field's own colors, and relit reprojection
  is as good as or a little better than plain reprojection. The remaining roughness comes from noisy
  surfaces, not from lighting.
- **With the later warps, it wins.** Once colors were copied coherently and with interpolated shades
  (see below), relit colors beat reprojected ones on 9 of the 11 held-out character directions: 24.0%
  exact against 21.4%, an RGB error of 17.2 against 18.1, and a blurred RGB error of 9.2 against 10.1,
  with the same speckle. So the lighting model is now the default.

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

## Coherent warps

Reprojection used to fetch every pixel on its own, and that speckled:

- **Noisy depth.** The field's depth is noisy at the scale of a pixel, so neighbouring pixels fetched
  from scattered places in the source.
- **Direction flipping.** Each pixel picked its own source direction. On a surface that two
  directions see equally well, as they do for an in-between direction, neighbouring pixels
  alternated between the two at random, and the two textures don't line up.

The warp now keeps neighbours together (`Warp` in `reproject.py`; `--warp plain` restores the old one):

1. **Median depth.** A pixel's depth is where its ray has gathered half its opacity, instead of the
   opacity-weighted mean. Where a ray grazes two layers, the mean falls between them, in empty space.
2. **Smoothing.** Every depth map, of the new direction and of the known ones, is replaced by robust
   local plane fits over 5 x 5 pixels. Depths across an edge get almost no weight, so edges stay
   sharp.
3. **A cost for each direction** that sees a surface point. Farther directions cost more, and so do
   directions that shade the surface differently from the new direction, since the light turned
   with the camera. The shading uses the light that the lighting model finds for every sprite (see
   above) and normals from the plane fits, so it works without a lighting model.
4. **One direction per region.** Inside a surface, neighbouring pixels also pay for using different
   directions, and iterated conditional modes settles the choice. Parts a pixel or two wide have no
   inside, and choose pixel by pixel: forcing one direction on the arrow's shaft cost 4 points of
   exact matches.
5. **Filling.** Pixels that no direction sees take a neighbour's color, instead of the field's own
   color, which nothing constrains there.

**Speckle metrics.**
- *Stray pixels*: pixels inside the silhouette whose color differs from all four neighbours' by
  more than 20 levels (0–255, mean over R, G and B). The originals have some too.
- *Blurred RGB error*: the RGB error after blurring both images slightly (σ = 1 pixel). It forgives a
  pixel of misplacement, and asks whether regions have the right colors.

**Results** (reprojected colors, held-out directions, averaged):

| Test | Warp | Exact | Same ramp | RGB error | Blurred RGB error | Stray pixels |
|------|------|------:|----------:|----------:|------------------:|-------------:|
| Characters, 11 directions (45°) | plain | 19.4% | 57.5% | 19.9 | 11.4 | 7.1% |
| | coherent | 20.8% | 58.4% | 18.5 | 10.2 | 5.5% |
| Arrow, 8 directions (22.5°) | plain | 37.1% | 55.5% | 13.2 | 7.1 | — |
| | coherent | 42.5% | 59.3% | 12.0 | 6.4 | — |

The characters are the warrior and the zombie with each diagonal direction held out in turn, and the
rogue with three of them. Their originals have 4.2% stray pixels. The arrow is too thin for the stray
pixel count to mean anything.

- **Speckle:** the stray pixels above the originals' rate fall by more than half, from 2.9 to 1.3
  points.
- **Colors improve too**, most on the arrow, where exact matches rise by 5 points.
- **With a lighting model**, relit colors gain the same way. On the zombie, stray pixels fall from
  4.9% to 1.6% (its originals have 1.0%), and the RGB error from 15.2 to 14.1.
- **At game scale** the in-between directions look cleaner, but not transformed: thin blades still
  break up.

**What each part does** (characters, leaving out one part at a time):

| Warp | Exact | Same ramp | RGB error | Blurred RGB error | Stray pixels |
|------|------:|----------:|----------:|------------------:|-------------:|
| coherent | 20.8% | 58.4% | 18.5 | 10.2 | 5.5% |
| without the shading cost | 20.4% | 59.6% | 18.8 | 11.1 | 5.5% |
| without one direction per region | 20.7% | 57.9% | 18.5 | 9.9 | 5.9% |
| without smoothing (so without the shading cost) | 19.8% | 58.1% | 19.4 | 11.0 | 5.7% |
| with the expected depth | 20.5% | 58.1% | 18.7 | 10.3 | 5.4% |
| without filling | 20.6% | 58.1% | 18.9 | 10.5 | 6.2% |

- **Smoothing and the median depth** matter most on the arrow. Its exact matches fall from 42.5% to
  36.5% without smoothing, and to 40.8% with the expected depth.
- **The shading cost** brings the largest color gain.
- **One direction per region** removes speckle, at a small cost in blurred error. Where neighbouring
  pixels alternate between two directions, a blur averages the two directions' shading, and that
  average is close to the new direction's.
- **Filling** removes the field's stray colors.

**Tried and dropped:**
- *Preferring the direction that sees a surface most squarely* (the least foreshortened): worse on
  exact matches and speckle, and the arrow lost about 4 points of exact matches.
- *A cost for source pixels on an outline*, next to the silhouette or a jump in depth: it traded
  exact matches and color error for ramp matches, and left speckle as it was.

**What's left.** Of the remaining stray pixels:
- about a third are copied from the originals, whose textures have stray pixels of their own;
- about 40% come from source pixels on an outline, where the colors are shaded for a grazing view
  or bleed from what's behind;
- the rest lie where the source direction switches (14%), or come from resampling (13%).

With the plain warp, another 16% were the field's own colors, in pixels that no direction sees.

Interpolated shades, added later, remove most of what's left of the speckle: see [Shades](#shades).

## Shadows

Character sprites carry a baked shadow: solid index 0 on the ground, under the character. The light
that cast it turned with the camera, so it falls the same way on screen in every direction: behind
the character and a little to the left. `shadow.py` gives a new direction its shadow the same way:

1. **Casting.** The ground point that a pixel sees is in shadow if the reconstruction blocks its way
   to the light: a ray is marched through the field, from the ground toward the light.
2. **Fitting the light.** The light's direction and the ground's height are searched for the shadows
   that best match the originals'. Black pixels inside the model are part of its texture, not
   shadow, so only groups of index-0 pixels that touch the background count.
3. **Drawing.** The shadow's opacity is averaged over 3 x 3 pixels, which cleans ragged edges, and
   drawn as index 0 wherever the model doesn't cover it.

`evaluate.py` does this for every sprite with baked shadows, and draws the shadows in all pictures.

**Results** (intersection over union with the originals' shadows; the 11 held-out character
directions from above):

| Shadow | Fitted directions | Held-out directions |
|--------|------------------:|--------------------:|
| cast by the reconstruction | 0.58 | 0.52 |
| the nearest original direction's, as it is | — | 0.26 |

- **The shadows' light is the same for every sprite.** Seen from the character, every fit puts it
  about 20° to the right of the camera and 55° above the ground (20–22.5° and 54–57°), for all three
  characters.
- **It isn't the light that shades the models.** Measured the same way, the lighting model's light is
  at about 73° and 65°, and shadows cast from it match the originals poorly (IoU under 0.2). The
  sprites were lit by more than one light, and the shadows come from one of the others.
- **The shapes match; the edges are off by a pixel or two.** The shadows have the right shapes, down
  to the streak of the warrior's sword. Most of the disagreement is a shift of a pixel or two along
  the edges, which costs a lot of overlap on shapes this thin.

## Shades

Even with coherent warps, the new directions looked blotchy. Up close, neighbouring pixels of one
material (one palette ramp) were too often flat duplicates or abrupt jumps of several shades, and
too rarely one-step gradients. That's what copying the nearest source pixel does: where a surface is
magnified, pixels are duplicated, and a pixel of misplacement jumps across a gradient.

| Neighbouring pixels of one material, shades apart | 0 | 1 | 2 | 3+ |
|---------------------------------------------------|--:|--:|--:|---:|
| originals | 47% | 35% | 11% | 6% |
| coherent warp | 49% | 29% | 11% | 10% |
| coherent warp, interpolated shades | 49% | 34% | 10% | 7% |

(The 11 held-out character directions.)

Diablo 1's palette is organized in ramps: runs of one hue from light to dark (`ramps.py`). So a
pixel's index says two things, its material (the ramp) and its shade (the step along the ramp), and
the warp now treats them differently (`Warp.interpolate`):

- **The material** comes from the nearest source pixel, as before.
- **The shade** is interpolated bilinearly between the neighbouring source pixels of the same material
  and surface, and snapped to the nearest shade of that ramp.
- **Relighting**, with a lighting model, changes only the shade too: the relit brightness is snapped
  to the pixel's own ramp, instead of to any palette color.

**Results** (held-out directions):

| Test | Shade | Exact | RGB error | Blurred RGB error | Stray pixels |
|------|-------|------:|----------:|------------------:|-------------:|
| Characters, 11 directions | nearest | 20.8% | 18.5 | 10.2 | 5.5% |
| | interpolated | 21.4% | 18.1 | 10.1 | 4.6% |
| Characters with a lighting model, 2 directions (relit colors) | nearest | 23.2% | 15.3 | 8.2 | 1.9% |
| | interpolated | 25.6% | 14.7 | 8.1 | 1.3% |
| Arrow, 8 directions | nearest | 42.5% | 12.0 | 6.4 | — |
| | interpolated | 42.3% | 11.8 | 6.4 | — |

- **The texture now matches the originals'.** Stray pixels are within half a point of the
  originals' rate (4.2% for the 11 character directions, 1.2% for the 2 lit ones), and the spread of
  shade steps is close to theirs.
- **Colors improve a little** on characters; the arrow's stay about the same.
- **With the lighting model, relit colors are the best so far**: 25.6% exact on the warrior's and the
  zombie's held-out SW (from 22.4% with the plain warp).

## Motion

Every test above is a single frame. In the game, a new direction plays whole animations, so each
frame is fitted on its own and the new directions must not flicker or wobble as they play. The
check: the warrior's walk in the dungeon (`--preset warrior-walk`, 8 frames), fitted on all 8
directions frame by frame, with the 8 new directions rendered for every frame.

```
python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --split all --frame 0 --tag f0
python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --split all --frame 1 --tag f1 --camera out/warrior-walk-all-phong1-f0
```

- **Each frame calibrated its own camera, and the new directions wobbled.** Silhouettes pin the
  camera down to about a pixel: across the 8 frames, the elevation came out between 25° and 26°,
  and the pivot offset varied by a pixel sideways. The new directions moved sideways by 0.39 pixels
  per frame on average, twice as much as the originals (0.19).
- **`--camera` shares one camera.** Frames 1–7 take frame 0's camera instead of calibrating, and the
  new directions then move like the originals: 0.18 pixels per frame.
- **Nothing flickers.** From one frame to the next, 72% of the new directions' pixels change color,
  against 68% for the originals (walking moves most pixels). Their shadows change by 38% of their
  area per frame, against 41% for the originals' baked shadows, although each frame fits its own
  shadow light.

**`animate.py`** does all this for a whole animation. It fits every frame on all 8 directions, with
frame 0's camera shared, fits the shadows' light once, and writes the animation in 16 directions
to `out/<preset>-16/`:
- `sheet.png`: a row per direction (from S clockwise, originals and new ones alternating) and a
  column per frame, at the frames' own size and anchor, in the palette, with index 255 transparent;
- `directions.gif`: the 16 directions animated, to watch.

```
python -m poc.animate --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk
```

With `animate.py` (and the lighting model), the new directions move and change like the originals:

| Animation | Directions | Sideways per frame | Pixels changing per frame | Shadow changing per frame |
|-----------|------------|-------------------:|--------------------------:|--------------------------:|
| Warrior's walk, 8 frames | originals | 0.19 px | 68% | 41% |
| | new | 0.20 px | 72% | 37% |
| Zombie's walk, 24 frames | originals | 0.57 px | 66% | 28% |
| | new | 0.61 px | 71% | 29% |
| Warrior's attack, 16 frames | originals | 1.44 px | 68% | 45% |
| | new | 1.41 px | 73% | 47% |

(The attack's frames are 128 pixels wide: `--preset warrior-attack`.)

## Gaussians

The voxel field is soft at the scale of a pixel, and nothing in it is thinner than a voxel. A 3D
Gaussian can be a fraction of a pixel thick and turned any way. `gaussians.py` represents a sprite
with them, rendered by [gsplat](https://github.com/nerfstudio-project/gsplat)'s rasterizer in its
orthographic mode, which is exactly the turntable camera: one pixel per world unit, with the world
origin at the pivot. It has the voxel field's `render()`, so copying pixels, scores and pictures work
unchanged.

```
python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset warrior --split holdout:1 --model gaussians
```

A Gaussian starts at each voxel of the visual hull. All directions are rendered in one call per
step, and gsplat's densification clones and splits Gaussians where the views pull hardest. They're
unlit for now: a color each, no lighting model and no shadows.

**Setup.** gsplat compiles CUDA code, and PyTorch only builds extensions against a CUDA toolkit of
its own major version. On Windows, this worked:
- PyTorch built for CUDA 13 (`torch==2.11.0+cu130`), the CUDA 13.2 toolkit, and Visual Studio 2022's
  compiler (from `vcvars64.bat`);
- gsplat 1.5.3 installed from a clone of its source, with submodules (`pip install
  --no-build-isolation .`), so that it compiles once, at install time;
- `NVCC_FLAGS=-Xcompiler /Zc:preprocessor`, because CUDA 13's headers refuse MSVC's traditional
  preprocessor;
- the Python environment's own `ninja` first on `PATH`: MSYS2's runs commands through `/bin/sh`,
  which mangles Windows paths;
- `TORCH_CUDA_ARCH_LIST` set to the GPU's architecture, to compile for it alone.

**Still results** (held-out directions):

| Test | Model | Silhouette IoU | Copied pixels: exact / RGB error |
|------|-------|---------------:|----------------------------------|
| Warrior's stance, SW hidden | voxels | 0.864 | 22.6% / 16.5 |
| | Gaussians | 0.854 | 22.5% / 17.5 |
| Warrior's walk, SW hidden in all 8 frames | voxels (lighting model, relit) | 0.754 | 30.2% / 15.3 |
| | Gaussians | 0.803 | 26.8% / 16.2 |

- **They fit five times faster:** 19 seconds for 3,000 iterations.
- **Their silhouettes** are about as good on the stance, and better on the walk.
- **Their own colors** are much cleaner than the voxels': 4.1% stray pixels against 12.4% on the
  stance, 2.9% against 6.7% on the walk. Blades stay whole in them. With copied pixels, the blades'
  zigzag comes back.
- **Copied pixels are still better colored with voxels**, because only voxels have the lighting
  model, and so relighting, so far.

### Moving Gaussians

`motion.py` fits a whole looping animation with one set of Gaussians. A looping animation is a
torus: the directions go around one circle, and the frames around another. A direction is the
camera turning around the model, which calibration already knows. A frame is the model changing
pose, which has to be learned. So the Gaussians' shape, opacity and color are shared by every
frame, and a few hundred nodes move them, as in SC-GS (embedded deformation). Each node has a
rotation and a translation per frame, each Gaussian follows its 4 nearest nodes, and neighbouring
nodes are held rigid to each other.

```
python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk
python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --hide-direction 1
python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --hide-frames odd
```

1. Every frame is fitted as a still. Frame 0 calibrates the camera, and its Gaussians become the
   moving ones.
2. Frame by frame, the nodes move the Gaussians to fit the next frame's views. Images only pull a
   Gaussian from a pixel or so away, and a leg moves several pixels per frame, so two things pull
   from further: blurred copies of the images, and each Gaussian's nearest same-colored Gaussian in
   that frame's still (a chamfer distance, recomputed now and then, as in ICP).
3. All frames are refined together, the last tied to the first, with the node paths kept smooth.
   Each Gaussian also gets a small correction of its position per frame, on top of the nodes'
   motion. That lets each frame match its views about as closely as a still, while the nodes carry
   the motion; the corrections are kept small, and alike between neighbours.
4. A phase between frames interpolates the node poses (and the corrections) periodically.

The frames' stills are saved, and reused by later runs (`--refit-stills` fits them again).

The output samples the torus at twice the resolution on both axes: 16 directions by twice the
frames.

- **Nodes are needed.** Moving every Gaussian on its own, held together only by its nearest
  neighbours (as in Dynamic 3D Gaussians), smeared the swinging legs: the frames' silhouettes fell to
  0.64–0.83 IoU. With 256 nodes, the walk moves coherently.

| Test | Nodes only: IoU / RGB error | With corrections: IoU / RGB error |
|------|----------------------------:|----------------------------------:|
| Warrior's walk, fitted frames and directions | 0.87 / 11.4 | 0.93 / 9.2 |
| Warrior's walk, SW hidden in all frames | 0.78 / 17.7 | 0.80 / 15.6 |
| Warrior's walk, odd frames hidden | 0.72 / 15.6 | 0.72 / 15.0 |
| Zombie's walk, odd frames hidden | | 0.91 / 13.0 |

The baseline for hidden frames is the previous frame repeated, as a game would show it: 0.71 / 13.9
on the warrior's walk, 0.79 / 13.1 on the zombie's.

- **The corrections close most of the fit gap.** The hidden direction then matches the stills'
  silhouettes (0.80), with better colors than theirs (an RGB error of 15.6 against 16.6).
- **In time, it takes frames close enough together.** With the zombie's 24 frames, hiding every
  other one leaves 12 per cycle, and the interpolated silhouettes overlap the truth far better than
  the repeated frame's (0.91 against 0.79), in colors as good as the artist's own pixels at the wrong
  pose.
- **The warrior's 8 frames, hiding every other one, are too few.** Between the 4 left, the legs pass
  each other, and nothing tells them apart: seen from the side, frames 0 and 2 look alike. So the
  tracker keeps each leg where it is, and the interpolated frames keep the legs apart when they
  should be passing. Tracking all 8 frames (the real task: 16 from 8), the feet do swing in opposite
  phase, crossing between frames 0 and 2, about 5 pixels either way.

**Copying pixels through time.** The moving Gaussians know where every surface point is in every
frame, so a new cell of the torus can take the artist's pixels across time as well as across
directions (`PixelCopier`). Each pixel's surface point, from the depth, is moved back to the rest
pose by inverting its nearest nodes' motion, then forward to each nearby original frame, and
projected into that frame's nearby directions. From there on it's reproject.py's warp: the original
that sees the point gives its palette index, nearer frames and directions cost less, regions keep
to one source, and shades are interpolated within the ramps. The sheet's new cells use it.

| Test | Model's own colors: exact / RGB error | Copied pixels: exact / RGB error | Baseline |
|------|------------------:|-----------------:|---------|
| Zombie's walk, odd frames hidden | 31% / 13.0 | 36% / 12.9 | the previous frame repeated: 35% / 13.1 |
| Warrior's walk, SW hidden (unlit) | 24% / 15.4 | 27% / 16.4 | voxels' relit copied pixels: 30% / 15.3 |

- **In time, copied pixels beat repeating the previous frame on every count but speckle** (1.6% stray
  pixels against 1.3%; the originals have 1.2%), with the pose right: 0.91 silhouette IoU against
  0.79.
- **Across directions, they need relighting.** The light turned with the camera, so a pixel copied
  from another direction is shaded for that direction. The voxel pipeline relights it with its
  lighting model, and so do the moving Gaussians now (see Lighting, below).
- **Rest positions mustn't be rendered as colors.** That was the first try, and a check that copying
  an original cell reproduces it failed (22% exact). A few Gaussians are several pixels wide, and
  rendered as a color, a Gaussian's rest position goes to every pixel it covers. Unposing each
  pixel's own surface point instead reproduces the original cell at 90–94% exact.

**Shadows.** Voxel shadows march rays through the density; Gaussians get a shadow map instead
(`shadow_map_opacity` in gaussians.py): the posed Gaussians rendered from the light, by another
orthographic camera, and each pixel's ground point looked up in it. One render per light direction
makes the light's fit (shadow.py's, which now takes any shadow function) quick. Fitted to frame 0 of
the warrior's walk, it finds the same light as the voxel fits (20° and 55°), matching the baked
shadows at 0.57 IoU, and 0.50 on the hidden direction. The sheet now shows the originals with their
baked shadows, and the new cells over generated ones.

**Lighting.** The moving Gaussians have the voxel field's lighting model too (on by default,
`--lighting none` to leave it out): colors become albedo, shaded by a light fixed to the camera, with
an ambient term and a highlight. A Gaussian's normal is its thinnest axis (they're mostly flat),
turned to face the camera, and shading is deferred: albedo, normal and highlight strength are
rendered, then shaded per pixel. The copier relights each copied pixel, from its source's shading
(the surface's normal turned back to the source frame by the nodes) to the new cell's, within its
ramp, and prefers sources that shade the point alike.

| Warrior's walk, SW hidden | Silhouette IoU | Exact | RGB error | Blurred RGB error |
|---------------------------|---------------:|------:|----------:|------------------:|
| Copied pixels, unlit | 0.81 | 27.9% | 16.2 | 10.4 |
| Copied pixels, relit | 0.81 | 29.2% | 15.4 | 9.2 |
| Voxels' relit copied pixels | 0.75 | 30.2% | 15.3 | 8.8 |

Relit, the moving Gaussians color a hidden direction almost as well as the voxel pipeline, with
better silhouettes. Their fit to the known cells improves too: 52% exact against 43% unlit.

## Next steps

- **Animations:** checked on two walks and an attack. Hits, deaths and spells, and the other
  characters, are still to be seen; every animation needs its own preset, with its frame width.
- **Few frames:** with every other frame of the warrior's walk hidden, the legs pass each other
  between the frames left, and tracking can't tell them apart (see Moving Gaussians). The real task,
  16 frames from 8, has enough of them; fewer would need some prior on how legs swing.
- **Lit stills:** fit.py's Gaussians are unlit; the moving Gaussians' lighting model would give the
  stills relit copied pixels too.
- **Cleaner surfaces:** 2D Gaussians (flat discs) would give sharper depth than 3D ones, but gsplat's
  2D rasterizer has no orthographic mode.
- **Thin parts:** blades and bows still break up. A blade's silhouette survives (its opacity stays
  above a half along its length), but its colors don't. The original blade is two lines, light and
  dark, and the warp's fetch positions zigzag between them, because the reconstruction's depth along
  something a pixel or two wide is poor. Blending the source colors across materials in parts under
  3 pixels wide, then snapping them to the palette, helped only a little: the arrow's exact matches
  rose from 42.3% to 43.8%, and the blades still zigzag. Finer voxels (0.6 pixels) didn't help
  either. Along the blade, pixels also alternate between source directions (in one new direction,
  30 of 60 came from one, 16 from another, 10 from a third), and extending one direction per region
  to thin parts doesn't hold them together: it changes nothing visible on the blades and costs the
  arrow 4.5 points of exact matches. Thin parts may need to be drawn rather than warped: a blade's
  centerline and its two tones, found in the originals, carried over as a line.
- **A ceiling:** render a known 3D model into 8 + 8 directions and run the pipeline on it. That would
  show how many exact pixels are achievable at all.
- **Blending:** where two directions see a surface about equally well, blend their colors and snap
  the blend to the palette, instead of picking one. That would trade some crispness for shading
  between the two directions'.
- **Lighting:** the lights could be fitted once for the whole game and then held fixed: the shading
  light and the shadows' light come out the same for every sprite.
- **Evaluation:** only the arrows have usable in-between directions. The fireball and the holy bolt
  aren't a rigid model turned: their flames trail along the direction of flight, and the
  reconstruction does worse than reusing the nearest direction. Characters can only be scored by
  hiding a direction, which is a harder, 45°, version of the task.
