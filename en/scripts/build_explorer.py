#!/usr/bin/env python3
"""Build a portable, offline design comparison from a local manifest."""

from __future__ import annotations

import argparse
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "assets" / "style-explorer.html"
MARKER = "/*__OIL_UI_DATA__*/ null"
CONNECT_CSP = "connect-src 'none'"
PREVIEW_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "font-src data:; media-src data:; script-src 'none'; "
    "form-action 'none'; base-uri 'none'; object-src 'none'"
)


def text_field(obj: dict, name: str, *, default: str | None = None) -> str:
    value = obj.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def text_list(obj: dict, name: str) -> list[str]:
    values = obj.get(name)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{name} must be a non-empty array of strings")
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f"every item of {name} must be a non-empty string")
    return [v.strip() for v in values]


class AssetCheck(HTMLParser):
    """Reject resource dependencies; the browser sandbox disables behavior."""

    def __init__(self):
        super().__init__()
        self.styles = []
        self.in_style = False
        self.head_position = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs = dict(attrs)
        if tag == "head" and self.head_position is None:
            self.head_position = (self.getpos(), self.get_starttag_text())
        if tag in ("iframe", "frame", "object", "embed"):
            raise ValueError("candidate HTML cannot contain nested documents; provide static content or a screenshot")
        if tag == "style":
            self.in_style = True
        if attrs.get("style"):
            self.styles.append(attrs["style"])
        if tag == "base":
            raise ValueError("candidate HTML must not contain a base element; resources need to be inlined")
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            raise ValueError("candidate HTML must not auto-redirect")
        for key in ("src", "poster", "data", "href", "xlink:href"):
            value = attrs.get(key, "") or ""
            if not value or value.startswith(("#", "data:")):
                continue
            raise ValueError(f"candidate HTML references an external resource {tag}.{key}: {value}")
        if attrs.get("srcset"):
            raise ValueError("candidate HTML must use an inlined src instead of srcset")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self.in_style = False

    def handle_data(self, data: str) -> None:
        if self.in_style:
            self.styles.append(data)


CSS_TOKEN = re.compile(
    r"(?P<comment>/\*.*?\*/)|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
    r"|(?P<ident>(?:[-_a-zA-Z]|\\(?:[0-9a-fA-F]{1,6}\s?|[^\r\n]))"
    r"(?:[-_a-zA-Z0-9]|\\(?:[0-9a-fA-F]{1,6}\s?|[^\r\n]))*)"
    r"|(?P<space>\s+)|(?P<symbol>.)", re.S,
)


def css_unescape(value: str) -> str:
    def replacement(match):
        if match.group(1):
            codepoint = int(match.group(1), 16)
            return chr(codepoint) if 0 < codepoint <= 0x10FFFF else "\ufffd"
        return match.group(2)
    return re.sub(r"\\([0-9a-fA-F]{1,6})(?:\s)?|\\([^\r\n])", replacement, value)


def check_css(css: str, label: str) -> None:
    tokens = [(m.lastgroup, m.group()) for m in CSS_TOKEN.finditer(css)
              if m.lastgroup not in ("comment", "space")]

    def check_resource(value: str):
        if not css_unescape(value).strip().lower().startswith(("data:", "#")):
            raise ValueError(f"{label}: CSS references an external resource")

    for index, (kind, value) in enumerate(tokens):
        if value == "@" and index + 1 < len(tokens) and tokens[index + 1][0] == "ident" and css_unescape(tokens[index + 1][1]).lower() == "import":
            raise ValueError(f"{label}: inline the CSS instead of using @import")
        name = css_unescape(value).lower() if kind == "ident" else ""
        if name not in ("url", "image-set", "-webkit-image-set", "image", "src"):
            continue
        if index + 1 >= len(tokens) or tokens[index + 1][1] != "(":
            continue
        depth, body = 1, []
        for inner_kind, inner_value in tokens[index + 2:]:
            if inner_kind == "symbol" and inner_value == "(":
                depth += 1
            elif inner_kind == "symbol" and inner_value == ")":
                depth -= 1
                if depth == 0:
                    break
            if name == "url":
                body.append(inner_value[1:-1] if inner_kind == "string" else inner_value)
            elif depth == 1 and inner_kind == "string":
                check_resource(inner_value[1:-1])
        if name == "url":
            check_resource("".join(body))


