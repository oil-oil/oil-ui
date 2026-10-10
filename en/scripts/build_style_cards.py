#!/usr/bin/env python3
"""Render a style-card config into static cards, then assemble them into a style comparison page.

Usage: python3 build_style_cards.py <cards.json> --out <output directory> [--force]

The config holds one shared set of real copy; each card only sets colors, fonts, radius, border,
shadow, density, and a layout sketch. For the fields, see references/design-direction.md,
section “Style cards”; for an example, see assets/style-cards/example.json.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
EXPLORER = SKILL / "scripts" / "build_explorer.py"

COLOR_ROLES = ("bg", "surface", "text", "muted", "accent", "accent_text", "line", "warn")
ROLE_NAMES = {"zh": {"bg": "底色", "surface": "表面", "text": "文字", "muted": "次要文字", "accent": "强调", "accent_text": "强调上的字",
                     "line": "线", "warn": "提醒"},
              "en": {"bg": "Background", "surface": "Surface", "text": "Text", "muted": "Muted", "accent": "Accent", "accent_text": "On accent",
                     "line": "Line", "warn": "Alert"}}
LAYOUTS = {"zh": {
    "sidebar-table": "侧栏加数据表",
    "topbar-cards": "顶栏加卡片网格",
    "queue-detail": "左列表右详情",
    "hero-center": "居中标题加产品实样",
    "hero-split": "左文字右画面",
    "editorial": "大字排版加分栏",
    "fullbleed": "满版画面压字",
}, "en": {
    "sidebar-table": "Sidebar and data table",
    "topbar-cards": "Top bar and card grid",
    "queue-detail": "Queue and detail pane",
    "hero-center": "Centered heading and product preview",
    "hero-split": "Text and visual side by side",
    "editorial": "Large type and columns",
    "fullbleed": "Full-bleed visual with text overlay",
}}
FONT_NAMES = {"zh": {"display": "标题", "body": "正文", "number": "数字"},
              "en": {"display": "Display", "body": "Body", "number": "Numbers"}}
DEFAULTS = {"zh": {"project": "风格卡片", "brief": "同一份内容，比较配色、字体、控件和版式气质", "round": "风格卡片"},
            "en": {"project": "Style cards", "brief": "Compare colors, typography, controls and layout using the same content", "round": "Style cards"}}
LABELS = {"zh": {"type": "字体与数字", "palette": "配色与用途", "controls": "控件", "layout": "版式示意", "style": "风格"},
          "en": {"type": "Type and numbers", "palette": "Colors", "controls": "Controls", "layout": "Layout sketch", "style": "Style"}}
DENSITY = {"compact": (12, 6, 12, 0.92), "regular": (18, 9, 16, 1.0), "airy": (26, 12, 20, 1.08)}
HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
FONT = re.compile(r"[\w \t\"',.-]+")


class ConfigError(ValueError):
    pass


def need(obj: dict, key: str, where: str, kind=str):
    if key not in obj:
        raise ConfigError(f"{where} is missing {key}")
    value = obj[key]
    if not isinstance(value, kind) or (kind is str and not value.strip()):
        expected = {str: "a non-empty string", dict: "an object", list: "a list"}[kind]
        raise ConfigError(f"{where}.{key} must be {expected}")
    return value


def text_list(obj: dict, key: str, where: str) -> None:
    value = obj.get(key, [])
    if not isinstance(value, list) or any(not isinstance(t, str) or not t.strip() for t in value):
        raise ConfigError(f"{where}.{key} must be a list of non-empty strings")


def load(path: Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from None
    if not isinstance(cfg, dict):
        raise ConfigError(f"the root of config {path} must be an object")
    lang = cfg.get("lang", "en")
    if lang not in ("zh", "en"):
        raise ConfigError('lang must be "zh" or "en"')
    for key, default in DEFAULTS[lang].items():
        cfg.setdefault(key, default)
        need(cfg, key, "config")
    content = need(cfg, "content", "config", dict)
    for key in ("title", "body", "number", "number_label", "primary", "secondary"):
        need(content, key, "content")
    for key in content:
        if key != "tags":
            need(content, key, "content")
    text_list(content, "tags", "content")
    cards = need(cfg, "cards", "config", list)
    if not 4 <= len(cards) <= 6:
        raise ConfigError("cards needs 4–6 entries")
    seen = set()
    for i, card in enumerate(cards, 1):
        where = f"card {i}"
        if not isinstance(card, dict):
            raise ConfigError(f"{where} must be an object")
        if "content" in card:
            raise ConfigError(f"{where}.content cannot be overridden; use the shared content")
        cid = need(card, "id", where)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", cid) or cid in seen:
            raise ConfigError(f"{where} has an invalid or duplicate id: {cid}")
        seen.add(cid)
        for key in ("name", "concept"):
            need(card, key, where)
        text_list(card, "traits", where)
        colors = need(card, "colors", where, dict)
        for role in COLOR_ROLES:
            value = need(colors, role, f"{where}.colors")
            if not HEX.fullmatch(value):
                raise ConfigError(f"{where}.colors.{role} must be a hex color: {value}")
        fonts = need(card, "fonts", where, dict)
        for role in ("display", "body", "number"):
            value = need(fonts, role, f"{where}.fonts")
            if not FONT.fullmatch(value):
                raise ConfigError(f"{where}.fonts.{role} must list font names only, no web fonts: {value}")
            for part in value.split(","):
                part = part.strip()
                if not part:
                    raise ConfigError(f"{where}.fonts.{role} must not contain empty font names")
                if part[0] in "\"'":
                    valid = len(part) > 2 and part[-1] == part[0] and part[0] not in part[1:-1] and part[1:-1].strip()
                else:
                    valid = not any(q in part for q in "\"'")
                if not valid:
                    raise ConfigError(f"{where}.fonts.{role} quotes must be balanced and names non-empty")
        for key, options, default in (("layout", LAYOUTS[lang], None), ("density", DENSITY, "regular"),
                                      ("border", ("none", "hairline", "solid"), "hairline"),
                                      ("shadow", ("none", "soft"), "none"), ("texture", ("none", "paper"), "none")):
            value = card.get(key, default)
            if not isinstance(value, str) or value not in options:
                raise ConfigError(f"{where}.{key} must be one of: {', '.join(options)}")
        radius = card.get("radius", 6)
        if type(radius) not in (int, float) or not 0 <= radius <= 28:
            raise ConfigError(f"{where}.radius must be a number from 0 to 28")
        for key, default in (("display_weight", 500), ("number_weight", 400)):
            weight = card.get(key, default)
            if type(weight) is not int or not 300 <= weight <= 900:
                raise ConfigError(f"{where}.{key} must be an integer from 300 to 900")
    return cfg


def first_font(stack: str) -> str:
    return stack.split(",")[0].strip().strip("\"'")


def sketch(layout: str) -> str:
    """Layout sketch: colored blocks only, arranged by preset."""
    b = lambda cls: f'<i class="{cls}"></i>'
    if layout == "sidebar-table":
        rows = "".join(b("rw") for _ in range(5))
        return f'<div class="sk sk-sidebar">{b("side")}<div class="main">{b("bar")}<div class="stats">{b("stat")*3}</div><div class="rows">{rows}</div></div></div>'
    if layout == "topbar-cards":
        return f'<div class="sk sk-topbar">{b("nav")}<div class="grid">{b("tile")*6}</div></div>'
    if layout == "queue-detail":
        items = b("item on") + "".join(b("item") for _ in range(4))
        return f'<div class="sk sk-queue"><div class="list">{items}</div><div class="detail">{b("head")}{b("line")*4}{b("cta")}</div></div>'
    if layout == "hero-center":
        return f'<div class="sk sk-center">{b("nav")}{b("h1")}{b("h2")}{b("cta")}<div class="shot">{b("line")*3}</div></div>'
    if layout == "hero-split":
        return f'<div class="sk sk-split">{b("nav")}<div class="cols"><div class="txt">{b("h1")}{b("h2")}{b("p")*2}{b("cta")}</div>{b("art")}</div></div>'
    if layout == "editorial":
        return f'<div class="sk sk-edit">{b("nav")}{b("mega")}{b("mega short")}<div class="cols3">{(b("p")*3)*3}</div></div>'
    return f'<div class="sk sk-full">{b("nav")}{b("h1")}{b("h2")}{b("cta")}</div>'


def card_html(cfg: dict, card: dict, index: int) -> str:
    lang = cfg.get("lang", "en")
    lab, roles = LABELS[lang], ROLE_NAMES[lang]
    c = cfg["content"]
    col, fonts = card["colors"], card["fonts"]
    gap, pad_y, pad_x, scale = DENSITY[card.get("density", "regular")]
    radius = card.get("radius", 6)
    border = {"none": "0 solid transparent", "hairline": f"1px solid {col['line']}", "solid": f"1.5px solid {col['text']}"}[card.get("border", "hairline")]
    shadow = "0 1px 2px rgba(0,0,0,.05), 0 10px 28px rgba(0,0,0,.07)" if card.get("shadow") == "soft" else "none"
    paper = ("background-image:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>"
             "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .05 0'/></filter>"
             "<rect width='100%' height='100%' filter='url(%23n)'/></svg>\");") if card.get("texture") == "paper" else ""
    esc = lambda s: html.escape(str(s))
    tags = c.get("tags") or []
    swatches = "".join(f'<div class="sw"><span style="background:{col[r]}"></span><b>{esc(roles[r])}</b><em>{col[r].upper()}</em></div>'
                       for r in ("bg", "surface", "text", "accent", "line", "warn"))
    font_rows = "".join(f"<li><b>{esc(n)}</b>{esc(first_font(fonts[k]))}</li>" for k, n in FONT_NAMES[lang].items())
    tag_html = "".join(f'<span class="tag{" warn" if i else ""}">{esc(t)}</span>' for i, t in enumerate(tags[:2]))
    input_html = f'<label class="field"><small>{esc(c.get("input_label", ""))}</small><span>{esc(c.get("input_value", ""))}</span></label>' if c.get("input_value") else ""
    traits = "".join(f"<span>{esc(t)}</span>" for t in card.get("traits", []))
    letter = chr(64 + index)
    return f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(card['name'])}</title><style>
:root{{--bg:{col['bg']};--surface:{col['surface']};--text:{col['text']};--muted:{col['muted']};--accent:{col['accent']};--on:{col['accent_text']};--line:{col['line']};--warn:{col['warn']};
--r:{radius}px;--border:{border};--shadow:{shadow};--gap:{gap}px;--py:{pad_y}px;--px:{pad_x}px;--display:{fonts['display']};--body:{fonts['body']};--num:{fonts['number']}}}
*{{box-sizing:border-box;margin:0}}
html,body{{height:100%}}
body{{background:var(--bg);{paper}color:var(--text);font:{round(15*scale)}px/1.6 var(--body);padding:44px 56px;display:flex;flex-direction:column;gap:calc(var(--gap)*1.6)}}
.top{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:14px}}
.brand{{font:{card.get('display_weight', 500)} 20px/1 var(--display)}}
.top small,.k{{font-size:12px;color:var(--muted);letter-spacing:.02em}}
.k{{display:block;margin-bottom:calc(var(--gap)*.7)}}
.row{{display:grid;grid-template-columns:1.15fr 1fr;gap:56px}}
h1{{font:{card.get('display_weight', 500)} {round(40*scale)}px/1.2 var(--display);letter-spacing:-.01em;text-wrap:balance}}
.body{{color:var(--muted);margin-top:8px;max-width:30em;text-wrap:pretty}}
.num{{font:{card.get('number_weight', 400)} {round(62*scale)}px/1.05 var(--num);font-variant-numeric:tabular-nums;margin-top:calc(var(--gap)*1.2)}}
.num+small{{color:var(--muted);font-size:13px}}
.sws{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}
.sw span{{display:block;aspect-ratio:1;border-radius:var(--r);border:1px solid rgba(0,0,0,.08)}}
.sw b{{display:block;font-weight:500;font-size:12px;margin-top:6px}}.sw em{{font-style:normal;font-size:11px;color:var(--muted);font-family:Menlo,monospace}}
.fonts{{list-style:none;padding:0;margin-top:calc(var(--gap)*1.1);font-size:13px;color:var(--muted)}}.fonts b{{display:inline-block;width:3.5em;color:var(--text);font-weight:500}}
.controls{{display:flex;align-items:center;gap:var(--gap);flex-wrap:wrap;border-top:1px solid var(--line);padding-top:calc(var(--gap)*1.2)}}
.btn{{font:500 14px/1 var(--body);padding:var(--py) var(--px);border-radius:var(--r);border:var(--border);background:var(--surface);color:var(--text);box-shadow:var(--shadow)}}
.btn.primary{{background:var(--accent);color:var(--on);border-color:var(--accent)}}
.tag{{font-size:12px;padding:3px 10px;border-radius:calc(var(--r) + 4px);background:color-mix(in srgb,var(--accent) 14%,var(--surface));color:var(--accent)}}
.tag.warn{{background:color-mix(in srgb,var(--warn) 14%,var(--surface));color:var(--warn)}}
.field{{margin-left:auto;display:flex;gap:10px;align-items:center;min-width:260px;padding:var(--py) 12px;border-radius:var(--r);border:var(--border);background:var(--surface);box-shadow:var(--shadow)}}
.field small{{color:var(--muted);font-size:12px}}
.bottom{{display:grid;grid-template-columns:1.15fr 1fr;gap:56px;border-top:1px solid var(--line);padding-top:calc(var(--gap)*1.2);flex:1}}
.frame{{height:230px;border-radius:var(--r);border:var(--border);background:var(--surface);box-shadow:var(--shadow);padding:14px;overflow:hidden}}
.sk{{height:100%;display:flex;flex-direction:column;gap:8px}} .sk i{{display:block;background:color-mix(in srgb,var(--text) 10%,transparent);border-radius:calc(var(--r)/2)}}
.sk .nav,.sk .bar{{height:10px;flex:none}} .sk .cta{{height:14px;width:22%;background:var(--accent);flex:none}}
.sk-sidebar{{flex-direction:row}} .sk-sidebar .side{{width:18%;background:color-mix(in srgb,var(--text) 82%,transparent)}} .sk-sidebar .main{{flex:1;display:flex;flex-direction:column;gap:8px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;height:40px}} .stats .stat:first-child{{background:color-mix(in srgb,var(--accent) 35%,transparent)}}
.rows{{display:flex;flex-direction:column;gap:6px;flex:1}} .rows .rw{{display:block;height:auto;flex:1;background:color-mix(in srgb,var(--text) 6%,transparent)}}
.sk-topbar .grid{{flex:1;display:grid;grid-template-columns:repeat(3,1fr);gap:8px}} .sk-topbar .tile:first-child{{background:color-mix(in srgb,var(--accent) 30%,transparent)}}
.sk-queue{{flex-direction:row}} .sk-queue .list{{width:38%;display:flex;flex-direction:column;gap:6px}} .sk-queue .item{{flex:1}} .sk-queue .item.on{{background:color-mix(in srgb,var(--accent) 35%,transparent)}}
.sk-queue .detail{{flex:1;display:flex;flex-direction:column;gap:8px}} .sk-queue .head{{height:22px}} .sk-queue .line{{height:8px}}
.sk-center{{align-items:center}} .sk-center .nav{{width:100%}} .sk-center .h1{{height:22px;width:60%}} .sk-center .h2{{height:10px;width:40%}} .sk-center .shot{{flex:1;width:78%;display:flex;flex-direction:column;gap:8px;padding:10px;background:color-mix(in srgb,var(--text) 6%,transparent)}} .sk-center .line{{height:8px}}
.sk-split .cols{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px}} .sk-split .txt{{display:flex;flex-direction:column;gap:8px;justify-content:center}} .sk-split .h1{{height:22px}} .sk-split .h2{{height:12px;width:70%}} .sk-split .p{{height:7px;width:85%}} .sk-split .art{{background:color-mix(in srgb,var(--accent) 30%,transparent)}}
.sk-edit .mega{{height:34px}} .sk-edit .mega.short{{width:62%}} .sk-edit .cols3{{flex:1;display:grid;grid-template-columns:repeat(3,1fr);gap:8px 14px;align-content:start}} .sk-edit .p{{height:7px}}
.sk-full{{background:color-mix(in srgb,var(--accent) 70%,var(--text));border-radius:calc(var(--r)/2);padding:14px;justify-content:center}} .sk-full i{{background:color-mix(in srgb,var(--on) 55%,transparent)}} .sk-full .nav{{margin-bottom:auto;opacity:.6}} .sk-full .h1{{height:24px;width:62%}} .sk-full .h2{{height:10px;width:40%}} .sk-full .cta{{background:var(--on);margin-bottom:auto}}
.style h2{{font:{card.get('display_weight', 500)} 24px/1.3 var(--display)}} .style p{{color:var(--muted);margin-top:6px}}
.traits{{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}} .traits span{{font-size:12px;padding:2px 9px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}}
</style></head><body>
<header class="top"><span class="brand">{esc(cfg.get('project', ''))}</span><small>{letter} · {esc(card['name'])}</small></header>
<section class="row"><div><span class="k">{lab['type']}</span><h1>{esc(c['title'])}</h1><p class="body">{esc(c['body'])}</p><div class="num">{esc(c['number'])}</div><small>{esc(c['number_label'])}</small></div>
<div><span class="k">{lab['palette']}</span><div class="sws">{swatches}</div><ul class="fonts">{font_rows}</ul></div></section>
<section class="controls"><span class="k" style="margin:0 8px 0 0">{lab['controls']}</span><button class="btn primary">{esc(c['primary'])}</button><button class="btn">{esc(c['secondary'])}</button>{tag_html}{input_html}</section>
<section class="bottom"><div><span class="k">{lab['layout']} · {esc(LAYOUTS[lang][card['layout']])}</span><div class="frame">{sketch(card['layout'])}</div></div>
<div class="style"><span class="k">{lab['style']}</span><h2>{esc(card['name'])}</h2><p>{esc(card['concept'])}</p><div class="traits">{traits}</div></div></section>
</body></html>
"""


