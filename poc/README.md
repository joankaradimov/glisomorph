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
   - Characters get a baked shadow, made from their new outline the way the originals' were (see
     [Shadows](#shadows)).

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
- shading from lights fixed to the camera, which differs from one direction to the next;
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
  (0.4, 0.75, 0.5): upper right and in front. It confirms that the lights were fixed to the camera.
  (The baked shadows fall the same way in every direction too, but no light casts them: see
  [Shadows](#shadows).)
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

Character sprites carry a baked shadow: solid index 0 on the ground beside the character, falling the
same way on screen in every direction, behind the character and a little to the left. No light casts
it in 3D. Each shadow is the sprite's own outline, transformed in 2D (`shadow.py`):

- **Squashed and sheared.** A pixel h rows above the *ground row* goes to h/3 rows above it and
  0.26 h pixels to the left (then one pixel right and 1.75 up). Where the outline itself is, the
  sprite covers the shadow.
- **About a ground row that stays put.** The ground row is fixed for each direction of an
  animation: the lowest row of the outline in its first frame. When the feet move, the ground
  doesn't.

One rule for everything: it reproduces the originals' shadows at 0.944 IoU over 712 cells (the
warrior, rogue, zombie and skeleton standing, the warrior's and the zombie's walks and the warrior's
attack, every frame, all 8 directions), the worst cell at 0.87. New cells get their shadows the same
way, from their own outlines; a new direction's ground row comes from its own first frame. (Black
pixels inside the model are part of its texture, so only groups of index-0 pixels that touch the
background count as an original's shadow.) So a shadow tells nothing about the shape that its own
sprite doesn't.

**How it was found.** The shadows were first cast in 3D, by a light that turned with the camera, found
by searching for the shadows that best match the originals': a ground point was shaded if the
reconstruction blocked its way to the light. The best light (20° to the right of the camera and 55°
above the ground, for every sprite) reached only 0.5 IoU, and the new cells' shadows, rounder than
the originals', made animations flicker where the two alternate. It couldn't have been right: even
the warrior's visual hull, which contains the real model, casts no shadow that covers more than 83%
of the originals', under any light and ground. Fitting the model to cast the originals' shadows, in the hope
that each would show the shape from another direction, only bent the model out of shape. A 2D
transform of each sprite's own outline fitted at once, with the ground row at each cell's lowest
pixel; the attack, whose feet move, then showed that the ground row is the first frame's.

**Black texture.** Fits and scores used to treat every index-0 pixel of a character as transparent,
including the black inside the model: 1.2% of the warrior's pixels, mostly the straps across his
chest (the zombie and the rogue have none). Now only the baked shadow is transparent (`masks_for` in
scene.py), and the model's colors can snap to black. A few pixels of shadow, seen through gaps
between the legs, don't touch the background either, so they count as texture now; counting diagonal
contacts would catch some of them, but also some of the straps.

| Warrior, SW hidden: IoU / exact / RGB error | Before | After |
|---------------------------------------------|--------|-------|
| Stance, voxels' relit copied pixels | 0.865 / 23.3% / 16.0 | 0.869 / 24.5% / 15.7 |
| Stance, Gaussians' copied pixels | 0.857 / 22.3% / 17.5 | 0.862 / 23.1% / 17.1 |
| Walk, moving Gaussians' relit copied pixels | 0.805 / 29.2% / 15.4 | 0.814 / 30.5% / 14.9 |

The fitted directions gain most, their silhouettes no longer holed by the straps: 0.977 to 0.987 IoU
with voxels. Other tables in this README predate the fix.

**Results** (IoU with the originals' shadows, warrior standing, SW hidden):

| Shadow | Fitted directions | Hidden direction |
|--------|------------------:|-----------------:|
| the originals' own outlines, by the rule | 0.94 | 0.94 |
| a voxel fit's outlines, by the rule | 0.93 | 0.68 |
| a Gaussian fit's outlines, by the rule | 0.88 | 0.80 |
| cast in 3D by the best light, from the voxel fit (before) | 0.51 | 0.46 |

A new direction's shadow is only as good as its outline, whose silhouette IoU is 0.86 or so; a
row's difference in its lowest pixel moves the whole shadow.

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
- **Nothing flickers.** From one frame to the next, 71% of the new directions' pixels change color,
  against 68% for the originals (walking moves most pixels). Their shadows change by 43% of their
  area per frame, against 41% for the originals' baked shadows.

**`animate.py`** does all this for a whole animation. It fits every frame on all 8 directions, with
frame 0's camera shared, gives the new directions shadows by the rule in [Shadows](#shadows), and
writes the animation in 16 directions to `out/<preset>-16/`:
- `sheet.png`: a row per direction (from S clockwise, originals and new ones alternating) and a
  column per frame, at the frames' own size and anchor, in the palette, with index 255 transparent;
- `directions.gif`: the 16 directions animated at the game's speed (a frame per 50 ms tick, as
  walks and attacks play), to watch.

```
python -m poc.animate --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk
```

With `animate.py` (and the lighting model), the new directions move and change like the originals:

| Animation | Directions | Sideways per frame | Pixels changing per frame | Shadow changing per frame |
|-----------|------------|-------------------:|--------------------------:|--------------------------:|
| Warrior's walk, 8 frames | originals | 0.19 px | 68% | 41% |
| | new | 0.20 px | 71% | 43% |
| Zombie's walk, 24 frames | originals | 0.57 px | 66% | 28% |
| | new | 0.61 px | 71% | 30% |
| Warrior's attack, 16 frames | originals | 1.44 px | 68% | 45% |
| | new | 1.42 px | 72% | 45% |

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
unlit for now: a color each, with no lighting model.

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

**Supersampled fitting.** A pixel of an original is an average: over edges it partly covers, and
colors that mix within it. Rendered once at each pixel's center, Gaussians can't match that. So by
default they're now fitted with every pixel the average of 16 x 16 samples (`fit.py --supersample`).
Rendered that way and snapped to the palette, the fit reproduces the originals far better:

| Warrior, all 8 directions | Silhouette IoU | Exact | RGB error | Fit |
|---|---:|---:|---:|---:|
| 1 sample per pixel | 0.941 | 61.0% | 6.0 | 27 s |
| 2 x 2 | 0.951 | 72.8% | 3.7 | |
| 4 x 4 | 0.983 | 86.1% | 1.6 | |
| 8 x 8 | 0.998 | 88.8% | 1.1 | 31 s |
| 16 x 16 | 0.999 | 89.6% | 1.0 | 69 s |

A hidden direction gains less: with SW hidden, its copied pixels get a silhouette IoU of 0.875
against 0.862, and an RGB error of 16.7 against 17.1 (8 x 8 and 16 x 16 alike). Its shadow can move
by a row: with the new outline's lowest pixel a row lower, the shadow hangs a row lower too.

**Fitting the palette.** The sprites' pixels were snapped to Diablo's palette, and their transparency
is one bit, but the Gaussians are fitted to the squared distance from each pixel's palette color, and
to full opacity. `--snap T` fits colors as they'll be snapped instead: by cross-entropy over the
palette's colors, softened by the temperature T, so that any color nearest the right palette color
will do. `--keyed` does the same for transparency: any opacity above a half is solid. Both are
options of fit.py (Gaussians) and of motion.py's refinement, off by default. On the warrior's stance
(SW hidden) and the zombie's walk (moving Gaussians, 4 x 4, odd frames hidden):

| IoU / exact / RGB error | Fitted cells, own colors | Hidden cells, own colors | Hidden cells, copied |
|---|---|---|---|
| Stance: squared distance | 1.000 / 93.8% / 0.59 | 0.820 / 17.0% / 17.0 | 0.820 / 26.2% / 16.2 |
| Stance: `--snap 0.0005` | 1.000 / 99.2% / 0.02 | 0.815 / 17.5% / 16.8 | 0.815 / 26.0% / 16.5 |
| Stance: `--snap 0.002 --keyed` | 1.000 / 98.9% / 0.03 | 0.804 / 15.9% / 17.0 | 0.804 / 24.4% / 17.4 |
| Zombie: squared distance (two runs) | 0.967–0.968 / 72.6–73.2% / 4.1–4.2 | 0.921–0.926 / 55.9–56.4% / 6.7–6.8 | 0.921–0.926 / 54.0–54.3% / 7.0–7.1 |
| Zombie: `--snap 0.0005` | 0.958 / 82.9% / 2.1 | 0.912 / 57.3% / 6.3 | 0.912 / 53.5% / 7.4 |

- **The fitted cells come back nearly exact, but half the stance's gain is in how it's scored.** The
  squared distance fits colors as rendered over black (times opacity), and snapping divides the
  opacity out, so partly covered edge pixels snap brighter than they were fitted. Scored the way it
  was fitted, the stance's squared distance is 96.6% exact, against 99.2% with `--snap 0.0005`; the
  misses left were colors landing next to the right palette color.
- **Hidden cells don't gain:** what they get wrong is the color itself (an unlit still gives a
  surface one color, a compromise between the views' shading), not how it's matched to the palette.
  The moving Gaussians' own colors, lit, gain a point.
- **Outlines lose a point or so,** with `--keyed` on the stance and with `--snap` on the zombie, and
  the copied pixels with them.

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
   Gaussian from a pixel or so away, and a leg moves several pixels per frame (a sword, tens), so
   two things pull from further: blurred copies of the images, and optimal transport from the
   model's surface to the surface of that frame's still (see [Fast motion](#fast-motion), below).
   The images are blurred by 4, 2 and then 1 pixels, in three stages of up to 266 iterations, and
   a stage ends once its image loss hasn't improved for 50 iterations (`--patience`).
3. The rest shape and the colors are refitted to all frames at once, through the tracked motion
   (see [The shape from every frame](#the-shape-from-every-frame)).
4. A phase between frames interpolates the node poses periodically.

Ending the stages early takes a quarter off the tracking of the warrior's walk and a fifth off the
zombie's, and scores the same within the noise. The attack's swing keeps improving to the end of
most stages, so it saves only 5% there:

| Copied pixels: IoU / exact / RGB error | Every stage in full | Ending early | Tracking iterations |
|---|---|---|---|
| Warrior's walk, SW hidden | 0.817 / 30.1% / 15.0 | 0.820 / 29.8% / 15.0 | 5,586 → 4,176 |
| Zombie's walk, odd frames hidden | 0.906 / 51.1% / 8.4 | 0.907 / 51.1% / 8.4 | 8,778 → 6,976 |
| Attack, odd frames hidden | 0.810 / 38.4% / 15.4 | 0.804 / 38.1% / 15.5 | 5,586 → 5,318 |

The frames' stills are saved, and reused by later runs (`--refit-stills` fits them again). The
tables before [Fast motion](#fast-motion) were measured with the first tracker, which matched
nearest neighbours instead, and a refinement of everything (now `--refine all`): all frames
together, the last tied to the first, the node paths kept smooth, and each Gaussian given a small
correction of its position per frame, on top of the nodes' motion.

The output samples the torus at twice the resolution on both axes: 16 directions by twice the
frames. Its GIF plays them at the game's speed, so at twice the frame rate: 40 frames a second.

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

**Shadows.** The sheet shows the originals with their baked shadows, and the new cells over shadows
made by the rule in [Shadows](#shadows): each cell's outline, about its direction's ground row, the
lowest row of frame 0's outline there (an original's, or in a new direction, the copied frame 0's).
The Gaussians first cast shadows in 3D instead, from a shadow map (the posed Gaussians rendered from
the fitted light), and those were rounder than the originals'. Where the two alternate, in the
original directions' in-between frames, the zombie's shadows jumped from frame to frame: their area
changed by 25 pixels on average (12%), against 5 in the new directions, where all are generated. By
the rule, it changes by 8. On the warrior's walk with SW hidden, the hidden direction's shadows match
the originals at 0.72 IoU (0.50 from the shadow map).

**Lighting.** The moving Gaussians have the voxel field's lighting model too (on by default,
`--lighting none` to leave it out): colors become albedo, shaded by a light fixed to the camera, with
an ambient term and a highlight. The light is held where the voxel fits find it (see Fast motion,
below, for why). A Gaussian's normal is its thinnest axis (they're mostly flat),
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

#### Fast motion

The warrior's attack (16 frames) swings a sword: between frames 7 and 9, its tip moves more than
30 pixels a frame. The first tracker drew each Gaussian to its nearest same-colored Gaussian in the
frame's still, and lost the sword at the swing: its Gaussians were pulled onto the body next to
them, and the refinement then faded it out in every frame. Three changes keep it.

- **Optimal transport instead of nearest neighbours.** The model as it is and the frame's still both
  become surface points: one per solid pixel of each known direction, at its depth, with its color.
  Unbalanced optimal transport (entropic, by Sinkhorn iterations) matches the two, and each Gaussian
  is pulled to where the surface around it goes, matched again every 200 iterations. Transport has
  to send each part somewhere with room for it, so the sword goes to where the sword is now, not
  onto the body. Counting pixels rather than Gaussians matters too: a still's blade is many faint
  Gaussians, which the old matching, taking only opaque ones, didn't see at all.
- **No refining of the motion.** Refining everything after tracking faded the sword anyway: opacity
  is shared by all frames, and a blade a pixel off in some of them is only ever pushed toward
  transparent. It also made the copied pixels worse (the table's "refining everything"). The known
  cells fit closer, but the frames agree less on where each surface point is, which is what copying
  relies on.
- **A fixed light.** Fitted along with a color per Gaussian, the light drifted anywhere, from straight
  overhead to almost none (the colors can explain the shading), and relighting suffered: 27.8% exact
  against 30.9% on the walk. It's now held where the voxel fits of every sprite find it.

| Copied pixels: IoU / exact / RGB error | Before | Now | Refining everything | Baseline: the previous frame |
|---|---|---|---|---|
| Attack, odd frames hidden | 0.770 / 29.6% / 18.5 | 0.791 / 38.2% / 15.8 | | 0.649 / 29.3% / 18.5 |
| Attack, SW hidden | 0.811 / 23.1% / 18.2 | 0.848 / 26.7% / 18.1 | | |
| Warrior's walk, SW hidden | 0.814 / 30.5% / 14.9 | 0.823 / 30.9% / 14.7 | 0.815 / 28.5% / 15.3 | |
| Zombie's walk, odd frames hidden | 0.913 / 36.1% / 12.9 | 0.877 / 49.8% / 9.0 | 0.913 / 36.2% / 12.6 | 0.791 / 35.4% / 13.1 |

"Before" is the first tracker with everything refined (the zombie's, unlit); "refining everything"
is the new tracker with `--refine all` and the fixed light. The same settings vary by about half a
point of exact pixels from run to run.

- **The attack keeps its sword,** and in the in-between frames it sweeps through the swing. With
  every other frame hidden, the in-between frames beat repeating the previous one by 9 points of
  exact pixels, with far better silhouettes. The blade breaks up in copied pixels, as thin parts do
  everywhere (see Next steps).
- **The colors gain most:** 14 points of exact pixels on the zombie.
- **Refining everything still gives better silhouettes on the zombie** (0.913 against 0.877), and
  the known cells' own colors fit closer (the walk's: 53% exact against 44%); but its copied pixels
  are worse, and those are what the sheets show.

"Now" in this table refined only the colors after tracking. The rest shape is now refitted too:

#### The shape from every frame

Frame 0's still sees the model from 8 directions. As an animation's parts move, the other frames
show them from more: a forearm turning, a sword swinging. So after tracking, the rest shape (the
Gaussians' positions, turns and sizes) is refitted to every frame's views at once, through the
tracked motion (`--refine shape`, the default; `--refine colors` refits only the colors). The motion
stays as tracked, and the opacities as they were, so that nothing fades and every frame is the same
shape, moved.

| Copied pixels: IoU / exact / RGB error | Colors only | Shape too |
|---|---|---|
| Zombie's walk, odd frames hidden | 0.877 / 49.8% / 9.0 | 0.902 / 51.9% / 8.0 |
| Attack, odd frames hidden (two runs each) | 0.791–0.796 / 38.2–39.0% / 14.6–15.8 | 0.806–0.811 / 37.3–39.2% / 14.6–16.2 |
| Warrior's walk, SW hidden | 0.825 / 31.1% / 14.6 | 0.828 / 30.6% / 14.7 |

- **Silhouettes improve everywhere,** most on the zombie, whose 24 frames show it from the most
  directions, and its colors with them. The known cells fit closer too: the zombie's go from 48% to
  64% exact.
- **The blade gains a little.** Of the attack's thin pixels (what a 5 × 5 opening removes from its
  outline: mostly the sword), the hidden frames cover 72% and get 25% exact, against 68% and 24%
  refining only the colors, and 51% and 17% repeating the previous frame. Where the sword swings
  fastest, hiding every other frame leaves too much between frames, and every version loses it.
- **Refining the motion with the shape was worse,** even with each frame still pulled to its still
  by transport: 0.743 silhouette IoU on the attack's hidden frames, and fewer thin pixels (60%
  covered).
- Runs of the attack vary by a point or two in exact pixels and RGB error, so its colors are a tie.

**Interpolating along screws didn't help.** Between frames, each node's rotation and move are
interpolated apart (periodic Catmull-Rom), so a node swinging around a joint cuts across its arc.
Blending the nodes' rigid motions as dual quaternions follows the arc instead, but the tracked nodes'
rotations are too loose for that. Scored on the same saved models (`--load` scores a saved
motion.pt again, without tracking), the attack's hidden frames came out worse (0.789 silhouette IoU
against 0.811, and 69% of the thin pixels covered against 72%), and the walks the same. Where the
sword is lost at the fastest part of the swing, it's already lost in the tracked frames on either
side, not between them.

#### Supersampled

Like the stills (see [Supersampled fitting](#gaussians)), the moving Gaussians make each pixel the
average of 4 x 4 samples (`--supersample`; 1 for one sample per pixel): in tracking, in the
refinement, and in the surfaces the transport pulls toward. The frames' stills are fitted alike
(`--still-supersample` follows `--supersample`), and saved apart from stills sampled otherwise.
Stills fitted finer than the moving Gaussians render don't suit them: with 16 x 16 stills and one
sample per pixel, the tracking loss tripled.

| IoU / exact / RGB error | 1 sample per pixel | 4 x 4 | 16 x 16 |
|---|---|---|---|
| Zombie's walk: known cells, own colors | 0.942 / 62.6–63.5% / 5.7–5.8 | 0.967–0.968 / 72.6–73.2% / 4.1–4.2 | 0.972 / 72.8% / 4.2 |
| Zombie's walk: odd frames hidden, copied | 0.903–0.907 / 50.6–51.1% / 8.4–8.5 | 0.921–0.926 / 54.0–54.3% / 7.0–7.1 | 0.923 / 53.4% / 7.5 |
| Warrior's walk: known cells, own colors | 0.922 / 54.5% / 7.1 | 0.948 / 65.2% / 4.7 | |
| Warrior's walk: SW hidden, copied | 0.820 / 29.8% / 15.0 | 0.820 / 30.3% / 14.6 | |
| Attack: known cells, own colors | 0.907 / 39.8% / 10.0 | 0.925 / 49.4% / 7.7 | |
| Attack: odd frames hidden, copied | 0.804 / 38.1% / 15.5 | 0.802 / 38.6% / 15.3 | |

(Ranges: the zombie's two runs of each.)

- **The known cells gain ten points of exact pixels,** as the stills did.
- **The zombie's hidden frames gain three,** well beyond the runs' spread, and lose the bright specks
  on its legs. The warrior's hidden direction and the attack's hidden frames gain a little color,
  within the noise. The attack still loses its sword where it swings fastest: that's tracking,
  which sampling doesn't change.
- **16 x 16 gains nothing more,** unlike the stills. Tracking and refining the zombie took 4.3
  minutes at one sample per pixel, 6.1 at 4 x 4 and 33 at 16 x 16, alone on the GPU. (Three runs
  sharing it take about three times as long each, so running them together saves nothing.)

## Higher resolution

The reconstructions render at any resolution, so sprites could be made larger than the originals.
Outlines can be drawn finer from the 3D shape, but new texture detail would have to come from
combining the originals: each sees a surface at other offsets below a pixel. `superres.py` measures
how much of it comes back:

```
python -m poc.superres --mpq PATH/TO/DIABDAT.MPQ --preset warrior --scale 2
```

There's no larger Diablo sprite to compare with, so the originals are the answer key. Each direction
is shrunk by the scale (pixels averaged in blocks, then snapped to the palette), and each method has to
bring the small sprites back to full size, from all 8 small sprites (known directions), or from 7,
making the 8th (a hidden direction). "Upscaled" repeats the small sprite's pixels: it has no new
information. The fits are Gaussians fitted to the small sprites, plainly or supersampled (`fit.py
--supersample` now works for Gaussians too: each pixel is the average of finer samples, so the model
can hold detail finer than a pixel).

| Warrior, 2x: IoU / exact / RGB error | Known directions | Hidden direction |
|---|---|---|
| upscaled | 0.862 / 41.9% / 9.0 | 0.779 / 18.5% / 18.1 |
| fit, copied pixels | 0.739 / 40.9% / 9.5 | 0.739 / 20.1% / 17.3 |
| supersampled fit, own colors | 0.852 / 17.6% / 18.3 | 0.775 / 8.7% / 25.5 |
| supersampled fit, copied pixels | 0.852 / 39.8% / 9.8 | 0.775 / 16.6% / 17.1 |

- **Nothing recovers detail yet.** In the known directions, nothing beats repeating the small
  sprite's pixels. The supersampled fit's own colors are noise between the small pixels: the eight
  views don't pin it down. They shade each surface differently (the light turned with the camera),
  the geometry is good to about a small pixel, and a surface point is seen from only a few
  directions, 45° apart.
- **A fit only renders finely if it was fitted finely.** Fitted at the originals' size, Gaussians
  are only ever seen at pixel centers, and rendered finer, they show holes between them (0.74
  silhouette IoU). Fitted supersampled, they hold together (0.85).
- **A synthetic answer key didn't work.** The first version used a supersampled fit of the real
  sprite as the truth, rendered finer: its detail below a pixel was the same kind of noise, which no
  method could, or should, recover.

### A clean look at 4x

Rendered at 4x, the Gaussians' own colors look scaly: between the originals' pixels nothing holds a
Gaussian's color to its neighbours'. With no answer key at 4x, the looks were judged by eye, with
the share of speckle (pixels at 4x unlike all four neighbours) as a number, and the fit checked at
1x, with SW hidden. The zombie's walk, frame 0, fitted 16 x 16 per pixel, rendered at 4x in two
fitted and two in-between directions:

| IoU / exact | Fitted, own colors | SW: IoU / own colors / copied | Speckle at 4x | Look at 4x |
|---|---|---|---|---|
| Plain | 1.000 / 97.1% | 0.923 / 20.6% / 23.9% | 5.8% | Scaly, streaky |
| Total variation at 4x (0.005) | 1.000 / 95.7% | 0.924 / 25.2% / 23.0% | 0.1% | Clean: flat patches |
| Colors pulled to the 8 nearest Gaussians' | 1.000 / 89.2% | 0.918 / 24.4% / 24.2% | 0.2% | Clean: soft gradients |
| No Gaussian under 0.5 px across | 0.968 / 80.8% | 0.919 / 21.0% / 25.0% | 0.0% | Clean, but soft |
| The same, on the two larger axes only | 0.999 / 91.5% | 0.918 / 19.1% / 23.8% | 0.9% | Brush strokes |
| 1.5 px voxels, no splitting | 0.998 / 86.3% | 0.918 / 17.2% / 23.8% | 1.6% | Still streaky |
| None longer than 4 times its width | 0.998 / 95.9% | 0.922 / 16.8% / 25.0% | 5.7% | As plain |
| The 0.5 px floor at render time only | 0.722 / 13.8% | 0.744 / 8.3% / 17.3% | 0.5% | Blotchy |

SW's own colors vary by about 2 points from run to run (20.6% to 22.8% exact, plain).

- **The scales come from each Gaussian having a color of its own,** not from their shapes: capping
  how long they are changes nothing. Tying colors together removes them, and leaves the outline as
  sharp as plain.
- **Total variation's weight:** from 0.005 up, the speckle is gone. Heavier, the patches grow and
  the fit loosens (the fitted cells 95.8% exact at 0.005, 83.2% at 0.02, 63.1% at 0.04), while SW's
  own colors creep up (22.3% plain, 25.6%, 26.1%, 27.3%) and its copied pixels stay put. Its patches
  follow the originals' pixels in fitted directions, and run in streaks in between.
- **A floor has to be fitted:** applied only to render, it bares inner Gaussians' colors.
- **Learned downsamplers didn't help.** One small CNN halving, shared by four levels (16 -> 8 -> 4 ->
  2 -> 1, each the 2 x 2 average plus a learned correction), took the coloring over: the Gaussians'
  colors drifted to gray and their opacity past 1, and the four levels put the color back step by
  step, so at 4x, two levels in, the sprite came out half colored. SW's copied pixels dropped from
  26.0% to 22.0% exact. A linear one, a shared symmetric filter [a, 1/2 - a, 1/2 - a, a] (a = 0 is
  the average), took a to the sharpest allowed, -1/8: the originals are crisper than an average.
  SW's outline got worse (0.903 against 0.914), 4x stayed streaky, and it fitted 5 times slower.

`motion.py --tv W` puts total variation in the moving Gaussians' refinement, on their samples (4 x 4
per pixel: the 4x image). On the zombie's walk, with odd frames hidden (rendered at 4x from the
saved models; rendering larger isn't in motion.py yet):

| Zombie's walk, 4 x 4 | Fitted cells, own colors | Hidden frames: own / copied | Outline | Look at 4x |
|---|---|---|---|---|
| Plain (two runs) | 72.6–73.2% | 55.9–56.4% / 54.0–54.3% | 0.921–0.926 | Scaly |
| `--tv 0.005` | 66.9% | 57.6% / 53.2% | 0.917 | Clean, painterly |
| Colors pulled to the 8 nearest (0.05) | 68.2% | 55.3% / 53.4% | 0.917 | Wrinkled, metallic |

Pulling colors together evens out only the albedo; lit, each Gaussian's normal still shades it a
little differently. Total variation, on the shaded samples, smooths both. It costs the 1x sheets
about a point of copied pixels, so it's off by default: it's for rendering larger.

**Edges.** At 4x, a thin blue-gray line ran around the sprite. It's in the originals: they were
rendered over a dark blue-gray background before it was keyed out, and their edge pixels kept a
share of it (`edges.py`). An outline pixel is close to a blend of its inside neighbours' color and
one background color, (34, 37, 50) for the zombie's walk and (29, 37, 57) for the warrior's, solved
separately; the blend halves the outline pixels' error (RMS 23 -> 10). At 1x it's a soft edge; at 4x
the outermost Gaussians, which learned it, draw it as a line, and copied pixels as bluish blocks.

- **Fitting the background didn't take it out.** With a learned background color behind the
  Gaussians (and 1-bit transparency, so that it can show), the fit painted the blue into the
  outermost Gaussians anyway: at 1x both explain the edge as well.
- **Taking it out of the originals did.** `--edges black`, now the default, redraws each blended
  edge pixel as if over black, pixel - (1 - coverage) x background (never as index 0, the shadows'
  black), before fitting and copying: the edges keep their falloff, without the blue. `--edges
  inside` gives them an inside neighbour's color instead, which leaves them too bright; `--edges
  none` keeps them. The fitted cells score as before (the zombie's walk, all frames: 66.4% exact
  against 66.5%), and the sheet's original cells keep their own edges.

**Legs.** Rendered at 4x from the model fitted to every other frame, the zombie's legs jumped
between some frames. Fitted to all 24 frames, they don't: the legs' silhouettes change from one
phase to the next as evenly as the originals' do from frame to frame (the largest change 1.81
times the median, in both), the largest where the artist's own stride is fastest.

## Next steps

- **Animations:** checked on two walks and an attack; the attack's sword swing needed the tracking
  of [Fast motion](#fast-motion). Hits, deaths and spells, and the other characters, are still to
  be seen; every animation needs its own preset, with its frame width.
- **Surfaces frame 0 hides:** the rest shape has only frame 0's Gaussians, refitted. Surfaces that
  only other frames show (the inside of an arm, the far side of a blade) could get Gaussians of
  their own. Densifying in the rest pose from every frame's views (gsplat's strategy, clones and
  splits following their Gaussian's nodes) tripled the Gaussians and made every test worse (the
  zombie's hidden frames: 0.885 IoU and 49.8% exact, against 0.902 and 51.9%), even the known
  cells' fit: with the opacities held, so that thin parts can't fade, new Gaussians can't find
  their own. Freeing only the new ones' opacities might work.
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
- **Lighting:** the shading light could be fitted once for the whole game and then held fixed: it
  comes out the same for every sprite (the moving Gaussians already hold it there).
- **Evaluation:** only the arrows have usable in-between directions. The fireball and the holy bolt
  aren't a rigid model turned: their flames trail along the direction of flight, and the
  reconstruction does worse than reusing the nearest direction. Characters can only be scored by
  hiding a direction, which is a harder, 45°, version of the task.
