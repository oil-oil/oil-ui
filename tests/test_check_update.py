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

# 配置来自测试文件，不能依赖被安全环境白名单过滤的假环境变量。
FAKE_NPX = f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
c = json.loads(Path(__file__).with_name('settings.json').read_text())
with Path(c['log']).open('a') as log: log.write(' '.join(sys.argv[1:])+'\\n')
Path(c['env_log']).write_text(json.dumps({{k: k in os.environ for k in
    ['AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY','NODE_OPTIONS','NPM_TOKEN','OIL_TOKEN','CI']}}))
if c.get('stderr'): print(c['stderr'], file=sys.stderr)
if c.get('json'): print(c['json'])
if c.get('fail'): sys.exit(1)
if '--path' in sys.argv:
    skill = Path(sys.argv[sys.argv.index('--path')+1])/'SKILL.md'
    skill.write_text(skill.read_text().replace('version: "0.10.0"','version: "99.0.0"'))
"""
FAKE_NODE = f"""#!{sys.executable}
import json
from pathlib import Path
print(json.loads(Path(__file__).with_name('settings.json').read_text()).get('node_version') or 'v20.0.0')
"""


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


@unittest.skipIf(sys.platform == "win32", "假 npx 是 shell 脚本")
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
        self.skill = self.tmp / "skills" / "oil-ui-pro"
        (self.skill / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.skill / "scripts" / "check_update.py")
        shutil.copy(LAUNCHER, self.skill / "scripts" / "check_update.sh")
        (self.skill / "SKILL.md").write_text('---\nname: oil-ui-pro\nmetadata:\n  version: "0.10.0"\n---\n', encoding="utf-8")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "npx").write_text(FAKE_NPX, encoding="utf-8")
        (bin_dir / "npx").chmod(0o755)
        (bin_dir / "node").write_text(FAKE_NODE, encoding="utf-8")
        (bin_dir / "node").chmod(0o755)
        self.bin = bin_dir
        self.npx_log = self.tmp / "npx.log"
        Versions.hits = 0
        self.set_latest("99.0.0", free=False)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def set_latest(self, version, free):
        entry = {"latest": version, "history": [{"version": version, "notes": "- 动效改成三处基本动效。\n- 其他修正"}]}
        if free:
            entry["download_url"] = "https://example.com/oil-ui-pro.tar.gz"
        Versions.payload = {"skills": {"oil-ui-pro": entry}}

    def login(self):
        config = self.tmp / "config" / "oil"
        config.mkdir(parents=True, exist_ok=True)
        (config / "config.json").write_text(json.dumps({"token": "oil_test", "email": "a@example.com"}), encoding="utf-8")

    def run_check(self, api=None, launcher=False, update=True, **extra):
        (self.bin / 'settings.json').write_text(json.dumps({
            'log': str(self.npx_log), 'env_log': str(self.tmp / 'env.json'),
            'stderr': extra.get('FAKE_NPX_STDERR'), 'json': extra.get('FAKE_NPX_JSON'),
            'fail': extra.get('FAKE_NPX_FAIL'), 'node_version': extra.get('FAKE_NODE_VERSION'),
        }), encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith("OIL_")}
        env.update(HOME=str(self.tmp / "home"), APPDATA=str(self.tmp / "config"), LOCALAPPDATA=str(self.tmp / "state"),
                   XDG_STATE_HOME=str(self.tmp / "state"), XDG_CONFIG_HOME=str(self.tmp / "config"),
                   PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", FAKE_NPX_LOG=str(self.npx_log),
                   LANG="zh_CN.UTF-8", LC_ALL="", LC_MESSAGES="",
                   OIL_API=api or f"http://127.0.0.1:{self.server.server_port}")
        env.update(extra)
        self.last_env = env
        script = self.skill / "scripts" / ("check_update.sh" if launcher else "check_update.py")
        result = subprocess.run([SH if launcher else sys.executable, str(script), *(['--update'] if update else [])],
                                capture_output=True, text=True, env=env, timeout=30, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def install_state(self):
        paths = list((self.tmp / "state" / "oil" / "installations").glob("*.json"))
        self.assertEqual(len(paths), 1)
        return paths[0], json.loads(paths[0].read_text(encoding="utf-8"))

    def assert_no_attempt(self):
        self.assertEqual(self.npx_calls(), [])
        _, state = self.install_state()
        self.assertNotIn("auto_failed_at", state)

    def npx_calls(self):
        return self.npx_log.read_text(encoding="utf-8").splitlines() if self.npx_log.exists() else []

    def test_logged_in_paid_skill_updates_itself(self):
        self.login()
        out = self.run_check()
        self.assertIn("Oil UI Pro 已自动更新到 99.0.0（原来是 0.10.0）。", out)
        self.assertIn(f"update oil-ui-pro --path {self.skill}", self.npx_calls()[0])
        self.assertIn('version: "99.0.0"', (self.skill / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_check(), "")

    def test_free_skill_updates_without_login(self):
        self.set_latest("99.0.0", free=True)
        self.assertIn("已自动更新到 99.0.0", self.run_check())

    def test_default_check_never_executes_the_updater_or_changes_the_skill(self):
        self.set_latest("99.0.0", free=True)
        before = (self.skill / 'SKILL.md').read_bytes()
        out = self.run_check(update=False)
        self.assertIn('有新版本 99.0.0', out)
        self.assertIn('--update', out)
        self.assertEqual(self.npx_calls(), [])
        self.assertEqual((self.skill / 'SKILL.md').read_bytes(), before)
        self.assertEqual(self.run_check(update=False), '')

    def test_explicit_update_pins_cli_and_filters_unrelated_secrets(self):
        self.set_latest('99.0.0', free=True)
        self.assertIn('已自动更新', self.run_check(
            AWS_SECRET_ACCESS_KEY='dummy-only-aws', OPENAI_API_KEY='dummy-only-openai',
            NODE_OPTIONS='--require /nonexistent-oil-test.js', NPM_TOKEN='dummy-only-npm',
            OIL_TOKEN='dummy-only-oil'))
        self.assertRegex(self.npx_calls()[0], r'-y github:oil-oil/oil-cli#[0-9a-f]{40} update')
        seen = json.loads((self.tmp / 'env.json').read_text(encoding="utf-8"))
        for key in ('AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY','NODE_OPTIONS','NPM_TOKEN'):
            self.assertFalse(seen[key], key)
        self.assertTrue(seen['OIL_TOKEN'])
        self.assertTrue(seen['CI'])

    def test_remote_release_notes_are_not_printed_or_cached(self):
        marker = 'REMOTE_INSTRUCTION_DO_NOT_FOLLOW'
        Versions.payload['skills']['oil-ui-pro']['history'][0]['notes'] = marker
        self.assertNotIn(marker, self.run_check(update=False))
        cache = self.tmp / 'state/oil/oil-ui-pro-update.json'
        data = json.loads(cache.read_text(encoding="utf-8"))
        self.assertNotIn('notes', data)
        data['notes'] = marker
        cache.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn(marker, self.run_check(update=False))
        self.assertNotIn('notes', json.loads(cache.read_text(encoding="utf-8")))

    def test_paid_skill_without_login_only_notifies_once_a_day(self):
        out = self.run_check()
        self.assertIn("Oil UI Pro 有新版本 99.0.0（当前 0.10.0）。", out)
        self.assertIn("--update", out)
        self.assertEqual(self.npx_calls(), [])
        self.assertEqual(self.run_check(), "")
        self.assertEqual(Versions.hits, 1)
        self.assert_no_attempt()

    def test_failed_update_falls_back_to_notice(self):
        self.login()
        out = self.run_check(FAKE_NPX_FAIL="1")
        self.assertIn("有新版本 99.0.0", out)
        self.assertEqual(len(self.npx_calls()), 1)
        self.assertEqual(self.run_check(FAKE_NPX_FAIL="1"), "")
        self.assertEqual(len(self.npx_calls()), 1)

    def test_auto_update_can_be_turned_off(self):
        self.login()
        self.assertIn("有新版本 99.0.0", self.run_check(OIL_NO_AUTO_UPDATE="1"))
        self.assertEqual(self.npx_calls(), [])
        self.assert_no_attempt()

    def test_cli_errors_have_specific_recovery_commands_in_both_languages(self):
        self.login()
        for language in ("zh_CN.UTF-8", "en_US.UTF-8"):
            for error in ("unauthorized", "inactive"):
                with self.subTest(language=language, error=error):
                    shutil.rmtree(self.tmp / "state", ignore_errors=True)
                    out = self.run_check(LANG=language, FAKE_NPX_FAIL="1", FAKE_NPX_JSON=json.dumps({
                        "ok": False, "command": "update", "error": error, "message": "DO NOT ECHO THIS",
                        "new_field": "forward-compatible"}))
                    self.assertIn(str(self.skill / 'scripts/check_update.py'), out)
                    self.assertIn('--update', out)
                    self.assertNotIn("DO NOT ECHO THIS", out)
                    if error == "unauthorized":
                        self.assertRegex(out, r"npx github:oil-oil/oil-cli#[0-9a-f]{40} login")
                        self.assertIn("Authorization has expired" if language.startswith("en") else "授权已失效", out)
                    else:
                        self.assertIn("https://ui.oiloil.org/en/pro/" if language.startswith("en") else "https://ui.oiloil.org/pro/", out)
                        self.assertIn("no purchase record" if language.startswith("en") else "没有对应的购买记录", out)
                    _, state = self.install_state()
                    self.assertEqual(state["auto_failed_reason"], error)
                    self.assertEqual(self.run_check(LANG=language, FAKE_NPX_FAIL="1", FAKE_NPX_JSON=json.dumps({"error": error})), "")

    def test_cli_network_errors_are_silent_and_retry_after_an_hour(self):
        self.login()
        extra = {"FAKE_NPX_FAIL": "1", "FAKE_NPX_JSON": '{"error":"network"}'}
        self.assertEqual(self.run_check(**extra), "")
        self.assertEqual(self.run_check(**extra), "")
        self.assertEqual(len(self.npx_calls()), 1)
        path, state = self.install_state()
        state["auto_failed_at"] -= 3601
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.run_check(**extra), "")
        self.assertEqual(len(self.npx_calls()), 2)

    def test_npm_network_errors_are_silent_without_json(self):
        self.login()
        self.assertEqual(self.run_check(FAKE_NPX_FAIL="1", FAKE_NPX_STDERR="npm error code ENOTFOUND"), "")

    def test_missing_or_old_node_and_missing_npx_do_not_count_as_attempts(self):
        self.login()
        for executable in ("npx", "node"):
            with self.subTest(executable=executable):
                target = self.bin / executable
                hidden = self.bin / (executable + "-hidden")
                target.rename(hidden)
                out = self.run_check(PATH=str(self.bin))
                self.assertIn("自动更新需要 Node.js 18 以上", out)
                self.assertIn(str(self.skill / 'scripts/check_update.py'), out)
                self.assert_no_attempt()
                hidden.rename(target)
        out = self.run_check(FAKE_NODE_VERSION="v16.20.0")
        self.assertIn("自动更新需要 Node.js 18 以上", out)
        self.assert_no_attempt()
        self.assertIn("已自动更新", self.run_check())

    def test_login_or_config_change_allows_immediate_retry(self):
        self.assertIn("login", self.run_check())
        self.login()
        self.assertIn("已自动更新", self.run_check())

    def test_reauthorization_and_environment_token_change_clear_failed_cooldown(self):
        self.login()
        self.run_check(FAKE_NPX_FAIL="1", FAKE_NPX_JSON='{"error":"unauthorized"}')
        config = self.tmp / "config" / "oil" / "config.json"
        config.write_text(json.dumps({"token": "oil_new_token", "email": "b@example.com"}), encoding="utf-8")
        self.assertIn("已自动更新", self.run_check())
        self.assertEqual(len(self.npx_calls()), 2)
        (self.skill / "SKILL.md").write_text('name: oil-ui-pro\nmetadata:\n  version: "0.10.0"\n', encoding="utf-8")
        self.run_check(OIL_TOKEN="oil_first", FAKE_NPX_FAIL="1", FAKE_NPX_JSON='{"error":"unauthorized"}')
        self.assertIn("已自动更新", self.run_check(OIL_TOKEN="oil_second"))
        state_text = "".join(p.read_text(encoding="utf-8") for p in (self.tmp / "state").rglob("*.json"))
        self.assertNotIn("oil_first", state_text)
        self.assertNotIn("oil_second", state_text)

    def test_repairing_dependency_after_a_failed_attempt_allows_immediate_retry(self):
        self.login()
        self.run_check(FAKE_NPX_FAIL="1")
        self.assertIn("已自动更新", self.run_check(FAKE_NODE_VERSION="v22.0.0"))
        self.assertEqual(len(self.npx_calls()), 2)

    def test_installations_share_versions_but_not_cooldowns_or_notices(self):
        self.login()
        original = self.skill
        other = self.tmp / "another host" / "oil-ui-pro"
        shutil.copytree(original, other)
        self.assertIn("有新版本", self.run_check(FAKE_NPX_FAIL="1"))
        self.skill = other
        self.assertIn("已自动更新", self.run_check())
        self.assertEqual(Versions.hits, 1)
        self.assertIn('version: "0.10.0"', (original / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(len(list((self.tmp / "state" / "oil" / "installations").glob("*.json"))), 2)

    def test_legacy_shared_failure_does_not_block_an_installation(self):
        self.login()
        cache = self.tmp / "state" / "oil" / "oil-ui-pro-update.json"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({"latest": "99.0.0", "checked_at": 9999999999,
                                     "auto_failed_version": "99.0.0", "auto_failed_at": 9999999999,
                                     "notified_version": "99.0.0", "notified_at": 9999999999}), encoding="utf-8")
        self.assertIn("已自动更新", self.run_check())

    def test_checks_versions_again_after_ten_minutes(self):
        self.run_check(OIL_NO_AUTO_UPDATE="1")
        self.run_check(OIL_NO_AUTO_UPDATE="1")
        self.assertEqual(Versions.hits, 1)
        cache = self.tmp / "state" / "oil" / "oil-ui-pro-update.json"
        state = json.loads(cache.read_text(encoding="utf-8"))
        state["checked_at"] -= 601
        cache.write_text(json.dumps(state), encoding="utf-8")
        self.run_check(OIL_NO_AUTO_UPDATE="1")
        self.assertEqual(Versions.hits, 2)

    def test_offline_with_stale_cache_is_silent_and_fetch_retries_later(self):
        self.run_check(OIL_NO_AUTO_UPDATE="1")
        cache = self.tmp / "state" / "oil" / "oil-ui-pro-update.json"
        state = json.loads(cache.read_text(encoding="utf-8"))
        state["checked_at"] = 0
        cache.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.run_check(api="http://127.0.0.1:9"), "")
        self.assertEqual(self.run_check(), "")
        self.assertEqual(Versions.hits, 1)
        state = json.loads(cache.read_text(encoding="utf-8"))
        state["fetch_failed_at"] -= 3601
        cache.write_text(json.dumps(state), encoding="utf-8")
        self.login()
        self.assertIn("已自动更新", self.run_check())
        self.assertEqual(Versions.hits, 2)

    def test_manual_command_targets_absolute_path_and_handles_shell_characters(self):
        self.login()
        self.skill.rename(self.skill.parent / 'custom space $HOME `false` "quote"')
        self.skill = self.skill.parent / 'custom space $HOME `false` "quote"'
        out = self.run_check(OIL_NO_AUTO_UPDATE="1")
        command = out.split("在终端运行 ", 1)[1].rsplit(" 即可更新。", 1)[0]
        # 实际复制执行提示；参数只能指向该副本，不能展开变量或命令替换。
        env = {k: v for k, v in self.last_env.items() if k != 'OIL_NO_AUTO_UPDATE'}
        result = subprocess.run([SH, "-c", command], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.skill), self.npx_calls()[0])
        self.assertIn('version: "99.0.0"', (self.skill / "SKILL.md").read_text(encoding="utf-8"))

    def test_non_chinese_locales_get_english(self):
        for language in ("ja_JP.UTF-8", "hi_IN.UTF-8", ""):
            with self.subTest(language=language):
                shutil.rmtree(self.tmp / "state", ignore_errors=True)
                self.assertIn("is available", self.run_check(LANG=language, LC_ALL="", LC_MESSAGES="", OIL_NO_AUTO_UPDATE="1"))

    def test_english_success_and_manual_notice(self):
        out = self.run_check(LANG="en_US.UTF-8", OIL_NO_AUTO_UPDATE="1")
        self.assertIn("Oil UI Pro 99.0.0 is available (current: 0.10.0)", out)
        self.assertIn("To update, run", out)
        self.assertIn("--update", out)
        self.login()
        self.assertIn("updated automatically to 99.0.0", self.run_check(LANG="en_US.UTF-8"))

    def shell_path(self):
        # 不从真实 PATH 找 Python；只保留入口写状态所需的工具。
        for tool in ("mkdir", "rmdir"):
            target = self.bin / tool
            if not target.exists():
                target.symlink_to(shutil.which(tool))
        return str(self.bin)

    def test_launcher_runs_when_only_python_is_available(self):
        (self.bin / "python").symlink_to(sys.executable)
        out = self.run_check(launcher=True, PATH=self.shell_path(), OIL_NO_AUTO_UPDATE="1")
        self.assertIn("有新版本", out)
        self.assertEqual(Versions.hits, 1)

    def test_missing_python_warns_once_and_recovery_resets_the_reminder(self):
        path = self.shell_path()
        self.assertEqual(self.run_check(launcher=True, PATH=path), "版本检查需要 Python 3，本次没有检查更新。\n")
        self.assertEqual(self.run_check(launcher=True, PATH=path), "OIL_UPDATE_CHECK_SKIPPED: missing_python\n")
        self.assertEqual(Versions.hits, 0)
        (self.bin / "python").symlink_to(sys.executable)
        self.assertIn("有新版本", self.run_check(launcher=True, PATH=path, OIL_NO_AUTO_UPDATE="1"))
        (self.bin / "python").unlink()
        self.assertIn("Version checks need Python 3", self.run_check(launcher=True, PATH=path, LANG="en_US.UTF-8"))

    def test_python2_is_not_used_and_disabled_or_development_launcher_is_silent(self):
        (self.bin / "python").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (self.bin / "python").chmod(0o755)
        path = self.shell_path()
        self.assertEqual(self.run_check(launcher=True, PATH=path, OIL_NO_UPDATE_CHECK="1"), "")
        (self.skill / ".git").mkdir()
        self.assertEqual(self.run_check(launcher=True, PATH=path), "")
        (self.skill / ".git").rmdir()
        self.assertIn("版本检查需要 Python 3", self.run_check(launcher=True, PATH=path))

    def test_silent_when_up_to_date_offline_disabled_or_in_a_checkout(self):
        self.set_latest("0.0.1", free=False)
        self.assertEqual(self.run_check(), "")
        self.set_latest("99.0.0", free=False)
        self.assertEqual(self.run_check(api="http://127.0.0.1:9", XDG_STATE_HOME=str(self.tmp / "s2")), "")
        self.assertEqual(self.run_check(OIL_NO_UPDATE_CHECK="1", XDG_STATE_HOME=str(self.tmp / "s3")), "")
        (self.skill / ".git").mkdir()
        self.assertEqual(self.run_check(XDG_STATE_HOME=str(self.tmp / "s4")), "")


if __name__ == "__main__":
    unittest.main()
