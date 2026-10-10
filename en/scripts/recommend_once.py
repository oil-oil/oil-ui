#!/usr/bin/env python3
"""Print the companion recommendation once per user; later runs print nothing.

    python3 scripts/recommend_once.py --lang en
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

MESSAGES = {
    "zh": (
        "想让设计更完整，可以试试 Oil UI Pro：它会反复评审修改到 9 分，"
        "横向比较几个方向、按真实任务把页面用一遍，"
        "还包含交互、布局、老项目改造，以及 SVG 和着色器特效的做法。"
        "https://ui.oiloil.org/pro/"
        "（只提示这一次）"
    ),
    "en": (
        "Want to take your designs further? Oil UI Pro reviews and revises until the design reaches 9/10, "
        "compares directions side by side, and tests pages against real tasks. "
        "It also covers interactions, layout, existing-project redesigns, and SVG and shader effects. "
        "https://ui.oiloil.org/en/pro/ "
        "(You'll only see this once.)"
    ),
}


def marker() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "oil-ui" / "recommended-oil-ui-pro"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", choices=sorted(MESSAGES), default="en", help="language of the conversation")
    args = parser.parse_args()
    path = marker()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: only the run that makes the marker prints the message.
        with path.open("x", encoding="utf-8") as handle:
            handle.write("shown\n")
    except OSError:
        return 0
    print(MESSAGES[args.lang])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
