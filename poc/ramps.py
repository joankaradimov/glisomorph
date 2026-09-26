"""The palette's ramps as tensors: which material each index is, and how bright.

Diablo 1's palette is organized in ramps: runs of one hue from light to dark (diablo1/palette.py).
Sprites use the ramps from index 128 up, so a sprite pixel's index says two things: its material
(the ramp) and its shade (the position in the ramp).
"""

import torch

from diablo1.palette import RAMPS

LUMA = (0.299, 0.587, 0.114)


class Ramps:
    def __init__(self, palette: torch.Tensor, first: int = 128, last: int = 254):
        """palette: (256, 3) in [0, 1]. Only indices first..last belong to ramps here: the sprites'."""
        device = palette.device
        self.luminance = palette @ torch.tensor(LUMA, device=device)                 # (256,)
        self.ramp = torch.full((256,), -1, dtype=torch.long, device=device)
        spans = [(max(s, first), min(s + n, last + 1)) for s, n in RAMPS if s + n > first and s <= last]
        width = max(b - a for a, b in spans)
        # Per ramp, its indices and their luminance, padded with infinity to a common length.
        self.members = torch.zeros((len(spans), width), dtype=torch.long, device=device)
        self.levels = torch.full((len(spans), width), float("inf"), device=device)
        for k, (a, b) in enumerate(spans):
            self.ramp[a:b] = k
            self.members[k, :b - a] = torch.arange(a, b, device=device)
            self.levels[k, :b - a] = self.luminance[a:b]

    def of(self, indices: torch.Tensor) -> torch.Tensor:
        """Ramp of each index (...), -1 for transparent pixels and indices outside the ramps."""
        return torch.where(indices >= 0, self.ramp[indices.clamp(min=0)], torch.full_like(indices, -1))

    def nearest(self, indices: torch.Tensor, luminance: torch.Tensor) -> torch.Tensor:
        """For each index (...), the index of the same ramp whose luminance is nearest the given one.
        Indices outside the ramps are kept."""
        ramp = self.of(indices)
        levels = self.levels[ramp.clamp(min=0)]                                    # (..., width)
        pick = (levels - luminance[..., None]).abs().argmin(-1, keepdim=True)
        shaded = self.members[ramp.clamp(min=0)].gather(-1, pick)[..., 0]
        return torch.where(ramp >= 0, shaded, indices)
