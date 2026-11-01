#!/usr/bin/env python3
"""采样 UI 设计参考图的真实色板、版式比例与局部图像资产；支持 JSON 清单或命令行直接采样。"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from statistics import median


def utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageFilter
except ImportError:
    Image = None
    ImageFilter = None

HELP_EXAMPLES = """常用命令：
  # 1) 命令行直接采样色值与版式比例（无需手写 JSON 清单）
  python3 <skill>/scripts/measure_reference.py design.png \\
    --color bg=40,20,80,30 --color cta=1180,920,160,40 \\
    --box col1=48,176,464,696 --css-width 1440

  # 2) 从生成的 UI 设计图中裁切局部插画/纹理资产（可选纯白或色度键去底）
  python3 <skill>/scripts/measure_reference.py design.png \\
    --extract oil_frame=548,348,440,428 --out-dir assets/extracted

  # 3) 使用 manifest.json 批量测量并生成带标注框的 annotations.svg
  python3 <skill>/scripts/measure_reference.py --manifest manifest.json --out-dir measured/
"""


class SimpleRGBAImage:
    """无 Pillow 环境下的纯标准库 8-bit PNG 读写回退。"""

    def __init__(self, width: int, height: int, pixels: list[tuple[int, int, int, int]]):
        self.width = width
        self.height = height
        self.size = (width, height)
        self._pixels = pixels

    @classmethod
    def open_bytes(cls, data: bytes) -> "SimpleRGBAImage":
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("当前环境未安装 Pillow，仅支持读取 PNG；请提供 PNG 或安装 Pillow")
        pos = 8
        width = height = bit_depth = color_type = interlace = None
        idat = bytearray()
        palette: list[tuple[int, int, int]] = []
        trns = b""
        while pos + 8 <= len(data):
            length = struct.unpack(">I", data[pos : pos + 4])[0]
            chunk_type = data[pos + 4 : pos + 8]
            chunk_data = data[pos + 8 : pos + 8 + length]
            pos += 12 + length
            if chunk_type == b"IHDR":
                width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data)
            elif chunk_type == b"PLTE":
                palette = [
                    (chunk_data[i], chunk_data[i + 1], chunk_data[i + 2])
                    for i in range(0, len(chunk_data), 3)
                ]
            elif chunk_type == b"tRNS":
                trns = chunk_data
            elif chunk_type == b"IDAT":
                idat.extend(chunk_data)
            elif chunk_type == b"IEND":
                break
        if not width or not height or bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 3, 4, 6):
            raise ValueError("PNG 格式超出纯标准库解码范围；请使用标准 8-bit 非交错 PNG")
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
        bpp = channels
        stride = width * bpp
        raw = zlib.decompress(bytes(idat))
        recon = bytearray(height * stride)
        in_pos = 0
        for y in range(height):
            ftype = raw[in_pos]
            in_pos += 1
            row_start = y * stride
            prev_start = (y - 1) * stride
            for x in range(stride):
                val = raw[in_pos]
                in_pos += 1
                a = recon[row_start + x - bpp] if x >= bpp else 0
                b = recon[prev_start + x] if y > 0 else 0
                c = recon[prev_start + x - bpp] if (x >= bpp and y > 0) else 0
                if ftype == 1:
                    val = (val + a) & 0xFF
                elif ftype == 2:
                    val = (val + b) & 0xFF
                elif ftype == 3:
                    val = (val + ((a + b) >> 1)) & 0xFF
                elif ftype == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    val = (val + pr) & 0xFF
                recon[row_start + x] = val
        pixels: list[tuple[int, int, int, int]] = []
        for i in range(width * height):
            off = i * bpp
            if color_type == 6:
                pixels.append((recon[off], recon[off + 1], recon[off + 2], recon[off + 3]))
            elif color_type == 2:
                pixels.append((recon[off], recon[off + 1], recon[off + 2], 255))
            elif color_type == 4:
                g = recon[off]
                pixels.append((g, g, g, recon[off + 1]))
            elif color_type == 0:
                g = recon[off]
                pixels.append((g, g, g, 255))
            elif color_type == 3:
                idx = recon[off]
                r, g, b = palette[idx] if idx < len(palette) else (0, 0, 0)
                alpha = trns[idx] if idx < len(trns) else 255
                pixels.append((r, g, b, alpha))
        return cls(width, height, pixels)

    def getpixel(self, xy: tuple[int, int]) -> tuple[int, int, int, int]:
        x, y = xy
        return self._pixels[y * self.width + x]

    def crop(self, box: tuple[int, int, int, int]) -> "SimpleRGBAImage":
        x0, y0, x1, y1 = box
        out: list[tuple[int, int, int, int]] = []
        for y in range(y0, y1):
            row = y * self.width
            out.extend(self._pixels[row + x0 : row + x1])
        return SimpleRGBAImage(x1 - x0, y1 - y0, out)

    def getdata(self) -> list[tuple[int, int, int, int]]:
        return list(self._pixels)

    def to_png_bytes(self) -> bytes:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        rows = bytearray()
        for y in range(self.height):
            rows.append(0)
            row = y * self.width
            for x in range(self.width):
                rows.extend(self._pixels[row + x])
        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def load_rgba(source: Path):
    if Image is not None:
        with Image.open(source) as original:
            return original.convert("RGBA")
    return SimpleRGBAImage.open_bytes(source.read_bytes())


def encode_png_bytes(im) -> bytes:
    if hasattr(im, "to_png_bytes"):
        return im.to_png_bytes()
    buffer = io.BytesIO()
    im.save(buffer, format="PNG")
    return buffer.getvalue()


def get_opaque_pixels(crop) -> list[tuple[int, int, int, int]]:
    if hasattr(crop, "get_flattened_data"):
        return [p for p in crop.get_flattened_data() if p[3] == 255]
    return [p for p in crop.getdata() if p[3] == 255]


def apply_alpha_cleanup(
    crop,
    *,
    white_to_alpha: bool = False,
    threshold: int = 248,
    key_color: str | None = None,
    key_threshold: int = 28,
    feather: int = 12,
    despill: bool = False,
):
    if not white_to_alpha and not key_color:
        return crop
    w, h = crop.size
    raw = list(crop.getdata())
    kr = kg = kb = 0
    if key_color:
        cleaned = key_color.strip().lstrip("#")
        if len(cleaned) != 6:
            raise ValueError("key_color 必须是 6 位十六进制色值，如 #00FF00")
        kr, kg, kb = int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16)
    updated: list[tuple[int, int, int, int]] = []
    for red, green, blue, alpha in raw:
        if key_color:
            dist = ((red - kr) ** 2 + (green - kg) ** 2 + (blue - kb) ** 2) ** 0.5
            if dist <= key_threshold:
                alpha = 0
            elif feather > 0 and dist <= key_threshold + feather:
                alpha = max(0, min(alpha, int(alpha * (dist - key_threshold) / feather)))
            if despill and alpha > 0:
                excess = green - max(red, blue)
                if excess > 0:
                    edge_factor = 1.0 - (alpha / 255.0)
                    green = max(max(red, blue), green - int(excess * (0.72 + 0.28 * edge_factor)))
        if white_to_alpha and alpha > 0:
            bright = max(red, green, blue)
            if red >= threshold and green >= threshold and blue >= threshold:
                alpha = 0
            elif feather > 0 and bright >= threshold - feather:
                alpha = max(0, min(alpha, int(alpha * (threshold - bright + feather) / feather)))
        updated.append((red, green, blue, alpha))
    if Image is not None:
        out = Image.new("RGBA", (w, h))
        out.putdata(updated)
        return out
    return SimpleRGBAImage(w, h, updated)


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 必须是有限正数")
    return value


def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 必须是整数")
    return value


def box_checked(box, size):
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("box 必须为 [x,y,width,height]")
    x, y, w, h = [integer(v, "box 坐标") for v in box]
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > size[0] or y + h > size[1]:
        raise ValueError(f"标注 {box} 越界或面积无效（原图尺寸 {size[0]}x{size[1]}）；不自动裁短")
    return x, y, w, h


def distribution(values):
    values = sorted(values)

    def quantile(p):
        pos = (len(values) - 1) * p
        lo, hi = math.floor(pos), math.ceil(pos)
        return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 3)

    return {"median": quantile(0.5), "p10": quantile(0.1), "p90": quantile(0.9)}


def measure_data(
    data: dict,
    *,
    base_dir: Path,
    out: Path | None = None,
    manifest_bytes: bytes | None = None,
    allow_existing_out: bool = False,
) -> dict:
    source = (base_dir / data["reference"]).resolve()
    if not source.is_file():
        raise ValueError(f"参考图不存在：{source}")
    im = load_rgba(source)
    css_width = data.get("css_viewport_width")
    factor = positive(css_width, "css_viewport_width") / im.width if css_width is not None else None
    regions = []
    names = set()

    def take_name(item):
        name = item["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("标注名称必须非空且唯一")
        names.add(name)
        return name

    extracted_files: list[tuple[Path, bytes]] = []
    for item in data.get("regions", []):
        name = take_name(item)
        kind = item.get("kind", "box")
        if kind not in ("box", "color", "extract"):
            raise ValueError("kind 只支持 box、color 或 extract")
        x, y, w, h = box_checked(item["box"], im.size)
        default_btype = "sample" if kind == "color" else "element"
        box_type = item.get("box_type", default_btype)
        if box_type not in ("element", "ink", "sample") or (kind == "color" and box_type != "sample"):
            raise ValueError("box_type 必须为 element、ink 或 sample；颜色区只能为 sample")
        region = {
            "name": name,
            "kind": kind,
            "box_type": box_type,
            "box": [x, y, w, h],
            "normalized_box": [
                round(x / im.width, 6),
                round(y / im.height, 6),
                round(w / im.width, 6),
                round(h / im.height, 6),
            ],
            "boundary_evidence": "Agent 选择的标注范围，用于提取比例与色板，不作为固定像素死锁",
        }
        if factor is not None:
            region["css_box"] = [round(v * factor, 3) for v in [x, y, w, h]]
        if "selector" in item:
            region["selector"] = item["selector"]
        region["dom_comparable"] = box_type == "element"
        if "group" in item:
            if box_type != "element":
                raise ValueError("重复网格只接受元素框，不能混用字形框或采样框")
            if not isinstance(item["group"], str) or not item["group"].strip():
                raise ValueError("group 必须是非空字符串")
            region["group"] = item["group"]
        if kind == "color":
            inset = integer(item.get("inset", 0), "inset")
            if inset < 0 or inset * 2 >= min(w, h):
                raise ValueError("inset 使采样区域无效")
            crop = im.crop((x + inset, y + inset, x + w - inset, y + h - inset))
            pixels = get_opaque_pixels(crop)
            if not pixels:
                raise ValueError(f"{name} 没有不透明的颜色样本")
            channels = [distribution([p[c] for p in pixels]) for c in range(3)]
            rgb = [round(c["median"]) for c in channels]
            region["color"] = {
                "median_hex": "#" + "".join(f"{v:02X}" for v in rgb),
                "rgb_channels": channels,
                "opaque_samples": len(pixels),
                "excluded_nonopaque": crop.width * crop.height - len(pixels),
                "sample_box": [x + inset, y + inset, w - inset * 2, h - inset * 2],
                "max_channel_p90_minus_p10": round(max(c["p90"] - c["p10"] for c in channels), 3),
                "meaning": "局部像素中位数统计，用于提取 CSS 变量色值",
            }
        if kind == "extract" or item.get("extract"):
            crop = im.crop((x, y, x + w, y + h))
            crop = apply_alpha_cleanup(
                crop,
                white_to_alpha=bool(item.get("white_to_alpha", False)),
                threshold=int(item.get("threshold", 248)),
                key_color=item.get("key_color"),
                key_threshold=int(item.get("key_threshold", 28)),
                feather=int(item.get("feather", 12)),
                despill=bool(item.get("despill", False)),
            )
            target_dir = out if out is not None else base_dir
            out_file = target_dir / f"{name}.png"
            extracted_files.append((out_file, encode_png_bytes(crop)))
            region["extracted_file"] = str(out_file)
        regions.append(region)

    groups = []
    for name in sorted({r["group"] for r in regions if "group" in r}):
        members = sorted([r for r in regions if r.get("group") == name], key=lambda r: r["box"][0])
        if len(members) < 2:
            raise ValueError("重复网格至少需要两个标注")
        gaps = [b["box"][0] - (a["box"][0] + a["box"][2]) for a, b in zip(members, members[1:])]
        groups.append(
            {
                "name": name,
                "members": [r["name"] for r in members],
                "x_gaps": gaps,
                "median_width": median([r["box"][2] for r in members]),
                "median_height": median([r["box"][3] for r in members]),
                "median_gap": median(gaps),
                "y_spread": max(r["box"][1] for r in members) - min(r["box"][1] for r in members),
                "width_spread": max(r["box"][2] for r in members) - min(r["box"][2] for r in members),
                "meaning": "横向重复结构的统计参考",
            }
        )

    scans = []
    for spec in data.get("vertical_scans", []):
        name = take_name(spec)
        x, y, _, h = box_checked([spec["x"], spec["y"], 1, spec["height"]], im.size)
        floor = integer(spec["min_channel"], "min_channel")
        spread = integer(spec["max_channel_spread"], "max_channel_spread")
        run_min = integer(spec.get("min_run", 1), "min_run")
        if not 0 <= floor <= 255 or not 0 <= spread <= 255 or run_min < 1:
            raise ValueError("扫描阈值无效")
        runs = []
        start = None
        for yy in range(y, y + h + 1):
            p = im.getpixel((x, yy)) if yy < y + h else None
            match = (
                p is not None
                and p[3] == 255
                and min(p[:3]) >= floor
                and max(p[:3]) - min(p[:3]) <= spread
            )
            if match and start is None:
                start = yy
            if not match and start is not None:
                if yy - start >= run_min:
                    runs.append({"y_start": start, "y_end_exclusive": yy, "height": yy - start})
                start = None
        scans.append({"name": name, "configuration": spec, "runs": runs, "meaning": "满足给定颜色阈值的连续像素段"})

    if not regions and not scans:
        raise ValueError("至少提供一个区域或扫描")

    result = {
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_size": list(im.size),
        "css_mapping": {
            "assumed_viewport_width": css_width,
            "css_per_image_pixel": factor,
            "meaning": "比例换算参考，响应式实现应采用 Grid / Flexbox 而非固定像素定位",
        },
        "regions": regions,
        "groups": groups,
        "vertical_scans": scans,
    }
    if "expected" in data:
        result["expected"] = data["expected"]
        result["expected_assets"] = data.get("expected_assets", {})
    if manifest_bytes is not None:
        result["input_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()

    if out is not None:
        out.mkdir(parents=True, exist_ok=allow_existing_out)
        (out / "measurements.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        encoded = base64.b64encode(encode_png_bytes(im)).decode("ascii")
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{im.width}" height="{im.height}" viewBox="0 0 {im.width} {im.height}">',
            f'<image width="{im.width}" height="{im.height}" href="data:image/png;base64,{encoded}"/>',
        ]
        for region in regions:
            x, y, w, h = region["box"]
            label = html.escape(region["name"])
            color = "#36edcc" if region["kind"] == "box" else ("#ff7a45" if region["kind"] == "extract" else "#f6cb46")
            svg.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="2"/>'
                f'<text x="{x + 3}" y="{y + 15}" fill="{color}" stroke="#000" stroke-width="3" paint-order="stroke" font-size="13" font-family="sans-serif">{label}</text>'
            )
        svg.append("</svg>")
        (out / "annotations.svg").write_text("\n".join(svg), encoding="utf-8")

    for file_path, png_bytes in extracted_files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(png_bytes)

    return result


def measure(manifest_path: Path, out: Path) -> dict:
    raw = manifest_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    return measure_data(data, base_dir=manifest_path.parent, out=out, manifest_bytes=raw, allow_existing_out=False)


def parse_spec(spec: str, kind: str, extra: dict | None = None) -> dict:
    if "=" not in spec:
        raise ValueError(f"--{kind} 格式应为 名称=x,y,width,height，收到：{spec}")
    name, coords = spec.split("=", 1)
    parts = [p.strip() for p in coords.split(",")]
    if len(parts) != 4:
        raise ValueError(f"--{kind} 坐标必须为 x,y,width,height 四个整数，收到：{coords}")
    box = [int(p) for p in parts]
    item = {"name": name.strip(), "kind": kind, "box": box}
    if extra:
        item.update(extra)
    return item


def main(argv=None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=HELP_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("image", nargs="?", type=Path, help="参考图路径（命令行直接采样模式）")
    parser.add_argument("--manifest", type=Path, help="标注清单 JSON 路径（清单模式）")
    parser.add_argument("--out-dir", type=Path, help="输出目录（清单模式必填；直接采样模式可选）")
    parser.add_argument("--color", action="append", default=[], metavar="NAME=X,Y,W,H", help="采样局部区域的中位数十六进制色值")
    parser.add_argument("--box", action="append", default=[], metavar="NAME=X,Y,W,H", help="测量局部区域像素框与归一化比例")
    parser.add_argument("--extract", action="append", default=[], metavar="NAME=X,Y,W,H", help="裁切并导出局部图像资产为 PNG")
    parser.add_argument("--css-width", type=float, help="假设的桌面端 CSS 视口宽度（如 1440），用于换算 css_box")
    parser.add_argument("--white-to-alpha", action="store_true", help="将 --extract 导出资产的近白背景转为透明")
    parser.add_argument("--key-color", help="将 --extract 导出资产的指定背景色（如 #00FF00）转为透明")
    parser.add_argument("--despill", action="store_true", help="配合 --key-color 去除边缘溢色")
    args = parser.parse_args(argv)

    try:
        if args.manifest:
            if not args.out_dir:
                raise ValueError("使用 --manifest 时必须指定 --out-dir")
            result = measure(args.manifest, args.out_dir)
            print(
                json.dumps(
                    {
                        "status": "标注区域测量完成，设计关系仍需判断",
                        "regions": len(result["regions"]),
                        "groups": len(result["groups"]),
                        "output": str(args.out_dir),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if not args.image:
            parser.print_help()
            return 2

        extra_extract = {
            "white_to_alpha": args.white_to_alpha,
            "key_color": args.key_color,
            "despill": args.despill,
        }
        regions = (
            [parse_spec(s, "color") for s in args.color]
            + [parse_spec(s, "box") for s in args.box]
            + [parse_spec(s, "extract", extra_extract) for s in args.extract]
        )
        data = {"reference": str(args.image.resolve()), "regions": regions}
        if args.css_width is not None:
            data["css_viewport_width"] = args.css_width
        result = measure_data(
            data,
            base_dir=Path.cwd(),
            out=args.out_dir,
            allow_existing_out=True,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(2, f"测量失败：{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
