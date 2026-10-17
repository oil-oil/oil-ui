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


def write_solid_png(path, width, height, rgb):
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress((b'\0' + bytes(rgb) * width) * height)) + chunk(b'IEND', b''))


@unittest.skipUnless(NODE, "Node is not installed")
class ShootCLITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed to inspect encoded frames')
    def test_encoder_keeps_short_feedback_at_its_original_time(self):
        with tempfile.TemporaryDirectory(prefix='oil-shoot-encoding-') as temp:
            folder = Path(temp)
            for name, color in [('red', (255, 0, 0)), ('blue', (0, 0, 255)), ('green', (0, 255, 0))]:
                ppm = b'P6\n64 64\n255\n' + bytes(color) * (64 * 64)
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'image2pipe', '-i', '-',
                                '-frames:v', '1', str(folder / (name + '.jpg'))],
                               input=ppm, check=True, capture_output=True, timeout=10)
            # Exercise the production concat writer without timing a real browser animation.
            javascript = '''import {readFileSync} from 'node:fs'; import {basename} from 'node:path';
const source=readFileSync(process.argv[1],'utf8');
const writer=source.slice(source.indexOf('function screencastList('),source.indexOf('async function record('));
const frames=JSON.parse(process.argv[2]);const finished=Number(process.argv[3]);
process.stdout.write(eval(writer+'; screencastList(frames,finished)'));'''
            frames = [{'name': name + '.jpg', 't': t} for name, t in
                      [('red', 0), ('blue', .949), ('green', .965), ('blue', 2.13)]]
            result = subprocess.run([NODE, '--input-type=module', '-e', javascript, str(SCRIPT), json.dumps(frames), '2.146'],
                                    check=True, capture_output=True, text=True, timeout=10, encoding='utf-8')
            (folder / 'list.txt').write_text(result.stdout, encoding='utf-8')
            video = folder / 'record.mp4'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i',
                            str(folder / 'list.txt'), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30',
                            '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True, timeout=10)
            decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-vf',
                                      'format=rgb24,crop=1:1:32:32', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                                     check=True, capture_output=True, timeout=10).stdout
            # The 949ms blue feedback overlaps the 30fps sample at frame 28; default JPEG
            # time-base rounding used to erase it while the separately saved JPEG survived.
            red, green, blue = decoded[28 * 3:29 * 3]
            self.assertLess(red, 50)
            self.assertLess(green, 50)
            self.assertGreater(blue, 180)
            # The end screenshot must also survive an ending halfway between output ticks.
            tail_frames = [{'name': 'red.jpg', 't': 0}, {'name': 'blue.jpg', 't': .950}]
            result = subprocess.run([NODE, '--input-type=module', '-e', javascript, str(SCRIPT),
                                     json.dumps(tail_frames), '.950'], check=True, capture_output=True, text=True, timeout=10, encoding='utf-8')
            (folder / 'list.txt').write_text(result.stdout, encoding='utf-8')
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i',
                            str(folder / 'list.txt'), '-vf', 'fps=30', '-pix_fmt', 'yuv420p', str(video)],
                           check=True, capture_output=True, timeout=10)
            decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-vf',
                                      'format=rgb24,crop=1:1:32:32', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                                     check=True, capture_output=True, timeout=10).stdout
            self.assertGreater(decoded[-1], 180, 'The appended screenshot must be the encoded last frame')
            self.assertLess(len(decoded) / (3 * 30), 3, 'A sub-second recording must not be padded to three seconds')

    def test_help(self):
        result = subprocess.run([NODE, str(SCRIPT), "--help"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("用法", result.stdout)

    def test_timeout_scale_validation(self):
        plan = self.dry('--timeout-scale', '2')
        self.assertEqual(plan['options']['timeout-scale'], '2')
        for value in ('0', '-1', '0.5', 'NaN', 'Infinity', 'slow'):
            with self.subTest(value=value):
                message = self.dry('--timeout-scale', value, ok=False)
                self.assertIn('收到 ' + value, message)
                self.assertIn('--timeout-scale 2', message)

    def test_missing_target(self):
        result = subprocess.run([NODE, str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)

    def test_unknown_option(self):
        for args in (("--xxx",), ("--xxx", "value")):
            with self.subTest(args=args):
                result = subprocess.run([NODE, str(SCRIPT), *args], cwd=ROOT,
                                        capture_output=True, text=True, timeout=10, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                self.assertIn("不认识的选项 --xxx", result.stderr)
                self.assertIn("是不是想写", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_missing_option_value(self):
        for option in ("--out", "--size", "--states", "--param", "--zoom", "--steps", "--hold", "--wait", "--compare", "--timeout-scale"):
            for following in ((), ("--force",)):
                with self.subTest(option=option, following=following):
                    result = subprocess.run([NODE, str(SCRIPT), option, *following], cwd=ROOT,
                                            capture_output=True, text=True, timeout=10, encoding='utf-8')
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, f"shoot：{option} 需要一个值\n")

    def dry(self, *args, ok=True):
        result = subprocess.run([NODE, str(SCRIPT), "page.html", "--dry-run", *args],
                                cwd=ROOT, capture_output=True, text=True, timeout=10, encoding='utf-8')
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result.stderr

    def test_dry_run_corpus_regressions(self):
        # Twenty corpus patterns; project-specific classes, labels and text are neutralized.
        cases = [
            ('click "[data-thread=sample]"', "click", "[data-thread=sample]"),
            ('click [data-id="sample"]', "click", '[data-id="sample"]'),
            ('click \'.cause [data-latest-release]\'', "click", '.cause [data-latest-release]'),
            ('click .nav button[data-view=sample]', "click", '.nav button[data-view=sample]'),
            ('click [aria-label="Send money"]', "click", '[aria-label="Send money"]'),
            ('click "[aria-label=\\"Send money\\"]"', "click", '[aria-label="Send money"]'),
            ('click \'[aria-label="Start Sample task"]\'', "click", '[aria-label="Start Sample task"]'),
            ('click ".nav button:nth-child(3)"', "click", '.nav button:nth-child(3)'),
            ('hover "[data-message=sample] .reaction"', "hover", '[data-message=sample] .reaction'),
            ('drag "[data-tile=\\"1\\"] .tile-paper" 240 0', "drag", '[data-tile="1"] .tile-paper'),
            ('drag [data-id="sample"] 214 -350', "drag", '[data-id="sample"]'),
            ('drag ".sample-line:nth-child(2)" 45 0', "drag", '.sample-line:nth-child(2)'),
            ('type #message-input 示例内容', "type", '#message-input'),
            ('type [aria-label="Message box"] 你好', "type", '[aria-label="Message box"]'),
            ('type "#search" Sample', "type", '#search'),
            ('click text=More', "click", 'More'),
            ('click button:has-text("Undo")', "click", 'Undo'),
            ('wait450', "wait", None),
            ('key ControlOrMeta+A', "key", None),
            ('key Meta+r', "key", None),
        ]
        for raw, action, selector in cases:
            with self.subTest(raw=raw):
                step = self.dry("--steps", raw)["groups"][0]["steps"][0]
                self.assertEqual(step["action"], action)
                if selector is not None:
                    self.assertEqual(step["selector"]["value"], selector)

    def test_dry_run_balanced_steps_and_parameters(self):
        parsed = self.dry("--steps", 'open: click [data-label="a;b"]; click :is([data-label="a;b"]); '
                          'type ".form input" "hello; world"; select #choice "Second item"; '
                          'wait450; wait 450ms; wait 0.5s; key Shift+Tab',
                          "--steps", 'click :has-text(\'Undo; action\')', "--mark", '1=text="a;b"')
        steps = parsed["groups"][0]["steps"]
        self.assertEqual(parsed["groups"][0]["name"], "open")
        self.assertEqual(len(steps), 8)
        self.assertEqual(steps[2]["params"], {"text": "hello; world"})
        self.assertEqual(steps[3]["params"], {"value": "Second item"})
        self.assertEqual([s["params"]["ms"] for s in steps[4:7]], [450, 450, 500])
        self.assertEqual(parsed["groups"][1]["name"], None)
        self.assertEqual(parsed["marks"][0]["selector"]["kind"], "text")
        for raw, expected in [('type #input "text [without a closing bracket"', 'text [without a closing bracket'),
                              ("type #input don't stop", "don't stop"),
                              ('type "body [aria-label="Message box"]" "hello world"', 'hello world')]:
            self.assertEqual(self.dry("--steps", raw)["groups"][0]["steps"][0]["params"]["text"], expected)
        for raw, action in [('doubleclick .a', 'dblclick'), ('press Control+A', 'key'),
                            ('fill #input "hello"', 'fill'), ('sleep 0.5s', 'wait'), ('waitfor text=Ready', 'waitfor')]:
            self.assertEqual(self.dry("--steps=" + raw)["groups"][0]["steps"][0]["action"], action)

    def test_fill_parses_as_replacement_action(self):
        for raw, kind, value, text in [
            ('fill ".form input" "hello world"', 'css', '.form input', 'hello world'),
            ('fill [aria-label="Message box"] ""', 'css', '[aria-label="Message box"]', ''),
            ('fill text="Old message" new', 'text', 'Old message', 'new'),
            ("fill textarea:has-text('Old message') new", 'has-text', 'Old message', 'new'),
        ]:
            with self.subTest(raw=raw):
                step = self.dry('--steps', raw)['groups'][0]['steps'][0]
                self.assertEqual(step['action'], 'fill')
                self.assertEqual(step['selector']['kind'], kind)
                self.assertEqual(step['selector']['value'], value)
                self.assertEqual(step['params'], {'text': text})
        self.assertIn('例如 fill #field "hello world"', self.dry('--steps', 'fill #field', ok=False))

    def test_dry_run_does_not_launch_or_write_and_shares_errors(self):
        with tempfile.TemporaryDirectory(prefix="oil-shoot-dry-") as folder:
            output = Path(folder) / "never-created"
            env = dict(os.environ, CHROME_PATH=str(Path(folder) / "no-browser"))
            args = [NODE, str(SCRIPT), "missing-page.html", "--out", str(output)]
            result = subprocess.run([*args, "--dry-run", "--steps", "click .nav button"],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=10, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["groups"][0]["steps"][0]["selector"]["kind"], "css")
            self.assertFalse(output.exists())
            errors = []
            for extra in ([], ["--dry-run"]):
                result = subprocess.run([*args, *extra, "--steps", "drag .tile 20 nope"],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=10, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                errors.append(result.stderr)
            self.assertEqual(errors[0], errors[1])

    def test_option_forms_aliases_and_errors(self):
        parsed = self.dry("--size=desktop,phone,mobile,800x600", "--zoom", "1,2", "--query=a=1&b=2", "--states", "idle,done")
        self.assertEqual(parsed["sizes"], [{"w": 1440, "h": 900}, {"w": 390, "h": 844}, {"w": 800, "h": 600}])
        self.assertEqual(parsed["zooms"], [1, 2])
        self.assertEqual(self.dry("--size", "mobile")["sizes"], [{"w": 390, "h": 844}])
        self.assertTrue(any("尺寸 已去重" in n for n in parsed["notices"]))
        self.assertEqual(self.dry()["sizes"], [{"w": 390, "h": 844}])
        for flag in ("--full", "--mask", "--sheet", "--record", "--motion", "--entry", "--evidence"):
            with self.subTest(flag=flag):
                error = self.dry(flag, "extra", ok=False)
                self.assertIn("page.html 和 extra", error)
                self.assertIn(flag + " 不带参数", error)
        for args, expected in [
            (("--zoon", "2"), "--zoom"),
            (("--motion", ".respond"), '--motion 不带参数'),
            (("other.html",), "page.html 和 other.html"),
            (("--full", "extra"), "page.html 和 extra"),
            (("--record=true",), "不带参数"), (("--zoom=0",), "--zoom 1,2"),
            (("--size=0x900",), "--size desktop"), (("--wait=abc",), "--wait 1000"),
            (("--steps", "clik .open"), "是不是想写 click"),
            (("--steps", "drag .a 1 nope"), "drag .tiles .paper 240 0"),
            (("--steps", "wait nope"), "wait 450ms"),
            (("--steps", "click [aria-label=\"x]"), "没有配对"),
            (("--steps", "key Invalid+A"), "ControlOrMeta+A"),
            (("--steps", "same: click .a", "--steps", "same: click .b"), "名字重复"),
        ]:
            with self.subTest(args=args):
                error = self.dry(*args, ok=False)
                self.assertIn(expected, error)

    def test_action_names_are_valid_group_names(self):
        for name, body in [('scroll', 'scroll 950; wait 300'), ('hover', 'hover .x'),
                           ('click', 'click .x'), ('sleep', 'wait 0')]:
            group = self.dry('--steps', name + ': ' + body)['groups'][0]
            self.assertEqual(group['name'], name)
            self.assertEqual(group['id'], name)
            self.assertEqual(group['steps'][0]['raw'], body.split(';')[0])

    def test_glued_numbers_only_apply_to_numeric_options(self):
        compact = self.dry('--hold1000', '--wait450', '--zoom1,2', '--timeout-scale2',
                           '--steps', 'wait450; wait0.5s; sleep450')
        spaced = self.dry('--hold', '1000', '--wait', '450', '--zoom', '1,2', '--timeout-scale', '2',
                          '--steps', 'wait450; wait0.5s; sleep450')
        self.assertEqual(compact, spaced)
        self.assertEqual([step['params']['ms'] for step in compact['groups'][0]['steps']], [450, 500, 450])
        for arg in ['--out123', '--size390x844', '--states123', '--full1000', '--steps450']:
            self.assertIn('不认识的选项', self.dry(arg, ok=False))
        for arg in ['--hold1000ms', '--wait450ms', '--zoom0', '--timeout-scale0.5']:
            self.assertIn('收到', self.dry(arg, ok=False))

    def test_stitch_and_sequence_options_validate_without_launching(self):
        with tempfile.TemporaryDirectory(prefix='oil-shoot-stitch-cli-') as temp:
            image = Path(temp) / 'before image.png'
            image.write_bytes(b'checked by the browser only when rendering')
            output = Path(temp) / 'not-created'

            def run(*args, ok=False):
                result = subprocess.run([NODE, str(SCRIPT), *args, '--dry-run', '--out', str(output)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=10, encoding='utf-8')
                self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
                self.assertFalse(output.exists())
                return json.loads(result.stdout) if ok else result.stderr

            plan = run('--stitch', str(image), '--label', '修改前', '--stitch=' + str(image),
                       '--label=修改后', '--columns2', ok=True)
            self.assertNotIn('target', plan)
            self.assertEqual(plan['stitch'], [{'path': str(image), 'label': '修改前'}, {'path': str(image), 'label': '修改后'}])
            self.assertEqual(plan['options']['columns'], '2')
            for args, hint in [
                (['--stitch'], '--stitch before.png'),
                (['--label', '修改前'], '--stitch before.png --label "修改前"'),
                (['--stitch', str(image), '--label', '前', '--label', '后'], '--label'),
                (['--stitch', str(Path(temp) / 'missing.png')], '第 1 张图片'),
                (['--stitch', temp], '不是文件'),
                (['page.html', '--stitch', str(image)], '拼图不需要页面'),
                (['--stitch', str(image), str(image), str(image)], '每张图片前都要写 --stitch'),
                (['--stitch', str(image), '--record'], '拼图不需要页面'),
                (['--stitch', str(image), '--frames', '8'], '拼图不需要页面'),
                (['page.html', '--frames', '8'], '--record --frames 8'),
                (['--frames', '8'], '缺少页面'),
                (['page.html', '--record', '--frames'], '--record --frames 8'),
                (['page.html', '--columns', '2'], '--record --frames 8 --columns 4'),
                (['--stitch', str(image), '--columns', '0'], '--columns 2'),
                (['--stitch', str(image), '--columns', '2.5'], '--columns 2'),
            ]:
                with self.subTest(args=args):
                    message = run(*args)
                    self.assertIn(hint, message)
                    self.assertIn('收到', message)
                    self.assertIn('例如', message)
            for value in ['0', '1', '-1', '2.5', 'NaN', '121', '99999999999999999']:
                self.assertIn('收到 ' + value, run('page.html', '--record', '--frames', value))
            plan = run('page.html', '--record', '--frames8', '--columns4', ok=True)
            self.assertEqual(plan['options']['frames'], '8')
            self.assertEqual(plan['options']['columns'], '4')
            self.assertEqual(self.dry('--evidence', '--frames', '6')['options']['frames'], '6')
            self.assertIn('--frames 8', self.dry('--record', '--frams', ok=False))
            self.assertIn('--stitch before.png', self.dry('--stitc', ok=False))

    def test_sequence_sampling_is_uniform_and_holds_sparse_frames(self):
        javascript = '''import {readFileSync} from 'node:fs';
const source=readFileSync(process.argv[1],'utf8');
const sample=eval('('+source.slice(source.indexOf('function sequenceFrames('),source.indexOf('function screencastList('))+')');
console.log(JSON.stringify(sample([{name:'red.jpg',t:10},{name:'blue.jpg',t:10.8},{name:'green.jpg',t:11.7}],12,5)));'''
        result = subprocess.run([NODE, '--input-type=module', '-e', javascript, str(SCRIPT)],
                                cwd=ROOT, check=True, capture_output=True, text=True, timeout=10, encoding='utf-8')
        samples = json.loads(result.stdout)
        self.assertEqual([frame['timeMs'] for frame in samples], [0, 500, 1000, 1500, 2000])
        self.assertEqual([frame['path'] for frame in samples], ['red.jpg', 'red.jpg', 'blue.jpg', 'blue.jpg', 'green.jpg'])
        self.assertEqual([frame['sourceTimeMs'] for frame in samples], [0, 0, 800, 800, 1700])



class ShootBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise unittest.SkipTest("Node 22+ is not installed")
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
</style></head><body><h1 id="state"></h1><button id="go">切换</button>
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
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def browser_leftovers(self):
        """Processes still holding this test's temporary profiles, and the profile folders themselves."""
        import time
        needle = self.folder.name
        for _ in range(40):
            if sys.platform == 'win32':
                script = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and "
                          "$_.CommandLine.Contains('" + needle + "') -and $_.CommandLine.Contains('user-data-dir') } | ForEach-Object { $_.Name }")
                found = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                       capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace').stdout.split()
            else:
                # Other programs' command lines are not ours to decode strictly; only our own folder name matters here.
                listing = subprocess.run(['ps', '-axww', '-o', 'command='], capture_output=True, text=True,
                                         encoding='utf-8', errors='replace').stdout
                found = [line[:120] for line in listing.splitlines() if needle in line and '--user-data-dir=' in line]
            folders = [path.name for path in self.profile_root.glob('oil-shoot-*')]
            if not found and not folders:
                break
            time.sleep(0.25)
        return found, folders

    def assert_no_browser_leftovers(self):
        processes, folders = self.browser_leftovers()
        self.assertEqual(processes, [], 'browser processes were left running')
        self.assertEqual(folders, [], 'temporary profiles were left behind')

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

    def test_stitch_local_images_without_page_preserves_order_ratio_and_chinese_labels(self):
        import struct
        first, second, third = self.folder / "前 'one.png", self.folder / 'after.png', self.folder / 'square.png'
        write_solid_png(first, 120, 60, (255, 0, 0))
        write_solid_png(second, 60, 120, (0, 0, 255))
        write_solid_png(third, 90, 90, (0, 255, 0))
        output = self.folder / 'stitch'
        result = subprocess.run([NODE, str(SCRIPT), '--stitch', str(first), '--label', '修改前',
                                 '--stitch', str(second), '--label', '修改后', '--stitch', str(third),
                                 '--columns', '2', '--out', str(output)], cwd=ROOT, env=self.env,
                                capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(report['file'], 'stitch.png')
        self.assertEqual(report['columns'], 2)
        self.assertEqual(report['issues'], [])
        self.assertEqual([item['label'] for item in report['items']], ['修改前', '修改后', ''])
        self.assertEqual([(item['width'], item['height']) for item in report['items']], [(120, 60), (60, 120), (90, 90)])
        self.assertEqual(struct.unpack('>II', (output / 'stitch.png').read_bytes()[16:24]), (report['width'], report['height']))
        self.assertEqual({p.name for p in output.iterdir()}, {'stitch.png', 'report.json'})
        if shutil.which('ffmpeg'):
            for item, color in zip(report['items'], [(255, 0, 0), (0, 0, 255), (0, 255, 0)]):
                self.assertEqual(self.frame_pixel(output / 'stitch.png', item['x'] + item['width'] // 2,
                                                 item['y'] + item['height'] // 2), color)
            captions = []
            for item in report['items'][:2]:
                left = 24 + (0 if item is report['items'][0] else 176)
                crop = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output / 'stitch.png'),
                                       '-vf', f"crop=160:24:{left}:{item['labelY']}", '-frames:v', '1',
                                       '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], check=True, capture_output=True, timeout=10).stdout
                captions.append(crop)
            self.assertNotEqual(captions[0], captions[1], 'Different Chinese glyphs must not render as identical missing-font boxes')
        self.assert_no_browser_leftovers()

    def test_stitch_wraps_labels_and_reports_decode_errors(self):
        image = self.folder / 'sample.svg'
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500"><rect width="1000" height="500" fill="red"/></svg>', encoding='utf-8')
        output = self.folder / 'wrapped'
        result = subprocess.run([NODE, str(SCRIPT), '--stitch', str(image), '--label', '中文标注' * 30,
                                 '--columns', '5', '--out', str(output)], cwd=ROOT, env=self.env,
                                capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(report['columns'], 1)
        self.assertEqual((report['items'][0]['width'], report['items'][0]['height']), (640, 320))
        self.assertGreater(report['items'][0]['labelHeight'], 32)
        self.assertGreaterEqual(report['height'], report['items'][0]['y'] + 320 + report['items'][0]['labelHeight'])
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1"><rect width="1500" height="1" fill="red"/></svg>', encoding='utf-8')
        thin = self.folder / 'thin'
        result = subprocess.run([NODE, str(SCRIPT), '--stitch', str(image), '--out', str(thin)],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tile = json.loads((thin / 'report.json').read_text(encoding='utf-8'))[0]['items'][0]
        self.assertEqual((tile['width'], tile['height']), (640, 1))
        corrupt = self.folder / 'corrupt.png'
        corrupt.write_bytes(b'not an image')
        result = subprocess.run([NODE, str(SCRIPT), '--stitch', str(image), '--stitch', str(corrupt),
                                 '--out', str(self.folder / 'corrupt')], cwd=ROOT, env=self.env,
                                capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('第 2 张图片无法解码，收到 ' + str(corrupt), result.stderr)
        self.assertIn('例如 --stitch before.png', result.stderr)
        self.assert_no_browser_leftovers()

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
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=90, encoding='utf-8')
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
        self.page.write_text(self.page.read_text(encoding='utf-8').replace('</body>', probe + '</body>'), encoding='utf-8')
        output = self.folder / 'boundary-shots'
        self.shoot(output, '--wait', '4000')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        issues = '\n'.join(report[0]['issues'])
        self.assertIn('AUDIT_FINISHED', issues)
        for marker in ('SECURITY_LEAK', 'LEGIT_RESOURCE_BLOCKED', 'AUDIT_FAILED'):
            self.assertNotIn(marker, issues)

    def test_state_labels_do_not_become_output_paths(self):
        output = self.folder / 'safe-states'
        states = ['../escaped', '<label & "quoted">']
        self.shoot(output, '--states', ','.join(states), '--mask', '--sheet')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual([entry['state'] for entry in report], states)
        for entry in report:
            self.assertRegex(entry['file'], r'^state-\d+-[0-9a-f]{12}\.png$')
            self.assertTrue((output / entry['file']).is_file())
        self.assertFalse((self.folder / 'escaped.png').exists())
        self.assert_artifacts(output, ('sheet.png', 'sheet-masked.png'))

    def test_type_accepts_selectors_with_quotes(self):
        self.page.write_text(self.page.read_text(encoding='utf-8').replace('</body>', '<input data-x="value"></body>'), encoding='utf-8')
        output = self.folder / 'quoted-selector'
        self.shoot(output, '--steps', '''type 'input[data-x="value"]' hello''')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report[0]['issues'], [])

    def test_record_steps(self):
        output = self.folder / "record's output"
        result = self.shoot(output, "--record", "--steps", "click #go; wait 300", "--hold", "300")
        self.assert_artifacts(output, ("motion-start.jpg", "motion-mid.jpg", "motion-end.jpg"))
        self.assertNotEqual((output / "motion-start.jpg").read_bytes(), (output / "motion-end.jpg").read_bytes())
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["issues"] for entry in report], [[]])
        self.assertNotIn('sequence', report[0])
        self.assertEqual(list(output.glob('*sequence*')), [], 'Default recordings must not create a sequence image')
        self.assertEqual(list(self.profile_root.glob("oil-shoot-*")), [], "Temporary browser profiles leaked")
        if shutil.which("ffmpeg"):
            self.assertTrue((output / "record.mp4").is_file(), result.stdout + result.stderr)
            self.assert_artifacts(output, ("record.mp4",))

    def frame_pixel(self, path, x=20, y=20):
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vf',
                                 f'format=rgb24,crop=1:1:{x}:{y}', '-frames:v', '1',
                                 '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(len(result.stdout), 3)
        return tuple(result.stdout)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed for recording and pixel checks')
    def test_record_sequence_has_uniform_times_original_ratios_and_named_zoom_files(self):
        output = self.folder / 'sequence'
        self.shoot(output, '--record', '--steps', 'go: click #go', '--zoom', '1,2',
                   '--hold', '250', '--frames', '5', '--columns', '2')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report), 2)
        self.assertEqual([item['sequence']['file'] for item in report], ['motion-go-sequence.png', 'motion-go-@2x-sequence.png'])
        for entry in report:
            sequence = entry['sequence']
            self.assertEqual(sequence['columns'], 2)
            self.assertEqual(len(sequence['items']), 5)
            times = [frame['timeMs'] for frame in sequence['frames']]
            self.assertEqual(times[0], 0)
            self.assertEqual(times[-1], entry['durationMs'])
            intervals = [b - a for a, b in zip(times, times[1:])]
            self.assertLessEqual(max(intervals) - min(intervals), 1)
            for sample, tile in zip(sequence['frames'], sequence['items']):
                self.assertLessEqual(sample['sourceTimeMs'], sample['timeMs'] + 1)
                self.assertEqual(tile['label'], f"{sample['timeMs'] / 1000:.3f} s")
                self.assertAlmostEqual(tile['width'] / tile['height'], 390 / 844, delta=.002)
                self.assertGreater(tile['labelHeight'], 0)
                self.assertLessEqual(tile['y'] + tile['height'] + tile['labelHeight'], sequence['height'])
            self.assert_artifacts(output, (sequence['file'], entry['frames']['start']['file'], entry['frames']['mid']['file'], entry['frames']['end']['file']))
            last = sequence['items'][-1]
            pixel = self.frame_pixel(output / sequence['file'], last['x'] + last['width'] - 10, last['y'] + last['height'] - 10)
            end = self.frame_pixel(output / entry['frames']['end']['file'], 300, 800)
            self.assertTrue(all(abs(a - b) < 8 for a, b in zip(pixel, end)), (pixel, end))
            first = sequence['items'][0]
            self.assertNotEqual(pixel, self.frame_pixel(output / sequence['file'], first['x'] + first['width'] - 10, first['y'] + first['height'] - 10))
        self.assertEqual(list(output.glob('frames*')), [])
        self.assert_no_browser_leftovers()

    def test_record_sequence_unnamed_filename_and_default_columns(self):
        output = self.folder / 'unnamed-sequence'
        self.shoot(output, '--record', '--hold', '100', '--frames', '5')
        entry = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(entry['sequence']['file'], 'motion-sequence.png')
        self.assertEqual(entry['sequence']['columns'], 4)
        self.assert_artifacts(output, ('motion-sequence.png', 'motion-start.jpg', 'motion-mid.jpg', 'motion-end.jpg'))
        self.assertEqual(list(output.glob('frames*')), [])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed for evidence recording')
    def test_sequence_png_respects_evidence_filename_collisions(self):
        output = self.folder / 'sequence-collision'
        self.shoot(output, '--evidence', '--states', 'motion-entry-sequence', '--hold', '100', '--frames', '2')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        sequence = next(item['sequence'] for item in report if 'sequence' in item)
        self.assertEqual(sequence['file'], 'motion-entry-2-sequence.png')
        self.assert_artifacts(output, ('motion-entry-sequence.png', sequence['file'], 'record-entry-2.mp4'))
        self.assertNotEqual((output / 'motion-entry-sequence.png').read_bytes(), (output / sequence['file']).read_bytes())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed to inspect frame pixels')
    def test_record_frames_follow_last_action_and_capture_short_feedback(self):
        if os.environ.get('OIL_SHOOT_SLOW_HOST'):
            self.skipTest('needs real-time frame capture: a 0.36s flash is missed on slow hosted runners')
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
body{margin:0}#box{position:absolute;left:20px;top:20px;width:120px;height:120px;background:red}
#box.prepared{background:lime}#box.feedback{animation:shake .36s linear}
@keyframes shake{0%,100%{background:red;transform:none}25%,75%{background:blue;transform:translateX(40px)}}
#controls{position:absolute;top:180px}#drag{display:inline-block;width:80px;height:30px}
#tail:hover{animation:tail .8s linear}@keyframes tail{from{opacity:.3}to{opacity:1}}
@keyframes loop{to{transform:rotate(360deg)}}#loop{position:absolute;top:270px;width:40px;height:40px;background:gray;animation:loop 2s linear infinite}
</style><div id="box"></div><div id="controls"><button id="prepare">Prepare</button>
<button id="click">Click</button><button id="double">Double</button><div id="drag">Drag</div>
<input id="edit" value="old"><select id="choice"><option value="a">A</option><option value="b">B</option></select>
<button id="tail">Tail</button></div><div id="loop"></div><script>
const box=document.querySelector('#box');
const feedback=()=>{box.className='feedback'};
document.querySelector('#prepare').onclick=()=>box.className='prepared';
document.querySelector('#click').onclick=feedback;
document.querySelector('#double').ondblclick=feedback;
document.querySelector('#drag').onmouseup=feedback;
document.querySelector('#edit').oninput=feedback;
document.querySelector('#choice').onchange=feedback;
addEventListener('keydown',e=>{if(e.key==='Enter')feedback()});
</script>''', encoding='utf-8')
        actions = [('click #click', 'click'), ('dblclick #double', 'dblclick'),
                   ('drag #drag 20 0', 'drag'), ('type #edit X', 'type'),
                   ('fill #edit replacement', 'fill'), ('select #choice b', 'select'), ('key Enter', 'key')]
        for raw, action in actions:
            with self.subTest(action=action):
                output = self.folder / action
                self.shoot(output, '--size', 'desktop', '--record', '--wait', '0', '--hold', '100',
                           '--steps', f'click #prepare; wait 700; {raw}; wait 500; hover #tail; scroll 0')
                entry = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
                self.assertEqual(entry['sampling'], {'mode': 'action', 'step': 3, 'action': action, 'raw': raw})
                self.assertEqual(entry['issues'], [])
                frames = entry['frames']
                self.assertGreater(frames['start']['timeMs'], 1000)
                self.assertLess(frames['start']['timeMs'], frames['mid']['timeMs'])
                self.assertLess(frames['mid']['timeMs'], frames['end']['timeMs'])
                self.assertEqual(frames['end']['timeMs'], entry['durationMs'])
                self.assertGreater(frames['end']['timeMs'] - frames['mid']['timeMs'], 500)
                before = self.frame_pixel(output / frames['start']['file'], 80, 80)
                middle = self.frame_pixel(output / frames['mid']['file'], 80, 80)
                after = self.frame_pixel(output / frames['end']['file'], 80, 80)
                self.assertGreater(before[1], 220, before)
                self.assertLess(before[0], 40, before)
                self.assertGreater(middle[2], 170, middle)
                self.assertLess(middle[0], 100, middle)
                self.assertGreater(after[0], 220, after)
                self.assertLess(after[2], 40, after)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed to inspect frame pixels')
    def test_entry_recording_starts_white_when_the_browser_is_in_dark_mode(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX launch wrapper; on Windows the CI job with the dark system theme covers this')
        import shlex
        # A dark system theme makes the browser paint about:blank dark grey. The opening frame of an entry
        # recording must not depend on the host theme.
        wrapper = self.folder / 'dark-browser'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(self.browser) + ' --force-dark-mode "$@"\n', encoding='utf-8')
        wrapper.chmod(0o755)
        self.page.write_text('<!doctype html><link rel="icon" href="data:,"><style>body{margin:0;background:#ffd000}</style><p>entry</p>', encoding='utf-8')
        output = self.folder / 'dark-entry'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--record', '--entry', '--wait', '0', '--hold', '50'],
                                cwd=ROOT, env=dict(self.env, CHROME_PATH=str(wrapper)), capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first = self.frame_pixel(output / 'record.mp4')
        self.assertTrue(all(channel > 245 for channel in first), first)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed to inspect frame pixels')
    def test_entry_frames_span_content_to_stable(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
body{margin:0;background:#ffd000}#box{width:200px;height:200px;background:blue;animation:appear .6s linear both}
@keyframes appear{from{opacity:0}to{opacity:1}}
</style><div id="box"></div>''', encoding='utf-8')
        output = self.folder / 'entry-timing'
        self.shoot(output, '--record', '--entry', '--wait', '0', '--hold', '50')
        entry = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(entry['sampling'], {'mode': 'entry'})
        frames = entry['frames']
        self.assertLess(frames['start']['timeMs'], frames['mid']['timeMs'])
        self.assertLess(frames['mid']['timeMs'], frames['end']['timeMs'])
        self.assertEqual(frames['end']['timeMs'], entry['durationMs'])
        self.assertGreater(entry['durationMs'], 600)
        first = self.frame_pixel(output / 'record.mp4')
        self.assertTrue(all(channel > 245 for channel in first), first)
        start = self.frame_pixel(output / frames['start']['file'])
        middle = self.frame_pixel(output / frames['mid']['file'])
        end = self.frame_pixel(output / frames['end']['file'])
        self.assertGreater(start[0], middle[0] + 30, (start, middle))
        self.assertGreater(middle[0], end[0] + 30, (middle, end))
        self.assertLess(end[0], 20, end)
        self.assertGreater(end[2], 230, end)

    def test_record_without_changing_actions_keeps_head_middle_tail_sampling(self):
        output = self.folder / 'no-action-timing'
        self.shoot(output, '--record', '--steps', 'wait 200; hover #go', '--hold', '100')
        entry = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(entry['sampling'], {'mode': 'recording'})
        frames = entry['frames']
        self.assertEqual(frames['start']['timeMs'], 0)
        self.assertLessEqual(frames['start']['timeMs'], frames['mid']['timeMs'])
        self.assertLessEqual(frames['mid']['timeMs'], frames['end']['timeMs'])
        self.assertLessEqual(frames['end']['timeMs'], entry['durationMs'])
        self.assertEqual((output / frames['start']['file']).read_bytes(), (output / frames['end']['file']).read_bytes())

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
        ], capture_output=True, text=True, timeout=10, encoding='utf-8')
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
        self.assertIn("首次进入：没有检测到动画", issues)
        self.assertIn("滚动：没有检测到", issues)

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
        self.assertIn("页面不滚动", result.stdout)

    def test_record_entry_captures_first_appearance(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;background:#fde68a}
@keyframes rise{from{opacity:0;transform:translateY(160px)}to{opacity:1;transform:none}}
h1{margin:40px;height:300px;background:#1e3a8a;animation:rise .3s ease-out both}</style></head>
<body><h1></h1></body></html>''', encoding="utf-8")
        # 出场 0.3 秒就结束：默认录屏开录时已经播完，只有 --entry 能录到它
        late = self.folder / "late"
        self.shoot(late, "--record", "--hold", "300")
        self.assertEqual((late / "motion-start.jpg").read_bytes(), (late / "motion-end.jpg").read_bytes())
        output = self.folder / "entry"
        self.shoot(output, "--record", "--entry", "--hold", "300")
        self.assert_artifacts(output, ("motion-start.jpg", "motion-mid.jpg", "motion-end.jpg"))
        self.assertNotEqual((output / "motion-start.jpg").read_bytes(), (output / "motion-end.jpg").read_bytes())

    def test_missing_favicon_is_not_reported_as_a_page_problem(self):
        self.page.write_text('<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>小样</title></head>'
                             '<body><h1 style="font-size:32px">没有图标的小样</h1></body></html>', encoding="utf-8")
        output = self.folder / "no-favicon"
        self.shoot(output, "--size", "1280x900")
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report[0]["issues"], [])

    def test_reports_page_problems(self):
        self.page.write_text(self.page.read_text(encoding="utf-8").replace("</body>", '''
<div style="width:2000px">溢出</div><img src="missing.png">
<script>console.error('shoot-test-error'); throw new Error('shoot-test-exception');</script>
</body>'''), encoding="utf-8")
        for args in ((), ("--record", "--hold", "300")):
            with self.subTest(record=bool(args)):
                output = self.folder / ("problem-record" if args else "problem-shots")
                self.shoot(output, "--size", "1280x900", *args)
                report = json.loads((output / "report.json").read_text(encoding="utf-8"))
                issues = "\n".join(report[0]["issues"])
                for expected in ("shoot-test-error", "shoot-test-exception", "横向溢出", "图片没加载出来"):
                    self.assertIn(expected, issues)


    def test_lint_flags_default_patterns(self):
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
        self.assertIn("默认做法提示", result.stdout)

    def test_lint_spares_reactions_but_keeps_navigation_and_feature_emoji(self):
        self.page.write_text('''<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,">
<button aria-pressed="false"><span>😍</span><span>5</span></button>
<button><span>🔥</span> 3</button><button role="button" aria-pressed="true"><span>😂</span></button>
<p>用户内容 <span>🚀</span></p><blockquote><span>💰</span></blockquote>
<div role="listbox"><button>🧡</button><button>☀️</button></div>
<nav><button aria-pressed="true"><span>🚀</span> 启动</button><a><span>💰</span> 账户</a></nav>
<ul><li><span>🧭</span> 方向</li><li><span>🎉</span> 成果</li></ul>''', encoding='utf-8')
        output = self.folder / 'semantic-emoji'
        self.shoot(output)
        hints = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['lint']
        emoji = next(h for h in hints if h['rule'] == 'emojiIcon')
        self.assertEqual(emoji['count'], 4)
        self.assertFalse(any(symbol in ' '.join(emoji['examples']) for symbol in ('😍', '🔥', '😂', '🧡', '☀️')))

    def test_lint_spares_interaction_boundaries_attachments_and_empty_slots(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
body{margin:0}.outer{border-radius:12px;background:#eee;padding:12px;width:340px}
.box{border:1px solid #777;border-radius:8px;padding:8px;width:260px;min-height:56px;background:white}
.popup{position:absolute;top:0;left:420px}.fixed{position:fixed;top:90px;left:420px}
</style><form class="outer"><textarea></textarea>
<div class="box"><strong>draft.svg</strong><small>SVG · 1 KB</small><button>移除</button></div>
<div class="box"><strong>draft.svg</strong><small>正在读取</small><button>重试</button></div>
<div class="box popup">候选 <div class="box">选项</div></div>
<div class="box fixed">候选</div></form>
<div class="outer"><div class="box" role="listbox">候选</div><div class="box" role="menu">菜单</div>
<div class="box" role="dialog">对话</div><div class="box" role="tooltip">说明</div>
<div class="box" popover="manual" id="popover">弹层</div><div class="box"></div></div>
<script>popover.showPopover()</script>''', encoding='utf-8')
        output = self.folder / 'semantic-cards'
        self.shoot(output, '--size', 'desktop')
        hints = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['lint']
        self.assertNotIn('nestedCards', {h['rule'] for h in hints})

    def test_lint_keeps_content_cards_inside_panels_and_editors(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
.outer{border-radius:12px;background:#eee;padding:12px;width:340px}
.box{border:1px solid #777;border-radius:8px;padding:8px;width:260px;min-height:56px}
</style><div class="outer" style="position:relative;height:100px"><div class="box" style="position:absolute;left:12px;top:12px">真正的内容卡片</div></div>
<form class="outer"><textarea></textarea><div class="box"><h3>另一个内容面板</h3><p>说明</p><button>操作</button></div></form>''', encoding='utf-8')
        output = self.folder / 'real-cards'
        self.shoot(output, '--size', 'desktop')
        hints = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['lint']
        self.assertEqual(next(h for h in hints if h['rule'] == 'nestedCards')['count'], 2)

    def test_lint_requires_body_contrast_of_4_5(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.6 sans-serif;color:#222;background:#fff}
body::before{content:"";position:absolute;left:0;top:0;width:12px;height:12px;background:#111}
.soft{color:#8a8a8a}
.faint{color:#eee}
.faint-tiny{color:#eee;font-size:11px;line-height:1.2;width:280px}
.seg{position:relative;display:inline-block;padding:8px 16px}
.seg-pill{position:absolute;inset:0;background:#111;border-radius:8px}
.seg-label{position:relative;color:#fff}
.pseudo-seg{position:relative;display:inline-block;padding:8px 16px;color:#fff}
.pseudo-seg::before{content:"";position:absolute;inset:0;background:#111;border-radius:8px;z-index:-1}
</style></head><body>
<p class="soft">Body text at about 3.5 to 1 contrast still fails the 4.5 to 1 floor.</p>
<p class="faint">Body text at 1.16 to 1 on a plain white background must also be reported.</p>
<p class="faint-tiny">这是一段在白底上几乎看不见而且字号过小、行高过紧的多行中文正文，用来验证极低对比度不会跳过排版检查。</p>
<div class="seg"><span class="seg-pill"></span><span class="seg-label">Active Tab</span></div>
<div class="pseudo-seg">Pseudo Pill Tab</div>
</body></html>''', encoding="utf-8")
        output = self.folder / "soft"
        self.shoot(output, "--size", "1280x800")
        lint = {item["rule"]: item for item in json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["lint"]}
        self.assertIn("contrastLow", lint)
        self.assertEqual(lint["contrastLow"]["count"], 3)
        self.assertIn("smallText", lint)
        self.assertIn("tightLeading", lint)

    def test_lint_spares_css_triangles_and_neutral_dividers(self):
        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.6 sans-serif;color:#222}
.play{width:0;height:0;border-top:12px solid transparent;border-bottom:12px solid transparent;border-left:20px solid #e11d48}
aside{border-right:1px solid #ddd;height:200px;width:200px}
blockquote{border-left:4px solid #e11d48;padding:8px 16px;margin:16px 0}
nav a{display:block;position:relative;padding:8px 16px;width:120px}
nav a[aria-current="page"]{border-left:3px solid #2563eb}
nav a.active::before{content:"";position:absolute;left:0;top:4px;width:3px;height:32px;background:#2563eb}
@keyframes rise{from{opacity:0}to{opacity:1}}h1{animation:rise .6s ease-out both;font-size:40px;margin:48px 0 12px}
</style></head><body><span class="play"></span><aside>Sidebar</aside><blockquote>Quoted passage with semantic blockquote border.</blockquote>
<nav><a href="#a" aria-current="page">Overview</a><a href="#b" class="active">Settings</a><a href="#c">Billing</a></nav>
<p>Intro paragraph above the heading.</p>
<h1>Plain heading</h1><p>Body text that follows the heading closely.</p></body></html>''', encoding="utf-8")
        output = self.folder / "clean"
        self.shoot(output, "--size", "1280x800")
        self.assertEqual(json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["lint"], [])

        self.page.write_text('''<!doctype html><html><head><link rel="icon" href="data:,"><style>
body{margin:0;padding:40px;font:16px/1.6 sans-serif;color:#222}
nav a{display:block;position:relative;padding:8px 16px;width:120px}
nav a.plain-border{border-left:4px solid #e11d48}
nav a.plain-pseudo::before{content:"";position:absolute;left:0;top:4px;width:4px;height:32px;background:#e11d48}
</style></head><body><nav><a href="#a" class="plain-border">Unselected A</a><a href="#b" class="plain-pseudo">Unselected B</a></nav></body></html>''', encoding="utf-8")
        flagged = self.folder / "nav-unselected"
        self.shoot(flagged, "--size", "1280x800")
        lint = {item["rule"]: item for item in json.loads((flagged / "report.json").read_text(encoding="utf-8"))[0]["lint"]}
        self.assertIn("sideStripe", lint)
        self.assertEqual(lint["sideStripe"]["count"], 2)

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
        self.assertIn("差异明显的像素占", result.stdout)
        missing = subprocess.run([NODE, str(SCRIPT), str(self.page), "--compare", str(self.folder / "nope.png")],
                                 cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("找不到参考图", missing.stderr)

    def test_reports_blank_webgl_canvas(self):
        # 同一块画布已经拿了 2d 上下文，再要 webgl 必然失败，用它模拟“截图成功但画布是空的”
        self.page.write_text(self.page.read_text(encoding="utf-8").replace("</body>", '''
<canvas id="bad"></canvas><canvas id="good"></canvas>
<script>
const bad = document.querySelector('#bad'); bad.getContext('2d'); bad.getContext('webgl');
const good = document.querySelector('#good'); good.getContext('webgl2') || good.getContext('webgl');
</script></body>'''), encoding="utf-8")
        output = self.folder / "webgl"
        self.shoot(output)
        issues = "\n".join(json.loads((output / "report.json").read_text(encoding="utf-8"))[0]["issues"])
        self.assertIn("WebGL：1 个画布没能创建绘图上下文", issues)

    def run_failure(self, output, *args):
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), "--out", str(output), *args],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=110, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        return result

    def test_fill_replaces_and_fires_events_while_type_inserts_at_cursor(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,">
<input id="insert" value="seed"><input id="replace" value="old value">
<textarea aria-label="Message box">old text</textarea><input id="empty" value="old value">
<div id="rich" contenteditable="true">old content</div><button id="verify">Verify</button>
<script>
const insert=document.querySelector('#insert'); insert.onfocus=()=>insert.setSelectionRange(2,2);
const changes={};
for(const el of document.querySelectorAll('#replace,textarea,#empty,#rich')) {
  changes[el.id||'textarea']=[];
  for(const event of ['input','change'])el.addEventListener(event,e=>{
    if(!e.bubbles)console.error('fill-event-not-bubbling');
    changes[el.id||'textarea'].push([event,el.isContentEditable?el.textContent:el.value]);
  });
}
document.querySelector('#verify').onclick=()=>{
  if(insert.value!=='seXed')console.error('type-did-not-insert-at-cursor');
  for(const [key,value] of Object.entries({replace:'new value',textarea:'new text',empty:'',rich:'new content'})) {
    const el=key==='textarea'?document.querySelector('textarea'):document.getElementById(key);
    if((el.isContentEditable?el.textContent:el.value)!==value ||
       JSON.stringify(changes[key])!==JSON.stringify([['input',value],['change',value]]))console.error('fill-failed-'+key);
  }
};</script>''', encoding='utf-8')
        output = self.folder / 'fill'
        self.shoot(output, '--size', 'desktop', '--steps', 'type #insert X; fill #replace "new value"; '
                   'fill [aria-label="Message box"] "new text"; fill #empty ""; '
                   'fill #rich "new content"; click #verify')
        self.assertEqual(json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues'], [])

    def test_fill_rejects_non_editable_elements_with_context(self):
        result = self.run_failure(self.folder / 'fill-invalid', '--steps', 'fill #go hello')
        self.assertIn('第 1 步「fill #go hello」', result.stderr)
        self.assertIn('fill 需要输入框、文本域或可编辑元素', result.stderr)
        self.assertIn('例如 fill #message "hello world"', result.stderr)

    def test_click_doubleclick_and_hover_warn_about_blocker_and_still_execute(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
#target,.veil{position:absolute;left:20px;top:20px;width:120px;height:60px}.veil{z-index:2}
#verify{position:absolute;left:200px;top:20px}</style>
<button id="target">Target</button><div class="veil">Overlay</div><button id="verify">Verify</button>
<script>
let clicks=0,doubles=0,hovers=0,hits=0;
document.querySelector('.veil').onclick=()=>clicks++;
document.querySelector('.veil').ondblclick=()=>doubles++;
document.querySelector('.veil').onmouseenter=()=>hovers++;
document.querySelector('#target').onclick=()=>hits++;
document.querySelector('#verify').onclick=()=>{
if(clicks!==3 || doubles!==1 || hovers!==1 || hits!==0)console.error('blocked-actions-not-executed');
};</script>''', encoding='utf-8')
        output = self.folder / 'blocked'
        result = self.shoot(output, '--steps', 'hover #target; click #target; dblclick #target; click #verify')
        issues = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues']
        self.assertEqual(len(issues), 3, issues)
        for i, action in enumerate(['hover', 'click', 'dblclick'], 1):
            message = f'第 {i} 步「{action} #target」：中心点被 div.veil 挡住'
            self.assertIn(message, issues[i - 1])
            self.assertIn(message, result.stdout)
            self.assertIn('动作仍照常执行', issues[i - 1])
        self.assertIn('发现 3 个问题', result.stdout)

    def test_descendant_at_center_is_not_a_blocker_and_mark_does_not_warn(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
#target{width:120px;height:60px}#target span{display:block;width:100%;height:100%}</style>
<button id="target"><span>Target</span></button><button id="disabled" disabled>Disabled</button>
<script>let count=0;document.querySelector('#target').onclick=()=>count++;
document.querySelector('#target').ondblclick=()=>{if(count!==3)console.error('descendant-click-failed')};</script>''', encoding='utf-8')
        output = self.folder / 'descendant'
        result = self.shoot(output, '--steps', 'hover #target; click #target; dblclick #target', '--mark', '#disabled')
        self.assertEqual(json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues'], [])
        self.assertNotIn('提示：第', result.stdout)

    def test_disabled_reasons_are_warnings_and_do_not_stop_actions(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>button{width:100px;height:50px}</style>
<button id="disabled" disabled>Disabled</button><button id="aria" aria-disabled="true">Aria</button>
<button id="pointer" style="pointer-events:none">Pointer</button>
<fieldset disabled><button id="inherited">Inherited</button></fieldset><button id="verify">Verify</button>
<script>let count=0;document.querySelector('#aria').onclick=()=>count++;
document.querySelector('#verify').onclick=()=>{if(count!==1)console.error('aria-action-stopped')};</script>''', encoding='utf-8')
        output = self.folder / 'disabled'
        result = self.shoot(output, '--size', 'desktop', '--steps', 'hover #disabled; click #aria; '
                            'dblclick #pointer; click #inherited; click #verify')
        issues = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues']
        for step, reason in [('hover #disabled', 'disabled'), ('click #aria', 'aria-disabled="true"'),
                             ('dblclick #pointer', 'pointer-events: none'), ('click #inherited', 'disabled')]:
            self.assertTrue(any(f'「{step}」：目标处于禁用状态（{reason}）' in issue for issue in issues), issues)
            self.assertIn(reason, result.stdout)
        self.assertFalse(any('控制台错误' in issue for issue in issues), issues)
        self.assertIn(f'发现 {len(issues)} 个问题', result.stdout)

    def test_action_warnings_are_in_recording_and_motion_reports(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
#target,#overlay{position:absolute;top:20px;left:20px;width:100px;height:50px}#overlay{z-index:2}</style>
<button id="target" aria-disabled="true">Target</button><div id="overlay">Overlay</div>''', encoding='utf-8')
        output = self.folder / 'warning-record'
        result = self.shoot(output, '--motion', '--record', '--steps', 'click #target', '--hold', '0')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report), 2)
        self.assertIn('motion', report[0])
        for entry in report:
            self.assertTrue(any('中心点被 div#overlay 挡住' in issue for issue in entry['issues']), entry)
            self.assertTrue(any('aria-disabled="true"' in issue for issue in entry['issues']), entry)
        self.assertIn('中心点被 div#overlay 挡住', result.stdout)
        self.assertIn(f"发现 {sum(len(r['issues']) for r in report)} 个问题", result.stdout)
        # A later failure must not erase warnings already raised by the recording.
        failed = self.folder / 'warning-before-failure'
        result = self.run_failure(failed, '--record', '--steps', 'click #target; click .missing', '--hold', '0')
        entry = json.loads((failed / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertTrue(entry['failed'])
        self.assertTrue(any('中心点被 div#overlay 挡住' in issue for issue in entry['issues']), entry)
        self.assertTrue(any('aria-disabled="true"' in issue for issue in entry['issues']), entry)
        self.assertTrue(any('找不到元素 .missing' in issue for issue in entry['issues']), entry)
        self.assertIn(f"发现 {len(entry['issues'])} 个问题", result.stdout)
        self.assertEqual(list(failed.glob('frames*')), [])

    def test_missing_elements_explain_iframe_and_open_shadow_root_scope(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,">
<iframe srcdoc="<button id='framed'>Framed</button>"></iframe><iframe srcdoc="<p>Another frame</p>"></iframe>
<div id="host"></div><div id="closed"></div><script>
const root=document.querySelector('#host').attachShadow({mode:'open'});
root.innerHTML='<button id="shadowed">Shadowed</button><div id="nested"></div>';
root.querySelector('#nested').attachShadow({mode:'open'}).innerHTML='<button>Nested</button>';
document.querySelector('#closed').attachShadow({mode:'closed'}).innerHTML='<button>Closed</button>';
</script>''', encoding='utf-8')
        for args in [('--steps', 'click #framed'), ('--steps', 'click text=Shadowed'),
                     ('--steps', 'fill #shadowed hello'), ('--mark', '#shadowed')]:
            with self.subTest(args=args):
                result = self.run_failure(self.folder / 'scope', *args)
                self.assertIn('找不到元素', result.stderr)
                self.assertIn('选择器只在主文档里找，页面里有 2 个 iframe、2 个开放的 shadow root', result.stderr)
        self.page.write_text('<!doctype html><link rel="icon" href="data:,"><body></body>', encoding='utf-8')
        result = self.run_failure(self.folder / 'no-roots', '--steps', 'click .missing')
        self.assertNotIn('选择器只在主文档里找', result.stderr)

    def test_missing_element_scope_counts_iframes_and_shadow_roots_independently(self):
        for markup, expected in [
            ('<iframe srcdoc="<p>Frame</p>"></iframe>', '1 个 iframe、0 个开放的 shadow root'),
            ('''<div id="host"></div><script>document.querySelector('#host').attachShadow({mode:'open'}).innerHTML='<p>Shadow</p>';</script>''',
             '0 个 iframe、1 个开放的 shadow root'),
        ]:
            with self.subTest(expected=expected):
                self.page.write_text('<!doctype html><link rel="icon" href="data:,">' + markup, encoding='utf-8')
                result = self.run_failure(self.folder / 'root-counts', '--steps', 'click .missing')
                self.assertIn(expected, result.stderr)

    def test_actions_text_selectors_and_marks(self):
        self.page.write_text('''<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,"><style>
body{margin:0;padding:20px}button{padding:12px}.hidden{display:none}</style>
<div class="nav"><button aria-label="Send money">More</button><button id="double">Undo</button></div>
<input aria-label="Message box"><select id="choice"><option value="a">First</option><option value="b">Second item</option></select>
<div id="status"></div><button class="hidden">More</button><div data-label="a;b">Semicolon</div>
<script>
let count=0; document.querySelector('[aria-label]').onclick=()=>count++;
document.querySelector('#double').ondblclick=()=>count+=10;
document.querySelector('#double').onmouseenter=()=>document.body.dataset.hover='yes';
for(const event of ['input','change']) document.querySelector('#choice').addEventListener(event,()=>document.body.dataset[event]='yes');
setTimeout(()=>{const b=document.createElement('button');b.textContent='Ready';document.body.append(b)},700);
setInterval(()=>document.querySelector('#status').textContent=JSON.stringify({count,text:document.querySelector('input').value,choice:document.querySelector('select').value,hover:document.body.dataset.hover,input:document.body.dataset.input,change:document.body.dataset.change}),30);
</script>''', encoding="utf-8")
        output = self.folder / "actions"
        result = self.shoot(output, "--steps", 'click text=More; click [aria-label="Send money"]; '
                            'click "[aria-label=\\"Send money\\"]"; hover button:has-text("Undo"); '
                            'doubleclick button:has-text(\'Undo\'); fill [aria-label="Message box"] "hello world"; '
                            'press ControlOrMeta+A; type "body input" "replacement"; select #choice b; '
                            'select #choice "Second item"; waitfor text=Ready; sleep 0.1s; '
                            'click [data-label="a;b"]; click :has-text("Semicolon")',
                            "--mark", '1=text=More; 2=button:has-text("Undo")')
        self.assert_artifacts(output, ("page.png", "page-marked.png"))
        # The report includes console output only on errors, so assert browser state through a guard.
        self.page.write_text(self.page.read_text(encoding='utf-8').replace('setInterval(()=>document', '''setTimeout(()=>{
if(count!==13 || document.querySelector('input').value!=='replacement' || document.querySelector('select').value!=='b' || document.body.dataset.hover!=='yes' || document.body.dataset.input!=='yes' || document.body.dataset.change!=='yes') console.error('action-guard-failed');
},2600);setInterval(()=>document'''), encoding='utf-8')
        self.shoot(self.folder / "guard", "--steps", 'click text=More; click [aria-label="Send money"]; '
                   'click "[aria-label=\\"Send money\\"]"; hover button:has-text("Undo"); '
                   'dblclick button:has-text("Undo"); type [aria-label="Message box"] "hello world"; '
                   'key ControlOrMeta+A; type "body input" replacement; select #choice "Second item"; wait 2000')
        report = json.loads((self.folder / "guard/report.json").read_text(encoding='utf-8'))
        self.assertEqual(report[0]["issues"], [], result.stdout)

    def test_selector_errors_include_context_and_hints(self):
        for raw, expected in [
            ('wait 0; click [id="missing"]', ('第 2 步', 'click [id="missing"]', 'id="go"')),
            ('click text=切', ('',)),  # containment fallback succeeds, tested separately
            ('click text=切换不存在', ('可见文字', '切换')),
            ('click body .missing', ('"body" 匹配 1 个元素',)),
            ('click button:unknown', ('不是合法的 CSS', 'text="Send money"', 'button:has-text("Undo")')),
            ('waitfor .missing', ('第 1 步', 'waitfor .missing', '找不到元素')),
        ]:
            if expected == ('',):
                # POSIX hands argv over as bytes in the locale's encoding and node reads them as UTF-8, so under a
                # non-UTF-8 locale this selector is garbled before the tool sees it. Windows passes Unicode.
                if sys.platform == 'win32' or sys.getfilesystemencoding().lower().replace('-', '') == 'utf8':
                    self.shoot(self.folder / "contained", "--steps", raw)
                continue
            with self.subTest(raw=raw):
                result = self.run_failure(self.folder / "missing", "--steps", raw)
                for text in expected:
                    self.assertIn(text, result.stderr)
        self.run_failure(self.folder / "mark-invalid", "--mark", "button:unknown")

    def test_playwright_selectors_find_the_intended_elements(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>button{margin:8px}</style>
<button onclick="hits.push('contains')">Save draft</button>
<button onclick="hits.push('exact')">Save</button>
<button onclick="hits.push('wrong')">Save more</button>
<button data-select="0842" onclick="hits.push('numeric')">Numeric</button>
<div><button class="item" onclick="hits.push('wrong')">First</button></div>
<p>Different sibling</p><button class="item" onclick="hits.push('nth')">Second</button>
<button onclick="hits.push('bare')">Unique nested <span>Target</span></button>
<button onclick="hits.push('chain')">4 replies</button>
<button data-label='literal :has-text("x") &gt;&gt; nth=1' onclick="hits.push('literal')">Literal</button>
<button id="verify" onclick="if(hits.join(',')!=='contains,exact,numeric,nth,bare,chain,literal')console.error(hits)">Verify</button>
<script>const hits=[];</script>''', encoding='utf-8')
        output = self.folder / 'playwright'
        self.shoot(output, '--size', 'desktop', '--steps',
                   '''click button:has-text("Save draft"); click button:text-is('Save');
click [data-select=0842]; click ".item >> nth=1"; click :has-text("Target");
click button:has-text(4):has-text(replies); click [data-label='literal :has-text("x") >> nth=1']; click #verify''',
                   '--mark', '1=button:text-is("Save"); 2=[data-select=0842]; 3=.item >> nth=1')
        self.assertEqual(json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues'], [])
        self.assert_artifacts(output, ('page.png', 'page-marked.png'))
        # Corpus calls also omit text quotes and escape nested quotes around the whole selector.
        self.shoot(self.folder / 'unquoted-text', '--steps', 'hover "button:text-is(Save)"; hover "button:has-text(\\"Save draft\\")"')

    def test_playwright_exact_text_and_nth_do_not_fall_back(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,">
<button>Save more</button><button class="item" hidden>Hidden</button><button class="item">Visible</button>''', encoding='utf-8')
        result = self.run_failure(self.folder / 'exact-missing', '--steps', 'wait 0; click button:text-is("Save")')
        self.assertIn('第 2 步', result.stderr)
        self.assertIn('找不到元素', result.stderr)
        result = self.run_failure(self.folder / 'hidden-nth', '--steps', 'click .item >> nth=0')
        self.assertIn('都不可见', result.stderr)
        result = self.run_failure(self.folder / 'missing-nth', '--steps', 'click .item >> nth=2')
        self.assertIn('找不到元素', result.stderr)
        self.shoot(self.folder / 'last-nth', '--steps', 'hover .item >> nth=-1')

    def test_unsupported_playwright_combinations_give_context_and_copyable_examples(self):
        for selector, rewrite in [('button:has-text("Save") > span', 'text="Save"'),
                                 ('.item >> nth=one', '.item >> nth=1'),
                                 (':is(button:has-text("Save"))', 'text="Save"'),
                                 ('button:has-text("Save") >> text=Draft', 'text="Save"')]:
            with self.subTest(selector=selector):
                result = self.run_failure(self.folder / 'unsupported', '--steps', 'wait 0; hover ' + selector)
                self.assertIn('第 2 步', result.stderr)
                self.assertIn('收到 ' + selector, result.stderr)
                self.assertIn('例如 hover ' + rewrite, result.stderr)
        result = self.run_failure(self.folder / 'unsupported-mark', '--mark', '.item >> nth=one')
        self.assertIn('--mark', result.stderr)
        self.assertIn('收到 .item >> nth=one', result.stderr)
        result = self.run_failure(self.folder / 'unsupported-fill', '--steps', 'fill ".item >> nth=one" hello')
        self.assertIn('例如 fill ".item >> nth=1" "hello"', result.stderr)

    def test_visible_element_does_not_scroll_and_offscreen_does(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
body{margin:0;height:2400px}#top{position:absolute;top:40px}#bottom{position:absolute;top:1800px}</style>
<button id="top">Top</button><button id="bottom">Bottom</button><script>
let last=0;topButton=document.querySelector('#top');topButton.onmouseenter=()=>{if(scrollY!==0)console.error('visible-scrolled')};
topButton.onclick=()=>{if(scrollY!==0)console.error('visible-scrolled')};
document.querySelector('#bottom').onclick=()=>{if(scrollY===0)console.error('offscreen-not-scrolled')};
</script>''', encoding='utf-8')
        self.shoot(self.folder / "scroll", "--size", "desktop", "--steps", "hover #top; click #top; click #bottom")
        self.assertEqual(json.loads((self.folder / "scroll/report.json").read_text(encoding='utf-8'))[0]["issues"], [])

    def test_query_multiple_zooms_and_groups_reset(self):
        self.page.write_text(self.page.read_text(encoding='utf-8').replace('</body>', '''<script>
if(new URLSearchParams(location.search).get('a')!=='1' || new URLSearchParams(location.search).get('b')!=='two words')console.error('query-missing');
document.querySelector('#go').addEventListener('click',()=>{if(document.body.dataset.state!=='b')console.error('group-not-reset')});
</script></body>'''), encoding='utf-8')
        output = self.folder / "multiple"
        self.shoot(output, "--size=desktop", "--zoom=1,2", "--query", "a=1&b=two+words", "--states", "a",
                   "--steps", "open: click body #go", "--steps", "send: click #go")
        self.assert_artifacts(output, ("a-open.png", "a-send.png", "a-open-@2x.png", "a-send-@2x.png"))
        report = json.loads((output / "report.json").read_text(encoding='utf-8'))
        self.assertTrue(all(r["issues"] == [] for r in report))
        self.assertEqual([r["zoom"] for r in report], [1, 1, 2, 2])
        aliases = self.folder / "aliases"
        self.shoot(aliases, "--size", "phone,800x600", "--query", "a=1&b=two+words")
        self.assert_artifacts(aliases, ("page-390x844.png", "page-800x600.png"))

    def test_named_and_unnamed_record_groups(self):
        output = self.folder / "record-groups"
        self.shoot(output, "--record", "--hold=100", "--wait=0", "--steps", "open: click #go", "--steps", "click #go")
        self.assert_artifacts(output, ("motion-open-start.jpg", "motion-open-mid.jpg", "motion-open-end.jpg", "motion-2-end.jpg"))
        if shutil.which('ffmpeg'):
            self.assert_artifacts(output, ("record-open.mp4", "record-2.mp4"))
        self.assertEqual(len(json.loads((output / "report.json").read_text(encoding='utf-8'))), 2)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed for complete evidence')
    def test_evidence_all_artifacts_and_partial_failure(self):
        output = self.folder / "evidence"
        self.shoot(output, "--evidence", "--states=a,b", "--hold=100", "--steps", "toggle: click #go")
        self.assert_artifacts(output, ("a.png", "b.png", "a-masked.png", "b-masked.png", "sheet.png", "sheet-masked.png",
                                      "a-@2x.png", "record-entry.mp4", "motion-entry-start.jpg", "motion-entry-mid.jpg", "motion-entry-end.jpg",
                                      "record-toggle.mp4", "motion-toggle-start.jpg", "motion-toggle-mid.jpg", "motion-toggle-end.jpg"))
        report = json.loads((output / "report.json").read_text(encoding='utf-8'))
        self.assertTrue(any(r["file"] == "motion-probe-toggle" for r in report))
        self.assertFalse((output / 'b-@2x.png').exists(), 'Default evidence still gives only the first state a 2x shot')
        failed = self.folder / "partial"
        result = self.run_failure(failed, "--evidence", "--hold=100", "--steps", "broken: click .missing", "--steps", "good: click #go")
        self.assert_artifacts(failed, ("page.png", "page-@2x.png", "record-entry.mp4", "record-good.mp4", "report.json"))
        report = json.loads((failed / "report.json").read_text(encoding='utf-8'))
        self.assertEqual(sum(r.get("failed", False) for r in report), 2)
        self.assertIn("失败", result.stdout)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed for complete evidence')
    def test_evidence_explicit_zooms_cover_each_state_and_entry_starts_blank(self):
        import struct
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
body{margin:0;background:#223344}#box{width:120px;height:120px;background:blue;animation:appear .36s linear both}
@keyframes appear{from{opacity:0}to{opacity:1}}#go{position:absolute;top:200px}
</style><div id="box"></div><button id="go">Change</button><script>
if(innerWidth!==800 || innerHeight!==600)console.error('zoom-changed-layout');
if(new URLSearchParams(location.search).get('state')==='b')document.body.style.background='#441122';
document.querySelector('#go').onclick=()=>document.body.style.background='#151515';
</script>''', encoding='utf-8')
        for option, zooms in [('--zoom=1', [1]), ('--zoom=1,2', [1, 2]), ('--zoom=2,3', [2, 3])]:
            with self.subTest(option=option):
                output = self.folder / ('evidence-' + '-'.join(map(str, zooms)))
                self.shoot(output, '--evidence', '--states', 'a,b', '--size', '800x600', option,
                           '--hold', '50', '--steps', 'change: click #go')
                report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
                shots = [entry for entry in report if entry['file'].endswith('.png')]
                self.assertEqual([(entry['zoom'], entry['state']) for entry in shots],
                                 [(zoom, state) for zoom in zooms for state in ['a', 'b']])
                self.assertTrue(all(entry['issues'] == [] for entry in shots), shots)
                for zoom in zooms:
                    suffix = '' if zoom == 1 else f'-@{zoom}x'
                    for state in ['a', 'b']:
                        name = f'{state}{suffix}.png'
                        dimensions = struct.unpack('>II', (output / name).read_bytes()[16:24])
                        self.assertEqual(dimensions, (800 * zoom, 600 * zoom))
                        self.assert_artifacts(output, (name, f'{state}{suffix}-masked.png'))
                    # Single-zoom sheets keep their existing names.
                    sheet_suffix = suffix if len(zooms) > 1 else ''
                    self.assert_artifacts(output, (f'sheet{sheet_suffix}.png', f'sheet{sheet_suffix}-masked.png'))
                if 1 not in zooms:
                    self.assertFalse((output / 'a.png').exists())
                if 2 not in zooms:
                    self.assertFalse((output / 'a-@2x.png').exists())
                entry = next(item for item in report if item.get('group') == 'entry')
                self.assertEqual(entry['sampling']['mode'], 'entry')
                first = self.frame_pixel(output / 'record-entry.mp4')
                self.assertTrue(all(channel > 245 for channel in first), first)
                # Content frames must belong to the new page, not the previous dark completed page.
                self.assertNotEqual(self.frame_pixel(output / entry['frames']['start']['file']), (21, 21, 21))
                self.assertEqual(list(output.glob('frames*')), [])

    def test_browser_timeout_retries_once(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX launch wrapper')
        wrapper = self.folder / 'chrome-wrapper'
        marker = self.folder / 'launch-count'
        # Accelerate the startup watchdog, but launch a real browser on the second run.
        import shlex
        wrapper.write_text('#!/bin/sh\nif [ ! -f ' + shlex.quote(str(marker)) + ' ]; then\n'
                           'touch ' + shlex.quote(str(marker)) + '\nexec sleep 60\nfi\nexec '
                           + shlex.quote(self.browser) + ' "$@"\n', encoding='utf-8')
        wrapper.chmod(0o755)
        env, journal = self.transport_fault_env('launch')
        env['CHROME_PATH'] = str(wrapper)
        output = self.folder / 'retried'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=110, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('45 秒内没有启动', result.stderr)
        self.assertIn('正在重试一次', result.stderr)
        self.assertIn('--timeout-scale 2', result.stderr)
        self.assertIn('同时开了很多个任务时会变慢', result.stderr)
        self.assert_artifacts(output, ('page.png', 'report.json'))
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])
        events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([row['timeout'] for row in events if row.get('stage') == 'launch'], [45000, 90000])

    def test_navigation_aborted_once_is_retried(self):
        import http.server
        import threading
        requests = []

        class AbortFirst(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                if handler.path != '/page':
                    handler.send_response(404)
                    handler.end_headers()
                    return
                requests.append(handler.path)
                if len(requests) == 1:
                    # A response without content cancels the navigation: the browser reports net::ERR_ABORTED.
                    handler.send_response(204)
                    handler.end_headers()
                    return
                body = b'<!doctype html><link rel="icon" href="data:,"><h1>loaded</h1>'
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/html; charset=utf-8')
                handler.send_header('Content-Length', str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(*args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), AbortFirst)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        output = self.folder / 'aborted-once'
        result = subprocess.run([NODE, str(SCRIPT), f'http://127.0.0.1:{server.server_port}/page', '--out', str(output)],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(requests), 2, requests)
        self.assert_artifacts(output, ('page.png', 'report.json'))

    def test_run_leaves_no_browser_process_or_profile(self):
        output = self.folder / 'clean'
        self.shoot(output)
        self.assert_artifacts(output, ('page.png', 'report.json'))
        self.assert_no_browser_leftovers()

    def test_launcher_that_hands_off_and_exits_is_ready_and_cleaned(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX launch wrapper')
        import shlex
        # The spawned process starts the real browser in the background and exits at once. Its stderr never
        # reaches the tool, so readiness has to come from the DevToolsActivePort file in the profile.
        wrapper = self.folder / 'hand-off'
        wrapper.write_text('#!/bin/sh\nnohup ' + shlex.quote(self.browser) + ' "$@" >/dev/null 2>&1 &\nexit 0\n', encoding='utf-8')
        wrapper.chmod(0o755)
        output = self.folder / 'handed-off'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output)], cwd=ROOT,
                                env=dict(self.env, CHROME_PATH=str(wrapper)), capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_artifacts(output, ('page.png', 'report.json'))
        self.assert_no_browser_leftovers()

    def test_browser_that_never_becomes_ready_is_killed_by_profile(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX launch wrapper')
        # The launcher exits while a real browser keeps running on a profile inside the tool's temporary folder,
        # so no readiness signal ever appears. Killing the spawned process would not reach that browser.
        wrapper = self.folder / 'never-ready'
        wrapper.write_text('#!' + sys.executable + '\nimport subprocess, sys\n'
                           'args = [a + "/elsewhere" if a.startswith("--user-data-dir=") else a for a in sys.argv[1:]]\n'
                           'subprocess.Popen([' + repr(self.browser) + ', *args], stdout=subprocess.DEVNULL, '
                           'stderr=subprocess.DEVNULL, start_new_session=True)\n', encoding='utf-8')
        wrapper.chmod(0o755)
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(self.folder / 'never')], cwd=ROOT,
                                env=dict(self.env, CHROME_PATH=str(wrapper)), capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('浏览器启动失败', result.stderr)
        self.assert_no_browser_leftovers()


    def test_text_matching_priority_and_combo_modifiers(self):
        self.page.write_text('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><style>button{padding:12px}</style>
<section><span>More</span><button id="clickable">More</button></section>
<div><button id="deep"><span>Deep</span></button></div><button id="partial">Send money now</button>
<div hidden><div><button>More</button></div></div><input id="edit"><button id="verify">Verify</button>
<script>
const hits=[];for(const id of ['clickable','deep','partial'])document.getElementById(id).onclick=()=>hits.push(id);
const keys=[];addEventListener('keydown',e=>keys.push([e.key,e.metaKey,e.ctrlKey,e.shiftKey]));
document.getElementById('verify').onclick=()=>{
if(hits.join(',')!=='clickable,deep,partial')console.error('text-priority-failed');
if(!keys.some(k=>k[0]==='A'&&k[1]) || !keys.some(k=>k[0]==='A'&&k[2]) || !keys.some(k=>k[0]==='Tab'&&k[3]))console.error('combo-modifiers-failed');
};</script>''', encoding='utf-8')
        output = self.folder / 'priorities'
        self.shoot(output, '--steps', 'click text=More; click text=Deep; click text="Send money"; '
                   'click #edit; key Meta+A; key Control+A; key Shift+Tab; click #verify')
        self.assertEqual(json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues'], [])

    def test_mark_and_waitfor_accept_later_visible_css_match(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><button class="target" hidden>Hidden</button>
<button class="target">Shown</button><div class="delayed" style="opacity:0">Ready</div>
<script>setTimeout(()=>document.querySelector('.delayed').style.opacity=1,800)</script>''', encoding='utf-8')
        output = self.folder / 'visible-match'
        self.shoot(output, '--steps', 'waitfor .target; waitfor .delayed', '--mark', '.target')
        self.assert_artifacts(output, ('page.png', 'page-marked.png'))

    def test_single_zoom_preserves_sheet_and_record_names(self):
        output = self.folder / 'zoom-sheet'
        self.shoot(output, '--zoom', '2', '--states', 'a,b', '--sheet', '--mask')
        self.assert_artifacts(output, ('a-@2x.png', 'sheet.png', 'sheet-masked.png'))
        output = self.folder / 'zoom-record'
        self.shoot(output, '--zoom', '2', '--record', '--steps', 'click #go', '--hold', '100')
        self.assert_artifacts(output, ('motion-start.jpg', 'motion-mid.jpg', 'motion-end.jpg'))
        if shutil.which('ffmpeg'):
            self.assert_artifacts(output, ('record.mp4',))


    def test_hidden_matches_report_count_reason_and_visible_example(self):
        cases = [
            ('style="display:none"', '', 'display:none'),
            ('style="visibility:hidden"', '', 'visibility:hidden'),
            ('style="width:0;height:0;padding:0;border:0"', '', '尺寸为 0'),
            ('', 'display:none', '被祖先 div#container 隐藏：display:none'),
            ('', 'visibility:hidden', '被祖先 div#container 隐藏：visibility:hidden'),
            ('', 'opacity:0', '被祖先 div#container 隐藏：opacity:0'),
        ]
        for attrs, parent_style, reason in cases:
            with self.subTest(reason=reason):
                self.page.write_text(f'''<!doctype html><link rel="icon" href="data:,">
<button data-view="activity">Activity</button><div id="container" style="{parent_style}">
<button data-view="accounts" {attrs}>Accounts</button><button data-view="accounts" {attrs}>Accounts 2</button></div>''', encoding='utf-8')
                result = self.run_failure(self.folder / 'hidden', '--size', 'desktop', '--steps', 'click [data-view="accounts"]')
                self.assertIn('匹配到 2 个元素', result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertNotIn('找不到元素', result.stderr)
                self.assertIn('先执行让它出现的那一步', result.stderr)
                self.assertIn('例如 click [data-view="activity"]', result.stderr)
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><details id="tools">
<summary>Tools</summary><button data-view="accounts">Accounts</button></details>''', encoding='utf-8')
        result = self.run_failure(self.folder / 'closed', '--steps', 'click [data-view="accounts"]')
        self.assertIn('details 未展开', result.stderr)
        self.assertIn('例如 click #tools > summary', result.stderr)
        self.shoot(self.folder / 'opened', '--steps', 'click #tools > summary; click [data-view="accounts"]')

    def test_all_actions_choose_first_visible_match(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>button{padding:12px}</style>
<button class="target" hidden>Hidden</button><button class="target">Visible</button>
<input class="edit" hidden><input class="edit">
<select class="choice" hidden><option value="a">A</option><option value="b">B</option></select>
<select class="choice"><option value="a">A</option><option value="b">B</option></select>
<button class="double" hidden>Hidden</button><button class="double">Double</button>
<div class="drag" hidden>Hidden</div><div class="drag" style="width:100px;height:50px">Drag</div>
<button id="verify">Verify</button><script>
let clicked=0, hovered=false, doubled=false, dragged=false;
const target=document.querySelectorAll('.target')[1]; target.onclick=()=>clicked++; target.onmouseenter=()=>hovered=true;
document.querySelectorAll('.double')[1].ondblclick=()=>doubled=true;
document.querySelectorAll('.drag')[1].onmousedown=()=>dragged=true;
document.querySelector('#verify').onclick=()=>{
if(clicked!==1 || !hovered || !doubled || !dragged || document.querySelectorAll('.edit')[1].value!=='hello' || document.querySelectorAll('.choice')[1].value!=='b')console.error('visible-match-failed');
};</script>''', encoding='utf-8')
        output = self.folder / 'visible-actions'
        self.shoot(output, '--size', 'desktop', '--steps', 'hover .target; click .target; dblclick .double; '
                   'drag .drag 20 0; type .edit hello; select .choice b; waitfor .target; click #verify')
        self.assertEqual(json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['issues'], [])
        # waitfor must continue polling matches that exist but are still hidden.
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><button id="later" hidden>Ready</button>
<script>setTimeout(()=>document.querySelector('#later').hidden=false,700)</script>''', encoding='utf-8')
        self.shoot(self.folder / 'later', '--wait', '0', '--steps', 'waitfor #later; click #later')

    def test_selector_examples_and_text_hints_are_relevant(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><p>Alpha unrelated</p><p>Send monez</p>
<button>Send money now</button><button data-view="accounts" hidden>Hidden</button>
<button data-view="activity">Activity</button>''', encoding='utf-8')
        for action in ['click', 'hover', 'dblclick']:
            result = self.run_failure(self.folder / action, '--steps', action + ' [data-view="missing"]')
            self.assertIn('例如 ' + action + ' [data-view="activity"]', result.stderr)
            self.assertLess(result.stderr.index('data-view="activity"'), result.stderr.index('data-view="accounts"'))
        # A CSS-filtered text search misses; the text hint search covers the visible page.
        result = self.run_failure(self.folder / 'text-hint', '--steps', 'click a:has-text("Send money")')
        self.assertIn('例如 click text="Send money now"', result.stderr)
        self.assertLess(result.stderr.index('可见文字 "Send money now"'), result.stderr.index('可见文字 "Send monez"'))
        result = self.run_failure(self.folder / 'similar', '--steps', 'click text="Send monet"')
        self.assertLess(result.stderr.index('可见文字 "Send monez"'), result.stderr.index('可见文字 "Alpha unrelated"'))
        self.page.write_text('<!doctype html><link rel="icon" href="data:,"><body></body>', encoding='utf-8')
        result = self.run_failure(self.folder / 'generic', '--steps', 'hover .missing')
        self.assertIn('例如 hover .open', result.stderr)

    def test_failed_recordings_clean_temporary_frames(self):
        failed = self.folder / 'failed-record'
        self.run_failure(failed, '--record', '--steps', 'broken: click .missing', '--hold', '0')
        self.assertEqual(list(failed.glob('frames*')), [])
        failed = self.folder / 'failed-evidence'
        self.run_failure(failed, '--evidence', '--steps', 'broken: click .missing', '--steps', 'good: click #go', '--hold', '100')
        self.assertEqual(list(failed.glob('frames*')), [])
        self.assert_artifacts(failed, ('motion-good-end.jpg', 'motion-entry-end.jpg', 'report.json'))
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def fault_env(self, drops='', stale=None):
        # Keep a real Chrome/CDP transport. Only selected responses are suppressed; accelerate
        # those watchdogs after recording the production timeout value, leaving all other timers intact.
        preload = self.folder / 'fault.mjs'
        journal = self.folder / 'fault.jsonl'
        preload.write_text('''import {appendFileSync,readFileSync,existsSync} from 'node:fs';
const originalTimer=globalThis.setTimeout;let watchdog;
globalThis.setTimeout=(callback,delay,...args)=>{const timer=originalTimer(callback,delay,...args);if(delay>=90000)watchdog={callback,delay,timer};return timer};
const previous=existsSync(process.env.SHOOT_TEST_JOURNAL)?readFileSync(process.env.SHOOT_TEST_JOURNAL,'utf8').trim().split('\\n').filter(Boolean).map(JSON.parse):[];
const Native=globalThis.WebSocket;let captures=previous.filter(row=>'capture' in row).length,connections=0;
const drops=new Set((process.env.SHOOT_TEST_DROPS||'').split(',').map(Number));
const write=row=>appendFileSync(process.env.SHOOT_TEST_JOURNAL,JSON.stringify(row)+'\\n');
globalThis.WebSocket=class extends Native {
 constructor(...args){super(...args);write({connection:++connections});
   const substituted=new WeakSet();
   this.addEventListener('message',event=>{
    if(substituted.has(event)||!process.env.SHOOT_TEST_STALE)return;
    const msg=JSON.parse(event.data);
    if(msg.method!=='Page.screencastFrame')return;
    event.stopImmediatePropagation();msg.params.data=readFileSync(process.env.SHOOT_TEST_STALE).toString('base64');
    const replacement=new MessageEvent('message',{data:JSON.stringify(msg)});substituted.add(replacement);this.dispatchEvent(replacement);
   });
 }
 send(data){const msg=JSON.parse(data);if(msg.method==='Page.captureScreenshot'){
   write({capture:++captures,timeout:watchdog.delay});
   if(drops.has(captures)){clearTimeout(watchdog.timer);originalTimer(watchdog.callback,100);return;}
 }return super.send(data)}
};''', encoding='utf-8')
        return dict(self.env, NODE_OPTIONS='--import=' + preload.as_uri(), SHOOT_TEST_DROPS=drops,
                    SHOOT_TEST_JOURNAL=str(journal), **({'SHOOT_TEST_STALE': str(stale)} if stale else {})), journal

    def transport_fault_env(self, mode, always=False):
        preload = self.folder / 'transport-fault.mjs'
        journal = self.folder / 'transport-fault.jsonl'
        preload.write_text('''import {appendFileSync,readFileSync,existsSync} from 'node:fs';
const path=process.env.SHOOT_TEST_TRANSPORT_JOURNAL,mode=process.env.SHOOT_TEST_TRANSPORT;
const rows=()=>existsSync(path)?readFileSync(path,'utf8').trim().split('\\n').filter(Boolean).map(JSON.parse):[];
const write=row=>appendFileSync(path,JSON.stringify(row)+'\\n');
const fault=()=>process.env.SHOOT_TEST_ALWAYS==='1'||!rows().some(row=>row.fault);
const original=globalThis.setTimeout;let watchdog;
globalThis.setTimeout=(callback,delay,...args)=>{
 const stage=delay===45000||delay===90000?'launch':null;
 if(mode==='launch'&&stage){write({stage,timeout:delay});if(fault()){write({fault:mode});return original(callback,1000,...args)}}
 const timer=original(callback,delay,...args);
 if(delay===30000||delay===60000||delay===120000)watchdog={callback,delay,timer};
 if(mode==='connect'&&String(callback).includes('连接浏览器')&&delay>=30000){
  write({stage:'connect',timeout:delay});
  if(fault()){write({fault:mode});clearTimeout(timer);return original(callback,100,...args)}
 }
 return timer;
};
const Native=globalThis.WebSocket;
globalThis.WebSocket=class extends Native {
 // The watchdog records the fault before onopen is assigned; decide once per socket.
 constructor(...args){super(...args);this.dropOpen=mode==='connect'&&fault()}
 set onopen(callback){super.onopen=this.dropOpen?null:callback}
 send(data){const msg=JSON.parse(data);
  const selected=mode==='setup'?msg.method==='Target.createTarget':mode==='cdp'&&msg.method==='Runtime.evaluate'&&msg.params.expression.includes('"value":"#hang"');
  if(selected){write({stage:mode,timeout:watchdog.delay});if(fault()){write({fault:mode});clearTimeout(watchdog.timer);original(watchdog.callback,100);return}}
  return super.send(data);
 }
};''', encoding='utf-8')
        return dict(self.env, NODE_OPTIONS='--import=' + preload.as_uri(), SHOOT_TEST_TRANSPORT=mode,
                    SHOOT_TEST_ALWAYS='1' if always else '0', SHOOT_TEST_TRANSPORT_JOURNAL=str(journal)), journal

    def test_connection_and_setup_timeouts_retry_the_whole_invocation(self):
        for mode in ['connect', 'setup', 'cdp']:
            with self.subTest(mode=mode):
                env, journal = self.transport_fault_env(mode)
                journal.unlink(missing_ok=True)
                self.page.write_text('''<!doctype html><link rel="icon" href="data:,">
<button id="hang">Ready</button><script>const query=new URLSearchParams(location.search);if(query.get('state')!=='done'||query.get('extra')!=='1')console.error(location.search);</script>''', encoding='utf-8')
                output = self.folder / mode
                result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--size', '800x600',
                                         '--states', 'done', '--query', 'extra=1', '--zoom', '2', '--timeout-scale', '2',
                                         '--steps', 'hover: hover #hang; wait450'], cwd=ROOT, env=env,
                                        capture_output=True, text=True, timeout=30, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr.count('正在重试一次'), 1)
                self.assertIn('--timeout-scale 4', result.stderr)
                events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
                self.assertEqual([row['timeout'] for row in events if row.get('stage') == mode], [60000, 120000])
                report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual([row['file'] for row in report], ['done-hover-@2x.png'])
                self.assertEqual(report[0]['size'], '800x600')
                self.assertEqual(report[0]['issues'], [])
                self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def test_persistent_startup_connection_and_setup_timeouts_stop_after_one_retry(self):
        for mode in (['launch'] if sys.platform != 'win32' else []) + ['connect', 'setup']:
            with self.subTest(mode=mode):
                env, journal = self.transport_fault_env(mode, always=True)
                journal.unlink(missing_ok=True)
                if mode == 'launch':
                    wrapper = self.folder / 'never-ready'
                    wrapper.write_text('#!/bin/sh\nexec sleep 60\n', encoding='utf-8')
                    wrapper.chmod(0o755)
                    env['CHROME_PATH'] = str(wrapper)
                result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(self.folder / mode)],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20, encoding='utf-8')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stderr.count('正在重试一次'), 1)
                events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
                self.assertEqual([row['timeout'] for row in events if row.get('stage') == mode],
                                 [45000, 90000] if mode == 'launch' else [30000, 60000])
                self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def test_screenshot_timeout_reopens_and_retries_once(self):
        env, journal = self.fault_env('1')
        output = self.folder / 'screenshot-retry'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--timeout-scale', '2'],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum('connection' in row for row in events), 2)
        self.assertEqual([row['timeout'] for row in events if 'capture' in row], [180000, 360000])
        self.assertIn('正在重试一次', result.stderr)
        self.assertIn('--timeout-scale 4', result.stderr)
        self.assertEqual(len(json.loads((output / 'report.json').read_text(encoding='utf-8'))), 1)
        self.assert_artifacts(output, ('page.png', 'report.json'))
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def test_masked_screenshot_timeout_replays_state_and_finishes_batch(self):
        env, journal = self.fault_env('2')
        output = self.folder / 'masked-retry'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--states', 'a,b', '--mask'],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[4/4]', result.stderr)
        self.assertIn('--mask', result.stderr)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual([entry['file'] for entry in report], ['a.png', 'b.png'])
        self.assertEqual([entry['issues'] for entry in report], [[], []])
        self.assert_artifacts(output, ('a.png', 'a-masked.png', 'b.png', 'b-masked.png'))
        self.assertNotEqual((output / 'a.png').read_bytes(), (output / 'a-masked.png').read_bytes())
        self.assertNotEqual((output / 'a-masked.png').read_bytes(), (output / 'b-masked.png').read_bytes())
        events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum('connection' in row for row in events), 2)
        # A full rerun captures the first plain image again, rather than only retrying the mask.
        self.assertEqual([row['timeout'] for row in events if 'capture' in row], [90000, 90000, 180000, 180000, 180000, 180000])
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed for evidence')
    def test_second_screenshot_timeout_marks_item_failed_and_continues_evidence(self):
        env, journal = self.fault_env('1,2')
        output = self.folder / 'screenshot-failed-evidence'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--evidence',
                                 '--hold', '100', '--steps', 'toggle: click #go'],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertTrue(report[0]['failed'])
        self.assertIn('Page.captureScreenshot 180 秒', report[0]['issues'][-1])
        self.assertFalse(any(row['file'] == 'browser' for row in report))
        self.assertTrue(any(row['file'] == 'motion-probe-toggle' for row in report))
        self.assert_artifacts(output, ('page-@2x.png', 'record-entry.mp4', 'record-toggle.mp4', 'report.json'))
        self.assertIn('[5/5]', result.stderr)
        self.assertNotRegex(result.stdout, r'\[\d+/\d+\]')
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def test_screenshot_retry_cannot_reopen_browser_aborts(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX browser wrapper')
        import shlex
        env, _ = self.fault_env('1')
        wrapper = self.folder / 'cannot-reopen'
        marker = self.folder / 'launched'
        wrapper.write_text('#!/bin/sh\nif [ -f ' + shlex.quote(str(marker)) + ' ]; then exit 1; fi\n'
                           'touch ' + shlex.quote(str(marker)) + '\nexec ' + shlex.quote(self.browser) + ' "$@"\n', encoding='utf-8')
        wrapper.chmod(0o755)
        output = self.folder / 'restart-failed'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--evidence'],
                                cwd=ROOT, env=dict(env, CHROME_PATH=str(wrapper)), capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('浏览器启动失败', result.stderr)
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report[-1]['file'], 'browser')
        self.assertEqual(list(output.glob('record*.mp4')), [])
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is needed to inspect recording')
    def test_stale_screencast_warns_preserves_stream_and_appends_screenshot(self):
        self.page.write_text('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><style>body{margin:0;background:#182838}'
                             '#box{position:absolute;left:60px;top:40px;width:240px;height:160px;border:4px solid #ffff00}</style><div id="box"></div>', encoding='utf-8')
        stale = self.folder / 'stale.jpg'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=0x182838:s=390x844,drawbox=x=60:y=40:w=248:h=168:color=yellow:t=4,'
                        'drawbox=x=304:y=44:w=4:h=160:color=0x182838:t=fill',
                        '-frames:v', '1', str(stale)], check=True, capture_output=True, timeout=10)
        env, _ = self.fault_env(stale=stale)
        output = self.folder / 'stale-stream'
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--record', '--hold', '100'],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        entry = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(entry['consistency']['status'], 'mismatch')
        self.assertIn('可能没拍全', entry['warnings'][0])
        self.assertIn('静止终态以 motion-end.jpg 为准', result.stdout)
        self.assertEqual((output / 'record-stream-end.jpg').read_bytes(), stale.read_bytes())
        self.assertLess(entry['consistency']['pixelRatio'], .005, 'A thin missing border must survive whole-viewport dilution')
        self.assertGreater(self.frame_pixel(output / 'motion-end.jpg', 306, 80)[1], 220)
        last = subprocess.run(['ffmpeg', '-v', 'error', '-sseof', '-0.04', '-i', str(output / 'record.mp4'),
                               '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-vf', 'format=rgb24,crop=1:1:306:80', '-'],
                              capture_output=True, timeout=10)
        self.assertEqual(last.returncode, 0, last.stderr)
        self.assertGreater(last.stdout[1], 220)
        self.assertEqual(list(output.glob('frames*')), [])

    def test_cdp_request_times_out_in_current_step(self):
        import time
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><button id="prepare">Prepare</button><button id="hang">Hang</button>
<script>document.querySelector('#prepare').onclick=()=>{document.querySelector('#hang').getBoundingClientRect=()=>{while(true){}}};</script>''', encoding='utf-8')
        output = self.folder / 'cdp-timeout'
        start = time.monotonic()
        env, journal = self.transport_fault_env('cdp', always=True)
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--size', 'desktop',
                                 '--steps', 'click #prepare; click #hang'], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=20, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        elapsed = time.monotonic() - start
        self.assertIn('第 2 步「click #hang」', result.stderr)
        self.assertIn('CDP Runtime.evaluate 30 秒内没有响应', result.stderr)
        self.assertIn('CDP Runtime.evaluate 60 秒内没有响应', result.stderr)
        self.assertEqual(result.stderr.count('正在重试一次'), 1)
        events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([row['timeout'] for row in events if row.get('stage') == 'cdp'], [30000, 60000])
        self.assertLess(elapsed, 20)
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])
        self.assertTrue(any(r.get('failed') for r in json.loads((output / 'report.json').read_text(encoding='utf-8'))))

    def test_browser_disconnect_interrupts_steps_and_cleans_frames(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX browser kill wrapper')
        import http.server
        import shlex
        import signal
        import threading
        import time
        pid_file = self.folder / 'chrome.pid'
        wrapper = self.folder / 'chrome-kill-wrapper'
        wrapper.write_text('#!/bin/sh\necho $$ > ' + shlex.quote(str(pid_file)) + '\nexec ' + shlex.quote(self.browser) + ' "$@"\n', encoding='utf-8')
        wrapper.chmod(0o755)

        class KillHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                handler.send_response(200)
                handler.end_headers()
                handler.wfile.write(b'ok')
                os.kill(int(pid_file.read_text(encoding='utf-8').strip()), signal.SIGKILL)

            def log_message(*args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), KillHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.page.write_text(f'''<!doctype html><link rel="icon" href="data:,"><button id="kill">Kill</button>
<script>document.querySelector('#kill').onclick=()=>setTimeout(()=>fetch('http://127.0.0.1:{server.server_port}/kill'),250);</script>''', encoding='utf-8')
        output = self.folder / 'disconnect'
        start = time.monotonic()
        result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--record', '--hold', '100',
                                 '--steps', 'disconnect: click #kill; wait 60000'], cwd=ROOT,
                                env=dict(self.env, CHROME_PATH=str(wrapper)), capture_output=True, text=True, timeout=15, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('第 2 步「wait 60000」', result.stderr)
        self.assertIn('浏览器连接意外断开', result.stderr)
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(list(output.glob('frames*')), [])
        self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])

    def test_deduplicated_states_sizes_zooms_and_filename_collisions(self):
        output = self.folder / 'deduplicated'
        result = self.shoot(output, '--states', 'a,a,b,a', '--size', 'desktop,1440x900,phone,mobile', '--zoom', '1,1.0')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report), 4)
        for message in ['状态 已去重', '尺寸 已去重', '倍数 已去重']:
            self.assertIn(message, result.stdout)
        output = self.folder / 'group-collision'
        result = self.shoot(output, '--states', 'a,a-b', '--steps', 'b-c: wait 0', '--steps', 'c: wait 0')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(set(r['file'] for r in report)), 4)
        self.assert_artifacts(output, ('a-b-c.png', 'a-b-c-2.png'))
        self.assertIn('文件名冲突，已区分', result.stdout)
        output = self.folder / 'variant-collision'
        self.shoot(output, '--states', 'a,a-masked,sheet', '--mask', '--sheet')
        self.assert_artifacts(output, ('a.png', 'a-masked.png', 'a-masked-2.png', 'a-masked-2-masked.png',
                                       'sheet.png', 'sheet-masked.png', 'sheet-2.png', 'sheet-2-masked.png'))
        self.assertEqual(len(list(output.glob('*.png'))), 8)

    def test_screenshots_wait_for_finite_animations_and_transitions(self):
        self.page.write_text('''<!doctype html><link rel="icon" href="data:,"><style>
@keyframes enter{from{opacity:0;transform:translateY(40px)}to{opacity:1;transform:none}}
#box{animation:enter .7s both;transition:margin-left .6s;margin-left:0}
</style><button id="go">Go</button><div id="box">Ready</div><script>
document.querySelector('#go').onclick=()=>document.querySelector('#box').style.marginLeft='100px';
const capture=()=>{
const s=getComputedStyle(document.querySelector('#box'));
if(s.opacity!=='1'||parseFloat(s.marginLeft)<99)console.error('captured-during-motion');
};
// Screenshot checks read document.images; inspect its computed styles at that moment.
Object.defineProperty(document,'images',{get(){capture();return []}});
</script>''', encoding='utf-8')
        output = self.folder / 'settled'
        self.shoot(output, '--wait', '0', '--steps', 'click #go')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(report['issues'], [])
        self.assertGreater(report['animationWaitMs'], 600)
        self.assertLessEqual(report['animationWaitMs'], 2000)

    def test_screenshot_animation_wait_is_capped_and_skips_infinite(self):
        for duration, expected_wait in [('60s', True), ('60s infinite', False)]:
            with self.subTest(duration=duration):
                self.page.write_text(f'''<!doctype html><link rel="icon" href="data:,"><style>
@keyframes slow{{from{{transform:translateX(0)}}to{{transform:translateX(100px)}}}}
div{{animation:slow {duration}}}</style><div>Ready</div>''', encoding='utf-8')
                output = self.folder / ('finite-cap' if expected_wait else 'infinite')
                self.shoot(output, '--wait', '0')
                waited = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]['animationWaitMs']
                if expected_wait:
                    self.assertGreaterEqual(waited, 1950)
                    self.assertLessEqual(waited, 2000)
                else:
                    self.assertEqual(waited, 0)
        # Recording and motion probing continue to observe the animation from the original timing.
        output = self.folder / 'record-unsettled'
        self.shoot(output, '--wait', '0', '--record', '--entry', '--hold', '100')
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))[0]
        self.assertNotIn('animationWaitMs', report)
        self.shoot(self.folder / 'motion-unsettled', '--wait', '0', '--motion')
        report = json.loads((self.folder / 'motion-unsettled/report.json').read_text(encoding='utf-8'))[0]
        self.assertNotIn('animationWaitMs', report)


    def test_disconnect_during_encoding_exits_without_waiting_for_encoder(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX browser and encoder wrappers')
        import shlex
        import signal
        import threading
        import time
        browser_pid = self.folder / 'browser.pid'
        wrapper = self.folder / 'chrome-encoder-wrapper'
        wrapper.write_text('#!/bin/sh\necho $$ > ' + shlex.quote(str(browser_pid)) + '\nexec ' + shlex.quote(self.browser) + ' "$@"\n', encoding='utf-8')
        wrapper.chmod(0o755)
        encoder_ready = self.folder / 'encoder-ready'
        fake_bin = self.folder / 'bin'
        fake_bin.mkdir()
        encoder = fake_bin / 'ffmpeg'
        encoder.write_text('#!/bin/sh\nif [ "$1" = "-version" ]; then exit 0; fi\n'
                           'touch ' + shlex.quote(str(encoder_ready)) + '\nexec sleep 60\n', encoding='utf-8')
        encoder.chmod(0o755)
        stop = threading.Event()

        def disconnect():
            while not stop.wait(.02):
                if encoder_ready.exists():
                    os.kill(int(browser_pid.read_text(encoding='utf-8')), signal.SIGKILL)
                    return

        thread = threading.Thread(target=disconnect, daemon=True)
        thread.start()
        try:
            output = self.folder / 'encoder-disconnect'
            start = time.monotonic()
            result = subprocess.run([NODE, str(SCRIPT), str(self.page), '--out', str(output), '--record', '--hold', '100'],
                                    cwd=ROOT, env=dict(self.env, CHROME_PATH=str(wrapper), PATH=str(fake_bin) + os.pathsep + os.environ['PATH']),
                                    capture_output=True, text=True, timeout=15, encoding='utf-8')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(encoder_ready.exists())
            self.assertIn('浏览器连接意外断开', result.stderr)
            self.assertLess(time.monotonic() - start, 10)
            self.assertEqual(list(output.glob('frames*')), [])
            self.assertEqual(list(self.profile_root.glob('oil-shoot-*')), [])
        finally:
            stop.set()
            thread.join(1)



if __name__ == "__main__":
    unittest.main()
