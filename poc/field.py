"""A voxel radiance field seen by orthographic turntable cameras.

World units are sprite pixels. y is up; the rotation axis is the y axis. A view with yaw phi and
camera elevation theta looks at the origin from azimuth phi, theta above the horizon.
"""

import math

import torch
import torch.nn.functional as F


def camera_basis(yaw_deg: torch.Tensor, elevation: torch.Tensor):
    """Right, up and forward unit vectors, each (V, 3), for views with the given yaws (degrees)."""
    phi = torch.deg2rad(yaw_deg)
    st, ct = torch.sin(elevation), torch.cos(elevation)
    sp, cp = torch.sin(phi), torch.cos(phi)
    zero = torch.zeros_like(phi)
    right = torch.stack([cp, zero, -sp], -1)
    up = torch.stack([-st * sp, ct.expand_as(phi), -st * cp], -1)
    forward = -torch.stack([ct * sp, st.expand_as(phi), ct * cp], -1)
    return right, up, forward


def pixel_rays(height: int, width: int, pivot, offset, right, up, forward):
    """Origins (H, W, 3) on the plane through the world origin, and the shared direction (3,)."""
    device = right.device
    x = torch.arange(width, device=device) + 0.5 - (pivot[0] + offset[0])
    y = (pivot[1] + offset[1]) - (torch.arange(height, device=device) + 0.5)
    origins = x[None, :, None] * right + y[:, None, None] * up
    return origins, forward


def ray_box(origins, direction, box_min, box_max):
    d = torch.where(direction.abs() < 1e-9, torch.full_like(direction, 1e-9), direction)
    t0 = (box_min - origins) / d
    t1 = (box_max - origins) / d
    near = torch.minimum(t0, t1).amax(-1)
    far = torch.maximum(t0, t1).amin(-1)
    return near, far


class VoxelField(torch.nn.Module):
    """Density and color on a voxel grid.

    With `harmonics` > 0, color also varies with the view's yaw, as a Fourier series of that order.
    Lighting that's fixed relative to the camera makes a surface's color depend on how the model is
    turned, and this lets the field represent that.
    """

    def __init__(self, box_min, box_max, voxel: float, device, harmonics: int = 0):
        super().__init__()
        self.register_buffer("box_min", torch.tensor(box_min, dtype=torch.float32, device=device))
        self.register_buffer("box_max", torch.tensor(box_max, dtype=torch.float32, device=device))
        size = [int(math.ceil((hi - lo) / voxel)) + 1 for lo, hi in zip(box_min, box_max)]
        self.size = size  # voxels along x, y, z
        gx, gy, gz = size
        self.harmonics = harmonics
        self.density = torch.nn.Parameter(torch.full((1, 1, gz, gy, gx), -6.0, device=device))
        self.color = torch.nn.Parameter(torch.zeros((1, 3 * (1 + 2 * harmonics), gz, gy, gx), device=device))
        # Where density may exist at all; set to the visual hull to keep floaters out.
        self.register_buffer("support", torch.ones((1, 1, gz, gy, gx), device=device))

    def restrict_to(self, inside: torch.Tensor) -> None:
        """Only allow density inside the given (gz, gy, gx) voxel set."""
        self.support = inside.float()[None, None]

    def voxel_centers(self):
        axes = [torch.linspace(float(lo), float(hi), n, device=self.box_min.device)
                for lo, hi, n in zip(self.box_min, self.box_max, self.size)]
        zz, yy, xx = torch.meshgrid(axes[2], axes[1], axes[0], indexing="ij")
        return torch.stack([xx, yy, zz], -1)  # (gz, gy, gx, 3)

    def sample(self, points, yaw_rad=None):
        """Density (P,) and color (P, 3) at world points (P, 3), seen from the given yaw."""
        grid = ((points - self.box_min) / (self.box_max - self.box_min) * 2 - 1).view(1, 1, 1, -1, 3)
        sigma = F.softplus(F.grid_sample(self.density, grid, align_corners=True).view(-1))
        sigma = sigma * F.grid_sample(self.support, grid, align_corners=True).view(-1)
        coeffs = F.grid_sample(self.color, grid, align_corners=True).view(-1, 3, points.shape[0])
        raw = coeffs[0]
        for k in range(1, self.harmonics + 1):
            raw = raw + coeffs[2 * k - 1] * torch.cos(k * yaw_rad) + coeffs[2 * k] * torch.sin(k * yaw_rad)
        return sigma, torch.sigmoid(raw.t())

    def render(self, height, width, pivot, offset, right, up, forward, samples: int, jitter: bool, yaw_rad=None):
        """Premultiplied color (H, W, 3) and opacity (H, W) of one view."""
        origins, direction = pixel_rays(height, width, pivot, offset, right, up, forward)
        near, far = ray_box(origins, direction, self.box_min, self.box_max)
        hit = far > near
        near = torch.where(hit, near, torch.zeros_like(near))
        far = torch.where(hit, far, torch.zeros_like(far))
        steps = torch.arange(samples, device=near.device) + 0.5
        if jitter:
            steps = steps + (torch.rand(height, width, samples, device=near.device) - 0.5)
        span = (far - near)[..., None]
        t = near[..., None] + steps * span / samples                      # (H, W, S)
        points = origins[..., None, :] + t[..., None] * direction           # (H, W, S, 3)
        sigma, color = self.sample(points.view(-1, 3), yaw_rad)
        sigma = sigma.view(height, width, samples)
        color = color.view(height, width, samples, 3)
        alpha = 1 - torch.exp(-sigma * span / samples)
        transmit = torch.cumprod(torch.cat([torch.ones_like(alpha[..., :1]), 1 - alpha[..., :-1] + 1e-10], -1), -1)
        weights = alpha * transmit
        self.last_alpha = alpha  # for regularizers
        # Expected depth along the view direction, from the plane through the world origin.
        self.last_depth = (weights * t).sum(-1) / weights.sum(-1).clamp(min=1e-6)
        self.last_origins = origins
        return (weights[..., None] * color).sum(-2), weights.sum(-1)


