#!/usr/bin/env python3
"""Build a portable, offline design comparison from a local manifest."""

from __future__ import annotations

import argparse
import base64
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import shlex
import sys
import tempfile
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "assets" / "style-explorer.html"
MARKER = "/*__OIL_UI_DATA__*/ null"
CONNECT_CSP = "connect-src 'none'"
PREVIEW_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "font-src data:; media-src data:; script-src 'none'; "
    "form-action 'none'; base-uri 'none'; object-src 'none'"
)
MAX_RESOURCE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_RESOURCE_BYTES = 100 * 1024 * 1024


class ManifestError(ValueError):
    """Every problem found in one pass, so the manifest can be fixed in one edit."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        if len(problems) == 1:
            super().__init__(problems[0])
        else:
            super().__init__(f"manifest 有 {len(problems)} 处要改：\n" + "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1)))


def text_field(obj: dict, name: str, *, default: str | None = None, where: str = "") -> str:
    value = obj.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}{name} 必须是非空字符串")
    return value.strip()


def text_list(obj: dict, name: str, *, where: str = "") -> list[str]:
    values = obj.get(name)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{where}{name} 必须是非空字符串数组")
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f"{where}{name} 的每项必须是非空字符串")
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
            raise ValueError("候选 HTML 不支持嵌套文档；请提供静态内容或截图")
        if tag == "style":
            self.in_style = True
        if attrs.get("style"):
            self.styles.append(attrs["style"])
        if tag == "base":
            raise ValueError("候选 HTML 不应包含 base；资源需要内嵌")
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            raise ValueError("候选 HTML 不应自动跳转")
        for key in ("src", "poster", "data", "href", "xlink:href"):
            value = attrs.get(key, "") or ""
            if not value or value.lower().startswith(("#", "data:")):
                continue
            raise ValueError(f"候选 HTML 含未内嵌资源 {tag}.{key}: {value}")
        if attrs.get("srcset"):
            raise ValueError("候选 HTML 请用内嵌 src 代替 srcset")

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
            raise ValueError(f"{label}: CSS 含未内嵌资源")

    for index, (kind, value) in enumerate(tokens):
        if value == "@" and index + 1 < len(tokens) and tokens[index + 1][0] == "ident" and css_unescape(tokens[index + 1][1]).lower() == "import":
            raise ValueError(f"{label}: 请内嵌 CSS，不使用 @import")
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


def read_asset(path: Path, used: set[Path]) -> bytes:
    """Bound input size before reading; keep every dependency protected from output overwrites."""
    size = path.stat().st_size
    if size > MAX_RESOURCE_BYTES:
        raise ValueError(f"本地资源 {path} 为 {size} 字节，超过单文件上限 {MAX_RESOURCE_BYTES} 字节；"
                         f"请压缩或裁剪此文件至 {MAX_RESOURCE_BYTES} 字节以内，保留原路径后重新运行")
    total = sum(p.stat().st_size for p in used | {path})
    if total > MAX_TOTAL_RESOURCE_BYTES:
        raise ValueError(f"内嵌资源累计 {total} 字节，超过总上限 {MAX_TOTAL_RESOURCE_BYTES} 字节；"
                         f"请压缩候选引用的图片、字体或视频，使输入文件总量不超过 {MAX_TOTAL_RESOURCE_BYTES} 字节后重新运行")
    used.add(path)
    return path.read_bytes()


def read_text_asset(path: Path, used: set[Path]) -> str:
    # Match Path.read_text's universal newline handling used by earlier versions.
    return read_asset(path, used).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def resource_parts(ref: str):
    path = Path(ref)
    if path.drive and path.is_absolute():
        ref = path.as_uri()
    return urlsplit(ref)


def local_file(ref: str, base: Path, root: Path) -> Path | None:
    """Resolve files anywhere on disk; root is retained for compatibility with existing callers."""
    ref = ref.strip()
    if not ref or ref.startswith("#") or ref.lower().startswith("data:"):
        return None
    try:
        parts = resource_parts(ref)
    except ValueError:
        raise ValueError(f"资源地址无效：{ref}；请把引用替换为已有文件的绝对路径后重新生成") from None
    if (parts.scheme and parts.scheme.lower() != "file") or parts.netloc not in ("", "localhost") or ref.startswith("//"):
        destination = base / (Path(unquote(parts.path)).name or "resource.bin")
        command = f"curl -L --fail --output {shlex.quote(str(destination))} -- {shlex.quote(ref)}"
        raise ValueError(f"远程资源 {ref} 不能离线使用；先运行 `{command}`，"
                         f"再把引用 {json.dumps(ref, ensure_ascii=False)} 替换为 {json.dumps(str(destination), ensure_ascii=False)} 后重新生成")
    # A file URL's /C:/... is not a Windows filesystem path. Decode it with
    # the platform converter, which also handles percent-escaped filenames.
    target = (base / url2pathname(parts.path)).resolve()
    if not target.is_file():
        raise ValueError(f"找不到本地资源 {ref}（解析为 {target}）；"
                         f"请将该文件保存到 {json.dumps(str(target), ensure_ascii=False)}，或把引用替换为已有文件的绝对路径后重新生成")
    return target


def resource_url(ref: str, base: Path, root: Path, used: set[Path]) -> str:
    target = local_file(ref, base, root)
    if target is None:
        return ref
    mime = EMBEDDABLE.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    fragment = resource_parts(ref).fragment
    return f"data:{mime};base64," + base64.b64encode(read_asset(target, used)).decode("ascii") + ("#" + fragment if fragment else "")


def apply_edits(content: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, replacement in sorted(edits, reverse=True):
        content = content[:start] + replacement + content[end:]
    return content


def embed_css(css: str, base: Path, root: Path, used: set[Path], stack: tuple[Path, ...] = ()) -> str:
    """Rewrite actual CSS tokens only, including escaped url names and nested local imports."""
    tokens = [m for m in CSS_TOKEN.finditer(css) if m.lastgroup not in ("comment", "space")]
    edits = []

    def closing(index):
        depth = 0
        for end in range(index, len(tokens)):
            if tokens[end].lastgroup == "symbol":
                if tokens[end].group() == "(":
                    depth += 1
                elif tokens[end].group() == ")":
                    depth -= 1
                    if depth == 0:
                        return end
        return len(tokens) - 1

    def value(start, end):
        raw = "".join(m.group() for m in CSS_TOKEN.finditer(css[start:end]) if m.lastgroup != "comment").strip()
        if raw[:1] in ("'", '"') and raw[-1:] == raw[:1]:
            raw = raw[1:-1]
        return css_unescape(raw)

    i = 0
    while i < len(tokens):
        token = tokens[i]
        name = css_unescape(token.group()).lower() if token.lastgroup == "ident" else ""
        if token.group() == "@" and i + 2 < len(tokens) and css_unescape(tokens[i + 1].group()).lower() == "import":
            first = i + 2
            last = first
            if tokens[first].lastgroup == "string":
                ref = value(tokens[first].start(), tokens[first].end())
            elif css_unescape(tokens[first].group()).lower() == "url" and first + 1 < len(tokens) and tokens[first + 1].group() == "(":
                last = closing(first + 1)
                ref = value(tokens[first + 1].end(), tokens[last].start())
            else:
                raise ValueError('CSS @import 无法解析；请改为 @import "已有文件的绝对路径.css";')
            end = last + 1
            while end < len(tokens) and tokens[end].group() != ";":
                if tokens[end].group() == "(":
                    end = closing(end)
                end += 1
            condition = css[tokens[last].end():tokens[end].start() if end < len(tokens) else len(css)].strip()
            target = local_file(ref, base, root)
            if target is None:
                # Embedded imports have no local base; decode and check them as well.
                if not ref.lower().startswith("data:text/css"):
                    raise ValueError('CSS @import 请使用本地 CSS 文件，例如 @import "./style.css";')
                header, payload = ref.split(",", 1)
                imported = (base64.b64decode(payload).decode("utf-8") if ";base64" in header.lower() else unquote(payload))
                imported = embed_css(imported, base, root, used, stack)
            elif target in stack:
                imported = ""  # Browsers ignore cyclic imports too.
            else:
                imported = embed_css(read_text_asset(target, used), target.parent, root, used, stack + (target,))
            # Preserve import layer/supports/media conditions when moving the CSS inline.
            wrappers = []
            for keyword in ("layer", "supports"):
                match = re.match(r"^" + keyword + r"\b", condition, re.I)
                if not match:
                    continue
                rest = condition[match.end():].lstrip()
                argument = ""
                if rest.startswith("("):
                    depth = 0
                    for pos, char in enumerate(rest):
                        depth += (char == "(") - (char == ")")
                        if depth == 0:
                            argument, rest = rest[1:pos], rest[pos + 1:].lstrip()
                            break
                wrappers.append("@layer " + argument if keyword == "layer" else "@supports (" + argument + ")")
                condition = rest
            if condition:
                wrappers.append("@media " + condition)
            for wrapper in reversed(wrappers):
                imported = wrapper + "{" + imported + "}"
            edits.append((token.start(), tokens[end].end() if end < len(tokens) else len(css), imported))
            i = end + 1
            continue
        if name in ("url", "image-set", "-webkit-image-set", "image", "src") and i + 1 < len(tokens) and tokens[i + 1].group() == "(":
            end = closing(i + 1)
            if name == "url":
                ref = value(tokens[i + 1].end(), tokens[end].start())
                url = resource_url(ref, base, root, used)
                if url != ref:
                    edits.append((token.start(), tokens[end].end(), 'url("' + url + '")'))
                i = end + 1
                continue
            depth = 0
            for inner in tokens[i + 2:end]:
                if inner.lastgroup == "symbol":
                    depth += (inner.group() == "(") - (inner.group() == ")")
                if depth == 0 and inner.lastgroup == "string":
                    ref = value(inner.start(), inner.end())
                    url = resource_url(ref, base, root, used)
                    if url != ref:
                        edits.append((inner.start(), inner.end(), '"' + url + '"'))
        i += 1
    return apply_edits(css, edits)


def widest_candidate(srcset: str) -> str | None:
    """Largest "url 1200w" / "url 2x" entry of a srcset; an entry without a descriptor counts as 1x.

    Parsed as the HTML spec does: a URL runs to the next whitespace, so data URLs keep their commas.
    """
    best, best_size, i, n = None, -1.0, 0, len(srcset)
    while i < n:
        while i < n and (srcset[i].isspace() or srcset[i] == ","):
            i += 1
        start = i
        while i < n and not srcset[i].isspace():
            i += 1
        url, descriptor = srcset[start:i], ""
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            start = i
            while i < n and srcset[i] != ",":
                i += 1
            descriptor = srcset[start:i].strip()
        try:
            size = float(descriptor[:-1]) if descriptor[-1:] in ("w", "x") else 1.0
        except ValueError:
            size = 1.0
        if url and size > best_size:
            best, best_size = url, size
    return best


HTML_ATTR = re.compile(r"""(?P<lead>\s+(?P<name>[^\s=/>]+)\s*=\s*)(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))""")


class LocalAssets(HTMLParser):
    """Edit only real tags and styles, preserving comments, text and inline script bodies."""

    def __init__(self, content: str, base: Path, root: Path, used: set[Path], interactive: bool, *, shell: bool = False):
        super().__init__(convert_charrefs=False)
        self.content, self.base, self.root, self.used = content, base, root, used
        self.interactive = interactive
        self.shell = shell
        self.lines = content.split("\n")
        self.edits = []
        self.in_style = False
        self.script = None
        self.deferred = []

    def char_index(self):
        line, col = self.getpos()
        return sum(len(part) + 1 for part in self.lines[:line - 1]) + col

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        raw = self.get_starttag_text()
        start = self.char_index()
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").lower().split() and attrs.get("href"):
            target = local_file(attrs["href"], self.base, self.root)
            if target is not None:
                css = embed_css(read_text_asset(target, self.used), target.parent, self.root, self.used, (target,))
                if attrs.get("media"):
                    css = "@media " + attrs["media"] + "{" + css + "}"
                self.edits.append((start, start + len(raw), "<style>" + re.sub(r"</style", r"<\\/style", css, flags=re.I) + "</style>"))
                return
        if tag == "script" and attrs.get("src"):
            target = local_file(attrs["src"], self.base, self.root)
            if target is not None:
                if self.interactive:
                    code = read_text_asset(target, self.used)
                else:
                    read_asset(target, self.used)
                    code = ""
                code = re.sub(r"</script", r"<\\/script", code, flags=re.I)
                module = (attrs.get("type") or "").lower() == "module"
                replacement = (('<script type="module">' if module else "<script>") + code + "</script>") if self.interactive else ""
                if "defer" in attrs and not module:
                    # Inline scripts ignore defer; keep their original execution after the DOM.
                    self.deferred.append(replacement)
                    replacement = ""
                self.script = (start, replacement)
                return
        if tag == "style":
            self.in_style = True

        def attribute(match):
            name = match["name"].lower()
            if self.shell and tag == "a" and name == "href":
                return match.group()  # Template navigation is not an offline resource dependency.
            ref = unescape(next(match[group] for group in ("double", "single", "bare") if match[group] is not None))
            has_src = bool((attrs.get("src") or "").strip())
            if name == "src" and tag == "img" and not has_src and widest_candidate(attrs.get("srcset") or ""):
                return ""  # An empty src gives way to the srcset candidate below, so the tag keeps one src.
            if name == "srcset" and tag == "img":
                # The page shows one fixed size, so one file is enough: keep src, or take the widest candidate.
                if has_src or not widest_candidate(ref):
                    return ""
                return match["lead"].replace(match["name"], "src") + '"' + escape(resource_url(widest_candidate(ref), self.base, self.root, self.used), quote=True) + '"'
            if name == "style":
                result = embed_css(ref, self.base, self.root, self.used)
            elif name in ("src", "poster", "data", "href", "xlink:href"):
                result = resource_url(ref, self.base, self.root, self.used)
            else:
                return match.group()
            return match.group() if result == ref else match["lead"] + '"' + escape(result, quote=True) + '"'

        replacement = HTML_ATTR.sub(attribute, raw)
        if replacement != raw:
            self.edits.append((start, start + len(raw), replacement))

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        if tag == "script" and self.script is not None:
            start, replacement = self.script
            end = self.content.find(">", self.char_index()) + 1
            self.edits.append((start, end, replacement))
            self.script = None

    def handle_data(self, data):
        if self.in_style:
            replacement = embed_css(data, self.base, self.root, self.used)
            if replacement != data:
                self.edits.append((self.char_index(), self.char_index() + len(data), replacement))

    def result(self):
        self.feed(self.content)
        self.close()
        if self.script is not None:
            start, replacement = self.script
            self.edits.append((start, len(self.content), replacement))
        content = apply_edits(self.content, self.edits)
        if self.deferred:
            close = content.lower().rfind("</body>")
            close = len(content) if close < 0 else close
            content = content[:close] + "".join(self.deferred) + content[close:]
        return content


def embed_local_files(content: str, base: Path, root: Path, used: set[Path]) -> str:
    return LocalAssets(content, base, root, used, False, shell=True).result()


def ensure_head(content: str) -> str:
    class Structure(HTMLParser):
        def __init__(self):
            super().__init__()
            self.head = self.html = self.body = self.html_end = self.declaration = None
            self.head_closed = False

        def char_index(self):
            line, col = self.getpos()
            return sum(len(part) + 1 for part in content.split("\n")[:line - 1]) + col

        def handle_starttag(self, tag, attrs):
            if tag == "head" and self.head is None:
                self.head = self.char_index() + len(self.get_starttag_text())
            if tag == "html" and self.html is None:
                self.html = self.char_index() + len(self.get_starttag_text())
            if tag == "body" and self.body is None:
                self.body = self.char_index()

        def handle_endtag(self, tag):
            if tag == "head":
                self.head_closed = True
            if tag == "html":
                self.html_end = self.char_index()

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag != "head":  # HTML does not allow a self-closing head.
                self.handle_endtag(tag)

        def handle_decl(self, decl):
            self.declaration = self.char_index() + len(decl) + 3

    parser = Structure()
    parser.feed(content)
    if parser.head is None:
        at = parser.html if parser.html is not None else parser.declaration or 0
        return content[:at] + "<head></head>" + content[at:]
    if not parser.head_closed:
        at = next((pos for pos in (parser.body, parser.html_end) if pos is not None and pos >= parser.head), len(content))
        return content[:at] + "</head>" + content[at:]
    return content


def prepare_html(path: Path, interactive: bool = False, root: Path | None = None, used: set[Path] | None = None) -> str:
    path = path.resolve()
    used = used if used is not None else set()
    content = read_text_asset(path, used)
    content = ensure_head(content)
    content = LocalAssets(content, path.parent, root or path.parent, used, interactive).result()
    parser = AssetCheck()
    parser.feed(content)
    for style in parser.styles:
        check_css(style, path.name)
    (line, column), start_tag = parser.head_position
    head_end = sum(len(part) + 1 for part in content.split('\n')[:line - 1]) + column + len(start_tag)
    meta = f'<meta http-equiv="Content-Security-Policy" content="{preview_csp(interactive)}">'
    return content[:head_end] + meta + (STORAGE_SHIM if interactive else "") + content[head_end:]


def prepare_image(path: Path, used: set[Path] | None = None) -> str:
    data = read_asset(path, used if used is not None else set())
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError(f"{path.name}: 静态预览支持 PNG、JPEG 和 WebP")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def local_url(value: str, label: str) -> str:
    """Live candidates only point at a dev server on this machine."""
    try:
        parts = urlsplit(value)
        parts.port  # Reject malformed ports before generating CSP origins.
    except ValueError:
        raise ValueError(f"{label}必须是有效的本机 http(s) 地址，收到的是 {value}") from None
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in LOOPBACK or parts.username or parts.password:
        raise ValueError(f"{label}只能是本机开发服务器地址，例如 http://localhost:5173/orders；收到的是 {value}")
    return value


HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_])")


def palette(value, where: str) -> list[str]:
    colors = HEX_COLOR.findall(json.dumps(value, ensure_ascii=False))
    if not colors:
        raise ValueError(f'{where}palette 没有可用的十六进制颜色，收到的是 {json.dumps(value, ensure_ascii=False)}；'
                         '请改为 "palette": ["#1a2b3c", "#ffffff"]')
    return colors


def native_viewport(value, where: str) -> dict:
    """Normalize a fixed canvas without changing manifests that omit it."""
    dimensions = None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", value)
        if match:
            dimensions = [int(part) for part in match.groups()]
    elif isinstance(value, dict):
        dimensions = [value.get("width"), value.get("height")]
    if dimensions and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                          and 0 < n <= 2**53 - 1 and n == int(n) for n in dimensions):
        return dict(zip(("width", "height"), map(int, dimensions)))
    raise ValueError(f'{where}nativeViewport 必须是正整数宽高；收到的是 {json.dumps(value, ensure_ascii=False)}；'
                     '例如 "1920x1080"、"1920×1080" 或 {"width":1920,"height":1080}')


def read_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"找不到 manifest：{path}。先在任务目录里写好 manifest.json，字段见 references/style-explorer.md 的“准备输入”")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest 不是合法的 JSON：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}") from None
    if not isinstance(raw, dict):
        raise ValueError("manifest 的最外层必须是一个对象，里面有 schemaVersion、project、brief 和 candidates")
    return raw


def load_manifest(path: Path) -> tuple[dict, set[Path]]:
    raw = read_manifest(path)
    problems: list[str] = []

    def attempt(check):
        """Run one check; keep its message and carry on so the rest still gets checked."""
        try:
            return check()
        except ValueError as exc:
            problems.append(str(exc))
            return None

    if raw.get("schemaVersion") != 1:
        problems.append("manifest.schemaVersion 必须为 1")
    data = {"schemaVersion": 1}
    for name, default in (("project", None), ("brief", None), ("round", "01")):
        data[name] = attempt(lambda: text_field(raw, name, default=default, where="manifest."))
    if "lang" in raw:
        if raw["lang"] not in ("zh", "en"):
            problems.append('manifest.lang 只能是 "zh" 或 "en"')
        data["lang"] = raw["lang"]
    if "serve" in raw:
        serve = raw["serve"]
        if not isinstance(serve, dict):
            problems.append("serve 必须是对象，例如 {\"command\": \"pnpm dev\", \"cwd\": \"/项目的绝对路径\", \"url\": \"http://localhost:3000\"}")
        else:
            if not isinstance(serve.get("command"), str) or not serve["command"].strip():
                problems.append("serve.command 必须是非空字符串")
            if "cwd" in serve and (not isinstance(serve["cwd"], str) or not Path(serve["cwd"]).is_absolute()):
                problems.append("serve.cwd 必须是绝对路径")
            if "url" in serve:
                if not isinstance(serve["url"], str) or not serve["url"].strip():
                    problems.append("serve.url 必须是非空的本机 http(s) 地址")
                else:
                    attempt(lambda: local_url(serve["url"], "serve.url "))
        data["serve"] = serve
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        problems.append("candidates 至少需要一个候选")
        candidates = []
    seen = set()
    inputs = {path, TEMPLATE.resolve()}
    output = []
    viewport = None
    if "nativeViewport" in raw:
        affected = "、".join(str(c.get("id", i)) for i, c in enumerate(candidates, 1)
                            if isinstance(c, dict) and "nativeViewport" not in c)
        where = f"manifest（用于候选 {affected}）：" if affected else "manifest."
        viewport = attempt(lambda: native_viewport(raw["nativeViewport"], where))
    for index, candidate in enumerate(candidates, 1):
        if not isinstance(candidate, dict):
            problems.append(f"第 {index} 个候选必须是对象")
            continue
        before = len(problems)
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            problems.append(f"第 {index} 个候选缺少 id")
            identifier = None
        else:
            identifier = identifier.strip()
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier):
                problems.append(f'候选 id "{identifier}" 无效：只用小写字母、数字、连字符和下划线，以字母或数字开头，例如 "a" 或 "dir-2"')
            elif identifier in seen:
                problems.append(f'候选 id "{identifier}" 重复了，每个候选要用不同的 id')
            seen.add(identifier)
        where = f"候选 {identifier}：" if identifier else f"第 {index} 个候选："
        candidate_viewport = (attempt(lambda: native_viewport(candidate["nativeViewport"], where))
                              if "nativeViewport" in candidate else viewport)
        kind = candidate.get("kind", "html")
        if kind not in ("html", "image", "url"):
            problems.append(f'{where}kind 只能是 "html"、"image" 或 "url"，收到的是 {json.dumps(kind, ensure_ascii=False)}')
            kind = None
        baseline = candidate.get("baseline", False)
        interactive = candidate.get("interactive", False)
        if not isinstance(baseline, bool) or not isinstance(interactive, bool):
            problems.append(f"{where}baseline 和 interactive 必须是 true 或 false")
        elif interactive and kind not in ("html", None):
            problems.append(f"{where}interactive 只用于 html 候选")
        source = url = None
        if kind == "url":
            url = attempt(lambda: local_url(text_field(candidate, "url", where=where), f"{where}url "))
        elif kind:
            name = attempt(lambda: text_field(candidate, "source", where=where))
            if name:
                def source_file():
                    try:
                        # source is a filesystem path, so literal #, ? and % retain their old meaning.
                        direct = (path.parent / name).resolve()
                        if direct.is_file():
                            return direct
                        target = local_file(name, path.parent, path.parent)
                        if target is None:
                            raise ValueError('请指向本地文件，例如 "source": "./a.html"')
                        return target
                    except ValueError as exc:
                        raise ValueError(f"{where}source {exc}") from None
                source = attempt(source_file)
                if source:
                    inputs.add(source)
        colors = attempt(lambda: palette(candidate.get("palette"), where))
        texts = {name: attempt(lambda: text_field(candidate, name, where=where)) for name in ("name", "concept", "typography")}
        traits = attempt(lambda: text_list(candidate, "traits", where=where))
        if len(problems) > before:
            continue
        try:
            content = url if kind == "url" else prepare_html(source, interactive, path.parent, inputs) if kind == "html" else prepare_image(source, inputs)
        except ValueError as exc:
            message = str(exc)
            if message.startswith(f"{source.name}: "):
                message = message[len(source.name) + 2:]
            problems.append(f"{where}{source.name} {message}" if source else f"{where}{message}")
            continue
        output.append({
            "id": identifier, **texts,
            "palette": colors, "traits": traits, "kind": kind,
            "content": content,
            "sourceLabel": url if kind == "url" else source.name,
            "baseline": baseline,
            "interactive": interactive,
            **({"nativeViewport": candidate_viewport} if candidate_viewport else {}),
        })
    if sum(c["baseline"] for c in output) > 1:
        problems.append("最多只能有一个基线候选（baseline: true）")
    if problems:
        raise ManifestError(problems)
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
        raise ValueError("输出不能覆盖输入或写进 Skill 安装目录")
    if output.exists() and not force:
        raise FileExistsError(f"输出已存在：{output}。要更新它就加 --force，要保留它就用 --output 换一个路径")
    template = embed_local_files(TEMPLATE.read_text(encoding="utf-8"), TEMPLATE.parent, SKILL_ROOT, inputs)
    skill_file = SKILL_ROOT / "SKILL.md"
    skill = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else ""
    data["edition"] = "pro" if re.search(r"^name:\s*oil-ui-pro\s*$", skill, re.MULTILINE) else "open"
    if template.count(MARKER) != 1:
        raise ValueError("模板数据入口缺失或重复")
    if template.count(CONNECT_CSP) != 1:
        raise ValueError("模板连接策略入口缺失或重复")
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
        print("提醒：本轮包含 url 候选，建议在 manifest 顶层补上 serve 启动方式，方便重新打开对比页。", file=sys.stderr)
    return {"output": str(output), "candidates": len(data["candidates"]), "fingerprint": data["fingerprint"], "bytes": output.stat().st_size}


HELP_EPILOG = """\
用法示例：
  python3 build_explorer.py <manifest 所在目录>/manifest.json
      生成 <manifest 所在目录>/style-explorer.html；已有同名文件时加 --force 覆盖，
      或用 --output 换一个文件名。

