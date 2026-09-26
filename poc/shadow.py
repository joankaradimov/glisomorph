"""Baked shadows for new directions.

Diablo's character sprites carry their own shadow: solid palette index 0 on the ground, under the
character. It was cast by a light that turned with the camera, so it falls the same way on screen
in every direction: behind the character, and a little to the left. A new direction gets its shadow
the same way. The ground point that a pixel sees is in shadow if the reconstruction blocks its way
to the light. The light's direction and the ground's height are fitted to the shadows of the known
directions.
"""

import math
from dataclasses import dataclass

import torch
import torch.nn.functional as F

from poc.field import VoxelField, pixel_rays, ray_box
from poc.reproject import neighbour


def light_directions(azimuth: torch.Tensor, elevation: torch.Tensor, right: torch.Tensor) -> torch.Tensor:
    """Unit vectors toward lights (B, 3) in the world, for a view with the given right vector.

    azimuth and elevation (B,), in degrees: the azimuth turns around the vertical from toward the
    camera (0) to the camera's right (90); the elevation is above the ground.
    """
    a, e = torch.deg2rad(azimuth)[:, None], torch.deg2rad(elevation)[:, None]
    toward = torch.stack([-right[2], torch.zeros_like(right[0]), right[0]])  # horizontal, toward the camera
    up = torch.tensor([0.0, 1.0, 0.0], device=right.device)
    return torch.cos(e) * (torch.sin(a) * right + torch.cos(a) * toward) + torch.sin(e) * up


@dataclass
class ShadowLight:
    azimuth: float    # degrees around the vertical, from toward the camera (0) to the camera's right (90)
    elevation: float  # degrees above the ground
    ground: float     # height of the ground (world y)

    def direction(self, right: torch.Tensor) -> torch.Tensor:
        """Unit vector toward the light (3,), for a view with the given right vector."""
        angles = torch.tensor([[self.azimuth], [self.elevation]], device=right.device)
        return light_directions(angles[0], angles[1], right)[0]


def shadow_opacity(field: VoxelField, origins, forward, lights, ground: float, samples: int):
    """Opacity (B, H, W) of the shadow on the ground under each pixel, for each of B lights.

    origins (H, W, 3) and forward (3,) are a view's rays, lights (B, 3) unit vectors toward the
    lights. A pixel's ray meets the ground (y = ground) at q, and the shadow there is how much light
    the reconstruction blocks between q and the light.
    """
    q = ground_points(origins, forward, ground)                                   # (H, W, 3)
    q = q[None].expand(len(lights), *q.shape)
    near, far = ray_box(q, lights[:, None, None, :], field.box_min, field.box_max)
    near = near.clamp(min=0)
    far = torch.maximum(far, near)
    step = (far - near) / samples                                                 # (B, H, W)
    t = near[..., None] + (torch.arange(samples, device=q.device) + 0.5) * step[..., None]
    points = q[..., None, :] + t[..., None] * lights[:, None, None, None, :]      # (B, H, W, S, 3)
    sigma = field.sigma(points.reshape(-1, 3)).view(t.shape)
    return 1 - torch.exp(-sigma.sum(-1) * step)


def shadow_mask(opacity: torch.Tensor, cover: torch.Tensor) -> torch.Tensor:
    """Where a view shows the shadow (H, W): ground whose shadow opacity (H, W), averaged over 3 x 3
    pixels to clean ragged edges, is at least a half, and that the model doesn't cover."""
    smooth = F.avg_pool2d(opacity[None, None], 3, stride=1, padding=1, count_include_pad=False)[0, 0]
    return (smooth >= 0.5) & ~cover


def baked_shadow(indices: torch.Tensor) -> torch.Tensor:
    """An original's shadow (H, W) bool: its index-0 pixels, without the black ones inside the model,
    which are part of its texture. The shadow lies on the ground, so it touches the background."""
    zero = indices == 0
    region = torch.zeros_like(zero)
    reach = indices < 0
    while True:
        grown = region | zero & (neighbour(reach, 0, False) | neighbour(reach, 1, False)
                                 | neighbour(reach, 2, False) | neighbour(reach, 3, False))
        if torch.equal(grown, region):
            return region
        region, reach = grown, grown


