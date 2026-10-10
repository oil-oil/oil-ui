#!/usr/bin/env python3
"""Report what changed upstream since the pinned commit and what the English edition must do about it.

    python3 en/translation/sync_upstream.py [--ref upstream/main] [--diff] [--apply] [--pin]

Reads en/translation/UPSTREAM (the upstream commit this translation was made from) and
compares it with --ref. Files that carry no language (fonts, vendored scripts) are copied
into en/ with --apply. Files that carry prose or messages are listed for re-translation;
--diff prints their upstream patch. --pin rewrites UPSTREAM to --ref once the translation
has caught up. Exit status is 1 while translatable changes remain, so an agent can loop on it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TRACKED_ROOTS = ("SKILL.md", "references/", "scripts/", "tests/", "assets/")
PASSTHROUGH = ("assets/fonts/", "assets/vendor/", "assets/logo.png")
IGNORED = ("assets/readme/",)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return result.stdout


def read_pin(path: Path) -> dict[str, str]:
    pin = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(" ")
        if key and value:
            pin[key] = value.strip()
    if "commit" not in pin:
        raise SystemExit(f"{path} has no 'commit' line")
    return pin


def skill_version(repo: Path, ref: str) -> str:
    text = git(repo, "show", f"{ref}:SKILL.md")
    match = re.search(r'^\s+version:\s*"?(\d+\.\d+\.\d+)"?\s*$', text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def classify(path: str) -> str:
    if path.startswith(IGNORED) or not path.startswith(TRACKED_ROOTS):
        return "ignore"
    if path.startswith(PASSTHROUGH):
        return "passthrough"
    return "translate"


def changes(repo: Path, pinned: str, ref: str) -> list[tuple[str, str, str]]:
    out = git(repo, "diff", "--name-status", "-M", pinned, ref, "--", *TRACKED_ROOTS)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        status, path = parts[0][0], parts[-1]
        rows.append((status, path, classify(path)))
    return rows


def apply_passthrough(repo: Path, ref: str, rows: list[tuple[str, str, str]]) -> list[str]:
    done = []
    for status, path, kind in rows:
        if kind != "passthrough":
            continue
        target = repo / "en" / path
        if status == "D":
            if target.exists():
                target.unlink()
                done.append(f"removed {target.relative_to(repo)}")
            continue
        blob = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, check=True).stdout
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        done.append(f"copied {target.relative_to(repo)}")
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2], help="repository root")
    parser.add_argument("--ref", default="upstream/main", help="upstream ref to compare against")
    parser.add_argument("--diff", action="store_true", help="print the upstream patch of each translatable file")
    parser.add_argument("--apply", action="store_true", help="copy passthrough files (fonts, vendor) into en/")
    parser.add_argument("--pin", action="store_true", help="record --ref as the new pinned upstream commit")
    args = parser.parse_args()

    repo = args.repo.resolve()
    pin_path = repo / "en" / "translation" / "UPSTREAM"
    pinned = read_pin(pin_path)["commit"]
    ref_commit = git(repo, "rev-parse", args.ref).strip()
    print(f"pinned   {pinned}  (version {skill_version(repo, pinned)})")
    print(f"upstream {ref_commit}  (version {skill_version(repo, ref_commit)})")

    rows = changes(repo, pinned, ref_commit)
    translate = [r for r in rows if r[2] == "translate"]
    passthrough = [r for r in rows if r[2] == "passthrough"]
    for status, path, _ in translate:
        print(f"translate   {status} {path}")
    for status, path, _ in passthrough:
        print(f"passthrough {status} {path}")
    if not rows:
        print("nothing changed under the tracked roots")

    if args.diff:
        for status, path, _ in translate:
            print(f"\n===== {path} ({status}) =====")
            sys.stdout.write(git(repo, "diff", pinned, ref_commit, "--", path))
    if args.apply:
        for line in apply_passthrough(repo, ref_commit, rows):
            print(line)
    if args.pin:
        pin_path.write_text(f"commit {ref_commit}\nversion {skill_version(repo, ref_commit)}\n", encoding="utf-8")
        print(f"pinned {ref_commit}")
        return 0
    return 1 if translate else 0


if __name__ == "__main__":
    raise SystemExit(main())
