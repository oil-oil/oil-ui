#!/usr/bin/env python3
"""检查本 Skill 有没有新版本；只有显式传入 --update 才更新。

由使用 Skill 触发，最多每 10 分钟联网检查一次，网络失败后一小时可重试。
只读取 ui.oiloil.org 公开的版本列表，不上传项目内容。
发现新版本时默认提示；用户要求更新后，用固定提交的 CLI 原地更新本目录：
成功打印一行“已自动更新”，不能自动更新时打印一行提示，条件不变时每天最多提示一次；
没有新版本、网络失败或在开发目录（含 .git）里运行时什么也不输出。
设置环境变量 OIL_NO_UPDATE_CHECK=1 关闭检查，OIL_NO_AUTO_UPDATE=1 强制只提示。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("OIL_API", "https://ui.oiloil.org").rstrip("/")
# 固定经过检查的 CLI：无 npm 依赖，下载包必须通过 SHA-256 与归档路径校验。
CLI = "github:oil-oil/oil-cli#64ada13fbf95d3154fa708cedaa1b3a963dc1151"
UPDATE_ENV_KEYS = {
    "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME",
    "SYSTEMROOT", "WINDIR", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_MESSAGES",
    "OIL_API", "OIL_TOKEN",
}
DAY = 24 * 3600
# 发版后用户下一次使用就能更新；版本列表有服务端缓存，频繁检查的成本很低
CHECK_INTERVAL = 10 * 60
# 联网检查不能拖慢任务：超时就跳过，下次再查
FETCH_TIMEOUT = 2
RETRY_AFTER_FAILURE = 3600
UPDATE_TIMEOUT = 300


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
    """公开版本缓存仍按 Skill 共享，兼容原来的缓存位置。"""
    return state_dir() / f"{name}-update.json"


def installation_state_path(name: str) -> Path:
    key = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()
    return state_dir() / "installations" / f"{name}-{key}.json"


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "oil" / "config.json"


def logged_in() -> bool:
    if os.environ.get("OIL_TOKEN"):
        return True
    try:
        return bool(json.loads(config_path().read_text(encoding="utf-8")).get("token"))
    except (OSError, ValueError, AttributeError):
        return False


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
    # 免费版的版本信息带公开下载地址，付费版没有
    return {"latest": entry["latest"], "free": bool(entry.get("download_url"))}


def file_signature(path: str | Path | None) -> list:
    if not path:
        return []
    try:
        stat = Path(path).stat()
        return [str(path), stat.st_mtime_ns, stat.st_size]
    except OSError:
        return [str(path)]


def update_environment() -> dict[str, str]:
    """只给已获准运行的 CLI 传必要路径、语言与其自身授权，不传无关密钥或注入选项。"""
    return {**{k: v for k, v in os.environ.items() if k.upper() in UPDATE_ENV_KEYS}, "CI": "1"}


def update_context(approved: bool = False) -> tuple[str, str | None, bool]:
    """只存指纹；登录配置变化或补齐依赖时不沿用旧冷却。"""
    npx = shutil.which("npx")
    node = shutil.which("node")
    node_version = ""
    if node and approved:
        try:
            result = subprocess.run([node, "--version"], env=update_environment(), capture_output=True, text=True, timeout=3, encoding="utf-8")
            if result.returncode == 0:
                node_version = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    version = re.fullmatch(r"v?(\d+)\.\d+\.\d+", node_version)
    ready = bool(npx and version and int(version.group(1)) >= 18)
    context = [API, file_signature(config_path()), os.environ.get("OIL_TOKEN", ""),
               file_signature(npx), file_signature(node), node_version,
               bool(os.environ.get("OIL_NO_AUTO_UPDATE")), approved, CLI]
    fingerprint = hashlib.sha256(json.dumps(context).encode()).hexdigest()
    return fingerprint, npx, ready


class UpdateResult(NamedTuple):
    attempted: bool
    reason: str


def cli_error(stdout: str, stderr: str) -> str:
    # npx 的日志可能混在 JSON 前面；不转述 CLI 原始 message，避免泄露信息。
    for line in reversed((stdout + "\n" + stderr).splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            return data["error"]
    return ""


def auto_update(name: str, latest: str, free: bool, npx: str | None, ready: bool, approved: bool = False) -> UpdateResult:
    if not approved or os.environ.get("OIL_NO_AUTO_UPDATE"):
        return UpdateResult(False, "manual")
    if not (free or logged_in()):
        return UpdateResult(False, "unauthorized")
    if not ready:
        return UpdateResult(False, "dependencies")
    # CI=1 让命令行在没登录时直接失败，不会停下来等浏览器确认
    env = update_environment()
    try:
        result = subprocess.run([npx, "-y", CLI, "update", name, "--path", str(ROOT), "--json"], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=UPDATE_TIMEOUT, check=False, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return UpdateResult(False, "dependencies")
    except subprocess.TimeoutExpired:
        return UpdateResult(True, "network")
    except (OSError, subprocess.SubprocessError):
        return UpdateResult(True, "failed")
    error = cli_error(result.stdout, result.stderr)
    if error:
        return UpdateResult(True, error)
    # npm 在启动 CLI 前的网络或 Node 缺失错误不是 JSON。
    if re.search(r"ENOTFOUND|EAI_AGAIN|ECONN\w+|ETIMEDOUT|ERR_SOCKET_TIMEOUT|fetch failed", result.stderr, re.I):
        return UpdateResult(True, "network")
    if re.search(r"node[^\n]*(?:not found|No such file)|EBADENGINE", result.stderr, re.I):
        return UpdateResult(False, "dependencies")
    skill = read_skill()
    if result.returncode == 0 and skill and parse(skill[1]) >= parse(latest):
        return UpdateResult(True, "updated")
    return UpdateResult(True, "failed")


def english() -> bool:
    # 只有中文环境用中文，其他语言和未设置时都用英文；宿主会再按对话语言转述。
    return not (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "")).lower().startswith("zh")


def update_command(name: str) -> str:
    # 从同一入口执行，保留固定 CLI 和环境白名单；不让宿主自行拼接 npx 命令。
    args = [sys.executable, str(ROOT / "scripts" / "check_update.py"), "--update"]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def product_name(name: str) -> str:
    if name == "oil-ui-pro":
        return "Oil UI Pro"
    if name == "oil-ui":
        return "Oil UI (open source)" if english() else "Oil UI 开源版"
    return name


def zh_label(label: str) -> str:
    # 中文句子里，以汉字结尾的名称后面不加空格。
    return label if re.search(r"[\u4e00-\u9fff]$", label) else f"{label} "


def notice(name: str, current: str, latest: str, detail: str, reason: str) -> str:
    command = update_command(name)
    label = product_name(name)
    if english():
        intro = f"{label} {latest} is available (current: {current}){detail}. "
        if reason == "unauthorized":
            return intro + f"Authorization has expired or is missing. Run npx {CLI} login, then run {command}."
        if reason == "inactive":
            return intro + f"This Skill has no purchase record. Purchase it at https://ui.oiloil.org/en/pro/ to get updates, then run {command}."
        if reason == "dependencies":
            return intro + f"Automatic updates need Node.js 18 or later. Install it, then run {command}."
        return intro + f"To update, run {command}."
    intro = f"{zh_label(label)}有新版本 {latest}（当前 {current}）{detail}。"
    if reason == "unauthorized":
        return intro + f"授权已失效或尚未授权。运行 npx {CLI} login 重新授权，再运行 {command}。"
    if reason == "inactive":
        return intro + f"这份 Skill 没有对应的购买记录，购买后才能获得更新。打开 https://ui.oiloil.org/pro/ 购买，再运行 {command}。"
    if reason == "dependencies":
        return intro + f"自动更新需要 Node.js 18 以上。安装后运行 {command}。"
    return intro + f"在终端运行 {command} 即可更新。"


def utf8_output() -> None:
    """管道另一头的 Agent 按 UTF-8 读；控制台的代码页可能连中文都没有。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8")