def iou(pred, target):
    """Intersection over union of masks (..., H, W) with a target (H, W)."""
    inter = (pred & target).sum((-2, -1)).float()
    union = (pred | target).sum((-2, -1)).float()
    return inter / union.clamp(min=1)


def ground_points(origins, forward, ground: float):
    """Where each pixel's ray (origins (H, W, 3), direction forward (3,)) meets the ground (y = ground)."""
    return origins + ((ground - origins[..., 1]) / forward[1])[..., None] * forward


def fit_light(scene, views: list[int], opacity=None, lowest=None) -> tuple[ShadowLight, float]:
    """The light and ground height whose shadows best match the given original views' baked shadows,
    and their mean intersection over union.

    opacity(origins, forward, lights, ground, fine) gives the shadow's opacity (B, H, W) on the
    ground under each pixel, for B lights; `fine` asks for full precision. By default it's marched
    through the scene's voxel field, and `lowest` (the model's lowest height, near which the ground
    is searched) comes from its occupied voxels. A coarse search over all directions (on every other
    pixel) is refined around the best one.
    """
    field = scene.field
    right, up, forward = scene.basis(scene.yaws)
    cases = []
    for j in views:
        v = scene.views[j]
        idx = torch.as_tensor(v.indices, device=scene.palette.device).long()
        target = baked_shadow(idx)
        cover = (idx >= 0) & ~target  # what the original's model hides of the shadow
        origins = pixel_rays(*v.shape, v.pivot, scene.offset, right[j], up[j], forward[j])[0]
        cases.append((origins, forward[j], right[j], target, cover))
    samples = scene.samples
    if opacity is None:
        def opacity(origins, forward, lights, ground, fine):
            return shadow_opacity(field, origins, forward, lights, ground, samples if fine else samples // 2)
    if lowest is None:
        # The ground is near the lowest part of the model.
        occupied = field.sigma(field.voxel_centers().view(-1, 3)) > math.log(2)  # half the light per voxel
        lowest = float(field.voxel_centers().view(-1, 3)[occupied, 1].quantile(0.001))

    def score(azimuths, elevation, ground, stride):
        """Mean IoU (B,) over the views, for lights at the given azimuths (B,) and one elevation, on
        every `stride`th pixel."""
        total = 0
        el = torch.full_like(azimuths, elevation)
        for origins, fwd, r, target, cover in cases:
            lights = light_directions(azimuths, el, r)
            s = (slice(None, None, stride),) * 2
            shade = opacity(origins[s], fwd, lights, ground, stride == 1)
            total = total + iou((shade >= 0.5) & ~cover[s], target[s])
        return total / len(cases)

    device = scene.palette.device
    best = (-1.0, None)
    azimuths = torch.arange(0, 360, 10, device=device, dtype=torch.float32)
    for ground in [lowest + d for d in range(-4, 5)]:
        for elevation in range(10, 90, 5):
            ious = score(azimuths, float(elevation), ground, 2)
            k = int(ious.argmax())
            if float(ious[k]) > best[0]:
                best = (float(ious[k]), ShadowLight(float(azimuths[k]), float(elevation), ground))
    coarse = best[1]
    best = (-1.0, None)
    azimuths = coarse.azimuth + torch.arange(-7.5, 7.6, 2.5, device=device)
    for ground in [coarse.ground + d for d in (-1, -0.5, 0, 0.5, 1)]:
        for elevation in [coarse.elevation + d for d in range(-4, 5)]:
            ious = score(azimuths, elevation, ground, 1)
            k = int(ious.argmax())
            if float(ious[k]) > best[0]:
                best = (float(ious[k]), ShadowLight(float(azimuths[k]) % 360, elevation, ground))
    return best[1], best[0]
