"""Exercise the zero-dependency screenshot CLI against a real local browser."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "shoot.mjs"
NODE = shutil.which("node")


def find_browser():
    candidates = [os.environ.get("CHROME_PATH")]
    if sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif sys.platform == "win32":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            root = os.environ.get(variable)
            if root:
                candidates += [
                    str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(root) / "Microsoft/Edge/Application/msedge.exe"),
                ]
    candidates += [shutil.which(name) for name in (
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
    )]
    return next((path for path in candidates if path and Path(path).is_file()), None)


@unittest.skipUnless(NODE, "Node is not installed")
class ShootCLITests(unittest.TestCase):
    def test_help(self):
        result = subprocess.run([NODE, str(SCRIPT), "--help"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage", result.stdout)

    def test_missing_target(self):
        result = subprocess.run([NODE, str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)

    def test_unknown_option(self):
        help_result = subprocess.run([NODE, str(SCRIPT), "--help"], cwd=ROOT,
                                     capture_output=True, text=True, timeout=10)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        options = [line.split()[0] for line in help_result.stdout.splitlines()
                   if line.startswith("  --")]
        for args in (("--xxx",), ("--xxx", "value")):
            with self.subTest(args=args):
                result = subprocess.run([NODE, str(SCRIPT), *args], cwd=ROOT,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.splitlines(), [
                    "shoot: Unknown option --xxx",
                    "Available options: " + " ".join(options),
                ])
                self.assertEqual(result.stdout, "")

    def test_missing_option_value(self):
        for option in ("--out", "--size", "--states", "--param", "--zoom", "--steps", "--hold", "--wait", "--compare"):
            for following in ((), ("--force",)):
                with self.subTest(option=option, following=following):
                    result = subprocess.run([NODE, str(SCRIPT), option, *following], cwd=ROOT,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, f"shoot: {option} needs a value\n")

    def test_force_is_ignored(self):
        result = subprocess.run([NODE, str(SCRIPT), "--force"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "shoot: Missing page URL or file.\n")


class ShootBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise unittest.SkipTest("Node 22+ is not installed")
        version = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=10)
        if version.returncode or int(version.stdout.strip().lstrip("v").split(".")[0]) < 22:
            raise unittest.SkipTest("Node 22+ is required")
        cls.browser = find_browser()
        if not cls.browser:
            raise unittest.SkipTest("Chrome, Chromium or Edge is not installed")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="oil-shoot-test-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.page = self.folder / "sample.html"
        self.page.write_text('''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<style>
body { margin: 0; padding: 24px; background: #fde68a; font: 20px sans-serif; }
body[data-state="b"] { background: #bfdbfe; }
button { padding: 16px; }
</style></head><body><h1 id="state"></h1><button id="go">Toggle</button>
<script>
const state = new URLSearchParams(location.search).get('state') || 'a';
function show(value) {
  document.body.dataset.state = value;
  document.querySelector('#state').textContent = value;
}
show(state);
document.querySelector('#go').onclick = () => show(document.body.dataset.state === 'a' ? 'b' : 'a');
</script></body></html>''', encoding="utf-8")
        self.env = dict(os.environ, CHROME_PATH=self.browser)
        self.profile_root = self.folder / "profiles"
        self.profile_root.mkdir()
        self.env.update(TMPDIR=str(self.profile_root), TMP=str(self.profile_root), TEMP=str(self.profile_root))

    def shoot(self, output, *args):
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), "--out", str(output), *args],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_artifacts(self, output, names):
        for name in names:
            with self.subTest(file=name):
                artifact = output / name
                self.assertTrue(artifact.is_file(), name)
                self.assertGreater(artifact.stat().st_size, 0, name)
                if artifact.suffix == ".png":
                    self.assertTrue(artifact.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), name)
                elif artifact.suffix == ".jpg":
                    self.assertTrue(artifact.read_bytes().startswith(b"\xff\xd8"), name)

    def test_states_masks_and_sheets(self):
        output = self.folder / "shots"
        self.shoot(output, "--states", "a,b", "--mask", "--sheet")
        self.assert_artifacts(output, (
            "a.png", "b.png", "a-masked.png", "b-masked.png",
            "sheet.png", "sheet-masked.png", "report.json",
        ))
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["state"] for entry in report], ["a", "b"])
        self.assertEqual([entry["issues"] for entry in report], [[], []])
        self.assertEqual([entry["lint"] for entry in report], [[], []])
        self.assertNotEqual((output / "a.png").read_bytes(), (output / "b.png").read_bytes())
        self.assertNotEqual((output / "a.png").read_bytes(), (output / "a-masked.png").read_bytes())
        self.assertEqual(list(self.profile_root.glob("oil-shoot-*")), [], "Temporary browser profiles leaked")

    def test_mark_draws_numbered_boxes_without_touching_plain_shot(self):
        output = self.folder / "marked"
        result = self.shoot(output, "--mark", "#go; h1")
        self.assert_artifacts(output, ("page.png", "page-marked.png"))
        self.assertIn("page-marked.png", result.stdout)
        self.assertNotEqual((output / "page.png").read_bytes(), (output / "page-marked.png").read_bytes())
        plain = self.folder / "plain"
        self.shoot(plain)
        self.assertEqual((output / "page.png").read_bytes(), (plain / "page.png").read_bytes(),
                         "Marks must not leak into the plain screenshot")

    def test_mark_accepts_explicit_numbers(self):
        numbered, by_order, reversed_order = self.folder / "numbered", self.folder / "by-order", self.folder / "reversed"
        self.shoot(numbered, "--mark", "2=#go; 1=h1")
        self.shoot(by_order, "--mark", "h1; #go")
        self.shoot(reversed_order, "--mark", "#go; h1")
        self.assertEqual((numbered / "page-marked.png").read_bytes(), (by_order / "page-marked.png").read_bytes())
        self.assertNotEqual((numbered / "page-marked.png").read_bytes(), (reversed_order / "page-marked.png").read_bytes(),
                            "Explicit numbers must decide the labels, not the order")

    def test_mark_reports_missing_elements(self):
        output = self.folder / "missing"
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), "--out", str(output), "--mark", "#go; .nope"],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=90)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".nope", result.stderr)

    def test_force_overwrites_existing_output(self):
        output = self.folder / "shots"
        output.mkdir()
        (output / "page.png").write_bytes(b"old screenshot")
        self.shoot(output, "--force")
        self.assert_artifacts(output, ("page.png", "report.json"))

    def test_preview_denies_sibling_paths_and_escaping_symlinks(self):
        outside = Path(str(self.folder) + '-private')
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside)
        (outside / 'secret.txt').write_text('test-only-secret', encoding='utf-8')
        (self.folder / 'leak.txt').symlink_to(outside / 'secret.txt')
        (self.folder / 'nested').mkdir()
        (self.folder / 'nested/okay.txt').write_text('allowed-resource', encoding='utf-8')
        (self.folder / '.env.production.local').write_text('synthetic-secret', encoding='utf-8')
        (self.folder / '.git').mkdir()
        (self.folder / '.git/config').write_text('synthetic-git-config', encoding='utf-8')
        (self.folder / 'credentials.json').write_text('{"token":"synthetic"}', encoding='utf-8')
        (self.folder / 'server.pem').write_text('synthetic-private-key', encoding='utf-8')
        (self.folder / 'env.txt').symlink_to(self.folder / '.env.production.local')
        (self.folder / 'nested/hidden').symlink_to(self.folder / '.git', target_is_directory=True)
        (self.folder / 'nested/module.mjs').write_text('export const value = "module-works";', encoding='utf-8')
        blocked = ['/..%2f' + outside.name + '%2fsecret.txt', '/leak.txt', '/%E0%A4%A',
                   '/.env.production.local', '/%2eenv.production.local', '/.git/config',
                   '/credentials.json', '/server.pem', '/env.txt', '/nested/hidden/config']
        probe = '''<script>(async () => {
          for (const path of PATHS) {
            const response = await fetch(path);
            if (response.status !== 404) console.error('SECURITY_LEAK:' + path);
          }
          const allowed = await fetch('/nested/okay.txt');
          if (await allowed.text() !== 'allowed-resource') console.error('LEGIT_RESOURCE_BLOCKED');
          const module = await import('/nested/module.mjs');
          if (module.value !== 'module-works') console.error('LEGIT_RESOURCE_BLOCKED');
          console.error('AUDIT_FINISHED');
        })().catch(() => console.error('AUDIT_FAILED'));</script>'''.replace('PATHS', json.dumps(blocked))
        self.page.write_text(self.page.read_text().replace('</body>', probe + '</body>'), encoding='utf-8')
        output = self.folder / 'boundary-shots'
        self.shoot(output, '--wait', '1000')
        report = json.loads((output / 'report.json').read_text())
        issues = '\n'.join(report[0]['issues'])
        self.assertIn('AUDIT_FINISHED', issues)
        for marker in ('SECURITY_LEAK', 'LEGIT_RESOURCE_BLOCKED', 'AUDIT_FAILED'):
            self.assertNotIn(marker, issues)

    def test_state_labels_do_not_become_output_paths(self):
        output = self.folder / 'safe-states'
        states = ['../escaped', '<label & "quoted">']
        self.shoot(output, '--states', ','.join(states), '--mask', '--sheet')
        report = json.loads((output / 'report.json').read_text())
        self.assertEqual([entry['state'] for entry in report], states)
        for entry in report:
            self.assertRegex(entry['file'], r'^state-\d+-[0-9a-f]{12}\.png$')
            self.assertTrue((output / entry['file']).is_file())
        self.assertFalse((self.folder / 'escaped.png').exists())
        self.assert_artifacts(output, ('sheet.png', 'sheet-masked.png'))

    def test_type_accepts_selectors_with_quotes(self):
        self.page.write_text(self.page.read_text().replace('</body>', '<input data-x="value"></body>'), encoding='utf-8')
        output = self.folder / 'quoted-selector'
        self.shoot(output, '--steps', '''type 'input[data-x="value"]' hello''')
        report = json.loads((output / 'report.json').read_text())
        self.assertEqual(report[0]['issues'], [])

    def test_record_steps(self):
        output = self.folder / "record's output"
        result = self.shoot(output, "--record", "--steps", "click #go; wait 300", "--hold", "300")
        self.assert_artifacts(output, ("motion-start.jpg", "motion-mid.jpg", "motion-end.jpg"))
        self.assertNotEqual((output / "motion-start.jpg").read_bytes(), (output / "motion-end.jpg").read_bytes())
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["issues"] for entry in report], [[]])
        self.assertEqual(list(self.profile_root.glob("oil-shoot-*")), [], "Temporary browser profiles leaked")
        if shutil.which("ffmpeg"):
            self.assertTrue((output / "record.mp4").is_file(), result.stdout + result.stderr)
            self.assert_artifacts(output, ("record.mp4",))

    def test_mask_preserves_current_color_icons(self):
        self.page.write_text('''<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,"></head><body>
<svg width="80" height="80" viewBox="0 0 80 80" style="color:#16a34a">
<circle cx="40" cy="40" r="32" fill="currentColor" /></svg>
</body></html>''', encoding="utf-8")
        output = self.folder / "icons"
        self.shoot(output, "--mask")
        self.assertEqual((output / "page.png").read_bytes(), (output / "page-masked.png").read_bytes(),
                         "Masking text must preserve icons using currentColor")

    def test_record_preserves_final_hold(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg and ffprobe are required to check recording duration")
        output = self.folder / "hold"
        self.shoot(output, "--record", "--steps", "click #go; wait 300", "--hold", "2000")
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
            str(output / "record.mp4"),
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(float(json.loads(result.stdout)["format"]["duration"]), 2.0)

    def test_motion_probe(self):
        self.page.write_text('''<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,"><style>
body{margin:0}.hero{height:1800px}.stage{position:sticky;top:0;height:800px;overflow:hidden}
#figure,#word{position:absolute;left:300px;width:400px;height:300px;background:#888}#word{top:400px;background:#444}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
h1{animation:rise .5s ease-out both}#go{transition:transform .3s}#go.on{transform:translateX(40px)}
.reveal{height:600px;opacity:0;transition:opacity .3s}.reveal.in{opacity:1}
</style></head><body><section class="hero"><div class="stage"><div id="figure"></div><div id="word"></div></div></section>
<h1>Hi</h1><button id="go" onclick="this.classList.add('on')">Go</button>
<div style="height:1200px"></div><div class="reveal">Later</div>
<script>addEventListener('scroll',()=>{const p=Math.min(scrollY/1000,1);figure.style.transform=`scale(${1-p*.2})`;word.style.transform=`scale(${1+p*.25})`});
new IntersectionObserver(e=>e.forEach(x=>x.isIntersecting&&x.target.classList.add('in'))).observe(document.querySelector('.reveal'))</script>
</body></html>''', encoding="utf-8")
        output = self.folder / "motion"
        self.shoot(output, "--motion", "--size", "1280x800", "--steps", "click #go")
        probe = json.loads((output / "report.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(probe["issues"], [])
        self.assertTrue(all(probe["motion"][k]["elements"] for k in ("load", "steps", "hero", "scroll")))
        self.assertGreaterEqual(probe["motion"]["hero"]["layers"], 2)

        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"></head>
<body><h1>Still</h1><div style="height:1600px"></div></body></html>''', encoding="utf-8")
        output = self.folder / "still"
        self.shoot(output, "--motion", "--size", "1280x800")
        issues = "\n".join(json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["issues"])
        self.assertIn("first load: no animation detected", issues)
        self.assertIn("Scroll: no change detected", issues)

    def test_steps_reject_unquoted_selectors_with_spaces(self):
        output = self.folder / "unquoted"
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), "--out", str(output), "--steps", "click body #go"],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=90)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Quote selectors", result.stdout + result.stderr)
        self.shoot(self.folder / "quoted", "--steps", 'click "body #go"')

    def test_motion_skips_scroll_check_on_single_screen(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
html,body{margin:0;height:100%;overflow:hidden}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
h1{animation:rise .5s ease-out both}</style></head><body><h1>Game</h1></body></html>''', encoding="utf-8")
        output = self.folder / "single-screen"
        result = self.shoot(output, "--motion")
        probe = json.loads((output / "report.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(probe["issues"], [])
        self.assertFalse(probe["motion"]["scroll"]["scrollable"])
        self.assertIn("page does not scroll", result.stdout)

    def test_record_entry_captures_first_appearance(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;background:#fde68a}
@keyframes rise{from{opacity:0;transform:translateY(160px)}to{opacity:1;transform:none}}
h1{margin:40px;height:300px;background:#1e3a8a;animation:rise .3s ease-out both}</style></head>
<body><h1></h1></body></html>''', encoding="utf-8")
        # The entrance ends after 0.3 s: the default recording starts after it has played, only --entry captures it
        late = self.folder / "late"
        self.shoot(late, "--record", "--hold", "300")
        self.assertEqual((late / "motion-start.jpg").read_bytes(), (late / "motion-end.jpg").read_bytes())
        output = self.folder / "entry"
        self.shoot(output, "--record", "--entry", "--hold", "300")
        self.assert_artifacts(output, ("motion-start.jpg", "motion-mid.jpg", "motion-end.jpg"))
        self.assertNotEqual((output / "motion-start.jpg").read_bytes(), (output / "motion-end.jpg").read_bytes())

    def test_reports_page_problems(self):
        self.page.write_text(self.page.read_text(encoding="utf-8").replace("</body>", '''
<div style="width:2000px">overflow</div><img src="missing.png">
<script>console.error('shoot-test-error'); throw new Error('shoot-test-exception');</script>
</body>'''), encoding="utf-8")
        for args in ((), ("--record", "--hold", "300")):
            with self.subTest(record=bool(args)):
                output = self.folder / ("problem-record" if args else "problem-shots")
                self.shoot(output, "--size", "1280x900", *args)
                report = json.loads((output / "report.json").read_text(encoding="utf-8"))
                issues = "\n".join(report[0]["issues"])
                for expected in ("shoot-test-error", "shoot-test-exception", "Horizontal overflow", "Image failed to load"):
                    self.assertIn(expected, issues)


    def test_lint_flags_default_patterns(self):
        # The fixture stays Chinese on purpose: the Chinese-interface detection and the englishLabel rule only fire on CJK-heavy pages.
        self.page.write_text('''<!doctype html><html lang="zh"><head><meta charset="utf-8"><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.7 sans-serif;color:#222;background:#fff}
.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin:0}
h1{font-size:48px;margin:0 0 24px;background:linear-gradient(90deg,#7c3aed,#06b6d4);background-clip:text;-webkit-background-clip:text;color:transparent}
.num{font-size:12px;margin:0}h2{font-size:28px;margin:4px 0 24px}
.card{border:1px solid #ddd;border-radius:16px;padding:24px;margin:16px 0}
.quote{border-left:4px solid #e11d48;padding:12px 16px}.low{color:#c8c8c8}
.dense{font-size:11px;line-height:1.2;width:600px}.ghost{opacity:0}
</style></head><body><p class="eyebrow">Smart Ledger</p><h1>让记账更简单</h1>
<p class="num">01 / 账户</p><h2>所有账户一目了然</h2>
<div class="card">外层<div class="card">里层卡片里有一些文字</div></div>
<div class="quote">好的工具让人忘记它的存在。</div><p class="low">很淡的说明文字，颜色几乎看不见。</p>
<p class="dense">这是一段很长的正文，用了很小的字号和很紧的行高，一行特别长，读的时候眼睛要跑很远才能换行，这是一段很长的正文，用了很小的字号和很紧的行高，一行特别长，读的时候眼睛要跑很远才能换行。</p>
<ul><li><span>🚀</span> 快</li><li><span>💰</span> 省</li></ul><div><span>WORKSPACE OVERVIEW</span> <span>CONTENT OBJECT</span></div>
<p class="ghost">这一段一直停在透明状态</p>
<p>这一页的中文足够多，用来判断这是中文界面。这一页的中文足够多，用来判断这是中文界面。这一页的中文足够多，用来判断这是中文界面。</p>
</body></html>''', encoding="utf-8")
        output = self.folder / "lint"
        result = self.shoot(output, "--size", "1440x900")
        entry = json.loads((output / "report.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(entry["issues"], [])
        rules = {item["rule"] for item in entry["lint"]}
        for rule in ("eyebrow", "numbered", "gradientText", "sideStripe", "nestedCards", "emojiIcon",
                     "englishLabel", "contrastLow", "smallText", "tightLeading", "longMeasure", "stuck"):
            self.assertIn(rule, rules)
        self.assertIn("Default-pattern hints", result.stdout)

    def test_lint_requires_body_contrast_of_4_5(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.6 sans-serif;color:#222;background:#fff}
.soft{color:#8a8a8a}
</style></head><body><p class="soft">Body text at about 3.5 to 1 contrast still fails the 4.5 to 1 floor.</p></body></html>''', encoding="utf-8")
        output = self.folder / "soft"
        self.shoot(output, "--size", "1280x800")
        lint = json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["lint"]
        self.assertIn("contrastLow", {item["rule"] for item in lint})

    def test_lint_spares_css_triangles_and_neutral_dividers(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.6 sans-serif;color:#222}
.play{width:0;height:0;border-top:12px solid transparent;border-bottom:12px solid transparent;border-left:20px solid #e11d48}
aside{border-right:1px solid #ddd;height:200px;width:200px}
@keyframes rise{from{opacity:0}to{opacity:1}}h1{animation:rise .6s ease-out both;font-size:40px;margin:48px 0 12px}
</style></head><body><span class="play"></span><aside>Sidebar</aside><p>Intro paragraph above the heading.</p>
<h1>Plain heading</h1><p>Body text that follows the heading closely.</p></body></html>''', encoding="utf-8")
        output = self.folder / "clean"
        self.shoot(output, "--size", "1280x800")
        self.assertEqual(json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["lint"], [])

    def test_compare_against_reference(self):
        reference = self.folder / "reference"
        self.shoot(reference, "--states", "a", "--size", "800x600")
        same = self.folder / "same"
        self.shoot(same, "--states", "a", "--size", "800x600", "--compare", str(reference / "a.png"))
        entry = json.loads((same / "report.json").read_text(encoding="utf-8"))[0]
        self.assert_artifacts(same, ("a-compare.png",))
        self.assertLess(entry["compare"]["overall"], 1)
        other = self.folder / "other"
        result = self.shoot(other, "--states", "b", "--size", "800x600", "--compare", str(reference / "a.png"))
        entry = json.loads((other / "report.json").read_text(encoding="utf-8"))[0]
        self.assertGreater(entry["compare"]["overall"], 20)
        self.assertEqual(len(entry["compare"]["cells"]), 9)
        self.assertIn("% of pixels differ clearly", result.stdout)
        missing = subprocess.run([NODE, str(SCRIPT), str(self.page), "--compare", str(self.folder / "nope.png")],
                                 cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("Reference image not found", missing.stderr)

    def test_reports_blank_webgl_canvas(self):
        # A canvas that already has a 2d context cannot get webgl; that simulates "screenshot succeeded, canvas blank"
        self.page.write_text(self.page.read_text(encoding="utf-8").replace("</body>", '''
<canvas id="bad"></canvas><canvas id="good"></canvas>
<script>
const bad = document.querySelector('#bad'); bad.getContext('2d'); bad.getContext('webgl');
const good = document.querySelector('#good'); good.getContext('webgl2') || good.getContext('webgl');
</script></body>'''), encoding="utf-8")
        output = self.folder / "webgl"
        self.shoot(output)
        issues = "\n".join(json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["issues"])
        self.assertIn("WebGL: 1 canvas(es) could not create a drawing context", issues)


if __name__ == "__main__":
    unittest.main()
