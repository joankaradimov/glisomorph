"""A fitted reconstruction and its cameras, saved with each fit so it can be rendered again later.

    scene = Scene.load("out/warrior-holdout1-h0/scene.pt", "PATH/TO/DIABDAT.MPQ")
"""

import dataclasses
from dataclasses import dataclass
from pathlib import Path

import torch

from poc.field import LitVoxelField, VoxelField, camera_basis
from poc.views import PRESETS, Preset, View, load_views


def masks_for(views: list[View], shadows: bool, device) -> list[torch.Tensor]:
    """1 where the model is seen, 0 elsewhere.

    A baked shadow (index 0 on a character) is on the ground, and the model doesn't cover it, so it
    counts as transparent.
    """
    out = []
    for v in views:
        idx = torch.as_tensor(v.indices, device=device).long()
        m = (idx >= 0).long()
        if shadows:
            m[idx == 0] = 0
        out.append(m)
    return out


def make_field(config: dict, device) -> VoxelField:
    """An empty field of the kind and size that `config` describes."""
    if config["lighting"] != "none":
        return LitVoxelField(config["box_min"], config["box_max"], config["voxel"], device,
                             lights=config["lights"], specular=config["lighting"] == "phong",
                             detach_normals=not config["coupled_normals"])
    return VoxelField(config["box_min"], config["box_max"], config["voxel"], device, harmonics=config["harmonics"])


@dataclass
class Scene:
    field: VoxelField
    views: list[View]
    masks: list[torch.Tensor]    # per view: 1 where the model is seen, 0 elsewhere
    palette: torch.Tensor        # (256, 3) in [0, 1]
    yaws: torch.Tensor           # (V,) degrees, in the calibrated sense of rotation
    elevation: torch.Tensor      # camera elevation, radians
    offset: tuple[float, float]  # pivot offset, pixels
    samples: int                 # samples per ray
    config: dict                 # how the field was made, what it was fitted to, and how

    @property
    def preset(self) -> Preset:
        return dataclasses.replace(PRESETS[self.config["preset"]], frame=self.config["frame"])

    @property
    def lit(self) -> bool:
        return isinstance(self.field, LitVoxelField)

    @property
    def sign(self) -> int:
        return self.config["yaw_sign"]

    @property
    def train(self) -> list[int]:
        return self.config["train_views"]

    @property
    def test(self) -> list[int]:
        return self.config["test_views"]

    @property
    def supersample(self) -> int:
        return self.config["supersample"]

    def basis(self, yaw_deg: torch.Tensor):
        """Right, up and forward, each (V, 3), for yaws in degrees (already in the calibrated sense)."""
        return camera_basis(yaw_deg, self.elevation)

    def save(self, path: Path) -> None:
        # Only the grids around the visual hull are saved: elsewhere the density is masked out. Two
        # voxels of margin keep interpolation at the hull's edge exact.
        hull = self.field.support[0, 0].nonzero()
        lo = (hull.min(0).values - 2).clamp(min=0).tolist() if len(hull) else [0, 0, 0]
        hi = (hull.max(0).values + 3).tolist() if len(hull) else list(self.field.support.shape[2:])
        state = {k: v[..., lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]].clone() if v.dim() == 5 else v
                 for k, v in self.field.state_dict().items()}
        torch.save({"config": self.config, "field": state, "corner": lo,
                    "elevation": float(self.elevation), "offset": [float(x) for x in self.offset],
                    "samples": self.samples}, path)

    @classmethod
    def load(cls, path, mpq_path: str, device=None) -> "Scene":
        device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        data = torch.load(path, map_location=device)
        config = data["config"]
        preset = dataclasses.replace(PRESETS[config["preset"]], frame=config["frame"])
        views, palette = load_views(mpq_path, preset)
        field = make_field(config, device)
        # Put the saved part of each grid back in place; outside it, nothing may have density.
        state = {k: v.clone() for k, v in field.state_dict().items()}
        state["support"].zero_()
        z, y, x = data.get("corner", [0, 0, 0])
        for k, v in data["field"].items():
            if v.dim() == 5:
                state[k][..., z:z + v.shape[2], y:y + v.shape[3], x:x + v.shape[4]] = v
            else:
                state[k] = v
        field.load_state_dict(state)
        yaws = config["yaw_sign"] * torch.tensor([v.yaw for v in views], dtype=torch.float32, device=device)
        return cls(field=field, views=views, masks=masks_for(views, preset.shadows, device),
                   palette=torch.as_tensor(palette, device=device), yaws=yaws,
                   elevation=torch.tensor(data["elevation"], device=device), offset=tuple(data["offset"]),
                   samples=data["samples"], config=config)
