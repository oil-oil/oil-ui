"""Structural checks that keep the English edition aligned with upstream."""
import re
import unittest
from pathlib import Path

EN = Path(__file__).resolve().parent.parent
UPSTREAM = EN.parent
CJK = re.compile(r"[一-鿿]")
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
TABLE_ROW = re.compile(r"^\|.*\|\s*$", re.MULTILINE)
PROSE = [EN / "SKILL.md", *sorted((EN / "references").glob("*.md"))]


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


class TranslationTest(unittest.TestCase):
    def test_prose_contains_no_chinese(self):
        for path in PROSE:
            hits = [n for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if CJK.search(line)]
            self.assertEqual(hits, [], f"{path.relative_to(EN)} still has Chinese on lines {hits}")

    def test_every_upstream_document_has_a_counterpart_and_nothing_extra(self):
        for folder in ("references", "scripts"):
            upstream = {p.name for p in (UPSTREAM / folder).iterdir() if p.is_file()}
            ours = {p.name for p in (EN / folder).iterdir() if p.is_file()}
            self.assertEqual(ours, upstream, f"{folder}/ differs from upstream")

    def test_structure_matches_upstream(self):
        for path in PROSE:
            source = (UPSTREAM / path.relative_to(EN)).read_text(encoding="utf-8")
            target = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertEqual(len(HEADING.findall(strip_code(target))), len(HEADING.findall(strip_code(source))), "heading count")
                self.assertEqual(len(TABLE_ROW.findall(target)), len(TABLE_ROW.findall(source)), "table row count")

    def test_relative_links_resolve(self):
        for path in PROSE:
            text = path.read_text(encoding="utf-8")
            for target in LINK.findall(strip_code(text)):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / file_part) if file_part else path
                with self.subTest(file=path.name, link=target):
                    self.assertTrue(resolved.is_file(), f"missing file {resolved}")
                    if anchor:
                        slugs = [slug(h) for h in HEADING.findall(resolved.read_text(encoding="utf-8"))]
                        self.assertIn(anchor, slugs)

    def test_frontmatter_names_this_edition_and_tracks_the_pinned_version(self):
        skill = (EN / "SKILL.md").read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"^name: oil-ui-en\s*$", skill, re.MULTILINE), "frontmatter name")
        version = re.search(r'^\s+version:\s*"(\d+\.\d+\.\d+)"', skill, re.MULTILINE).group(1)
        pin = dict(line.split(" ", 1) for line in (EN / "translation" / "UPSTREAM").read_text().splitlines())
        self.assertEqual(version, pin["version"].strip())
        upstream_version = re.search(r'^\s+version:\s*"(\d+\.\d+\.\d+)"', (UPSTREAM / "SKILL.md").read_text(), re.MULTILINE).group(1)
        self.assertEqual(version, upstream_version, "upstream moved; run en/translation/sync_upstream.py")


if __name__ == "__main__":
    unittest.main()