def build(cfg_path: Path, out: Path, force: bool) -> dict:
    cfg_path, out = cfg_path.resolve(), out.resolve()
    cfg = load(cfg_path)
    if out.is_relative_to(SKILL):
        raise ConfigError(f"the output directory cannot be inside the skill installation directory: {out}")
    if out.exists() and not out.is_dir():
        raise ConfigError(f"the output path must be a directory, but it is a file: {out}")
    page = out / "style-explorer.html"
    if page.exists() and not force:
        raise ConfigError(f"comparison page already exists: {page}; pass --force to overwrite it")
    names = [f"card-{c['id']}.html" for c in cfg["cards"]] + ["manifest.json", page.name]
    if cfg_path.parent == out and cfg_path.name in names:
        raise ConfigError(f"the config file would be overwritten by the output; rename it: {cfg_path}")
    for name in names:
        target = out / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ConfigError(f"an output file path cannot be a directory or a symlink: {target}")

    lang = cfg.get("lang", "en")
    candidates = []
    for i, card in enumerate(cfg["cards"], 1):
        name = f"card-{card['id']}.html"
        f = card["fonts"]
        candidates.append({
            "id": card["id"], "name": card["name"], "concept": card["concept"],
            "typography": " · ".join(f"{label} {first_font(f[role])}" for role, label in FONT_NAMES[lang].items()),
            "palette": [card["colors"][r] for r in ("bg", "text", "accent", "warn")],
            "traits": card.get("traits") or [LAYOUTS[lang][card["layout"]]], "kind": "html", "source": name,
        })
    manifest = {"schemaVersion": 1, "lang": lang, "project": cfg["project"],
                "brief": cfg["brief"], "round": cfg["round"],
                "candidates": candidates}

    out.mkdir(parents=True, exist_ok=True)
    # Build the whole set in a temp dir first and swap files in only on success, so a failure leaves the output untouched.
    with tempfile.TemporaryDirectory(prefix=".oil-style-cards-", dir=out) as tmp:
        stage = Path(tmp)
        for i, (card, cand) in enumerate(zip(cfg["cards"], candidates), 1):
            (stage / cand["source"]).write_text(card_html(cfg, card, i), encoding="utf-8")
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        cmd = [sys.executable, str(EXPLORER), str(stage / "manifest.json"), "--output", str(stage / page.name)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            details = [f"comparison page build failed (exit code {result.returncode})"]
            for label, stream in (("stdout", result.stdout), ("stderr", result.stderr)):
                if stream.strip():
                    details.append(f"{label}: {stream.strip()}")
            raise ConfigError("\n".join(details))
        for name in names:
            (stage / name).replace(out / name)
    return {"output": str(page), "cards": len(cfg["cards"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a style-card config into static cards and assemble a comparison page")
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Output directory for the cards, manifest.json, and style-explorer.html")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing comparison page")
    args = parser.parse_args()
    try:
        result = build(args.config, args.out, args.force)
    except (ConfigError, OSError) as exc:
        print(f"build_style_cards：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
