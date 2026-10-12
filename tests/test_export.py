"""The preview exporters and the sprite, on synthetic sprites (never game data).

    python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

from common.export import Animation, AnimationExporter, ComparisonExporter, DemoExporter, Sprite
from common.export.preview import gif_durations

PALETTE = np.stack([np.arange(256)] * 3, 1).astype(np.uint8)


def bar(direction: int, directions: int, length: int, size: int = 32) -> np.ndarray:
    """A cell with a bar from the canvas center, turned like a unit facing `direction` of a half turn."""
    cell = np.full((size, size), -1, np.int16)
    angle = np.pi * direction / (directions - 1)
    for r in range(length):
        x, y = size // 2 + int(round(r * np.sin(angle))), size // 2 - int(round(r * np.cos(angle)))
        cell[y, x] = 100 + r
    return cell


def turning(directions=17, lengths=(4, 6, 8, 10), scale=1, drawn=None) -> Sprite:
    """Frames of a bar growing, in every direction (or, with `drawn`, only those), at a scale."""
    cells = []
    for length in lengths:
        row = []
        for d in range(directions):
            c = bar(d, directions, length)
            row.append(None if drawn is not None and d not in drawn else c.repeat(scale, 0).repeat(scale, 1))
        cells.append(row)
    n = len(lengths)
    return Sprite(cells, PALETTE, [Animation("walk", list(range(n)), [67] * n),
                                   Animation("attack", [n - 1, n - 2], [100, 100])], scale=scale)


def ours_and_game() -> Sprite:
    """Ours at 2x with in-betweens, every direction; the game's at 1x, every other direction."""
    game = turning(lengths=(4, 8), drawn=set(range(0, 17, 2)))
    game.animations = [Animation("walk", [0, 1], [67, 67]), Animation("attack", [1, 0], [100, 100])]
    ours = turning(lengths=(4, 6, 8, 6), scale=2)
    ours.animations = [Animation("walk", [0, 1, 2, 3], [33.5] * 4), Animation("attack", [2, 0], [100, 100])]
    ours.new_directions = set(range(1, 17, 2))
    ours.original = game
    return ours


def total_duration(path: Path) -> float:
    total = 0
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            frame.load()  # WebP fills in a frame's duration on loading it
            total += frame.info.get("duration", 0)
    return total


class Previews(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_gif_durations(self):
        d = gif_durations([33.5] * 4)
        self.assertTrue(all(x % 10 == 0 and x >= 20 for x in d))
        self.assertAlmostEqual(sum(d), 134, delta=10)
        self.assertEqual(gif_durations([5, 5, 5]), [20, 20, 20])

    def test_comparison_in_every_format(self):
        for suffix in (".gif", ".png", ".webp"):
            path = ComparisonExporter(zoom=2).export(ours_and_game(), self.dir / ("c" + suffix))[0]
            self.assertTrue(path.exists())
            self.assertAlmostEqual(total_duration(path), 4 * 33.5 + 200, delta=15)

    def test_comparison_plays_animations_in_order(self):
        exporter = ComparisonExporter(play=["walk", "walk", "attack"])
        timeline = exporter.timeline(ours_and_game())
        self.assertEqual([f for f, _, _ in timeline], [0, 1, 2, 3, 0, 1, 2, 3, 2, 0])
        self.assertEqual([g for _, g, _ in timeline[:4]], [0, 0, 1, 1])  # each of the game's over two of ours

    def test_comparison_needs_the_original(self):
        with self.assertRaises(ValueError):
            ComparisonExporter().export(turning(), self.dir / "c.gif")

    def test_comparison_per_direction_windows(self):
        path = ComparisonExporter(crop="direction", per_line=6).export(ours_and_game(), self.dir / "c.gif")[0]
        self.assertTrue(path.exists())

    def test_a_file_per_animation(self):
        written = AnimationExporter(columns=6).export(turning(), self.dir / "unit.gif")
        self.assertEqual([p.name for p in written], ["unit-walk.gif", "unit-attack.gif"])
        self.assertAlmostEqual(total_duration(written[0]), 4 * 67, delta=10)

    def test_demo_turns_through_every_direction(self):
        sprite = turning()
        path = DemoExporter(zoom=2).export(sprite.mirrored(), self.dir / "demo.png")[0]
        self.assertAlmostEqual(total_duration(path), 32 * (4 * 67 + 200), delta=40)

    def test_mirrored(self):
        sprite = turning()
        whole = sprite.mirrored()
        self.assertEqual(whole.directions, 32)
        self.assertEqual(whole.mirrors[17], 15)
        np.testing.assert_array_equal(whole.cell(0, 17), sprite.cell(0, 15)[:, ::-1])


if __name__ == "__main__":
    unittest.main()
