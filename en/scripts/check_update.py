#!/usr/bin/env python3
"""Tell the agent when upstream Oil UI has moved past this English edition.

Triggered by using the skill. At most once every 10 minutes it reads the public
version list on ui.oiloil.org for the upstream skill `oil-ui` and compares it with
the upstream version this translation tracks (metadata.version in SKILL.md). When
upstream is ahead it prints one English line pointing at the translation repo; the
agent relays it in the user's language. It never downloads or runs an updater:
upstream's updater would replace this directory with the Chinese skill.
Nothing is printed when there is no newer version, when the network fails, or when
run inside a git checkout. Set OIL_NO_UPDATE_CHECK=1 to turn the check off.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("OIL_API", "https://ui.oiloil.org").rstrip("/")
# This edition is named oil-ui-en but follows upstream's oil-ui releases.
UPSTREAM_NAME = "oil-ui"
REPO = "https://github.com/shubhamd/oil-ui-english"
REINSTALL = "npx skills add shubhamd/oil-ui-english --full-depth --skill oil-ui-en"
DAY = 24 * 3600
# The version list is cached server-side, so frequent checks are cheap.
CHECK_INTERVAL = 10 * 60
# A network check must not slow the task down: time out, skip, try next time.
FETCH_TIMEOUT = 2
RETRY_AFTER_FAILURE = 3600


def read_skill() -> tuple[str, str] | None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    name = re.search(r"^name:\s*\"?([\w-]+)\"?\s*$", text, re.MULTILINE)
    version = re.search(r"^\s+version:\s*\"?(\d+\.\d+\.\d+)\"?\s*$", text, re.MULTILINE)
    if not name or not version:
        return None
    return name.group(1), version.group(1)


def state_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "oil"


def state_path(name: str) -> Path:
    """The public version cache is shared per upstream skill name."""
    return state_dir() / f"{name}-update.json"


def installation_state_path(name: str) -> Path:
    key = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()
    return state_dir() / "installations" / f"{name}-{key}.json"


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def fetch(name: str) -> dict | None:
    request = urllib.request.Request(f"{API}/api/store/versions", headers={"User-Agent": "oil-skill-update-check"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        entry = json.load(response).get("skills", {}).get(name)
    if not isinstance(entry, dict) or not re.fullmatch(r"\d+\.\d+\.\d+", str(entry.get("latest", ""))):
        return None
    return {"latest": entry["latest"]}


def notice(current: str, latest: str) -> str:
    return (f"Oil UI {latest} is available upstream (this English edition tracks {current}). "
            f"Check {REPO} for an updated translation, then reinstall with: {REINSTALL}")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if os.environ.get("OIL_NO_UPDATE_CHECK") or (ROOT / ".git").exists() or (ROOT.parent / ".git").exists():
        return 0
    skill = read_skill()
    if not skill:
        return 0
    name, current = skill
    path = state_path(UPSTREAM_NAME)
    # Only the public version cache is kept; anything else that lands in the file is dropped.
    previous_cache = load(path)
    cache = {key: value for key, value in previous_cache.items() if key in {"checked_at", "latest", "fetch_failed_at"}}
    if cache != previous_cache:
        save(path, cache)
    install_path = installation_state_path(name)
    state = load(install_path)
    now = time.time()

    if now - float(cache.get("checked_at", 0)) >= CHECK_INTERVAL:
        if now - float(cache.get("fetch_failed_at", 0)) < RETRY_AFTER_FAILURE:
            return 0
        try:
            found = fetch(UPSTREAM_NAME)
        except Exception:
            found = None
        if found:
            cache.update(found)
            cache["checked_at"] = now
            cache.pop("fetch_failed_at", None)
        else:
            cache["fetch_failed_at"] = now
        save(path, cache)
        if not found:
            return 0

    latest = cache.get("latest")
    if not isinstance(latest, str) or not re.fullmatch(r"\d+\.\d+\.\d+", latest) or parse(latest) <= parse(current):
        return 0
    if state.get("notified_version") == latest and now - float(state.get("notified_at", 0)) < DAY:
        return 0
    save(install_path, {"notified_version": latest, "notified_at": now})
    print(notice(current, latest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