manifest.json 最少要有：
  {"schemaVersion": 1, "project": "<项目名>", "brief": "<所有候选共同的内容与任务>",
   "candidates": [{"id": "a", "name": "<方向名>", "concept": "<一句体验意图>",
     "typography": "<实际使用的字体关系>", "palette": ["#112233", "#f5f5f5"],
     "traits": ["<看得见的特征>"], "source": "a.html"}]}

可选字段：
  lang              顶层。"zh" 或 "en"，只决定对比页外壳的语言；省略时按浏览器语言。
  round             顶层。轮次，例如 "01"，会出现在用户复制的选择里。
  nativeViewport    固定画布的原生视口。写在顶层对所有候选生效，写在候选里只对它生效。
                    认 "1920x1080"、"1920×1080" 和 {"width": 1920, "height": 1080}。
                    省略时用默认视口：桌面 1280×900，手机 390×844。
  kind              候选。"html"（默认）、"image"（source 指向 PNG、JPEG 或 WebP），
                    或 "url"（用 url 字段代替 source，指向本机开发服务器上的页面，
                    只认 localhost、127.0.0.1 和 ::1）。
  serve             顶层。有 url 候选时写下启动方式：
                    {"command": "<启动命令>", "cwd": "<项目的绝对路径>", "url": "<服务地址>"}
  interactive       候选。true 表示可操作的小样：单个 HTML，脚本内联。它不能联网，
                    也不能加载外部文件；浏览器存储在页面关闭后清空；alert、confirm
                    这类系统弹窗不会出现，需要确认时用页面内的对话框。
  baseline          候选。true 表示现状，排在第一位，编号显示为“现状”，每轮最多一个。

