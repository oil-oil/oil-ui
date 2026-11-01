"""Tests for scripts/measure_reference.py using only Python standard library."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/measure_reference.py"
sys.path.insert(0, str(ROOT / "scripts"))
import measure_reference  # noqa: E402


def make_test_png(path: Path) -> None:
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(60):
        for x in range(80):
            if 10 <= x < 30 and 10 <= y < 30:
                pixels.append((48, 60, 53, 255))  # #303C35 forest ink
            elif 40 <= x < 70 and 15 <= y < 45:
                if 50 <= x < 60 and 25 <= y < 35:
                    pixels.append((210, 120, 60, 255))  # foreground warm ochre
                else:
                    pixels.append((0, 255, 0, 255))  # chroma green background
            else:
                pixels.append((250, 248, 241, 255))  # #FAF8F1 warm paper
    img = measure_reference.SimpleRGBAImage(80, 60, pixels)
    path.write_bytes(img.to_png_bytes())


class MeasureReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="oil-measure-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.png_path = self.folder / "ref.png"
        make_test_png(self.png_path)

    def test_cli_direct_color_box_and_extract_with_chroma_key(self) -> None:
        out_dir = self.folder / "direct-out"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.png_path),
                "--color",
                "paper=0,0,8,8",
                "--color",
                "ink=12,12,12,12",
                "--box",
                "card=10,10,20,20",
                "--extract",
                "badge=40,15,30,30",
                "--key-color",
                "#00FF00",
                "--despill",
                "--css-width",
                "160",
                "--out-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(proc.stdout)
        by_name = {r["name"]: r for r in data["regions"]}
        self.assertEqual(by_name["paper"]["color"]["median_hex"], "#FAF8F1")
        self.assertEqual(by_name["ink"]["color"]["median_hex"], "#303C35")
        self.assertEqual(by_name["card"]["css_box"], [20.0, 20.0, 40.0, 40.0])
        extracted = out_dir / "badge.png"
        self.assertTrue(extracted.is_file())
        badge_img = measure_reference.SimpleRGBAImage.open_bytes(extracted.read_bytes())
        self.assertEqual(badge_img.size, (30, 30))
        self.assertEqual(badge_img.getpixel((0, 0))[3], 0)
        self.assertEqual(badge_img.getpixel((15, 15))[:3], (210, 120, 60))
        self.assertEqual(badge_img.getpixel((15, 15))[3], 255)

    def test_manifest_mode_writes_measurements_and_annotations_svg(self) -> None:
        manifest = self.folder / "manifest.json"
        out_dir = self.folder / "measured"
        manifest.write_text(
            json.dumps(
                {
                    "reference": "ref.png",
                    "css_viewport_width": 160,
                    "regions": [
                        {"name": "bg", "kind": "color", "box": [0, 0, 8, 8]},
                        {"name": "col_a", "kind": "box", "box": [10, 10, 20, 20], "group": "cols"},
                        {"name": "col_b", "kind": "box", "box": [40, 10, 20, 20], "group": "cols"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--out-dir", str(out_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["regions"], 3)
        self.assertEqual(summary["groups"], 1)
        self.assertTrue((out_dir / "measurements.json").is_file())
        self.assertTrue((out_dir / "annotations.svg").is_file())

    def test_pure_stdlib_rgba_fallback_matches_measurements(self) -> None:
        im = measure_reference.SimpleRGBAImage.open_bytes(self.png_path.read_bytes())
        self.assertEqual(im.size, (80, 60))
        self.assertEqual(im.getpixel((15, 15)), (48, 60, 53, 255))


if __name__ == "__main__":
    unittest.main()
