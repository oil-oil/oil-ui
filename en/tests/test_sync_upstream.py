import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "translation" / "sync_upstream.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


class SyncUpstreamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        self.write("SKILL.md", '---\nname: oil-ui\nmetadata:\n  version: "0.1.0"\n---\n# 一\n')
        self.write("references/a.md", "# 甲\n")
        self.write("assets/fonts/x.ttf", "font-v1")
        self.write("assets/vendor/y.js", "lib-v1")
        self.write("assets/readme/hero.webp", "img")
        self.write("README.md", "readme")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD").strip()
        self.write("en/translation/UPSTREAM", f"commit {self.base}\nversion 0.1.0\n")
        self.write("en/assets/fonts/x.ttf", "font-v1")
        self.write("en/assets/vendor/y.js", "lib-v1")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_sync(self, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), "--ref", "HEAD", *flags],
                              capture_output=True, text=True)

    def commit_upstream_changes(self) -> str:
        self.write("SKILL.md", '---\nname: oil-ui\nmetadata:\n  version: "0.2.0"\n---\n# 二\n')
        self.write("references/a.md", "# 甲乙\n")
        self.write("references/new.md", "# 新\n")
        self.write("assets/fonts/x.ttf", "font-v2")
        (self.repo / "assets/vendor/y.js").unlink()
        self.write("assets/readme/hero.webp", "img2")
        self.write("README.md", "readme2")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "upstream moves")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def test_nothing_changed_exits_zero(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing changed", result.stdout)

    def test_classifies_changes_and_reports_versions(self):
        self.commit_upstream_changes()
        result = self.run_sync()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("(version 0.1.0)", result.stdout)
        self.assertIn("(version 0.2.0)", result.stdout)
        self.assertIn("translate   M SKILL.md", result.stdout)
        self.assertIn("translate   M references/a.md", result.stdout)
        self.assertIn("translate   A references/new.md", result.stdout)
        self.assertIn("passthrough M assets/fonts/x.ttf", result.stdout)
        self.assertIn("passthrough D assets/vendor/y.js", result.stdout)
        self.assertNotIn("README.md", result.stdout)
        self.assertNotIn("hero.webp", result.stdout)

    def test_diff_prints_patch_for_translatable_files_only(self):
        self.commit_upstream_changes()
        result = self.run_sync("--diff")
        self.assertIn("===== references/a.md (M) =====", result.stdout)
        self.assertIn("+# 甲乙", result.stdout)
        self.assertNotIn("===== assets/fonts/x.ttf", result.stdout)

    def test_apply_copies_and_removes_passthrough_files(self):
        self.commit_upstream_changes()
        result = self.run_sync("--apply")
        self.assertIn("copied en/assets/fonts/x.ttf", result.stdout)
        self.assertIn("removed en/assets/vendor/y.js", result.stdout)
        self.assertEqual((self.repo / "en/assets/fonts/x.ttf").read_text(), "font-v2")
        self.assertFalse((self.repo / "en/assets/vendor/y.js").exists())
        self.assertEqual((self.repo / "references/a.md").read_text(), "# 甲乙\n", "upstream files stay untouched")

    def test_pin_records_new_commit_and_version(self):
        head = self.commit_upstream_changes()
        result = self.run_sync("--pin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "en/translation/UPSTREAM").read_text(), f"commit {head}\nversion 0.2.0\n")
        self.assertIn("nothing changed", self.run_sync().stdout)


if __name__ == "__main__":
    unittest.main()
