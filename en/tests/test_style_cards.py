import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_style_cards.py"
EXAMPLE = ROOT / "assets" / "style-cards" / "example.json"
spec = importlib.util.spec_from_file_location("build_style_cards", SCRIPT)
cards_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cards_builder)


def run(config, out, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(config), "--out", str(out), *extra],
                          capture_output=True, text=True, timeout=60)


class StyleCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="oil-cards-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, mutate):
        cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        mutate(cfg)
        path = self.dir / "cards.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return path

    def snapshot(self, out):
        return {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}

    def assert_rejected(self, config, out, needle, *extra):
        before = self.snapshot(out) if out.is_dir() else None
        result = run(config, out, *extra)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(needle, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if before is not None:
            self.assertEqual(self.snapshot(out), before)
        return result

    def test_example_builds_cards_manifest_and_explorer(self):
        out = self.dir / "out"
        result = run(EXAMPLE, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        cards = json.loads(EXAMPLE.read_text(encoding="utf-8"))["cards"]
        self.assertEqual([c["id"] for c in manifest["candidates"]], [c["id"] for c in cards])
        self.assertEqual(manifest["round"], "Style cards")
        for c in manifest["candidates"]:
            page = (out / c["source"]).read_text(encoding="utf-8")
            self.assertIn("<head>", page)
            self.assertNotRegex(page, r"https?://(?!www\.w3\.org/2000/svg)")
        self.assertTrue((out / "style-explorer.html").stat().st_size > 0)

    def test_existing_explorer_needs_force(self):
        out = self.dir / "out"
        self.assertEqual(run(EXAMPLE, out).returncode, 0)
        (out / "notes.txt").write_bytes(b"keep these bytes\x00")
        config = self.write(lambda c: c["content"].update(title="Changed title"))
        self.assert_rejected(config, out, "--force")
        self.assertEqual(run(config, out, "--force").returncode, 0)
        manifest = json.loads((out / "manifest.json").read_text())
        for candidate in manifest["candidates"]:
            self.assertIn("Changed title", (out / candidate["source"]).read_text())
        self.assertEqual((out / "notes.txt").read_bytes(), b"keep these bytes\x00")

    def test_rejects_bad_config_with_clear_message(self):
        cases = {
            "colors.accent": lambda c: c["cards"][0]["colors"].update(accent="green"),
            "layout": lambda c: c["cards"][0].update(layout="three-columns"),
            "4–6 entries": lambda c: c.update(cards=c["cards"][:2]),
            "no web fonts": lambda c: c["cards"][0]["fonts"].update(display="url(https://fonts.example/x.woff2)"),
        }
        for needle, mutate in cases.items():
            with self.subTest(needle):
                out = self.dir / f"bad-{len(needle)}"
                self.assert_rejected(self.write(mutate), out, needle)
                self.assertFalse(out.exists())

    def test_card_count_boundaries(self):
        def count(cfg, n):
            first = cfg["cards"][0]
            cfg["cards"] = [dict(first, id=f"style-{i}") for i in range(n)]
        for n in (3, 4, 6, 7):
            with self.subTest(count=n):
                config = self.write(lambda c: count(c, n))
                out = self.dir / f"count-{n}"
                if n in (3, 7):
                    self.assert_rejected(config, out, "4–6 entries")
                    self.assertFalse(out.exists())
                else:
                    result = run(config, out)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["cards"], n)

    def test_rejects_wrong_types_before_writing(self):
        cases = [
            ("content", lambda c: c.update(content=[])),
            ("cards", lambda c: c.update(cards="four")),
            ("card 1", lambda c: c["cards"].__setitem__(0, [])),
            ("id", lambda c: c["cards"][0].update(id=1)),
            ("name", lambda c: c["cards"][0].update(name=1)),
            ("concept", lambda c: c["cards"][0].update(concept=None)),
            ("traits", lambda c: c["cards"][0].update(traits=None)),
            ("traits", lambda c: c["cards"][0].update(traits="dense")),
            ("traits", lambda c: c["cards"][0].update(traits=[1])),
            ("tags", lambda c: c["content"].update(tags="OK")),
            ("tags", lambda c: c["content"].update(tags=[None])),
            ("colors", lambda c: c["cards"][0].update(colors=[])),
            ("accent", lambda c: c["cards"][0]["colors"].update(accent=42)),
            ("fonts", lambda c: c["cards"][0].update(fonts=[])),
            ("layout", lambda c: c["cards"][0].update(layout=[])),
            ("density", lambda c: c["cards"][0].update(density=[])),
            ("project", lambda c: c.update(project="  ")),
            ("brief", lambda c: c.update(brief=1)),
            ("round", lambda c: c.update(round=[])),
        ]
        for key in ("title", "body", "number", "number_label", "primary", "secondary", "input_label", "input_value"):
            for value in ("  ", 42, {}, None):
                cases.append((f"content.{key}", lambda c, k=key, v=value: c["content"].update({k: v})))
        for key in ("display", "body", "number"):
            cases.append((f"fonts.{key}", lambda c, k=key: c["cards"][0]["fonts"].update({k: 42})))
        for i, (needle, mutate) in enumerate(cases):
            with self.subTest(field=needle, case=i):
                out = self.dir / f"invalid-{i}"
                self.assert_rejected(self.write(mutate), out, needle)
                self.assertFalse(out.exists())

    def test_bad_input_and_output_paths_have_friendly_errors(self):
        config = self.dir / "broken.json"
        for data, needle in ((b"[]", "root"), (b"{bad", str(config)), (b"\xff\xff", str(config))):
            with self.subTest(data=data):
                config.write_bytes(data)
                self.assert_rejected(config, self.dir / "out", needle)
        self.assert_rejected(self.dir / "missing.json", self.dir / "out", "missing.json")
        out = self.dir / "file-output"
        out.write_bytes(b"existing file")
        self.assert_rejected(EXAMPLE, out, str(out))
        self.assertEqual(out.read_bytes(), b"existing file")

    def test_config_inside_output_is_kept_unless_names_collide(self):
        for name in ("manifest.json", "card-glaze.html"):
            with self.subTest(name=name):
                out = self.dir / name
                config = out / name
                config.parent.mkdir(parents=True)
                config.write_bytes(EXAMPLE.read_bytes())
                self.assert_rejected(config, out, "would be overwritten", "--force")
        out = self.dir / "beside"
        out.mkdir()
        config = out / "cards.json"
        config.write_bytes(EXAMPLE.read_bytes())
        result = run(config, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_bytes(), EXAMPLE.read_bytes())
        self.assertEqual(sorted(p.name for p in out.iterdir() if not p.name.startswith(".")),
                         sorted(["cards.json", "manifest.json", "style-explorer.html",
                                 "card-glaze.html", "card-gallery.html", "card-kiln.html", "card-zine.html"]))

    def test_rejects_output_file_collisions(self):
        out = self.dir / "out"
        out.mkdir()
        (out / "manifest.json").mkdir()
        (out / "keep.txt").write_bytes(b"old")
        self.assert_rejected(EXAMPLE, out, "manifest.json", "--force")

    def test_rejects_output_in_skill_directory_before_creating_it(self):
        out = ROOT / "rejected-style-cards-test-output"
        self.assertFalse(out.exists())
        self.assert_rejected(EXAMPLE, out, "skill installation directory")
        self.assertFalse(out.exists())

    def test_rejects_card_content_override(self):
        config = self.write(lambda c: c["cards"][0].update(content={"title": "Different product"}))
        self.assert_rejected(config, self.dir / "out", "cannot be overridden")

    def test_css_values_are_validated_before_writing(self):
        payload = "400;</style><script>alert(1)</script><style>"
        for key in ("display_weight", "number_weight"):
            for value in (payload, "400", 400.0, True, 299, 901):
                with self.subTest(field=key, value=value):
                    config = self.write(lambda c: c["cards"][0].update({key: value}))
                    out = self.dir / "out"
                    self.assert_rejected(config, out, key)
                    self.assertFalse(out.exists())
        for key in ("radius", "border", "shadow", "texture"):
            config = self.write(lambda c: c["cards"][0].update({key: payload}))
            self.assert_rejected(config, self.dir / "out", key)
        for value in (True, float("nan"), float("inf")):
            config = self.write(lambda c: c["cards"][0].update(radius=value))
            self.assert_rejected(config, self.dir / "out", "radius")
        config = self.write(lambda c: c["cards"][0].update(display_weight=300, number_weight=900))
        result = run(config, self.dir / "valid-weights")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_invalid_font_items(self):
        for value in ("  ", "Georgia,", ",serif", "Georgia,,serif", '"Georgia, serif',
                      "'Georgia\", serif", '"", serif', '"  ", serif', 'Georgia"', "Georgia\n, serif",
                      "</style><script>alert(1)</script>"):
            with self.subTest(font=value):
                config = self.write(lambda c: c["cards"][0]["fonts"].update(display=value))
                self.assert_rejected(config, self.dir / "out", "fonts.display")
                self.assertFalse((self.dir / "out").exists())
        config = self.write(lambda c: c["cards"][0]["fonts"].update(display="'Times New Roman', Georgia, serif"))
        result = run(config, self.dir / "valid-font")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_content_html_is_escaped(self):
        payload = "</style><script>alert(1)</script>"
        config = self.write(lambda c: c["content"].update(title=payload))
        out = self.dir / "out"
        result = run(config, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (out / "card-glaze.html").read_text()
        self.assertNotIn(payload, page)
        self.assertIn("&lt;script&gt;", page)

    def test_english_defaults_and_generated_labels(self):
        def english(cfg):
            cfg["lang"] = "en"
            for key in ("project", "brief", "round"):
                cfg.pop(key)
            cfg["content"] = {k: "English content" for k in ("title", "body", "number", "number_label", "primary", "secondary")}
            for i, card in enumerate(cfg["cards"]):
                card.update(name=f"Style {i}", concept="A style", fonts={k: "Georgia, serif" for k in ("display", "body", "number")})
                card.pop("traits")
        out = self.dir / "out"
        result = run(self.write(english), out)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["project"], "Style cards")
        self.assertEqual(manifest["round"], "Style cards")
        self.assertIn("Compare colors", manifest["brief"])
        for candidate in manifest["candidates"]:
            self.assertIn("Display Georgia · Body Georgia · Numbers Georgia", candidate["typography"])
            page = (out / candidate["source"]).read_text()
            self.assertIn('<html lang="en">', page)
            self.assertIn(candidate["traits"][0], page)
            self.assertNotRegex(json.dumps(candidate, ensure_ascii=False) + page, r"[\u4e00-\u9fff]")

    def test_explorer_failure_reports_streams_and_preserves_old_files(self):
        out = self.dir / "out"
        self.assertEqual(run(EXAMPLE, out).returncode, 0)
        before = self.snapshot(out)
        config = self.write(lambda c: c["content"].update(title="Changed"))
        for stdout, stderr in (("useful stdout", "useful stderr"), ("useful stdout", "\n"), ("", "")):
            with self.subTest(stdout=stdout, stderr=stderr):
                failure = subprocess.CompletedProcess([], 7, stdout=stdout, stderr=stderr)
                with patch.object(cards_builder.subprocess, "run", return_value=failure):
                    with self.assertRaises(cards_builder.ConfigError) as caught:
                        cards_builder.build(config, out, True)
                message = str(caught.exception)
                self.assertIn("exit code 7", message)
                for label, stream in (("stdout", stdout), ("stderr", stderr)):
                    if stream.strip():
                        self.assertIn(f"{label}: {stream.strip()}", message)
                self.assertEqual(self.snapshot(out), before)


if __name__ == "__main__":
    unittest.main()