# Sandboxed previews have no storage; give prototypes an in-memory stand-in so their scripts keep running.
STORAGE_SHIM = (
    "<script>(()=>{const mem=()=>{const m=new Map();return{get length(){return m.size},"
    "key:i=>[...m.keys()][i]??null,getItem:k=>m.has(String(k))?m.get(String(k)):null,"
    "setItem:(k,v)=>{m.set(String(k),String(v))},removeItem:k=>{m.delete(String(k))},clear:()=>m.clear()}};"
    "for(const n of['localStorage','sessionStorage']){try{window[n].length}catch{"
    "Object.defineProperty(window,n,{value:mem(),configurable:true})}}})();</script>"
)


def preview_csp(interactive: bool) -> str:
    # Interactive prototypes may run their own inline scripts, still with no network or external files.
    # 'unsafe-eval' lets declarative libraries such as Alpine.js evaluate their attribute expressions.
    return PREVIEW_CSP.replace("script-src 'none'", "script-src 'unsafe-inline' 'unsafe-eval'") if interactive else PREVIEW_CSP


EMBEDDABLE = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".avif": "image/avif", ".svg": "image/svg+xml",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
    ".mp4": "video/mp4", ".webm": "video/webm",
}
ATTR_REF = re.compile(r"""(?P<lead>\b(?:src|poster|href|xlink:href)\s*=\s*)(?P<q>["'])(?P<ref>[^"'#][^"']*)(?P=q)""")
CSS_REF = re.compile(r"""url\(\s*(?P<q>["']?)(?P<ref>[^"')\s][^"')]*)(?P=q)\s*\)""")


def embed_local_files(content: str, base: Path, root: Path, used: set[Path]) -> str:
    """Inline images, fonts and videos referenced relative to the candidate, as long as they stay inside the manifest folder."""

    def data_url(ref: str) -> str | None:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//", ref):
            return None
        target = (base / ref.split("?")[0].split("#")[0]).resolve()
        mime = EMBEDDABLE.get(target.suffix.lower())
        if not mime or not target.is_file() or not target.is_relative_to(root):
            return None
        used.add(target)
        return f"data:{mime};base64," + base64.b64encode(target.read_bytes()).decode("ascii")

    def attr(match):
        url = data_url(match["ref"])
        return match.group(0) if url is None else f'{match["lead"]}{match["q"]}{url}{match["q"]}'

    def css(match):
        url = data_url(match["ref"])
        return match.group(0) if url is None else f'url("{url}")'

    return CSS_REF.sub(css, ATTR_REF.sub(attr, content))


