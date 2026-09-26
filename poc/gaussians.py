"""A sprite as 3D Gaussians, rendered by gsplat's orthographic rasterizer.

The alternative to field.py's voxels (fit.py --model gaussians). It sees the sprite through the same
turntable cameras and has the same render() interface, so the rest of the pipeline (reprojection,
scores, pictures) works unchanged. Unlike a voxel, a Gaussian can be much thinner than a pixel and
turned any way, which suits blades and surfaces.

gsplat's orthographic camera maps camera coordinates (x right, y down, z forward) to pixels as
f * x + c, without a perspective divide. With f = 1 and c at the pivot, that is exactly the
turntable camera: one pixel per world unit, the world origin at the pivot. The camera sits
`DISTANCE` back along its view, which only has to clear the model (gsplat culls Gaussians behind
the camera).
"""

import math
import time

import torch
import torch.nn.functional as F
from gsplat import rasterization
from gsplat.strategy import DefaultStrategy

from poc.field import pixel_rays, pool

DISTANCE = 1000.0


def viewmat(right, up, forward):
    """World-to-camera transform (4, 4), in gsplat's convention: x right, y down, z forward."""
    m = torch.eye(4, device=right.device)
    m[0, :3], m[1, :3], m[2, :3] = right, -up, forward
    m[2, 3] = DISTANCE
    return m


def intrinsics(pivot, offset, device, supersample: int = 1):
    """(3, 3): one pixel per world unit (times `supersample`), the world origin at the pivot plus the
    calibrated offset."""
    s = supersample
    offset = torch.as_tensor(offset, device=device, dtype=torch.float32)
    center = (torch.tensor(pivot, device=device, dtype=torch.float32) + offset) * s
    zero, one = torch.zeros((), device=device), torch.full((), float(s), device=device)
    return torch.stack([torch.stack([one, zero, center[0]]), torch.stack([zero, one, center[1]]),
                        torch.stack([zero, zero, torch.ones((), device=device)])])


def shadow_map_opacity(means, quats, scales, opacities, origins, forward, lights, ground: float, size: int = 256):
    """Opacity (B, H, W) of the shadow on the ground under each pixel, for each of B lights (unit
    vectors toward them): the Gaussians rendered from the light (a shadow map, orthographic, one pixel
    per world unit), looked up where each pixel's ground point falls. The counterpart of
    shadow.shadow_opacity, which marches through voxels."""
    from poc.shadow import ground_points
    device = means.device
    q = ground_points(origins, forward, ground)                                         # (H, W, 3)
    world_up = torch.tensor([0.0, 1.0, 0.0], device=device)
    blank = torch.zeros((len(means), 3), device=device)
    K = intrinsics((size / 2, size / 2), (0.0, 0.0), device)
    out = []
    for light in lights:
        forward_l = -F.normalize(light, dim=0)
        right_l = torch.cross(forward_l, world_up, dim=0)
        if right_l.norm() < 1e-4:  # the light straight overhead
            right_l = torch.tensor([1.0, 0.0, 0.0], device=device)
        right_l = F.normalize(right_l, dim=0)
        up_l = torch.cross(right_l, forward_l, dim=0)
        _, alpha, _ = rasterization(means, quats, scales, opacities, blank, viewmat(right_l, up_l, forward_l)[None],
                                    K[None], size, size, camera_model="ortho", packed=False)
        u = q @ right_l + size / 2
        v = size / 2 - q @ up_l
        grid = torch.stack([u / size * 2 - 1, v / size * 2 - 1], -1)[None]
        out.append(F.grid_sample(alpha.permute(0, 3, 1, 2), grid, align_corners=False)[0, 0])
    return torch.stack(out)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