def main() -> int:
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Explicitly authorize updating this installation")
    approved = parser.parse_args().update
    if os.environ.get("OIL_NO_UPDATE_CHECK") or (ROOT / ".git").exists():
        return 0
    skill = read_skill()
    if not skill:
        return 0
    name, current = skill
    path = state_path(name)
    # 原来的共享文件可能包含失败与提示记录，迁移时只保留公开缓存。
    previous_cache = load(path)
    cache = {key: value for key, value in previous_cache.items()
             if key in {"checked_at", "latest", "free", "fetch_failed_at"}}
    if cache != previous_cache:
        save(path, cache)
    install_path = installation_state_path(name)
    state = load(install_path)
    now = time.time()

    if now - float(cache.get("checked_at", 0)) >= CHECK_INTERVAL:
        if now - float(cache.get("fetch_failed_at", 0)) < RETRY_AFTER_FAILURE:
            return 0
        try:
            found = fetch(name)
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
    detail = ""
    context, npx, ready = update_context(approved)

    reason = state.get("auto_failed_reason", "failed")
    cooldown = RETRY_AFTER_FAILURE if reason == "network" else DAY
    if (state.get("auto_failed_version") != latest or state.get("auto_failed_context") != context
            or now - float(state.get("auto_failed_at", 0)) >= cooldown):
        result = auto_update(name, latest, bool(cache.get("free")), npx, ready, approved)
        reason = result.reason
        if reason == "updated":
            save(install_path, {})
            label = product_name(name)
            if english():
                print(f"{label} updated automatically to {latest} (previous: {current}){detail}. Read SKILL.md again before continuing.")
            else:
                print(f"{zh_label(label)}已自动更新到 {latest}（原来是 {current}）{detail}。请重新读取 SKILL.md 再继续。")
            return 0
        if result.attempted:
            state.update(auto_failed_version=latest, auto_failed_at=now,
                         auto_failed_reason=reason, auto_failed_context=context)
        else:
            for key in list(state):
                if key.startswith("auto_failed_"):
                    state.pop(key)
        save(install_path, state)

    if reason == "network":
        return 0

    language = "en" if english() else "zh"
    if (state.get("notified_version") == latest and state.get("notified_reason") == reason
            and state.get("notified_context") == context and state.get("notified_language") == language
            and now - float(state.get("notified_at", 0)) < DAY):
        return 0
    state["notified_version"], state["notified_at"] = latest, now
    state.update(notified_reason=reason, notified_context=context, notified_language=language)
    save(install_path, state)
    print(notice(name, current, latest, detail, reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