SCRIPT_SRC = re.compile(r"""<script\b(?P<attrs>[^>]*?)\bsrc\s*=\s*(?P<q>["'])(?P<ref>[^"']+)(?P=q)(?P<rest>[^>]*)>\s*</script>""", re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
LINK_ATTR = re.compile(r"""\b(?P<name>rel|href)\s*=\s*(?P<q>["'])(?P<value>[^"']*)(?P=q)""", re.I)


def local_file(ref: str, base: Path, root: Path) -> Path | None:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//", ref):
        return None
    target = (base / ref.split("?")[0].split("#")[0]).resolve()
    return target if target.is_file() and target.is_relative_to(root) else None


def inline_local_code(content: str, base: Path, root: Path, used: set[Path], interactive: bool) -> str:
    """Inline stylesheets and, for interactive candidates, scripts that live in the manifest folder."""

    def link(match):
        attrs = {m["name"].lower(): m["value"] for m in LINK_ATTR.finditer(match.group(0))}
        target = local_file(attrs.get("href", ""), base, root) if "stylesheet" in attrs.get("rel", "").lower() else None
        if target is None:
            return match.group(0)
        used.add(target)
        css = embed_local_files(target.read_text(encoding="utf-8"), target.parent, root, used)
        return "<style>" + css.replace("</style", "<\\/style") + "</style>"

    deferred = []

    def script(match):
        target = local_file(match["ref"], base, root)
        if target is None:
            return match.group(0)
        used.add(target)
        if not interactive:
            return ""
        attrs = re.sub(r"\s+", " ", f'{match["attrs"]} {match["rest"]}').strip()
        code = target.read_text(encoding="utf-8").replace("</script", "<\\/script")
        is_module = re.search(r"""type\s*=\s*["']module["']""", attrs, re.I)
        tag = ('<script type="module">' if is_module else "<script>") + code + "</script>"
        # Inline scripts ignore defer, so deferred files move to the end of the body to keep their timing.
        if re.search(r"\bdefer\b", attrs, re.I) and not is_module:
            deferred.append(tag)
            return ""
        return tag

    content = SCRIPT_SRC.sub(script, LINK_TAG.sub(link, content))
    if deferred:
        close = content.lower().rfind("</body>")
        content = content + "".join(deferred) if close < 0 else content[:close] + "".join(deferred) + content[close:]
    return content


def prepare_html(path: Path, interactive: bool = False, root: Path | None = None, used: set[Path] | None = None) -> str:
    content = path.read_text(encoding="utf-8")
    if root is not None:
        root = root.resolve()
        used = used if used is not None else set()
        content = inline_local_code(content, path.parent, root, used, interactive)
        content = embed_local_files(content, path.parent, root, used)
    parser = AssetCheck()
    parser.feed(content)
    for style in parser.styles:
        check_css(style, path.name)
    if parser.head_position is None:
        raise ValueError(f"{path.name}: candidate HTML needs a complete head element")
    (line, column), start_tag = parser.head_position
    head_end = sum(len(part) + 1 for part in content.split('\n')[:line - 1]) + column + len(start_tag)
    meta = f'<meta http-equiv="Content-Security-Policy" content="{preview_csp(interactive)}">'
    return content[:head_end] + meta + (STORAGE_SHIM if interactive else "") + content[head_end:]


def prepare_image(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError(f"{path.name}: static previews support PNG, JPEG, and WebP")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def local_url(value: str, identifier: str) -> str:
    """Live candidates only point at a dev server on this machine."""
    try:
        parts = urlsplit(value)
        parts.port  # Reject malformed ports before generating CSP origins.
    except ValueError:
        raise ValueError(f"{identifier}: url must be a valid local http(s) address") from None
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in LOOPBACK or parts.username or parts.password:
        raise ValueError(f"{identifier}: url must point at a local dev server, for example http://localhost:5173/orders")
    return value


def load_manifest(path: Path) -> tuple[dict, set[Path]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ValueError("manifest.schemaVersion must be 1")
    data = {"schemaVersion": 1, "project": text_field(raw, "project"),
            "brief": text_field(raw, "brief"), "round": text_field(raw, "round", default="01")}
    if "lang" in raw:
        if raw["lang"] not in ("zh", "en"):
            raise ValueError('manifest.lang must be "zh" or "en"')
        data["lang"] = raw["lang"]
    if "serve" in raw:
        serve = raw["serve"]
        if not isinstance(serve, dict):
            raise ValueError("serve must be an object")
        if not isinstance(serve.get("command"), str) or not serve["command"].strip():
            raise ValueError("serve.command must be a non-empty string")
        if "cwd" in serve and (not isinstance(serve["cwd"], str) or not Path(serve["cwd"]).is_absolute()):
            raise ValueError("serve.cwd must be an absolute path")
        if "url" in serve:
            if not isinstance(serve["url"], str) or not serve["url"].strip():
                raise ValueError("serve.url must be a non-empty local http(s) address")
            local_url(serve["url"], "serve")
        data["serve"] = serve
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates needs at least one candidate")
    seen = set()
    inputs = {path, TEMPLATE.resolve()}
    output = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("every candidate must be an object")
        identifier = text_field(candidate, "id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier) or identifier in seen:
            raise ValueError(f"candidate id is invalid or duplicated: {identifier}")
        seen.add(identifier)
        kind = candidate.get("kind", "html")
        if kind not in ("html", "image", "url"):
            raise ValueError(f"unknown candidate kind: {kind}")
        baseline = candidate.get("baseline", False)
        interactive = candidate.get("interactive", False)
        if not isinstance(baseline, bool) or not isinstance(interactive, bool):
            raise ValueError(f"{identifier}: baseline and interactive must be true or false")
        if interactive and kind != "html":
            raise ValueError(f"{identifier}: interactive applies to html candidates only")
        if kind == "url":
            source = None
            url = local_url(text_field(candidate, "url"), identifier)
        else:
            source = (path.parent / text_field(candidate, "source")).resolve()
            if not source.is_relative_to(path.parent) or not source.is_file():
                raise ValueError(f"candidate source must be a readable file inside the manifest folder: {identifier}")
            inputs.add(source)
        colors = text_list(candidate, "palette")
        if any(not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", c) for c in colors):
            raise ValueError(f"{identifier}: palette needs hex colors")
        output.append({
            "id": identifier,
            **{name: text_field(candidate, name) for name in ("name", "concept", "typography")},
            "palette": colors, "traits": text_list(candidate, "traits"), "kind": kind,
            "content": url if kind == "url" else prepare_html(source, interactive, path.parent, inputs) if kind == "html" else prepare_image(source),
            "sourceLabel": url if kind == "url" else source.name,
            "baseline": baseline,
            "interactive": interactive,
        })
    if sum(c["baseline"] for c in output) > 1:
        raise ValueError("at most one candidate may be the baseline")
    # The current version always sits first so every direction is read against it.
    output.sort(key=lambda c: not c["baseline"])
    data["candidates"] = output
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    data["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return data, inputs


def build(manifest: Path, output: Path, *, force: bool = False) -> dict:
    manifest, output = manifest.resolve(), output.resolve()
    data, inputs = load_manifest(manifest)
    if output in inputs or output.is_relative_to(SKILL_ROOT):
        raise ValueError("the output cannot overwrite an input or be written into the skill installation directory")
    if output.exists() and not force:
        raise FileExistsError("output already exists; use a new path, or pass --force to update it")
    template = embed_local_files(TEMPLATE.read_text(encoding="utf-8"), TEMPLATE.parent, SKILL_ROOT, inputs)
    skill_file = SKILL_ROOT / "SKILL.md"
    skill = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else ""
    data["edition"] = "pro" if re.search(r"^name:\s*oil-ui-pro\s*$", skill, re.MULTILINE) else "open"
    if template.count(MARKER) != 1:
        raise ValueError("template data marker is missing or duplicated")
    if template.count(CONNECT_CSP) != 1:
        raise ValueError("template connect-src marker is missing or duplicated")
    origins = set()
    for candidate in data["candidates"]:
        if candidate["kind"] == "url":
            parts = urlsplit(candidate["content"])
            # Browsers reject IPv6 literals in CSP source lists; probe their loopback alias.
            host = "localhost" if parts.hostname == "::1" else parts.hostname.lower()
            port = f":{parts.port}" if parts.port is not None else ""
            origins.add(f"{parts.scheme}://{host}{port}")
    connect_csp = "connect-src " + (" ".join(sorted(origins)) if origins else "'none'")
    # A closing script tag in metadata or a nested candidate cannot escape the container.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    page = template.replace(CONNECT_CSP, connect_csp).replace(MARKER, payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    if force:
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as handle:
                temp = Path(handle.name)
                handle.write(page)
            temp.replace(output)
        finally:
            if temp and temp.exists():
                temp.unlink()
    else:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(page)
    if origins and "serve" not in data:
        print("Reminder: this round contains url candidates. Add a top-level serve entry to the manifest so the comparison page can be reopened later.", file=sys.stderr)
    return {"output": str(output), "candidates": len(data["candidates"]), "fingerprint": data["fingerprint"], "bytes": output.stat().st_size}


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Assemble local candidates and a manifest into a standalone style comparison HTML")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Explicitly allow an atomic update of an existing output")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.manifest, args.output, force=args.force), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Comparison page not generated: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
