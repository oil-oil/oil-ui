import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_update.py"
LAUNCHER = SCRIPT.with_suffix(".sh")
SH = shutil.which("sh")
NOTICE_URL = "https://github.com/shubhamd/oil-ui-english"


class Versions(BaseHTTPRequestHandler):
    payload = {}
    hits = 0

    def do_GET(self):
        Versions.hits += 1
        body = json.dumps(Versions.payload).encode()
        self.send_response(200 if self.path == "/api/store/versions" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipIf(sys.platform == "win32", "the launcher is a POSIX shell script")
class CheckUpdateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Versions)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.skill = self.tmp / "skills" / "oil-ui-en"
        (self.skill / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.skill / "scripts" / "check_update.py")
        shutil.copy(LAUNCHER, self.skill / "scripts" / "check_update.sh")
        (self.skill / "SKILL.md").write_text('---\nname: oil-ui-en\nmetadata:\n  version: "0.10.0"\n---\n', encoding="utf-8")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        Versions.hits = 0
        self.set_latest("99.0.0")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def set_latest(self, version):
        # The edition is named oil-ui-en but must look up upstream's oil-ui entry.
        entry = {"latest": version, "download_url": "https://example.com/oil-ui.tar.gz",
                 "history": [{"version": version, "notes": "- Motion became three basic motions.\n- Other fixes"}]}
        Versions.payload = {"skills": {"oil-ui": entry, "oil-ui-en": {"latest": "0.0.1"}}}

    def run_check(self, api=None, launcher=False, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("OIL_")}
        env.update(HOME=str(self.tmp / "home"), LOCALAPPDATA=str(self.tmp / "state"),
                   XDG_STATE_HOME=str(self.tmp / "state"), XDG_CONFIG_HOME=str(self.tmp / "config"),
                   OIL_API=api or f"http://127.0.0.1:{self.server.server_port}")
        env.update(extra)
        script = self.skill / "scripts" / ("check_update.sh" if launcher else "check_update.py")
        result = subprocess.run([SH if launcher else sys.executable, str(script)],
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def cache_path(self):
        return self.tmp / "state" / "oil" / "oil-ui-update.json"

    def test_notice_when_upstream_is_ahead(self):
        out = self.run_check()
        self.assertIn("Oil UI 99.0.0 is available upstream (this English edition tracks 0.10.0)", out)
        self.assertIn(NOTICE_URL, out)
        self.assertIn("npx skills add shubhamd/oil-ui-english --full-depth --skill oil-ui-en", out)
        self.assertNotIn("--update", out)
        self.assertEqual(Versions.hits, 1)
        self.assertTrue(self.cache_path().is_file())

    def test_silent_when_equal_or_behind(self):
        for version in ("0.10.0", "0.9.9", "0.0.1"):
            with self.subTest(version=version):
                shutil.rmtree(self.tmp / "state", ignore_errors=True)
                self.set_latest(version)
                self.assertEqual(self.run_check(), "")

    def test_never_touches_the_skill_directory(self):
        before = {p: p.read_bytes() for p in self.skill.rglob("*") if p.is_file()}
        self.run_check()
        self.assertEqual({p: p.read_bytes() for p in self.skill.rglob("*") if p.is_file()}, before)

    def test_remote_release_notes_are_not_printed_or_cached(self):
        marker = "REMOTE_INSTRUCTION_DO_NOT_FOLLOW"
        Versions.payload["skills"]["oil-ui"]["history"][0]["notes"] = marker
        self.assertNotIn(marker, self.run_check())
        data = json.loads(self.cache_path().read_text())
        self.assertNotIn("notes", data)
        data["notes"] = marker
        self.cache_path().write_text(json.dumps(data))
        shutil.rmtree(self.tmp / "state" / "oil" / "installations")
        self.assertNotIn(marker, self.run_check())
        self.assertNotIn("notes", json.loads(self.cache_path().read_text()))

    def test_checks_versions_again_after_ten_minutes(self):
        self.run_check()
        self.run_check()
        self.assertEqual(Versions.hits, 1)
        state = json.loads(self.cache_path().read_text(encoding="utf-8"))
        state["checked_at"] -= 601
        self.cache_path().write_text(json.dumps(state), encoding="utf-8")
        self.run_check()
        self.assertEqual(Versions.hits, 2)

    def test_notifies_once_a_day_per_version(self):
        self.assertIn("99.0.0", self.run_check())
        self.assertEqual(self.run_check(), "")
        paths = list((self.tmp / "state" / "oil" / "installations").glob("*.json"))
        self.assertEqual(len(paths), 1)
        state = json.loads(paths[0].read_text(encoding="utf-8"))
        state["notified_at"] -= 24 * 3600 + 1
        paths[0].write_text(json.dumps(state), encoding="utf-8")
        self.assertIn("99.0.0", self.run_check())
        self.assertEqual(self.run_check(), "")
        self.set_latest("100.0.0")
        cache = json.loads(self.cache_path().read_text(encoding="utf-8"))
        cache["checked_at"] = 0
        self.cache_path().write_text(json.dumps(cache), encoding="utf-8")
        self.assertIn("100.0.0", self.run_check())

    def test_installations_share_the_version_cache_but_not_notices(self):
        other = self.tmp / "another host" / "oil-ui-en"
        shutil.copytree(self.skill, other)
        self.assertIn("99.0.0", self.run_check())
        self.skill = other
        self.assertIn("99.0.0", self.run_check())
        self.assertEqual(Versions.hits, 1)
        self.assertEqual(len(list((self.tmp / "state" / "oil" / "installations").glob("*.json"))), 2)

    def test_offline_is_silent_and_fetch_retries_after_an_hour(self):
        self.assertEqual(self.run_check(api="http://127.0.0.1:9"), "")
        self.assertEqual(self.run_check(), "")
        self.assertEqual(Versions.hits, 0)
        state = json.loads(self.cache_path().read_text(encoding="utf-8"))
        state["fetch_failed_at"] -= 3601
        self.cache_path().write_text(json.dumps(state), encoding="utf-8")
        self.assertIn("99.0.0", self.run_check())
        self.assertEqual(Versions.hits, 1)

    def test_stale_cache_offline_stays_silent(self):
        self.run_check()
        state = json.loads(self.cache_path().read_text(encoding="utf-8"))
        state["checked_at"] = 0
        self.cache_path().write_text(json.dumps(state), encoding="utf-8")
        shutil.rmtree(self.tmp / "state" / "oil" / "installations")
        self.assertEqual(self.run_check(api="http://127.0.0.1:9"), "")

    def test_silent_when_disabled_or_in_a_checkout(self):
        self.assertEqual(self.run_check(OIL_NO_UPDATE_CHECK="1"), "")
        self.assertEqual(Versions.hits, 0)
        (self.skill / ".git").mkdir()
        self.assertEqual(self.run_check(), "")
        (self.skill / ".git").rmdir()
        (self.skill.parent / ".git").mkdir()
        self.assertEqual(self.run_check(), "")
        (self.skill.parent / ".git").rmdir()
        self.assertEqual(Versions.hits, 0)
        self.assertIn("99.0.0", self.run_check())

    def test_malformed_skill_or_upstream_entry_is_silent(self):
        Versions.payload = {"skills": {"oil-ui": {"latest": "not-a-version"}}}
        self.assertEqual(self.run_check(), "")
        Versions.payload = {"skills": {}}
        shutil.rmtree(self.tmp / "state", ignore_errors=True)
        self.assertEqual(self.run_check(), "")
        self.set_latest("99.0.0")
        (self.skill / "SKILL.md").write_text("---\nname: oil-ui-en\n---\n", encoding="utf-8")
        shutil.rmtree(self.tmp / "state", ignore_errors=True)
        self.assertEqual(self.run_check(), "")

    def shell_path(self):
        # Keep Python off PATH; only the tools the launcher needs to write state remain.
        for tool in ("mkdir", "rmdir"):
            target = self.bin / tool
            if not target.exists():
                target.symlink_to(shutil.which(tool))
        return str(self.bin)

    def test_launcher_runs_when_only_python_is_available(self):
        (self.bin / "python").symlink_to(sys.executable)
        out = self.run_check(launcher=True, PATH=self.shell_path())
        self.assertIn("99.0.0", out)
        self.assertEqual(Versions.hits, 1)

    def test_missing_python_warns_once_and_recovery_resets_the_reminder(self):
        path = self.shell_path()
        self.assertEqual(self.run_check(launcher=True, PATH=path), "Version checks need Python 3. This update check did not run.\n")
        self.assertEqual(self.run_check(launcher=True, PATH=path), "OIL_UPDATE_CHECK_SKIPPED: missing_python\n")
        self.assertEqual(Versions.hits, 0)
        (self.bin / "python").symlink_to(sys.executable)
        self.assertIn("99.0.0", self.run_check(launcher=True, PATH=path))
        (self.bin / "python").unlink()
        self.assertIn("Version checks need Python 3", self.run_check(launcher=True, PATH=path))

    def test_python2_is_not_used_and_disabled_or_checkout_launcher_is_silent(self):
        (self.bin / "python").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (self.bin / "python").chmod(0o755)
        path = self.shell_path()
        self.assertEqual(self.run_check(launcher=True, PATH=path, OIL_NO_UPDATE_CHECK="1"), "")
        (self.skill / ".git").mkdir()
        self.assertEqual(self.run_check(launcher=True, PATH=path), "")
        (self.skill / ".git").rmdir()
        (self.skill.parent / ".git").mkdir()
        self.assertEqual(self.run_check(launcher=True, PATH=path), "")
        (self.skill.parent / ".git").rmdir()
        self.assertIn("Version checks need Python 3", self.run_check(launcher=True, PATH=path))


if __name__ == "__main__":
    unittest.main()