候选文件的要求：
  source 按 manifest 所在目录解析；图片、字体、视频、CSS 和脚本按引用它的文件
  所在目录解析，也支持绝对路径和目录外的本地文件，生成器会自动内嵌。
  单文件上限 20 MiB，输入文件总量上限 100 MiB；不引用网络资源。
  HTML 缺少 head 时自动补上；不运行脚本也要显示出内容
  （interactive 和 url 候选除外）。
  img 的 srcset 只取一张：有 src 用 src，否则取最宽的那张。不认 iframe、object、embed 和 <picture><source>：
  改成一张用相对路径引用的 <img>，或者直接用截图做图片候选。
  id 用小写字母、数字、连字符或下划线，不重复；palette 推荐用十六进制色值数组，
  也能从描述文字中提取颜色，一个有效色值都没有时才报错。

需要 Python 3.10 或更新版本。产物不能写进 Skill 目录。Skill 更新以后，
已经生成的对比页不会跟着变，用原来的 manifest 加 --force 重新生成。
写错时会把 manifest 里所有要改的地方一次列出来，旧的对比页不会被改动。
成功时在标准输出打印一行 JSON：output、candidates、fingerprint、bytes。"""


def utf8_output() -> None:
    """管道另一头的 Agent 按 UTF-8 读；控制台的代码页可能连中文都没有。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    utf8_output()
    if sys.version_info < (3, 10):
        print("需要 Python 3.10 或更新版本", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="把 manifest 里列出的候选页面组装成一个可以离线打开的风格对比页",
                                     epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="manifest.json 的路径，source 的相对路径以此文件所在目录为准")
    parser.add_argument("--output", type=Path, help="输出的 HTML 路径；不写时是 manifest 旁边的 style-explorer.html")
    parser.add_argument("--force", action="store_true", help="输出文件已经存在时覆盖它")
    args = parser.parse_args(argv)
    output = args.output or args.manifest.resolve().parent / "style-explorer.html"
    try:
        print(json.dumps(build(args.manifest, output, force=args.force), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"未生成对比页：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