class GaussianField(torch.nn.Module):
    """Gaussians with a color each (no view dependence). The parameters are named as gsplat's
    densification strategy expects: log scales, opacity and color logits."""

    def __init__(self, count: int, device):
        super().__init__()
        self.params = torch.nn.ParameterDict({
            "means": torch.nn.Parameter(torch.zeros((count, 3), device=device)),
            "scales": torch.nn.Parameter(torch.full((count, 3), math.log(0.5), device=device)),
            "quats": torch.nn.Parameter(torch.tensor([1.0, 0, 0, 0], device=device).repeat(count, 1)),
            "opacities": torch.nn.Parameter(torch.full((count,), _logit(0.1), device=device)),
            "colors": torch.nn.Parameter(torch.zeros((count, 3), device=device)),
        })

    @classmethod
    def from_points(cls, points: torch.Tensor, spacing: float) -> "GaussianField":
        """One small round Gaussian at each point (P, 3), such as the voxels of a visual hull."""
        field = cls(len(points), points.device)
        with torch.no_grad():
            field.params["means"].copy_(points)
            field.params["scales"].fill_(math.log(spacing / 2))
        return field

    def rasterize(self, viewmats, Ks, width: int, height: int):
        """gsplat's colors with expected depth (C, H, W, 4), opacity (C, H, W, 1) and its info."""
        p = self.params
        return rasterization(p["means"], F.normalize(p["quats"], dim=-1), torch.exp(p["scales"]),
                             torch.sigmoid(p["opacities"]), torch.sigmoid(p["colors"]), viewmats, Ks, width, height,
                             camera_model="ortho", render_mode="RGB+ED", packed=False)

    def render(self, height, width, pivot, offset, right, up, forward, samples=None, jitter=False, yaw_rad=None,
               supersample: int = 1):
        """Premultiplied color (H, W, 3) and opacity (H, W) of one view, like VoxelField.render. Also keeps
        the depth (expected, from the plane through the world origin) and the pixel-center origins."""
        s = supersample
        colors, alpha, _ = self.rasterize(viewmat(right, up, forward)[None],
                                          intrinsics(pivot, offset, self.params["means"].device, s)[None],
                                          width * s, height * s)
        colors, alpha = colors[0], alpha[0, ..., 0]
        depth = colors[..., 3] - DISTANCE
        self.last_depth = pool(depth * alpha, s) / pool(alpha, s).clamp(min=1e-6)
        self.last_surface = self.last_depth
        self.last_origins = pixel_rays(height, width, pivot, offset, right, up, forward)[0]
        return pool(colors[..., :3], s), pool(alpha, s)

    def fit(self, viewmats, Ks, targets, masks, iters: int = 3000, lr: float = 0.05, densify: bool = True):
        """Fit to views: viewmats (C, 4, 4) and Ks (C, 3, 3) as viewmat() and intrinsics() make them,
        target colors (C, H, W, 3), masks (C, H, W), True where the model is seen. All views render in
        one call per step. With `densify`, gsplat's default strategy clones and splits Gaussians where
        the views pull hardest, and prunes transparent ones."""
        params = self.params
        rates = {"means": lr / 5, "scales": lr / 10, "quats": lr / 50, "opacities": lr, "colors": lr / 2}
        optimizers = {k: torch.optim.Adam([params[k]], lr=rates[k]) for k in params}
        decay = 0.1 ** (1 / iters)
        strategy = DefaultStrategy(refine_start_iter=200, refine_stop_iter=int(iters * 0.6), refine_every=100,
                                   reset_every=10 ** 9)
        state = strategy.initialize_state(scene_scale=1.0)
        solid = masks.float()
        _, h, w = masks.shape
        t0 = time.time()
        for step in range(iters):
            colors, alphas, info = self.rasterize(viewmats, Ks, w, h)
            if densify:
                strategy.step_pre_backward(params, optimizers, state, step, info)
            rgb, alpha = colors[..., :3], alphas[..., 0]
            loss = ((rgb - targets) ** 2)[masks].mean()
            loss = loss + 0.5 * F.binary_cross_entropy(alpha.clamp(1e-5, 1 - 1e-5), solid)
            loss = loss + F.relu(params["scales"] - math.log(3.0)).square().mean()  # keep Gaussians small
            loss.backward()
            if densify:
                strategy.step_post_backward(params, optimizers, state, step, info, packed=False)
            for name, opt in optimizers.items():
                opt.step()
                opt.zero_grad(set_to_none=True)
                if name == "means":
                    opt.param_groups[0]["lr"] *= decay
            if step % 500 == 0 or step == iters - 1:
                print("iter %5d  loss %.5f  %d Gaussians  (%.0fs)" % (step, loss.item(), len(params["means"]),
                                                                       time.time() - t0))
