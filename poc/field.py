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

    def _march(self, height, width, pivot, offset, right, up, forward, samples: int, jitter: bool):
        """Sample points along every pixel's ray: points (H, W, S, 3), depths t (H, W, S), step length."""
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
        self.last_origins = origins
        return points, t, span / samples

    def _composite(self, sigma, t, step):
        """Per-sample weights (H, W, S) from densities; also keeps depth and opacity for later."""
        alpha = 1 - torch.exp(-sigma * step)
        transmit = torch.cumprod(torch.cat([torch.ones_like(alpha[..., :1]), 1 - alpha[..., :-1] + 1e-10], -1), -1)
        weights = alpha * transmit
        self.last_alpha = alpha  # for regularizers
        # Expected depth along the view direction, from the plane through the world origin.
        self.last_depth = (weights * t).sum(-1) / weights.sum(-1).clamp(min=1e-6)
        return weights

    def render(self, height, width, pivot, offset, right, up, forward, samples: int, jitter: bool, yaw_rad=None):
        """Premultiplied color (H, W, 3) and opacity (H, W) of one view."""
        points, t, step = self._march(height, width, pivot, offset, right, up, forward, samples, jitter)
        sigma, color = self.sample(points.view(-1, 3), yaw_rad)
        weights = self._composite(sigma.view(height, width, samples), t, step)
        return (weights[..., None] * color.view(height, width, samples, 3)).sum(-2), weights.sum(-1)


def _inverse_softplus(x: float) -> float:
    return math.log(math.expm1(x))


class LitVoxelField(VoxelField):
    """Albedo, normals from the density, and directional lights fixed relative to the camera.

    Diablo's sprites were rendered by turning the model under lights that stayed put relative to the
    camera. So each light is a direction in camera space (x right, y up, z toward the camera); for a
    view it becomes a world direction through that view's camera basis. Shading is deferred: albedo,
    normal and specular strength are accumulated along each ray, then shaded once per pixel.
    """

    def __init__(self, box_min, box_max, voxel: float, device, lights: int = 1, specular: bool = True,
                 detach_normals: bool = True):
        super().__init__(box_min, box_max, voxel, device, harmonics=0)
        # Letting shading gradients flow into the density through the normals lets the optimizer bend
        # geometry to fake shading, which hurt silhouettes in tests. By default normals follow the
        # density, but don't push it.
        self.detach_normals = detach_normals
        gz, gy, gx = self.density.shape[2:]
        self.specular = (torch.nn.Parameter(torch.full((1, 1, gz, gy, gx), -3.0, device=device))
                         if specular else None)
        start = torch.tensor([[0.6, 0.6, 0.5], [-0.6, 0.3, 0.5]][:lights], device=device)
        self.light_dirs = torch.nn.Parameter(start)
        self.light_raw = torch.nn.Parameter(torch.full((lights,), _inverse_softplus(0.8), device=device))
        self.ambient_raw = torch.nn.Parameter(torch.tensor(_inverse_softplus(0.3), device=device))
        self.shininess_raw = torch.nn.Parameter(torch.tensor(math.log(16.0), device=device))
        self._normals = None

    def light_parameters(self):
        return [self.light_dirs, self.light_raw, self.ambient_raw, self.shininess_raw]

    def begin_step(self) -> None:
        """Forget cached normals; call whenever the density has changed."""
        self._normals = None

    def normal_grid(self):
        """Outward normals (unnormalized) on the voxel grid: minus the gradient of smoothed density."""
        if self._normals is None:
            density = self.density.detach() if self.detach_normals else self.density
            d = F.softplus(density) * self.support
            d = F.avg_pool3d(d, 3, stride=1, padding=1)
            gx = F.pad((d[..., 2:] - d[..., :-2]) / 2, (1, 1))
            gy = F.pad((d[..., 2:, :] - d[..., :-2, :]) / 2, (0, 0, 1, 1))
            gz = F.pad((d[..., 2:, :, :] - d[..., :-2, :, :]) / 2, (0, 0, 0, 0, 1, 1))
            self._normals = -torch.cat([gx, gy, gz], 1)
        return self._normals

    def lights_world(self, right, up, forward):
        """Unit light directions (L, 3) in world space for a view."""
        cam = F.normalize(self.light_dirs, dim=-1)
        return F.normalize(cam[:, :1] * right + cam[:, 1:2] * up - cam[:, 2:3] * forward, dim=-1)

    def shading(self, normals, right, up, forward):
        """Diffuse-plus-ambient factor (...,) and specular term (...,) for unit normals (..., 3)."""
        lights = self.lights_world(right, up, forward)
        power = F.softplus(self.light_raw)
        diffuse = F.softplus(self.ambient_raw) + (power * torch.relu(normals @ lights.t())).sum(-1)
        halfway = F.normalize(lights - forward, dim=-1)  # the camera is at -forward
        specular = (power * torch.relu(normals @ halfway.t()) ** torch.exp(self.shininess_raw)).sum(-1)
        return diffuse, specular

    def render(self, height, width, pivot, offset, right, up, forward, samples: int, jitter: bool, yaw_rad=None):
        points, t, step = self._march(height, width, pivot, offset, right, up, forward, samples, jitter)
        flat = points.view(-1, 3)
        grid = ((flat - self.box_min) / (self.box_max - self.box_min) * 2 - 1).view(1, 1, 1, -1, 3)
        sigma = F.softplus(F.grid_sample(self.density, grid, align_corners=True).view(-1))
        sigma = sigma * F.grid_sample(self.support, grid, align_corners=True).view(-1)
        albedo = torch.sigmoid(F.grid_sample(self.color, grid, align_corners=True).view(3, -1).t())
        normal = F.normalize(F.grid_sample(self.normal_grid(), grid, align_corners=True).view(3, -1).t(), dim=-1)
        weights = self._composite(sigma.view(height, width, samples), t, step)
        w = weights[..., None]
        albedo = (w * albedo.view(height, width, samples, 3)).sum(-2)                  # premultiplied
        normal = F.normalize((w * normal.view(height, width, samples, 3)).sum(-2), dim=-1)
        diffuse, specular = self.shading(normal, right, up, forward)
        rgb = albedo * diffuse[..., None]
        if self.specular is not None:
            ks = torch.sigmoid(F.grid_sample(self.specular, grid, align_corners=True).view(-1))
            ks = (weights * ks.view(height, width, samples)).sum(-1)                     # premultiplied
            rgb = rgb + (ks * specular)[..., None]
        self.last_normal = normal
        return rgb, weights.sum(-1)


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