def allowed_masks(masks, slack: int = 1):
    """Where a voxel may project: solid or don't-care pixels, grown by `slack` pixels.

    masks[i] is (H, W) with 1 = solid, 0 = transparent, -1 = don't care (e.g. a baked shadow).
    The slack keeps thin parts (an arrow is 1-3 pixels wide) from being carved away by
    sub-pixel misalignment.
    """
    out = []
    for m in masks:
        a = (m != 0).float()[None, None]
        if slack:
            a = F.max_pool2d(a, 2 * slack + 1, stride=1, padding=slack)
        out.append(a[0, 0] > 0)
    return out


def carve(field: VoxelField, allowed, views, right, up, offset):
    """Visual hull: voxels that project onto an allowed pixel in every view. (gz, gy, gx) bool."""
    centers = field.voxel_centers()
    inside = torch.ones(centers.shape[:3], dtype=torch.bool, device=centers.device)
    for mask, view, r, u in zip(allowed, views, right, up):
        h, w = mask.shape
        col = torch.floor((centers @ r) + view.pivot[0] + offset[0]).long()
        row = torch.floor((view.pivot[1] + offset[1]) - (centers @ u)).long()
        valid = (col >= 0) & (col < w) & (row >= 0) & (row < h)
        value = torch.zeros_like(col, dtype=torch.bool)
        value[valid] = mask[row[valid], col[valid]]
        inside &= value
    return inside


def silhouettes(inside, field: VoxelField, views, right, up, offset):
    """Project a voxel set back into each view: (H, W) bool masks."""
    centers = field.voxel_centers()[inside]
    out = []
    for view, r, u in zip(views, right, up):
        h, w = view.shape
        x = torch.floor(centers @ r + view.pivot[0] + offset[0]).long()
        y = torch.floor(view.pivot[1] + offset[1] - centers @ u).long()
        valid = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        m = torch.zeros((h, w), dtype=torch.bool, device=centers.device)
        m[y[valid], x[valid]] = True
        out.append(m)
    return out
