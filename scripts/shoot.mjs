#!/usr/bin/env node
// 给设计小样截图、录屏和做基本检查。只依赖 Node 22+ 和本机的 Chrome / Chromium / Edge。
// 用法见 references/tools.md；`node shoot.mjs --help` 打印同样的说明。
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { basename, dirname, extname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { createChrome } from "./chrome.mjs";

const HELP = `常用命令：
  node scripts/shoot.mjs page.html --size desktop --out shots
  node scripts/shoot.mjs page.html --size desktop --steps "click .nav button; wait 300" --out shots
  node scripts/shoot.mjs page.html --size desktop --frames 8 --steps "send: click text=Send" --out evidence

用法：node shoot.mjs <页面地址、文件、manifest.json 或目录> [...] [选项]
多个本地 HTML 也可用逗号分隔；多目标共用服务器和浏览器，默认生成带名称的 sheet.png。

  --out <目录>          输出目录，默认 ./shots
  --root <目录>         本地页面的静态服务根目录，默认按页面和 cwd 推断；共享资源用项目根
  --size <尺寸,...>     默认 390x844；desktop=1440x900，phone/mobile=390x844，可混用数字尺寸
  --states <a,b,...>    依次用 ?state=<名字> 打开并各截一张
  --param <名字>        状态参数名，默认 state
  --query <查询参数>    给地址加参数，例如 --query "a=1&b=2"；可和 --states 一起用
  --zoom <倍数,...>     默认 1；例如 --zoom 1,2，每个倍数各出一套；配 --evidence 时覆盖默认截图倍数
  --full                截整页，默认只截视口
  --selector <选择器>   只截匹配元素的区域，自动滚入视口；不与 --full、--record、--frames、--motion、--entry、--evidence 同用
  --thumb               快速缩略图：按 0.5 倍分辨率截视口，缩短等待并跳过可读性检查
  --mask                另截一份遮掉全部文字的版本
  --sheet               把状态拼成并排图，配合 --mask 再拼遮字版
  --no-sheet            多目标截图时不自动生成 sheet.png
  --mark "1=<选择器>;..." 给匹配的元素画框和编号，另出标注版；不写编号时按顺序编号
  --steps "<动作>"      可写多次，每组从重新打开的页面开始；组名前可写任意文字和冒号："编辑并保存: click .save"
  --record              每组录屏并留最后一个变化动作的三帧；无名组沿用 record.mp4、motion-start/mid/end.jpg
  --entry               配合 --record 或 --frames，先取帧再打开页面，捕捉首次出场
  --hold <毫秒>         动作结束后再录多久，默认 1200
  --motion              探测首次进入、动作反馈、首屏滚动和从头滚到底的动效；单屏跳过滚动
  --evidence            一次取齐状态截图、并排图和遮字并排图、首状态 2 倍图、动效探测、
                        首次出场录屏和每组动作录屏；显式 --zoom 按倍数截每个状态；一项失败仍继续
  --compare <参考图>    截图与 png/jpg/webp 参考图出四格对比和九宫格差异报告
  --wait <毫秒>         页面加载后等待时间，默认 400；截图另等有限动画，最多 2 秒
  --timeout-scale <倍数> 整体放宽协议、启动和编码超时，例如 --timeout-scale 2；默认 1
  --dry-run             只检查选项和动作写法，输出解析 JSON，不启动浏览器
  --stitch <图片>       拼图，不需要页面：可写多次，每张后面可接 --label <标注>；输出 stitch.png，--columns <列数> 默认 2
  --match-width <像素>  跟在各张 --stitch 后，填同一共有元素在该原图里的像素宽；统一到首图元素宽，所有图都要填
  --scale <倍数>        跟在 --stitch 后，显式缩放该图，未填的为 1；不与 --match-width 混用
  --crop <x,y,宽,高>   拼图统一缩放后，从每张图左上角起裁同一矩形；全局只写一次，不含标注，超出任一图时报错
  --frames <帧数>       只出 motion[-组名]-sequence.png：均匀取 2–120 帧并标时间，不编码视频；加 --record 才同时出视频
                        默认最多 4 列，--columns 可改；--evidence 配 --frames 也用序列图代替视频

同一比例并排对照（图片路径有空格时加引号）：
  node scripts/shoot.mjs --stitch ref.png --match-width 240px --label 参考 --stitch shot.png --match-width 300 --label 当前 --crop "0,0,800,600" --out shots
  node scripts/shoot.mjs --stitch ref.png --scale 1 --stitch shot.png --scale 80% --crop "0 0 800 600" --out shots
  --match-width 量的是原图中的共有元素，不是整张图片宽；工具不自动识别元素。
  --scale 接受 0.8、0.8x、80% 或 4/5；--crop 接受逗号、空格或 × 分隔，数值可带 px。
  先统一比例，再按 --crop 裁切，最后整组一起缩小到预览尺寸；不会把每张图各自拉成等宽。
  不写 --match-width / --scale / --crop 时保留原拼图方式：每张图各自等比缩小。report.json 记录实际缩放与裁切。

动作写法（用分号分隔；引号、方括号、圆括号里的分号不拆）：
  click <选择器> | hover <选择器> | dblclick <选择器> | waitfor <选择器>
  drag <选择器> <dx> <dy>，例如 drag .tiles .paper 240 0
  type <选择器> <文字>，例如 type [aria-label="Message box"] "hello world"
  type 在当前光标处插入文字；fill 先清空原内容，再填入文字并触发 input 和 change。
  fill <选择器> <文字>，例如 fill #message "hello world"
  type 和 fill 的选择器是第一个词，后代选择器可包引号：fill ".form input" hello
  select <选择器> <值或可见文字>，例如 select #country "China"
  key <按键或组合键>，例如 key ControlOrMeta+A；macOS 用 Meta，其他用 Control
  scroll <dy> | wait <时间>，例如 wait450、wait 450ms、wait 0.5s
  waitfor 最多等 5 秒，等元素出现并可见。
  别名：doubleclick=dblclick，press=key，sleep=wait。

选择器写法（动作和 --mark 通用）：
  CSS：click .nav button:nth-child(3)，click [aria-label="Send money"]，无需外层引号
  文字：click text=More 或 click text="Send money"，先找相等文字，再找包含文字
  包含文字：click button:has-text("Undo")，单双引号都可；省略 CSS 时查全部元素
  精确文字：click button:text-is("Save")；文字括号里也可不加引号
  匹配序号：click ".item >> nth=1"，从 0 开始；数字属性值 [data-select=0842] 自动补引号
  选择器只在主文档里找，不进入 iframe 或 Shadow DOM；找不到时报告 iframe 和开放 shadow root 数量。

选项都可写成 --名字=值 或 --名字 值；开关不带值。重复状态、尺寸和倍数会去重；文件名冲突会自动加编号。
数值选项 --hold、--wait、--zoom、--timeout-scale、--match-width、--scale 也可连写，例如 --hold1000、--scale0.8。
元素匹配多个时取第一个可见的；匹配到但隐藏时说明原因，并给可见元素的写法。
点击、双击和悬停前检查中心点遮挡和禁用状态；提示写进输出和 report.json 的问题汇总，动作照常执行，返回码不变。
截图单次最多等 90 秒，其他 CDP 请求默认等 30 秒。
启动、连接浏览器或 CDP 请求超时，自动用双倍时限整次重跑一次，并打印重试说明。
重跑后截图仍超时则继续后面的项，返回码 1；其他协议超时或浏览器意外断开时退出。
多项命令每完成一项向标准错误打印进度，标准输出仍是最后的汇总。
每张图检查控制台错误、横向溢出和加载失败的图片，明细写进 report.json；
可读性与渲染提示写进 lint 字段。录屏需要 ffmpeg，没有时只留帧。

和 --states 一起用：
  普通截图会在每个状态执行每组 --steps；动效探测和动作录屏只从第一个状态、第一种尺寸开始，
  --evidence 每组各录一次，不会给每个状态各录一遍。
  --evidence 默认只有第一个状态出 2 倍图；每个状态都要时写 --zoom 1,2 或 --zoom 2，
  文件会多出将近一倍，只在各状态都要放大查细节或交付高分辨率图时这样做。

输出文件（写进 --out）：
  <状态>.png，遮字版 <状态>-masked.png，标注版 <状态>-marked.png，并排图 sheet.png 和 sheet-masked.png，
  还原比对 <状态>-compare.png（四格依次是参考、当前、叠加和差异热图）。多个倍数各出一套，2 倍的文件名带 @2x。
  @2x 是同一个视口用 2 倍像素密度截的图，页面布局不变，不是把页面放大到 200% 后的重排。
  录屏：单个无名组是 record.mp4 和 motion-start/mid/end.jpg；具名或多组是 record-<安全组名>.mp4
  和 motion-<安全组名>-start/mid/end.jpg；首次出场是 record-entry.mp4 和 motion-entry-start/mid/end.jpg。
  组名中的文件名非法字符会替换为连字符，空白变为连字符，重名文件名自动加编号；--help 和 report.json 保留原组名。
  report.json 的最外层是数组，每个元素是一张图或一项检查的结果；lint、motion、issues 在各个元素里。结构示意：
  [{"file":"idle.png","lint":[],"issues":[]},
   {"file":"motion-probe","motion":{},"issues":[]}]

录屏怎样取样：
  动作录屏的开始帧取最后一个 click、dblclick、drag、type、fill、select 或 key 派发前，
  中间帧取这个动作反馈的中段，结束帧取 hold 结束时；等待、悬停和滚动不改变取样动作。
  出场三帧从第一次出现内容取到稳定；没有动作的普通录屏取整段的头、中、尾。
  各帧的文件名和时间在 report.json 的 frames.start/mid/end 里，录屏时长在 durationMs 里。
  动效本身不足 3 秒时，录屏短于 3 秒是正常的。
  录屏的最后一帧和结束时新截的图差得明显时，汇总和 report.json 的 warnings 里会有警告，
  并用结束截图补上录像的最后一帧；这时静止终态以 motion-<组名>-end.jpg 为准，过渡过程不能据此判通过。

其他：
  --compare 先用 --size 设成参考图的逻辑尺寸，例如 2880 宽的 2 倍图用 1440 宽；
  差异占比只用来找先修哪一块、看修改有没有让差异变少，不是还原度的分数。
  --motion 只说明动了没有、动了多少：首次进入没有动画、动作没有反馈、从头滚到底没有变化会记为问题；
  没有配 --steps 时，如果动效由点击等交互触发，提示会说明需要配 --steps 才能探测；
  页面不能滚动时跳过滚动检查；Canvas 和 WebGL 里的动画可能探测不到，以录屏为准。
  本地文件会用只监听本机的临时服务器打开；地址里带 ? 或 & 时加引号，或改用 --query。
  WebGL 页面在没有显卡的机器上改用软件渲染；画布没能创建绘图上下文时会记为问题，这时截图是空的。`;

function fail(message) { console.error(`shoot：${message}`); process.exit(1); }
const STITCH_EXAMPLE = 'node scripts/shoot.mjs --stitch ref.png --match-width 240 --stitch shot.png --match-width 300 --crop "0,0,800,600" --out shots';
const SCALE_EXAMPLE = 'node scripts/shoot.mjs --stitch ref.png --scale 1 --stitch shot.png --scale 80% --out shots';
function stitchNumber(value, key) {
  let text = value.trim().toLowerCase(), factor = 1;
  const example = key === "scale" ? SCALE_EXAMPLE : STITCH_EXAMPLE;
  if (key === "scale") {
    if (text.endsWith("%")) { factor = .01; text = text.slice(0, -1).trim(); }
    else text = text.replace(/\s*(?:x|×|倍)$/, "").trim();
  } else text = text.replace(/\s*px$/, "").trim();
  const number = /^(?:\d+(?:\.\d*)?|\.\d+)$/;
  const parts = key === "scale" ? text.split("/").map((part) => part.trim()) : [text];
  const n = parts.every((part) => number.test(part)) && parts.length <= 2 ? Number(parts[0]) / (parts.length === 2 ? Number(parts[1]) : 1) * factor : NaN;
  if (!Number.isFinite(n) || n <= 0) fail(`--${key} 需要正数，收到 ${value}；例如 ${example}`);
  return n;
}
function stitchCrop(value) {
  const parts = value.trim().replace(/(\d)\s*px(?=\s|[,，x×)\]]|$)/gi, "$1").replace(/^[[(]\s*|\s*[\])]$/g, "").trim().split(/[\s,，x×]+/i);
  const numbers = parts.map(Number);
  if (parts.length !== 4 || parts.some((part) => !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(part)) || numbers.some((n) => !Number.isFinite(n)) || numbers[2] <= 0 || numbers[3] <= 0) {
    fail(`--crop 需要非负 x、y 和正的宽、高，收到 ${value}；例如 ${STITCH_EXAMPLE}`);
  }
  const [x, y, width, height] = numbers;
  return { x, y, width, height };
}
function distance(a, b) {
  let row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 0; i < a.length; i++) {
    const next = [i + 1];
    for (let j = 0; j < b.length; j++) next.push(Math.min(next[j] + 1, row[j + 1] + 1, row[j] + (a[i] !== b[j])));
    row = next;
  }
  return row[b.length];
}
const closest = (word, choices) => [...choices].sort((a, b) => distance(word, a) - distance(word, b))[0];
const ACTIONS = ["click", "hover", "dblclick", "drag", "type", "fill", "select", "waitfor", "key", "scroll", "wait"];
const ALIASES = { doubleclick: "dblclick", press: "key", sleep: "wait" };
const unquote = (s) => /^(["'])[\s\S]*\1$/.test(s) ? s.slice(1, -1).replace(/\\(["'\\])/g, "$1") : s;
// Split only outside quoted strings and selector brackets. Preserve the source for diagnostics.
function splitOutside(text, words = false) {
  const parts = []; let start = 0, quote = null, outerQuote = null, stack = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "\\") { i++; continue; }
    // Outer quotes around a selector may contain attribute quotes, even unescaped ones.
    if (outerQuote) {
      if (!quote && !stack.length && c === outerQuote) { outerQuote = null; continue; }
      if (quote) { if (c === quote) quote = null; continue; }
      if (c === "[" || c === "(") { stack.push(c); continue; }
      if (c === "]" || c === ")") { stack.pop(); continue; }
      if (stack.length && (c === '"' || c === "'")) quote = c;
      continue;
    }
    if (quote) { if (c === quote) quote = null; continue; }
    const quoteStarts = (c === '"' || c === "'") && (i === 0 || /[\s=(]/.test(text[i - 1]));
    const prefix = text.slice(start, i).trim();
    const selectorQuote = words ? !parts.length && !prefix :
      /^(?:click|hover|dblclick|doubleclick|drag|type|fill|select|waitfor)$/.test(prefix) || /^(?:\d+\s*=\s*)?$/.test(prefix);
    if (quoteStarts) { if (selectorQuote) outerQuote = c; else quote = c; continue; }
    if (c === "[" || c === "(") stack.push(c);
    else if (c === "]" || c === ")") {
      if (stack.pop() !== (c === "]" ? "[" : "(")) throw new Error(`括号没有配对，收到 ${text}；例如 click [aria-label="Send money"]`);
    } else if (!stack.length && (words ? /\s/.test(c) : c === ";")) {
      if (text.slice(start, i).trim()) parts.push(text.slice(start, i).trim());
      start = i + 1;
    }
  }
  if (quote || outerQuote || stack.length) throw new Error(`引号或括号没有配对，收到 ${text}；例如 click [aria-label="Send money"]`);
  if (text.slice(start).trim()) parts.push(text.slice(start).trim());
  return parts;
}
function parseSelector(source) {
  const value = unquote(source.trim());
  if (!value) throw new Error(`缺少选择器，收到 ${source}；例如 click .open`);
  if (value.startsWith("text=")) return { kind: "text", value: unquote(value.slice(5).trim()) };
  const m = value.match(/^(.*):has-text\(\s*(["'])([\s\S]*)\2\s*\)$/);
  if (m) return { kind: "has-text", css: m[1].trim() || "*", value: unquote(m[2] + m[3] + m[2]) };
  return { kind: "css", value };
}
function parseSteps(text) {
  let name = null;
  let quote = null, stack = [], split = null;
  const actions = [...ACTIONS, ...Object.keys(ALIASES)];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "\\") { i++; continue; }
    if (quote) { if (c === quote) quote = null; continue; }
    if (c === '"' || c === "'") { quote = c; continue; }
    if (c === "[" || c === "(") { stack.push(c); continue; }
    if (c === "]" || c === ")") { stack.pop(); continue; }
    if (stack.length || c !== ":" || !/\s/.test(text[i + 1] || "")) continue;
    const prefix = text.slice(0, i).trim(), rest = text.slice(i + 1).trimStart();
    const first = rest.match(/^(\S+)/)?.[1] || "";
    const action = ALIASES[first] || first.replace(/^(wait|sleep)\d[\s\S]*$/, "$1");
    if (prefix && (ACTIONS.includes(action) || actions.some((item) => distance(first, item) <= 2))) split = { prefix, rest };
  }
  if (split) { name = split.prefix; text = split.rest; }
  const steps = splitOutside(text).map((raw, i) => {
    const m = raw.match(/^(\S+)(?:\s+([\s\S]*))?$/);
    let action = ALIASES[m[1]] || m[1], tail = m[2] || "";
    if (/^(wait|sleep)\d/.test(action)) { tail = action.replace(/^(wait|sleep)/, ""); action = "wait"; }
    const bad = (example) => { throw new Error(`第 ${i + 1} 步动作参数不对，收到 ${raw}；例如 ${example}`); };
    if (!ACTIONS.includes(action)) throw new Error(`第 ${i + 1} 步不认识的动作，收到 ${raw}；是不是想写 ${closest(action, [...ACTIONS, ...Object.keys(ALIASES)])}？全部动作：${ACTIONS.join("、")}；别名：${Object.keys(ALIASES).join("、")}`);
    const step = { action, raw, params: {} };
    if (["click", "hover", "dblclick", "waitfor"].includes(action)) {
      if (!tail) bad(`${action} .open`);
      step.selector = parseSelector(tail);
    } else if (action === "drag") {
      const match = tail.match(/^([\s\S]+?)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))$/);
      if (!match) bad("drag .tiles .paper 240 0");
      step.selector = parseSelector(match[1]); step.params = { dx: +match[2], dy: +match[3] };
    } else if (["type", "fill", "select"].includes(action)) {
      const tokens = splitOutside(tail, true);
      if (tokens.length < 2) bad(`${action} #field "hello world"`);
      step.selector = parseSelector(tokens[0]);
      step.params = action === "select" ? { value: unquote(tail.slice(tokens[0].length).trim()) } : { text: unquote(tail.slice(tokens[0].length).trim()) };
    } else if (action === "wait") {
      const match = tail.match(/^(\d+(?:\.\d+)?)(ms|s)?$/);
      if (!match) bad("wait 450ms");
      step.params = { ms: +match[1] * (match[2] === "s" ? 1000 : 1) };
    } else if (action === "scroll") {
      if (!tail || !Number.isFinite(Number(tail))) bad("scroll -400");
      step.params = { dy: +tail };
    } else {
      const keys = unquote(tail).split("+");
      const mods = keys.slice(0, -1);
      if (!tail || /\s/.test(tail) || mods.some((k) => !["Alt", "Control", "Meta", "Shift", "ControlOrMeta"].includes(k)) || !keys.at(-1)) bad("key ControlOrMeta+A");
      step.params = { key: keys.at(-1), modifiers: mods };
    }
    return step;
  });
  return { name, steps };
}
const args = process.argv.slice(2);
if (!args.length || args.includes("--help") || args.includes("-h")) { console.log(HELP); process.exit(args.length ? 0 : 1); }
const opt = { out: "shots", size: "390x844", param: "state", zoom: "1", hold: "1200", wait: "400" };
const options = [...HELP.matchAll(/^  (--\S+)/gm)].map((m) => m[1]);
options.push("--label", "--columns", "--frames");
const booleanOptions = new Set(["full", "thumb", "mask", "sheet", "record", "motion", "entry", "evidence", "dry-run", "force", "no-sheet"]);
const flags = new Set(), stepsInputs = [], positional = [], suppliedOptions = new Set(), stitchInputs = [];
let lastFlag = null;
for (let i = 0; i < args.length; i++) {
  // Only numeric options accept a glued value; --out123 and switches keep their old errors.
  const gluedNumber = args[i].match(/^(--(?:hold|wait|zoom|timeout-scale|columns|frames|match-width|scale))((?:\d|\.\d)[\s\S]*)$/);
  const a = gluedNumber ? `${gluedNumber[1]}=${gluedNumber[2]}` : args[i];
  if (a.startsWith("--")) {
    const equal = a.indexOf("="), option = equal < 0 ? a : a.slice(0, equal), key = option.slice(2);
    if (!options.includes(option) && key !== "force") {
      const glued = options.find((o) => a.startsWith(o) && /^\d/.test(a.slice(o.length)));
      const suggestion = glued ? `${glued} ${a.slice(glued.length)}` : closest(option, options);
      const examples = { out: "shots", size: "desktop", states: "idle,done", param: "state", query: '"a=1&b=2"', zoom: "1,2", mark: '"1=.open"', steps: '"click .open"', hold: "1000", compare: "ref.png", wait: "400", stitch: "before.png", label: '"修改前"', columns: "2", frames: "8", "match-width": "240", scale: "80%", crop: '"0,0,800,600"' };
      const example = glued ? suggestion : `${suggestion}${examples[suggestion.slice(2)] ? " " + examples[suggestion.slice(2)] : ""}`;
      fail(`不认识的选项 ${a}；是不是想写 ${example}？\n可用选项：${options.join(" ")}`);
    }
    if (booleanOptions.has(key)) {
      if (equal >= 0) fail(`${option} 不带参数，收到 ${a}；例如 ${option}`);
      flags.add(key); lastFlag = option;
    } else {
      lastFlag = null;
      if (equal < 0 && (i + 1 >= args.length || args[i + 1].startsWith("--"))) {
        const example = { stitch: "--stitch before.png --stitch after.png --out shots", label: '--stitch before.png --label "修改前"', columns: "--stitch before.png --columns 2", frames: "page.html --record --frames 8", "match-width": STITCH_EXAMPLE, scale: SCALE_EXAMPLE, crop: STITCH_EXAMPLE }[key];
        fail(`${option} 需要一个值${example ? `，收到 ${a}；例如 ${example}` : ""}`);
      }
      const value = equal < 0 ? args[++i] : a.slice(equal + 1);
      if (!value) fail(`${option} 需要一个值，收到 ${a}；例如 ${{ "match-width": STITCH_EXAMPLE, scale: SCALE_EXAMPLE, crop: STITCH_EXAMPLE }[key] || `${option} 值`}`);
      suppliedOptions.add(key);
      if (key === "steps") stepsInputs.push(value);
      else if (key === "stitch") stitchInputs.push({ path: value });
      else if (key === "label") {
        if (!stitchInputs.length || stitchInputs.at(-1).label !== undefined) fail(`--label 要跟在一张 --stitch 图片后，收到 ${a} ${value}；例如 --stitch before.png --label "修改前" --stitch after.png --label "修改后"`);
        stitchInputs.at(-1).label = value;
      } else if (key === "match-width" || key === "scale") {
        const image = stitchInputs.at(-1), field = key === "match-width" ? "matchWidth" : "scale";
        if (!image || image[field] !== undefined) fail(`--${key} 要跟在一张 --stitch 图片后且每张只写一次，收到 ${a} ${value}；例如 ${key === "scale" ? SCALE_EXAMPLE : STITCH_EXAMPLE}`);
        image[field] = stitchNumber(value, key);
      } else if (key === "crop") {
        if (opt.crop !== undefined) fail(`--crop 是所有图片共用的区域，只写一次，收到 ${value}；例如 ${STITCH_EXAMPLE}`);
        opt.crop = stitchCrop(value);
      } else opt[key] = value;
    }
  } else {
    if (stitchInputs.length) fail(`拼图不需要页面，每张图片前都要写 --stitch，收到 ${a}；例如 --stitch before.png --label "修改前" --stitch after.png --label "修改后" --columns 2 --out shots`);
    if (lastFlag === "--motion" && /^(?:[.#\[]|text=)|:has-text\(/.test(a)) fail(`--motion 不带参数，收到 --motion 和 ${a}；要探测的动作写进 --steps，例如 --motion --steps "click ${a}"`);
    if (positional.length && !/^(?:https?:|file:)|\.html?(?:[?#,]|$)|(?:^|[\\/])manifest\.json$/i.test(a) && !existsSync(a)) fail(`页面地址或多余参数冲突，收到 ${positional[0]} 和 ${a}${lastFlag ? `；${lastFlag} 不带参数` : ""}；例如 page.html --steps "click .open"`);
    // Selector-like extras after a switch are never page targets.
    if (lastFlag && /^(?:[.#\[]|text=)/.test(a) && !/\.html?(?:[?#]|$)/i.test(a) && !existsSync(a)) fail(`${lastFlag} 不带参数，收到 ${lastFlag} 和 ${a}；例如 page.html ${lastFlag}`);
    positional.push(a); lastFlag = null;
  }
}
// Expand explorer inputs before dry-run, without requiring ordinary page paths to exist.
let batchMode = positional.length > 1;
// 文件系统只接收路径；查询与锚点留到静态服务器 URL 上，不能参与 realpath/root/文件名计算。
const localAddress = (value, base = process.cwd()) => {
  if (/^file:\/\//i.test(value)) {
    const url = new URL(value);
    return { path: fileURLToPath(url), search: url.search, hash: url.hash };
  }
  // 普通路径允许目录/文件名含 # 或 ?。先认真实文件，再从右往左找
  // 已存在的路径前缀，避免把目录名里的符号误切成查询或锚点。
  const literal = resolve(base, value);
  if (existsSync(literal)) return { path: literal, search: "", hash: "" };
  for (let i = value.length - 1; i >= 0; i--) {
    if (value[i] !== "?" && value[i] !== "#") continue;
    const path = resolve(base, value.slice(0, i));
    if (!existsSync(path)) continue;
    const suffix = value.slice(i).match(/^(\?[^#]*)?(#.*)?$/s);
    if (suffix) return { path, search: suffix[1] || "", hash: suffix[2] || "" };
  }
  const [, path, search = "", hash = ""] = value.match(/^([^?#]*)(\?[^#]*)?(#.*)?$/s);
  return { path: resolve(base, path), search, hash };
};
const localPath = (value) => localAddress(value).path;
function expandTarget(value) {
  if (/^https?:\/\//i.test(value)) return [{ target: value }];
  let path;
  try { path = localPath(value); } catch { fail(`找不到文件：${value}`); }
  if (!existsSync(path) && value.includes(",") && value.split(",").every((p) => /\.html?(?:[?#].*)?$/i.test(p.trim()))) {
    batchMode = true;
    return value.split(",").flatMap((p) => expandTarget(p.trim()));
  }
  if (existsSync(path) && statSync(path).isDirectory()) {
    if (existsSync(join(path, "manifest.json"))) return expandTarget(join(path, "manifest.json"));
    if (existsSync(join(path, "index.html"))) return [{ target: value }];
    batchMode = true;
    const pages = readdirSync(path, { withFileTypes: true }).filter((p) => p.isFile() && /\.html$/i.test(p.name) && p.name.toLowerCase() !== "style-explorer.html").map((p) => p.name).sort();
    if (!pages.length) fail(`目录里找不到候选 HTML：${value}`);
    return pages.flatMap((page) => expandTarget(join(path, page)));
  }
  if (basename(path).toLowerCase() === "manifest.json") {
    batchMode = true;
    let manifest;
    try { manifest = JSON.parse(readFileSync(path, "utf8")); }
    catch (error) { fail(`无法读取 manifest：${value}（${error.message}）`); }
    if (!Array.isArray(manifest.candidates)) fail(`manifest 缺少 candidates 数组：${value}`);
    const candidates = manifest.candidates.filter((c) => c && (!c.kind || c.kind === "html") && typeof c.source === "string" && /\.html?(?:[?#].*)?$/i.test(c.source) && !/^[a-z][a-z\d+.-]*:/i.test(c.source));
    if (!candidates.length) fail(`manifest 里找不到本地 HTML 候选：${value}`);
    return candidates.map((c) => {
      const { path: file, search, hash } = localAddress(c.source, dirname(path));
      return { target: file + search + hash, id: c.id, name: c.name };
    });
  }
  return [{ target: value }];
}
const targets = positional.flatMap(expandTarget);
const target = targets[0]?.target;
// IDs become filenames only after removing separators and reserved path components.
const targetStem = (candidate) => {
  const path = /^https?:\/\//i.test(candidate.target) ? new URL(candidate.target).pathname : localPath(candidate.target);
  const source = candidate.id || basename(path, extname(path));
  return String(source).replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/^[. ]+|[. ]+$/g, "") || "page";
};
const stitching = stitchInputs.length > 0;
if (opt.crop !== undefined && !stitching) fail(`--crop 需要 --stitch 图片，收到 ${args.join(" ")}；例如 ${STITCH_EXAMPLE}`);
if (!target && !stitching) {
  if (opt.frames !== undefined || opt.columns !== undefined) fail(`缺少页面或拼图输入，收到 ${args.join(" ")}；例如 page.html --record --frames 8 --columns 4，或 --stitch before.png --stitch after.png --columns 2`);
  fail("缺少页面地址或文件。");
}
if (stitching) {
  const incompatible = [...suppliedOptions].filter((key) => !["stitch", "label", "columns", "out", "timeout-scale", "match-width", "scale", "crop"].includes(key));
  if (target || incompatible.length || [...flags].some((key) => key !== "dry-run" && key !== "force")) fail(`拼图不需要页面或截图/录屏选项，收到 ${target || incompatible.map((key) => "--" + key).join("、") || [...flags].join("、")}；例如 --stitch before.png --label "修改前" --stitch after.png --label "修改后" --columns 2 --out shots`);
  for (const [i, image] of stitchInputs.entries()) {
    try { if (!statSync(image.path).isFile()) throw new Error("不是文件"); }
    catch { fail(`拼图第 ${i + 1} 张图片不存在或不是文件，收到 ${image.path}；例如 --stitch before.png --label "修改前" --out shots`); }
  }
  if (stitchInputs.some((image) => image.matchWidth !== undefined)) {
    if (stitchInputs.some((image) => image.scale !== undefined)) fail(`--match-width 与 --scale 不能混用，收到两种比例声明；例如 ${STITCH_EXAMPLE}；或 ${SCALE_EXAMPLE}`);
    if (stitchInputs.some((image) => image.matchWidth === undefined)) fail(`使用 --match-width 时每张图都要声明共有元素宽，收到未声明的图片；例如 ${STITCH_EXAMPLE}`);
  }
}
if (opt.frames !== undefined && (!/^\d+$/.test(opt.frames) || !Number.isSafeInteger(+opt.frames) || +opt.frames < 2 || +opt.frames > 120)) fail(`--frames 需要 2–120 的整数，收到 ${opt.frames}；例如 page.html --record --frames 8`);
const captureMotion = flags.has("record") || opt.frames !== undefined;
if (opt.columns !== undefined && (!/^\d+$/.test(opt.columns) || !Number.isSafeInteger(+opt.columns) || +opt.columns < 1)) fail(`--columns 需要正整数，收到 ${opt.columns}；例如 --stitch before.png --stitch after.png --columns 2`);
if (opt.columns !== undefined && !stitching && opt.frames === undefined) fail(`--columns 需要配合 --stitch 或 --frames，收到 --columns ${opt.columns}；例如 page.html --record --frames 8 --columns 4`);
if (flags.has("thumb")) {
  const badThumb = [...["full", "mask", "record", "motion", "entry", "evidence"].filter((k) => flags.has(k)).map((k) => "--" + k), ...(opt.frames !== undefined ? ["--frames"] : []), ...(opt.mark ? ["--mark"] : []), ...(opt.compare ? ["--compare"] : [])];
  if (badThumb.length) fail(`--thumb 只用于快速缩略图，不和 ${badThumb.join("、")} 一起用，收到 ${badThumb.join("、")}；例如 page.html --size desktop --thumb --out shots`);
  if (!suppliedOptions.has("wait")) opt.wait = "150";
}
const notices = [];
function deduplicate(values, key, label) {
  const seen = new Set(), removed = [];
  const unique = values.filter((value) => {
    const id = key(value); if (seen.has(id)) { removed.push(id); return false; } seen.add(id); return true;
  });
  if (removed.length) notices.push(`${label} 已去重：${[...new Set(removed)].join("、")}`);
  return unique;
}
let groups, sizes, zooms, marks, selector = null;
if (opt.selector) {
  const conflicts = [...["full", "record", "motion", "entry", "evidence"].filter((key) => flags.has(key)), ...(opt.frames !== undefined ? ["frames"] : [])];
  if (conflicts.length) fail(`--selector 不与 ${conflicts.map((key) => "--" + key).join("、")} 同用`);
}
try {
  selector = opt.selector ? parseSelector(opt.selector) : null;
  groups = stepsInputs.map(parseSteps);
  const names = groups.map((g, i) => g.name || (groups.length > 1 ? String(i + 1) : ""));
  if (new Set(names).size !== names.length) throw new Error(`动作组名字重复，收到 ${names.join("、")}；例如 --steps "open: click .open" --steps "send: click .send"`);
  const usedGroupFiles = new Set();
  const safeGroupFile = (value) => {
    let stem = String(value).trim().replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, "-").replace(/\s+/g, "-")
      .replace(/^[. ]+|[. ]+$/g, "").replace(/[. ]+$/g, "");
    let bytes = 0;
    stem = Array.from(stem).filter((character) => {
      bytes += Buffer.byteLength(character);
      return bytes <= 120;
    }).join("");
    if (!stem) stem = "group";
    if (/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i.test(stem)) stem = `_${stem}`;
    const base = stem; let n = 2;
    while (usedGroupFiles.has(stem.toLowerCase())) stem = `${base}-${n++}`;
    usedGroupFiles.add(stem.toLowerCase());
    return stem;
  };
  groups.forEach((g, i) => { g.reportName = names[i]; g.id = names[i] ? safeGroupFile(names[i]) : ""; });
  sizes = opt.size.split(",").map((s) => {
    const value = ({ desktop: "1440x900", phone: "390x844", mobile: "390x844" })[s.trim()] || s.trim();
    const m = value.match(/^(\d+)x(\d+)$/);
    if (!m || +m[1] < 1 || +m[2] < 1) throw new Error(`尺寸不对，收到 ${s}；例如 --size desktop,390x844`);
    return { w: +m[1], h: +m[2] };
  });
  zooms = opt.zoom.split(",").map((s) => {
    const n = Number(s); if (!Number.isFinite(n) || n <= 0) throw new Error(`倍数不对，收到 ${s}；例如 --zoom 1,2`); return n;
  });
  sizes = deduplicate(sizes, (s) => `${s.w}x${s.h}`, "尺寸");
  zooms = deduplicate(zooms, String, "倍数");
  for (const key of ["hold", "wait"]) if (!/^\d+(?:\.\d+)?$/.test(opt[key])) throw new Error(`--${key} 需要毫秒数，收到 ${opt[key]}；例如 --${key} 1000`);
  if (opt["timeout-scale"] !== undefined && (!Number.isFinite(Number(opt["timeout-scale"])) || Number(opt["timeout-scale"]) < 1)) throw new Error(`超时倍数不对，收到 ${opt["timeout-scale"]}；例如 --timeout-scale 2`);
  marks = (opt.mark ? splitOutside(opt.mark) : []).map((s, i) => {
    const m = s.match(/^(\d+)\s*=\s*(.+)$/);
    return { label: m ? m[1] : String(i + 1), selector: parseSelector(m ? m[2] : s) };
  });
} catch (error) { fail(error.message); }
const timeoutScale = Number(opt["timeout-scale"] || 1);
const timeoutMs = (ms) => Math.min(2147483647, ms * timeoutScale);
const quoteArg = (value) => "'" + String(value).replaceAll("'", "'\\''") + "'";
const retryCommand = `node ${quoteArg(resolve(process.argv[1]))} ${stitching ? args.map(quoteArg).join(" ") : quoteArg(target)} --timeout-scale 2`;
let currentRetryCommand = retryCommand;
const slowHint = () => `同时开了很多个任务时会变慢；可先单独重跑：${currentRetryCommand}`;
const states = deduplicate(opt.states ? opt.states.split(",").map((s) => s.trim()).filter(Boolean) : [null], String, "状态");
if (!states.length) fail(`--states 没有状态，收到 ${opt.states}；例如 --states idle,done`);
const stateIds = states.map((s, i) => !s ? "page" : /^[A-Za-z0-9_-]{1,80}$/.test(s) ? s : `state-${i + 1}-${createHash("sha256").update(s).digest("hex").slice(0, 12)}`);
const refImage = opt.compare ? resolve(opt.compare) : null;
if (refImage && !existsSync(refImage)) fail(`找不到参考图：${opt.compare}`);
if (refImage && !/\.(png|jpe?g|webp)$/i.test(refImage)) fail("--compare 只接受 png、jpg 或 webp");
if (refImage && (captureMotion || flags.has("evidence"))) fail("--compare 用在截图上，不和 --record、--frames 或 --evidence 一起用；例如 --compare ref.png");
if (flags.has("dry-run")) {
  console.log(JSON.stringify({ target, ...(targets.length > 1 ? { targets: targets.map((t) => t.target) } : {}), selector, options: opt, flags: [...flags], sizes, zooms, states, groups, marks, notices, ...(stitching ? { stitch: stitchInputs } : {}) }, null, 2));
  process.exit(0);
}
// A small supervisor preserves the complete invocation and gives every run fresh state.
// The worker reports only transport/startup timeouts with 75; ordinary failures stay 1.
const attemptKey = "OIL_SHOOT_TIMEOUT_ATTEMPT";
const workerAttempt = process.env[attemptKey];
if (workerAttempt === undefined) {
  let child;
  process.on("SIGINT", () => child?.kill("SIGINT"));
  process.on("SIGTERM", () => child?.kill("SIGTERM"));
  const run = (attempt) => new Promise((ok) => {
    child = spawn(process.execPath, [...process.execArgv, process.argv[1], ...args,
      ...(attempt ? ["--timeout-scale", String(timeoutScale * 2)] : [])],
    { stdio: "inherit", env: { ...process.env, [attemptKey]: String(attempt) } });
    child.once("error", (error) => { console.error(`shoot：启动截图进程失败，收到 ${error.message}`); ok(1); });
    child.once("exit", (code, signal) => ok(signal === "SIGINT" ? 130 : signal === "SIGTERM" ? 143 : code ?? 1));
  });
  let code = await run(0);
  if (code === 75) {
    console.error(`shoot：正在重试一次：时限放宽到原来的两倍（--timeout-scale ${timeoutScale * 2}），整次重跑，保留全部原始参数`);
    code = await run(1);
  }
  process.exit(code);
}
if (typeof WebSocket !== "function") fail("需要 Node 22 或更新的版本。");
const out = resolve(opt.out);
mkdirSync(out, { recursive: true });
const temporaryFrames = new Set(), encoders = new Set();
function removeFrames() { for (const dir of temporaryFrames) rmSync(dir, { recursive: true, force: true }); temporaryFrames.clear(); }

// ---------- 本地文件用一个只监听本机的静态服务器打开，模块脚本和 fetch 才能正常工作 ----------
const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif", ".woff2": "font/woff2", ".woff": "font/woff",
  ".ttf": "font/ttf", ".otf": "font/otf", ".mp4": "video/mp4", ".webm": "video/webm",
  ".txt": "text/plain; charset=utf-8", ".wasm": "application/wasm", ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json", ".bin": "application/octet-stream", ".geojson": "application/geo+json",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".pdf": "application/pdf",
  ".csv": "text/csv; charset=utf-8", ".ico": "image/x-icon", ".mov": "video/quicktime", ".m4a": "audio/mp4",
  ".hdr": "application/octet-stream", ".exr": "image/x-exr", ".ktx2": "image/ktx2",
};
const privatePath = (path) => path.split(/[\\/]/).some((part) => part !== ".oil-ui" && (part.startsWith(".")
  || /^(?:credentials?|secrets?|id_(?:rsa|dsa|ecdsa|ed25519))(?:[._-]|$)/i.test(part)));
let server = null;
const localFiles = targets.filter((t) => !/^https?:\/\//i.test(t.target)).map(({ target }) => {
  const path = localPath(target);
  if (!existsSync(path)) fail(`找不到文件：${target}`);
  const file = statSync(path).isDirectory() ? join(path, "index.html") : path;
  if (!existsSync(file) || !statSync(file).isFile()) fail(`找不到文件：${file}`);
  return realpathSync(file);
});
let sharedRoot = localFiles.length ? dirname(localFiles[0]) : null;
for (const file of localFiles) {
  while (relative(sharedRoot, file) === ".." || relative(sharedRoot, file).startsWith(`..${sep}`) || isAbsolute(relative(sharedRoot, file))) {
    const parent = dirname(sharedRoot);
    if (parent === sharedRoot) fail("本地批量目标必须位于同一个磁盘，才能共用静态服务器");
    sharedRoot = parent;
  }
}
let explicitRoot = null;
if (opt.root) {
  const candidate = resolve(opt.root);
  if (!existsSync(candidate) || !statSync(candidate).isDirectory()) fail(`--root 需要已有目录：${opt.root}`);
  explicitRoot = realpathSync(candidate);
  if (explicitRoot === parse(explicitRoot).root || explicitRoot === realpathSync(tmpdir())) fail(`--root 范围过宽，请使用项目目录：${opt.root}`);
  for (const file of localFiles) {
    const fromRoot = relative(explicitRoot, file);
    if (fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) fail(`本地目标不在 --root 内：${file}`);
  }
}
async function resolveTarget(t) {
  if (/^https?:\/\//i.test(t)) return t;
  const { path: file, search, hash } = localAddress(t);
  if (!existsSync(file)) fail(`找不到文件：${t}`);
  const isDir = statSync(file).isDirectory();
  const fileDir = realpathSync(isDir ? file : dirname(file));
  let root = explicitRoot || sharedRoot || fileDir;
  try {
    const cwdReal = realpathSync(process.cwd());
    const tmpReal = realpathSync(tmpdir());
    const relDir = relative(cwdReal, root);
    if (!explicitRoot && relDir && relDir !== ".." && !relDir.startsWith(`..${sep}`) && !isAbsolute(relDir)
      && relDir.split(sep).length <= 3 && cwdReal !== parse(cwdReal).root && cwdReal !== tmpReal && !fileDir.startsWith(tmpReal + sep)) {
      root = cwdReal;
    }
  } catch {}
  const targetFile = isDir ? join(fileDir, "index.html") : realpathSync(file);
  const pagePath = relative(root, targetFile).split(sep).map(encodeURIComponent).join("/");
  const pageURL = () => `http://127.0.0.1:${server.address().port}/${pagePath}${search}${hash}`;
  if (server) return pageURL();
  server = createServer((req, res) => {
    try {
      const origin = `http://127.0.0.1:${server.address().port}`;
      const url = new URL(req.url, origin);
      if (req.headers.host !== new URL(origin).host || url.origin !== origin || !["GET", "HEAD"].includes(req.method)) {
        res.writeHead(404).end();
        return;
      }
      const path = decodeURIComponent(url.pathname);
      if (privatePath(path)) { res.writeHead(404).end(); return; }
      const local = realpathSync(resolve(join(root, path)));
      const fromRoot = relative(root, local);
      const type = MIME[extname(local).toLowerCase()];
      if (fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot) || privatePath(fromRoot) || !type || !statSync(local).isFile()) {
        res.writeHead(404).end();
        return;
      }
      res.writeHead(200, { "Content-Type": type, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store" });
      res.end(req.method === "HEAD" ? undefined : readFileSync(local));
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  return pageURL();
}

// ---------- 启动一个独立的临时浏览器，不碰用户自己的浏览器数据 ----------
let ws, cleaning;
let browser;
try { browser = createChrome({ timeoutMs, prefix: "oil-shoot-", label: "shoot" }); }
catch (error) { fail(error.message); }
const launchChrome = () => browser.launch();
const stopChrome = () => browser.stop(ws);
function cleanup() { return cleaning ||= (async () => { for (const child of encoders) child.kill("SIGKILL"); await stopChrome(); server?.close(); removeFrames(); })(); }
process.on("exit", () => {
  try { for (const child of encoders) child.kill("SIGKILL"); removeFrames(); } catch {}
  try { server?.close(); } catch {}
  browser.dispose();
});
process.on("SIGINT", async () => { await cleanup(); process.exit(130); });
process.on("SIGTERM", async () => { await cleanup(); process.exit(143); });
let wsUrl;
try { wsUrl = await launchChrome(); }
catch (error) {
  await cleanup();
  console.error(`shoot：浏览器启动失败，收到 ${error.message === "timeout" ? `${45 * timeoutScale} 秒内没有启动` : error.message}；${slowHint()}`);
  process.exit(error.message === "timeout" && workerAttempt === "0" ? 75 : 1);
}

// ---------- Chrome DevTools 协议 ----------
let currentContext = "连接浏览器", transportFailure = null, finishing = false;
async function during(context, work) {
  const previous = currentContext; currentContext = context;
  try { return await work(); } finally { currentContext = previous; }
}
let sessionId, browserNeedsRestart = false;
let seq = 0;
const pending = new Map(), listeners = [];
let saveFatalReport = () => {};
function abortTransport(error) {
  if (transportFailure || finishing) return;
  transportFailure = error; process.exitCode = error.code === "TRANSPORT_TIMEOUT" && workerAttempt === "0" ? 75 : 1;
  for (const request of pending.values()) { clearTimeout(request.timer); request.no(error); }
  pending.clear();
  console.error(`shoot：${error.message}`);
  try { saveFatalReport(error); } catch {}
  void cleanup().finally(() => process.exit(process.exitCode));
}
async function connectTransport(url) {
  ws = new WebSocket(url);
  ws.onclose = () => abortTransport(new Error(`${currentContext}：浏览器连接意外断开，已停止执行；${slowHint()}`));
  ws.onerror = () => abortTransport(new Error(`${currentContext}：浏览器连接出错，已停止执行；${slowHint()}`));
  await new Promise((ok, no) => {
    const timer = setTimeout(() => { const error = new Error(`连接浏览器：${30 * timeoutScale} 秒内没有响应；${slowHint()}`); error.code = "TRANSPORT_TIMEOUT"; no(error); abortTransport(error); }, timeoutMs(30000));
    ws.onopen = () => { clearTimeout(timer); ok(); };
    const failed = () => { clearTimeout(timer); no(transportFailure || new Error("连接浏览器失败")); };
    ws.addEventListener("close", failed, { once: true }); ws.addEventListener("error", failed, { once: true });
  });
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, no, timer, context } = pending.get(msg.id);
      pending.delete(msg.id); clearTimeout(timer);
      msg.error ? no(new Error(`${context}：${msg.error.message}`)) : ok(msg.result);
    } else if (msg.method) listeners.forEach((fn) => fn(msg));
  };
}
const send = (method, params = {}, targetSession) => new Promise((ok, no) => {
  if (transportFailure || ws.readyState !== WebSocket.OPEN) { no(transportFailure || new Error(`${currentContext}：浏览器连接已经断开。`)); return; }
  const id = ++seq, context = currentContext;
  // Rasterization competes with other tasks for CPU/GPU time; allow three ordinary request budgets.
  const limit = timeoutMs(method === "Page.captureScreenshot" ? 90000 : 30000);
  const timer = setTimeout(() => {
    const error = new Error(`${context}：CDP ${method} ${limit / 1000} 秒内没有响应；${slowHint()}`);
    error.code = "TRANSPORT_TIMEOUT";
    if (method === "Page.navigate") {
      pending.delete(id); error.code = "NAVIGATION_TIMEOUT"; no(error);
    } else if (method === "Page.captureScreenshot" && workerAttempt === "1") {
      pending.delete(id); browserNeedsRestart = true; error.code = "SCREENSHOT_TIMEOUT"; no(error);
    } else abortTransport(error);
  }, limit);
  pending.set(id, { ok, no, timer, context });
  try { ws.send(JSON.stringify({ id, method, params, ...(targetSession ? { sessionId: targetSession } : {}) })); }
  catch { abortTransport(new Error(`${context}：发送 CDP ${method} 时浏览器连接断开，已停止执行；${slowHint()}`)); }
});
try { await connectTransport(wsUrl); } catch { await cleanup(); process.exit(process.exitCode || 1); }

async function setupSend(...args) {
  try { return await send(...args); }
  catch (error) { if (transportFailure) { await cleanup(); process.exit(process.exitCode || 1); } throw error; }
}
const cdp = (method, params) => setupSend(method, params, sessionId);
async function setupSession() {
  const { targetId } = await setupSend("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await setupSend("Target.attachToTarget", { targetId, flatten: true }));
  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Log.enable");
  // 记下创建失败或丢失的 WebGL 上下文：截图照样成功，画布却是空的。
  // 先试 webgl2、失败后退回 webgl 的页面不算失败，只看最后有没有拿到。
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
    const gl = window.__oilWebgl = { failed: [], ok: [], lost: 0 };
    const get = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      const ctx = get.call(this, type, ...rest);
      if (/^(webgl2?|experimental-webgl)$/.test(type)) {
        if (!ctx) gl.failed.push(this);
        else if (!gl.ok.includes(this)) { gl.ok.push(this); this.addEventListener("webglcontextlost", () => gl.lost++); }
      }
      return ctx;
    };
  })()` });
}
await setupSession();
async function restartBrowser() {
  ws.onclose = ws.onerror = ws.onmessage = null; ws.close();
  for (const request of pending.values()) { clearTimeout(request.timer); request.no(new Error("截图超时，正在重开浏览器")); }
  pending.clear();
  await stopChrome();
  try {
    await connectTransport(await launchChrome());
    await setupSession(); browserNeedsRestart = false;
  } catch (error) {
    abortTransport(new Error(`浏览器重开失败，收到 ${error.message}；${slowHint()}`));
    throw error;
  }
}

let problems = [];
function isAutoFavicon(url) {
  try { return new URL(url || "").pathname === "/favicon.ico"; } catch { return false; }
}
listeners.push((m) => {
  if (m.sessionId !== sessionId) return;
  if (m.method === "Runtime.exceptionThrown") problems.push(`脚本错误：${m.params.exceptionDetails?.exception?.description?.split("\n")[0] || m.params.exceptionDetails?.text}`);
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") problems.push(`控制台错误：${m.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200)}`);
  // Browsers ask for /favicon.ico on their own; a mockup without one has no page problem.
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error" && !isAutoFavicon(m.params.entry.url)) problems.push(`加载错误：${m.params.entry.text.slice(0, 200)} ${m.params.entry.url || ""}`.trim());
});

const evaluate = async (expression) => {
  const r = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function setViewport(w, h, scale) {
  await cdp("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: scale, mobile: w < 600 });
  await cdp("Emulation.setTouchEmulationEnabled", { enabled: w < 600 });
}

async function open(url, wait = Number(opt.wait)) {
  return during(`${currentContext} / 打开页面 ${url}`, async () => {
    let loadedListener, timer;
    const loaded = new Promise((ok) => {
      loadedListener = (m) => { if (m.sessionId === sessionId && m.method === "Page.loadEventFired") ok(); };
      listeners.push(loadedListener);
      timer = setTimeout(ok, timeoutMs(15000));
    });
    try {
      let nav, retried = false;
      try { nav = await cdp("Page.navigate", { url }); }
      catch (error) {
        if (error.code !== "NAVIGATION_TIMEOUT") throw error;
        retried = true; await sleep(300); nav = await cdp("Page.navigate", { url });
      }
      // 被取消或超时都不等于打不开：浏览器自己的导航偶尔会打断这一次，只补试一次。
      if (!retried && nav.errorText === "net::ERR_ABORTED") { await sleep(300); nav = await cdp("Page.navigate", { url }); }
      if (nav.errorText) throw new Error(`打不开 ${url}：${nav.errorText}`);
      await loaded;
      await evaluate(`document.fonts ? document.fonts.ready.then(() => true) : true`);
      await sleep(wait);
    } finally {
      clearTimeout(timer); const index = listeners.indexOf(loadedListener); if (index >= 0) listeners.splice(index, 1);
    }
  });
}

async function check() {
  const found = await evaluate(`(() => {
    const out = [];
    const doc = document.documentElement;
    if (doc.scrollWidth > innerWidth + 2 && [doc, document.body].every((el) => !["hidden", "clip"].includes(getComputedStyle(el).overflowX))) {
      const examples = [];
      for (const el of document.body.querySelectorAll("*")) {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        if (r.width <= 0 || r.height <= 0 || r.right <= innerWidth + 2 || s.visibility !== "visible" || s.display === "none") continue;
        let alpha = 1;
        for (let node = el; node; node = node.parentElement) alpha *= parseFloat(getComputedStyle(node).opacity);
        if (alpha <= 0.05) continue;
        const cls = [...el.classList].slice(0, 2).map((name) => "." + name).join("");
        examples.push(el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + cls + " 超出 " + Math.round((r.right - innerWidth) * 10) / 10 + "px");
        if (examples.length === 3) break;
      }
      out.push("横向溢出：页面宽 " + doc.scrollWidth + "px，视口 " + innerWidth + "px" + (examples.length ? "（" + examples.join("；") + "）" : ""));
    }
    for (const img of document.images) if (img.complete && img.naturalWidth === 0) out.push("图片没加载出来：" + (img.getAttribute("src") || "").slice(0, 120));
    const gl = window.__oilWebgl;
    if (gl) {
      const blank = new Set(gl.failed.filter((c) => !gl.ok.includes(c))).size;
      if (blank) out.push("WebGL：" + blank + " 个画布没能创建绘图上下文，截图里是空的");
      if (gl.lost) out.push("WebGL：绘图上下文丢失 " + gl.lost + " 次");
    }
    return out;
  })()`);
  return [...problems, ...found];
}

// ---------- 可读性与渲染提示：对比度、过小字号、过紧行高、停在透明 ----------
// 在页面里运行，不能引用外层变量。
function lintPage() {
  const LABELS = {
    contrastLow: "文字对比度不达标（正文低于 3:1，大字低于 2.5:1）",
    smallText: "文字小于 11px", tightLeading: "多行正文行高过紧",
    stuck: "首屏有内容停在透明状态（出场动画没触发？）",
  };
  const found = new Map();
  const describe = (el) => {
    const cls = typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 24);
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + cls + (text ? "「" + text + "」" : "");
  };
  const add = (rule, el, note) => {
    let r = found.get(rule);
    if (!r) found.set(rule, r = { rule, label: LABELS[rule], count: 0, examples: [] });
    r.count++;
    if (r.examples.length < 3) r.examples.push(describe(el) + (note ? "（" + note + "）" : ""));
  };
  const css = (el, pseudo) => getComputedStyle(el, pseudo);
  const shown = (el) => {
    const r = el.getBoundingClientRect(), s = css(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  // 颜色统一画到画布上再读回，oklch、color-mix 这类写法也能比较。
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const colors = new Map();
  const rgba = (value) => {
    if (!ctx || !value) return { r: 0, g: 0, b: 0, a: 0 };
    if (colors.has(value)) return colors.get(value);
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "rgba(0,0,0,0)";
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    const c = { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
    colors.set(value, c);
    return c;
  };
  const luminance = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a), a: 1,
  });
  const ownText = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
  const textRect = (el) => {
    for (const node of el.childNodes) {
      if (node.nodeType !== 3 || !node.textContent.trim()) continue;
      const range = document.createRange();
      range.setStart(node, node.textContent.search(/\S/));
      range.setEnd(node, node.textContent.trimEnd().length);
      const rect = [...range.getClientRects()].find((r) => r.width > 0 && r.height > 0);
      if (rect) return rect;
    }
    return null;
  };
  const opacity = (el) => {
    let alpha = 1;
    for (let node = el; node; node = node.parentElement) alpha *= parseFloat(css(node).opacity);
    return alpha;
  };
  const scaledDown = (el) => {
    for (let node = el; node; node = node.parentElement) {
      const transform = css(node).transform;
      if (transform === "none") continue;
      const m = new DOMMatrixReadOnly(transform);
      if (Math.hypot(m.m11, m.m12, m.m13) < 0.999 || Math.hypot(m.m21, m.m22, m.m23) < 0.999) return true;
    }
    return false;
  };
  // 命中文字的首个 Range，而非宽容器的中心。命中栈只包含实际覆盖该点的底板，
  // 因此能看到兄弟底板，也不会读到绝对定位文字背后并不存在的窄父容器背景。
  const backdrop = (el, r) => {
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (hasOverlayPlate(el, r, true)) return null;
    let stack;
    if (cx >= 0 && cx < innerWidth && cy >= 0 && cy < innerHeight) {
      stack = document.elementsFromPoint(cx, cy);
      const start = stack.indexOf(el);
      if (start < 0) return null; // 视口内被裁掉或无法命中时不猜底色。
      stack = stack.slice(start);
    } else {
      // 命中 API 不覆盖长页的屏外内容。先排除局部滚动/裁切框外的点，
      // 再只采实际覆盖该点的祖先，绝对定位文字不会误读窄轨道的底色。
      stack = [];
      for (let node = el; node; node = node.parentElement) {
        const nr = node.getBoundingClientRect(), ns = css(node);
        const inX = cx >= nr.left && cx <= nr.right, inY = cy >= nr.top && cy <= nr.bottom;
        if ((["hidden", "clip", "scroll", "auto"].includes(ns.overflowX) && !inX)
          || (["hidden", "clip", "scroll", "auto"].includes(ns.overflowY) && !inY)) return null;
        if (inX && inY) stack.push(node);
      }
    }
    const layers = [];
    for (const node of stack) {
      const s = css(node);
      if (opacity(node) <= 0.05) continue;
      if (node.matches("img,video,canvas,picture,iframe,svg image") || s.backgroundImage !== "none") return null;
      const c = rgba(s.backgroundColor);
      if (c.a > 0) { layers.push(c); if (c.a >= 0.99) break; }
    }
    return layers.reverse().reduce((base, c) => over(c, base), { r: 255, g: 255, b: 255, a: 1 });
  };
  const all = [document.body, ...document.body.querySelectorAll("*")]
    .filter((el) => !el.closest("svg,script,style,noscript,template,head,[aria-hidden='true'],#oil-mark"));
  const nonTextInputs = new Set(["hidden", "checkbox", "radio", "range", "color", "file", "button", "submit", "reset", "image"]);
  const textControl = (el) => el.matches("textarea,select") || (el.tagName === "INPUT" && !nonTextInputs.has(el.type));
  const texts = all.filter((el) => (ownText(el).length >= 2 || textControl(el)) && shown(el));
  const containingRect = (node, pos) => {
    if (pos === "fixed") return { left: 0, top: 0 };
    for (let p = node; p && p.nodeType === 1; p = p.parentElement) {
      if (css(p).position !== "static") return p.getBoundingClientRect();
    }
    return document.documentElement?.getBoundingClientRect?.() || { left: 0, top: 0 };
  };
  const hasOverlayPlate = (el, r, imageOnly = false) => {
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      for (const pseudo of ["::before", "::after"]) {
        const ps = css(node, pseudo);
        if (!ps || !ps.content || ps.content === "none" || !(ps.backgroundImage !== "none" || rgba(ps.backgroundColor).a > 0.05)) continue;
        if (imageOnly && ps.backgroundImage === "none") continue;
        const pw = parseFloat(ps.width), ph = parseFloat(ps.height);
        if (!(pw >= r.width * 0.5 && ph >= r.height * 0.5)) continue;
        const base = (ps.position === "absolute" || ps.position === "fixed") ? containingRect(node, ps.position) : node.getBoundingClientRect();
        const pl = base.left + (parseFloat(ps.left) || 0), pt = base.top + (parseFloat(ps.top) || 0);
        if (cx >= pl && cx <= pl + pw && cy >= pt && cy <= pt + ph) return true;
      }
      if (rgba(css(node).backgroundColor).a >= 0.99) break;
    }
    return false;
  };

  for (const el of texts) {
    const s = css(el), r = el.getBoundingClientRect();
    if (el.matches(":disabled") || el.closest("[disabled],[aria-disabled='true'],option")) continue;
    const control = textControl(el);
    if (!control && el.closest("input,textarea,select")) continue;
    const alpha = opacity(el);
    if (alpha <= 0.05) continue;
    const size = parseFloat(s.fontSize);
    if (!(size > 0)) continue; // 窄屏图标按钮常用 0px 有意隐藏自己的文字。
    const sample = textRect(el) || (control ? r : null);
    if (!sample) continue; // 普通文字没有可见 Range 时不能拿按钮的图标/内边距代替。
    if (size < 11 && !el.closest("sup,sub") && !scaledDown(el)) add("smallText", el, size + "px");
    let ink = s, hasText = true;
    if (control) {
      const value = el.tagName === "SELECT" ? [...el.selectedOptions].map((o) => o.text).join("") : el.value;
      hasText = value.length > 0;
      if (!hasText && el.placeholder?.trim() && el.matches(":placeholder-shown")) {
        ink = css(el, "::placeholder");
        hasText = true;
      }
    }
    const bg = hasText ? backdrop(el, sample) : null;
    const fg = rgba(ink.color);
    if (bg && (fg.a > 0 || control)) {
      const color = over({ ...fg, a: fg.a * alpha * (ink === s ? 1 : parseFloat(ink.opacity)) }, bg);
      const contrast = ratio(color, bg);
      const large = !control && (size >= 24 || (size >= 18.6 && parseInt(s.fontWeight, 10) >= 700));
      // 伪元素不在命中栈里，沿用底板免误报；兄弟底板已按绘制顺序采到，极低对比度也照常报。
      if (!(contrast < 1.5 && hasOverlayPlate(el, sample))) {
        if (contrast < (large ? 2.5 : 3.0)) add("contrastLow", el, contrast.toFixed(2) + ":1");
      }
    }
    // 正文：两行以上的段落
    if (control) continue;
    const text = ownText(el);
    const zh = /[一-鿿]/.test(text);
    if (text.length < (zh ? 30 : 60) || el.closest("code,pre,table,nav,button,label,figcaption,kbd")) continue;
    const lh = s.lineHeight === "normal" ? size * 1.2 : parseFloat(s.lineHeight);
    if (r.height < lh * 1.8) continue;
    if (lh / size < (zh ? 1.4 : 1.3)) add("tightLeading", el, (lh / size).toFixed(2));
  }

  // 首屏里停在透明的内容：出场动画没触发时截图会缺一块
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.top >= innerHeight || r.bottom <= 0 || r.width < 40 || r.height < 16) continue;
    if (!(ownText(el).length >= 4 || (el.tagName === "IMG" && el.complete))) continue;
    if (el.closest("[role='dialog'],[role='tooltip'],[role='menu'],[hidden],dialog:not([open]),details:not([open])")) continue;
    let alpha = 1, hider = null;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const o = parseFloat(css(node).opacity);
      if (o < 0.5 && !hider) hider = node;
      alpha *= o;
    }
    if (alpha >= 0.05 || !hider) continue;
    const hs = css(hider);
    if (/absolute|fixed/.test(hs.position) || hs.pointerEvents === "none" || css(el).visibility === "hidden") continue;
    add("stuck", el);
  }

  return [...found.values()];
}

async function lint() {
  try {
    return await evaluate(`(${lintPage.toString()})()`);
  } catch (error) {
    return [{ rule: "lintError", label: "可读性检查没跑完", count: 1, examples: [error.message.slice(0, 160)] }];
  }
}
const lintLine = (items) => items.map((i) => `${i.label} ${i.count} 处（${i.examples.join("，")}）`).join("；");

async function settleAnimations(limit) {
  if (limit <= 0) return 0;
  return during(`${currentContext} / 等待有限动画结束`, () => evaluate(`(async () => {
    const start = performance.now(), limit = ${limit};
    let waited = false;
    while (true) {
      const animations = document.getAnimations().filter((a) => (a.playState === "running" || a.pending) && a.effect
        && Number.isFinite(a.effect.getComputedTiming().endTime));
      if (!animations.length || performance.now() - start >= limit) break;
      waited = true;
      await Promise.race([Promise.all(animations.map((a) => a.finished.catch(() => {}))),
        new Promise((ok) => setTimeout(ok, Math.min(50, Math.max(0, limit - (performance.now() - start))))) ]);
    }
    return waited ? Math.min(limit, Math.round(performance.now() - start)) : 0;
  })()`));
}

async function selectorClip() {
  try {
    await locate(selector, "--selector", false, "screenshot");
    const box = await evaluate(`(async () => {
      const el = (${findSource})(${JSON.stringify(selector)})[0];
      if (!el) return null;
      const r0 = el.getBoundingClientRect();
      const hasTopBar = [...document.body.querySelectorAll("*")].slice(0, 1000).some((n) => {
        if (n === el || n.contains(el) || el.contains(n)) return false;
        const pos = getComputedStyle(n).position;
        if (pos !== "fixed" && pos !== "sticky") return false;
        const nr = n.getBoundingClientRect();
        return nr.width > innerWidth * 0.3 && nr.height > 0 && nr.height <= 160 && nr.top <= 24 && nr.bottom > 0;
      });
      if (r0.height > innerHeight * 0.65 || hasTopBar) {
        el.scrollIntoView({ block: "nearest", inline: "center", behavior: "instant" });
        const r1 = el.getBoundingClientRect();
        window.scrollTo({ top: Math.max(0, r1.top + scrollY - 72), left: scrollX, behavior: "instant" });
      } else {
        el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
      }
      await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
      const r = el.getBoundingClientRect();
      return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height };
    })()`);
    if (!box || box.width <= 0 || box.height <= 0) throw new Error(`--selector：找不到元素或元素宽高为 0：${opt.selector}`);
    return { ...box, scale: flags.has("thumb") ? 0.5 : 1 };
  } catch (error) {
    if (transportFailure) throw error;
    await cleanup(); fail(error.message);
  }
}
async function screenshot(file, full, clipOverride = null) {
  let clip = clipOverride;
  if (full) {
    const { contentSize } = await cdp("Page.getLayoutMetrics");
    clip = { x: 0, y: 0, width: Math.ceil(contentSize.width), height: Math.ceil(contentSize.height), scale: 1 };
  }
  const { data } = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: !!full || !!clip, ...(clip ? { clip } : {}) });
  writeFileSync(file, Buffer.from(data, "base64"));
  return file;
}

// Keep color intact: SVG icons and CSS decorations may use currentColor.
const MASK_CSS = `*,*::before,*::after{text-shadow:none!important;-webkit-text-fill-color:transparent!important;caret-color:transparent!important}
::placeholder{color:transparent!important}svg text,svg tspan{fill:transparent!important;stroke:transparent!important}`;
const mask = () => evaluate(`(() => { const s = document.createElement("style"); s.id = "oil-mask"; s.textContent = ${JSON.stringify(MASK_CSS)}; document.head.append(s); return true; })()`);

// 标注版：框和编号画在页面最上层，按文档坐标定位，整页截图时也对得上。
async function mark() {
  for (const { selector } of marks) await locate(selector, "--mark", false);
  const result = await evaluate(`((selectors) => {
    const find = ${findSource};
    const layer = document.createElement("div");
    layer.id = "oil-mark";
    layer.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none";
    const color = "#e8175d";
    const missing = [];
    selectors.forEach(({ label, selector }) => {
      let found;
      try { found = find(selector); } catch { missing.push(selector + "（选择器写错了）"); return; }
      const boxes = found.map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
      if (!boxes.length) { missing.push(selector + (found.length ? "（元素不可见）" : "")); return; }
      boxes.forEach((r, j) => {
        const box = document.createElement("div");
        box.style.cssText = "position:absolute;box-sizing:border-box;border:2px solid " + color + ";border-radius:3px;" +
          "left:" + (r.left + scrollX - 4) + "px;top:" + (r.top + scrollY - 4) + "px;width:" + (r.width + 8) + "px;height:" + (r.height + 8) + "px";
        if (j === 0) {
          // 小元素的编号放到框外，免得盖住元素；左边放不下就放右边。
          const small = r.width < 48 || r.height < 28;
          const pos = !small ? "left:-12px;top:-12px" : r.left + scrollX - 34 >= 0 ? "left:-30px;top:" + (r.height / 2 - 7) + "px" : "right:-30px;top:" + (r.height / 2 - 7) + "px";
          const tag = document.createElement("span");
          tag.textContent = label;
          tag.style.cssText = "position:absolute;" + pos + ";min-width:22px;height:22px;padding:0 6px;box-sizing:border-box;border-radius:11px;" +
            "background:" + color + ";color:#fff;font:600 13px/22px -apple-system,'PingFang SC',sans-serif;text-align:center;box-shadow:0 0 0 2px #fff";
          box.append(tag);
        }
        layer.append(box);
      });
    });
    document.body.append(layer);
    return missing;
  })(${JSON.stringify(marks)})`);
  if (result.length) throw new Error(`--mark 找不到元素：${result.join("；")}`);
}
const unmark = () => evaluate(`(document.getElementById("oil-mark")?.remove(), true)`);

// ---------- 动作 ----------
// Serialized into the page; each helper includes its own dependencies.
function hiddenReason(el) {
  const describe = (e) => e.tagName.toLowerCase() + (e.id ? "#" + e.id : "");
  for (let e = el; e; e = e.parentElement) {
    const style = getComputedStyle(e);
    const owner = e === el ? "" : "被祖先 " + describe(e) + " 隐藏：";
    if (style.display === "none") return owner + "display:none";
    // An ancestor's hidden visibility can be overridden by the child.
    if (e === el && (style.visibility === "hidden" || style.visibility === "collapse")) {
      let owner = e;
      while (owner.parentElement && getComputedStyle(owner.parentElement).visibility === style.visibility) owner = owner.parentElement;
      return (owner === el ? "" : "被祖先 " + describe(owner) + " 隐藏：") + "visibility:" + style.visibility;
    }
    if (Number(style.opacity) === 0) return owner + "opacity:0";
    if (style.contentVisibility === "hidden") return owner + "content-visibility:hidden";
    if (e !== el && e.tagName === "DETAILS" && !e.open && !e.querySelector(":scope > summary")?.contains(el)) return "被祖先 " + describe(e) + " 隐藏：details 未展开";
  }
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return "尺寸为 0（宽 " + r.width + "px，高 " + r.height + "px）";
  if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return "被祖先或浏览器布局隐藏";
  return null;
}
// Normalize at lookup time so existing --dry-run selector objects remain byte-for-byte stable.
// Read quoted strings/brackets before recognizing Playwright operators: their literals are CSS data.
function compatibleSelector(selector) {
  if (selector.kind === "text") return selector;
  const source = selector.kind === "has-text" ? selector.css : selector.value;
  const received = selector.kind === "has-text" ? `${selector.css}:has-text(${JSON.stringify(selector.value)})` : source;
  const filters = [], legacyText = selector.kind === "has-text" ? selector.value : null;
  let css = "", nth, depth = 0;
  const unsupported = () => {
    const value = filters[0]?.value ?? legacyText ?? "Send money";
    const error = new Error(`无法转换选择器，收到 ${received}；请用文字定位或 CSS，序号从 0 开始`);
    error.selectorExample = filters.length || legacyText !== null ? `text=${JSON.stringify(value)}` : `${!depth && css.trim() || ".item"} >> nth=1`;
    throw error;
  };
  const quotedEnd = (start) => {
    for (let i = start + 1; i < source.length; i++) {
      if (source[i] === "\\") { i++; continue; }
      if (source[i] === source[start]) return i;
    }
    unsupported();
  };
  for (let i = 0; i < source.length;) {
    const c = source[i];
    if (c === "\\") { css += source.slice(i, i + 2); i += 2; continue; }
    if (c === '"' || c === "'") { const end = quotedEnd(i); css += source.slice(i, end + 1); i = end + 1; continue; }
    if (c === "[") {
      let end = i + 1;
      for (; end < source.length && source[end] !== "]"; end++) {
        if (source[end] === "\\") end++;
        else if (source[end] === '"' || source[end] === "'") end = quotedEnd(end);
      }
      const attr = source.slice(i, end + 1);
      css += attr.replace(/^(\[\s*[^\s~|^$*!=\]]+\s*[~|^$*]?=\s*)(\d[^\s"'\\\[\]]*)(\s*(?:[is]\s*)?\])$/, (_, prefix, value, suffix) => prefix + JSON.stringify(value) + suffix);
      i = end + 1; continue;
    }
    if (source.startsWith(">>", i)) {
      if (depth || legacyText !== null) unsupported();
      const match = source.slice(i).match(/^>>\s*nth\s*=\s*(-?\d+)\s*$/);
      if (!match || !Number.isSafeInteger(Number(match[1]))) unsupported();
      nth = Number(match[1]); break;
    }
    const pseudo = source.slice(i).match(/^:(has-text|text-is)\(/);
    if (pseudo) {
      let end = i + pseudo[0].length, start = end;
      for (; end < source.length && source[end] !== ")"; end++) {
        if (source[end] === "\\") end++;
        else if (source[end] === '"' || source[end] === "'") end = quotedEnd(end);
        else if (source[end] === "(") unsupported();
      }
      if (end >= source.length) unsupported();
      const argument = source.slice(start, end).trim();
      const quoted = /^("|')[\s\S]*\1$/.test(argument);
      if (!quoted && /["']/.test(argument)) unsupported();
      const value = quoted ? argument.slice(1, -1).replace(/\\(["'\\])/g, "$1") : argument;
      filters.push({ exact: pseudo[1] === "text-is", value });
      if (depth) unsupported();
      i = end + 1; continue;
    }
    // A descendant/combinator after a text filter changes the subject; do not silently drop it.
    if (filters.length && depth === 0 && /[\s>+~,]/.test(c) && source.slice(i).trim() && !source.slice(i).trimStart().startsWith(">>")) unsupported();
    if (c === "(") depth++;
    if (c === ")") depth--;
    css += c; i++;
  }
  if (legacyText !== null) filters.push({ exact: false, value: legacyText });
  if (!filters.length) return { kind: "css", value: css.trim(), ...(nth === undefined ? {} : { nth }) };
  return { kind: "filtered-text", css: css.trim() || "*", value: filters[0].value, filters, ...(nth === undefined ? {} : { nth }) };
}
function findElements(selector, includeHidden = false) {
  selector = compatibleSelector(selector);
  const reason = hiddenReason;
  const text = (el) => (includeHidden && reason(el) ? el.textContent : typeof el.innerText === "string" ? el.innerText : el.textContent || "").trim().replace(/\s+/g, " ");
  let all = [...document.querySelectorAll(selector.kind === "css" ? selector.value : selector.css || "*")];
  if (selector.kind === "filtered-text") {
    all = all.filter((el) => !el.closest("script,style,template,noscript,head") && selector.filters.every((f) => {
      const wanted = f.value.trim().replace(/\s+/g, " ");
      return f.exact ? text(el) === wanted : text(el).includes(wanted);
    }));
    // Unscoped text lookup uses the existing deepest-text-first behavior instead of clicking body.
    if (selector.css === "*") all.sort((a, b) => {
      const depth = (el) => { let n = 0; for (; el; el = el.parentElement) n++; return n; };
      return depth(b) - depth(a);
    });
  }
  if (selector.nth !== undefined) {
    const index = selector.nth < 0 ? all.length + selector.nth : selector.nth;
    all = index >= 0 && index < all.length ? [all[index]] : [];
  }
  const visible = all.filter((el) => !reason(el));
  if (selector.kind === "css" || selector.kind === "filtered-text") return includeHidden ? all : visible;
  const wanted = selector.value.trim().replace(/\s+/g, " ");
  const match = (pool) => {
    // Script literals and metadata are not page text, including in hidden-match diagnostics.
    pool = pool.filter((el) => !el.closest("script,style,template,noscript,head"));
    let found = pool.filter((el) => text(el) === wanted);
    if (!found.length) found = pool.filter((el) => text(el).includes(wanted));
    const depth = (el) => { let n = 0; for (; el; el = el.parentElement) n++; return n; };
    found.sort((a, b) => depth(b) - depth(a) || Number(b.matches("button,a,[role=button],input,label,summary,[tabindex]")) - Number(a.matches("button,a,[role=button],input,label,summary,[tabindex]")));
    return found;
  };
  return includeHidden ? match(all) : match(visible).slice(0, 1);
}
const findSource = findElements.toString().replace("selector = compatibleSelector(selector);", "selector = (" + compatibleSelector.toString() + ")(selector);")
  .replace("const reason = hiddenReason;", "const reason = " + hiddenReason.toString() + ";");
async function locate(selector, context, scroll = true, action = "click", params = {}) {
  const result = await evaluate(String.raw`((selector) => {
    const find = ${findSource}, reason = ${hiddenReason.toString()};
    let found, usable;
    try { found = find(selector, true); usable = find(selector); } catch (error) { return { invalid: true, detail: error.message, selectorExample: error.selectorExample }; }
    const el = usable[0];
    if (el) {
      let r = el.getBoundingClientRect();
      if (${scroll} && (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth)) {
        el.scrollIntoView({ block: "center", inline: "center" }); r = el.getBoundingClientRect();
      }
      const x = Math.max(1, Math.min(innerWidth - 1, r.left + r.width / 2)), y = Math.max(1, Math.min(innerHeight - 1, r.top + r.height / 2));
      const warnings = [];
      if (${scroll && ["click", "dblclick", "hover"].includes(action)}) {
        const identify = (element) => {
          const parts = [];
          for (let e = element; e; e = e.parentElement) {
            let part = e.localName;
            if (e.id) part += "#" + CSS.escape(e.id);
            else {
              part += [...e.classList].slice(0, 3).map((c) => "." + CSS.escape(c)).join("");
              const siblings = e.parentElement ? [...e.parentElement.children].filter((s) => s.localName === e.localName) : [e];
              if (siblings.length > 1) part += ":nth-of-type(" + (siblings.indexOf(e) + 1) + ")";
            }
            parts.unshift(part);
            if (document.querySelectorAll(parts.join(" > ")).length === 1) break;
          }
          return parts.join(" > ");
        };
        const top = document.elementFromPoint(x, y);
        if (top && top !== el && !el.contains(top)) warnings.push("中心点被 " + identify(top) + " 挡住，动作仍照常执行");
        const disabled = [];
        if (el.hasAttribute("disabled") || el.matches(":disabled")) disabled.push("disabled");
        if (el.getAttribute("aria-disabled")?.toLowerCase() === "true") disabled.push('aria-disabled="true"');
        if (getComputedStyle(el).pointerEvents === "none") disabled.push("pointer-events: none");
        if (disabled.length) warnings.push("目标处于禁用状态（" + disabled.join("、") + "），动作仍照常执行");
      }
      return { x, y, warnings };
    }
    const hints = [], suggestions = [];
    const css = selector.kind === "css" ? selector.value : selector.css || "";
    const attrs = [...css.matchAll(/\[([^\s~|^$*!=\]]+)(?:[^\]]*)\]/g)].map((m) => m[1]);
    for (const attr of selector.kind === "css" ? [...new Set(attrs)] : []) {
      const candidates = [...document.querySelectorAll("*")].filter((e) => e.hasAttribute(attr));
      candidates.sort((a, b) => Number(!!reason(a)) - Number(!!reason(b)));
      const seen = new Set();
      for (const e of candidates) {
        const value = e.getAttribute(attr); if (seen.has(value)) continue; seen.add(value);
        const query = "[" + CSS.escape(attr) + "=" + JSON.stringify(value) + "]";
        if (hints.length < 5) hints.push(attr + "=" + JSON.stringify(value) + (reason(e) ? "（不可见）" : ""));
        if (!reason(e)) suggestions.push(query);
      }
      if (!candidates.length && hints.length < 5) hints.push("页面没有属性 " + attr);
    }
    if (selector.kind !== "css") {
      const distance = ${distance.toString()};
      const texts = [...new Set([...document.querySelectorAll("body *")].filter((e) => !reason(e))
        .map((e) => (typeof e.innerText === "string" ? e.innerText : e.textContent || "").trim().replace(/\s+/g, " ")).filter((t) => t && t.length < 160))];
      const wanted = selector.value.trim().replace(/\s+/g, " ");
      const contains = (t) => t.includes(wanted) || wanted.includes(t);
      texts.sort((a, b) => Number(contains(b)) - Number(contains(a)) || distance(a, wanted) - distance(b, wanted));
      hints.push(...texts.slice(0, 5).map((t) => "可见文字 " + JSON.stringify(t)));
      suggestions.push(...texts.slice(0, 5).map((t) => "text=" + JSON.stringify(t)));
    }
    if (!hints.length) {
      const prefix = css.replace(/\s*[^\s]+$/, "").replace(/[>+~]\s*$/, "").trim();
      let matches = []; try { if (prefix) matches = [...document.querySelectorAll(prefix)]; } catch {}
      hints.push("去掉最后一段后 " + JSON.stringify(prefix || "（空）") + " 匹配 " + matches.length + " 个元素");
      if (matches.some((e) => !reason(e))) suggestions.push(prefix);
    }
    const closed = found[0]?.closest("details:not([open])"), summary = closed?.querySelector(":scope > summary");
    const opener = summary && !reason(summary) ? (closed.id ? "#" + CSS.escape(closed.id) + " > summary" : "details:not([open]) > summary") : null;
    let iframes = 0, shadowRoots = 0;
    if (!found.length) {
      const roots = [document];
      for (let i = 0; i < roots.length; i++) for (const e of roots[i].querySelectorAll("*")) {
        if (e.localName === "iframe") iframes++;
        if (e.shadowRoot) { shadowRoots++; roots.push(e.shadowRoot); }
      }
    }
    return { opener, missing: !found.length, count: found.length, reasons: [...new Set(found.map(reason))].slice(0, 5), hints: hints.slice(0, 5), suggestion: suggestions[0], iframes, shadowRoots };
  })(${JSON.stringify(selector)})`);
  const source = selector.kind === "css" ? selector.value : selector.kind === "text" ? `text=${selector.value}` : `${selector.css}:has-text(${JSON.stringify(selector.value)})`;
  const suffix = action === "drag" ? ` ${params.dx ?? 0} ${params.dy ?? 0}` : ["type", "fill"].includes(action) ? ` ${JSON.stringify(params.text ?? "文字")}` : action === "select" ? ` ${JSON.stringify(params.value ?? "选项")}` : "";
  const example = result.opener && !result.suggestion ? `click ${result.opener}` : `${action} ${result.suggestion || (selector.kind === "css" ? ".open" : 'text="Send money"')}${suffix}`;
  if (result.invalid && result.detail?.startsWith("无法转换选择器")) {
    const selectorExample = ["type", "fill", "select"].includes(action) ? JSON.stringify(result.selectorExample) : result.selectorExample;
    const rewrite = context === "--mark" ? `--mark ${quoteArg(`1=${result.selectorExample}`)}` : `${action} ${selectorExample}${suffix}`;
    throw new Error(`${context}：${result.detail}；例如 ${rewrite}`);
  }
  if (result.invalid) throw new Error(`${context}：收到 ${source}，不是合法的 CSS；支持文字写法 text="Send money" 和 button:has-text("Undo")，例如 ${action} text="Send money"${suffix}`);
  const scope = result.iframes || result.shadowRoots ? `；选择器只在主文档里找，页面里有 ${result.iframes} 个 iframe、${result.shadowRoots} 个开放的 shadow root` : "";
  if (result.missing) throw new Error(`${context}：找不到元素 ${source}；线索：${result.hints.join("；")}；例如 ${example}${scope}`);
  if (result.count) throw new Error(`${context}：匹配到 ${result.count} 个元素 ${source}，但都不可见，不能操作（${result.reasons.join("；")}）；先执行让它出现的那一步，或换成当前可见的元素；线索：${result.hints.join("；")}；例如 ${example}`);
  for (const warning of result.warnings || []) {
    const message = `${context}：${warning}`;
    problems.push(message); console.log(`提示：${message}`);
  }
  return result;
}
const KEYS = { ArrowUp: 38, ArrowDown: 40, ArrowLeft: 37, ArrowRight: 39, Enter: 13, Escape: 27, Tab: 9, " ": 32, Space: 32, Home: 36, End: 35, PageUp: 33, PageDown: 34, Backspace: 8, Delete: 46 };
const mouse = (type, x, y, extra = {}) => cdp("Input.dispatchMouseEvent", { type, x, y, button: "left", pointerType: "mouse", ...extra });
async function runSteps(steps = [], observer = {}) {
  for (const [i, step] of steps.entries()) {
    const { action, selector, params } = step;
    const context = `第 ${i + 1} 步「${step.raw}」`;
    await during(`${currentContext} / ${context}`, async () => {
      await observer.step?.(step, i);
      if (action === "wait") { await sleep(params.ms); return; }
      if (action === "waitfor") {
        const end = Date.now() + timeoutMs(5000);
        while (true) {
          try { await locate(selector, context, false, action, params); break; }
          catch (error) { if ((!error.message.includes("找不到元素") && !error.message.includes("都不可见")) || Date.now() >= end) throw error; await sleep(100); }
        }
        return;
      }
      if (["click", "hover", "dblclick", "drag"].includes(action)) {
        const p = await locate(selector, context, true, action, params);
        await mouse("mouseMoved", p.x, p.y);
        if (action === "hover") { await sleep(200); return; }
        await observer.before?.(step, i);
        await mouse("mousePressed", p.x, p.y, { clickCount: 1, buttons: 1 });
        if (action === "drag") {
          for (let n = 1; n <= 24; n++) { await mouse("mouseMoved", p.x + params.dx * n / 24, p.y + params.dy * n / 24, { buttons: 1 }); await sleep(16); }
          await mouse("mouseReleased", p.x + params.dx, p.y + params.dy, { clickCount: 1 });
        } else {
          await mouse("mouseReleased", p.x, p.y, { clickCount: 1 });
          if (action === "dblclick") {
            await mouse("mousePressed", p.x, p.y, { clickCount: 2 }); await mouse("mouseReleased", p.x, p.y, { clickCount: 2 });
          }
        }
        await observer.after?.(step, i);
        await sleep(120);
      } else if (["type", "fill", "select"].includes(action)) {
        await locate(selector, context, false, action, params);
        await observer.before?.(step, i);
        await evaluate(`(() => {
          const el = (${findSource})(${JSON.stringify(selector)})[0];
          el.focus();
          ${action === "select" ? `if (!(el instanceof HTMLSelectElement)) throw new Error(${JSON.stringify(`${context}：select 需要原生下拉框；例如 select #country China`)});
          const option = [...el.options].find((o) => o.value === ${JSON.stringify(params.value)}) || [...el.options].find((o) => o.textContent.trim() === ${JSON.stringify(params.value)});
          if (!option) throw new Error(${JSON.stringify(`${context}：找不到下拉选项 ${params.value}；例如 select #country China`)});
          el.value = option.value; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));` : action === "fill" ? `
          if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
            const prototype = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
            const set = Object.getOwnPropertyDescriptor(prototype, "value").set;
            set.call(el, ""); set.call(el, ${JSON.stringify(params.text)});
          } else if (el.isContentEditable) {
            el.replaceChildren(); el.textContent = ${JSON.stringify(params.text)};
            const range = document.createRange(); range.selectNodeContents(el); range.collapse(false);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
          } else throw new Error(${JSON.stringify(`${context}：fill 需要输入框、文本域或可编辑元素；例如 fill #message "hello world"`)});
          el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));` : ""}
          return true;
        })()`);
        if (action === "type") await cdp("Input.insertText", { text: params.text });
        await observer.after?.(step, i);
        await sleep(120);
      } else if (action === "key") {
        const modifiers = params.modifiers.reduce((n, k) => n | ({ Alt: 1, Control: 2, Meta: 4, Shift: 8, ControlOrMeta: process.platform === "darwin" ? 4 : 2 })[k], 0);
        const key = params.key === "Space" ? " " : params.key;
        const code = KEYS[params.key] ?? key.toUpperCase().charCodeAt(0);
        const event = { key, code: /^[a-z]$/i.test(key) ? `Key${key.toUpperCase()}` : /^\d$/.test(key) ? `Digit${key}` : params.key, windowsVirtualKeyCode: code, modifiers };
        await observer.before?.(step, i);
        await cdp("Input.dispatchKeyEvent", { type: "keyDown", ...event, ...(modifiers & 4 && key.toLowerCase() === "a" ? { commands: ["selectAll"] } : {}) });
        await cdp("Input.dispatchKeyEvent", { type: "keyUp", ...event });
        await observer.after?.(step, i); await sleep(80);
      } else if (action === "scroll") { await evaluate(`scrollBy(0, ${params.dy}), true`); await sleep(200); }
    });
  }
}

// ---------- 本地拼图和录屏序列：共享同一份等比例排版 ----------
async function composeImages(items, file, columns, crop = null) {
  const example = stitching ? '--stitch before.png --stitch after.png --columns 2 --out shots' : 'page.html --record --frames 8 --columns 4 --out shots';
  const types = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif", ".bmp": "image/bmp", ".svg": "image/svg+xml" };
  const inputs = items.map((item, i) => {
    try { return { ...item, data: `data:${types[extname(item.path).toLowerCase()] || "application/octet-stream"};base64,${readFileSync(item.path).toString("base64")}` }; }
    catch (error) { throw new Error(`拼图第 ${i + 1} 张图片读取失败，收到 ${item.path}（${error.code || error.message}）；例如 --stitch before.png --label "修改前" --out shots`); }
  });
  // Render off the recorded page so its scripts, styles and fonts cannot alter the composition.
  await open("data:text/html,<meta charset=utf-8><meta http-equiv=Content-Security-Policy content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">", 0);
  const result = await evaluate(`(async (items, columns, crop) => {
    const images = await Promise.all(items.map((item, i) => new Promise((ok, no) => {
      const image = new Image(); image.onload = () => ok(image);
      image.onerror = () => no(new Error('拼图第 ' + (i + 1) + ' 张图片无法解码，收到 ' + item.path + '；例如 --stitch before.png --label "修改前" --out shots'));
      image.src = item.data;
    })));
    const margin = 24, gap = 16, lineHeight = 24;
    const normalized = !!crop || items.some((item) => item.matchWidth !== undefined || item.scale !== undefined);
    const regions = images.map((image, i) => {
      const scale = items[i].matchWidth !== undefined ? items[0].matchWidth / items[i].matchWidth : (items[i].scale ?? 1);
      const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
      if (![scale, width, height].every((n) => Number.isFinite(n) && n > 0)) throw new Error('拼图第 ' + (i + 1) + ' 张图片的比例过大或过小，收到 ' + scale + '；例如 ' + ${JSON.stringify(SCALE_EXAMPLE)});
      if (items[i].matchWidth > image.naturalWidth) throw new Error('拼图第 ' + (i + 1) + ' 张共有元素宽超出原图宽，收到 ' + items[i].matchWidth + '，原图宽 ' + image.naturalWidth + '；例如 ' + ${JSON.stringify(STITCH_EXAMPLE)});
      if (crop && (crop.x + crop.width > width + 1e-7 || crop.y + crop.height > height + 1e-7)) throw new Error('拼图第 ' + (i + 1) + ' 张裁切超出图片，收到 ' + JSON.stringify(crop) + '，统一比例后为 ' + width + '×' + height + '；缩小裁切范围或先去掉 --crop 查看整图，例如 ' + ${JSON.stringify(SCALE_EXAMPLE)});
      const region = crop || { x: 0, y: 0, width, height };
      return { scale, width: region.width, height: region.height,
        sourceCrop: { x: region.x / scale, y: region.y / scale, width: region.width / scale, height: region.height / scale } };
    });
    const widest = Math.max(...regions.map((region) => region.width));
    const cell = Math.ceil(Math.min(640, Math.max(items.some((item) => item.label) ? 160 : 1, widest)));
    // A single preview factor preserves the declared relationship, even for different image widths.
    const commonFit = Math.min(1, cell / widest);
    columns = Math.min(columns, images.length);
    const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
    const font = '18px "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
    ctx.font = font;
    const labels = items.map((item) => {
      if (!item.label) return [];
      return String(item.label).split(/\\r?\\n/).flatMap((paragraph) => {
        const lines = []; let line = '';
        for (const character of paragraph) {
          if (line && ctx.measureText(line + character).width > cell) { lines.push(line); line = ''; }
          line += character;
        }
        lines.push(line); return lines;
      });
    });
    const dimensions = images.map((image, i) => {
      const region = regions[i], fit = normalized ? commonFit : Math.min(1, cell / region.width);
      return { naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
        scale: region.scale, renderScale: region.scale * fit, sourceCrop: region.sourceCrop,
        ...(items[i].matchWidth !== undefined ? { matchWidth: items[i].matchWidth } : {}),
        width: Math.max(1, Math.round(region.width * fit)), height: Math.max(1, Math.round(region.height * fit)),
        labelHeight: labels[i].length ? 8 + labels[i].length * lineHeight : 0 };
    });
    const heights = [];
    dimensions.forEach((item, i) => { const row = Math.floor(i / columns); heights[row] = Math.max(heights[row] || 0, item.height + item.labelHeight); });
    canvas.width = columns * cell + (columns - 1) * gap + margin * 2;
    canvas.height = heights.reduce((sum, height) => sum + height, 0) + (heights.length - 1) * gap + margin * 2;
    if (canvas.width > 32767 || canvas.height > 32767 || canvas.width * canvas.height > 67108864) throw new Error('拼图画布过大，收到 ' + canvas.width + '×' + canvas.height + '；请减少图片/帧数或调整列数，例如 ' + ${JSON.stringify(example)});
    ctx.fillStyle = '#ececea'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = font; ctx.textBaseline = 'top';
    let top = margin;
    const layout = dimensions.map((item, i) => {
      const row = Math.floor(i / columns), column = i % columns;
      if (i && !column) top += heights[row - 1] + gap;
      const x = margin + column * (cell + gap) + Math.floor((cell - item.width) / 2);
      const source = item.sourceCrop;
      ctx.drawImage(images[i], source.x, source.y, source.width, source.height, x, top, item.width, item.height);
      ctx.fillStyle = '#333';
      labels[i].forEach((line, index) => ctx.fillText(line, margin + column * (cell + gap), top + item.height + 8 + index * lineHeight));
      return { ...item, x, y: top, label: items[i].label || '', labelY: top + item.height + 8 };
    });
    const data = canvas.toDataURL('image/png').split(',')[1];
    if (!data) throw new Error('拼图无法导出 PNG；请减少图片/帧数，例如 ' + ${JSON.stringify(example)});
    return { data, width: canvas.width, height: canvas.height, columns, ...(crop ? { crop } : {}), items: layout };
  })(${JSON.stringify(inputs)}, ${columns}, ${JSON.stringify(crop)})`);
  writeFileSync(file, Buffer.from(result.data, "base64"));
  const { data, ...layout } = result;
  return { file: basename(file), ...layout };
}

// ---------- 并排图：用同一个浏览器把截图排成一张 ----------
async function sheet(items, file, w, h) {
  const cell = Math.min(w, 420);
  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const figures = items.map(({ path, label }) =>
    `<figure><img src="data:image/png;base64,${readFileSync(path).toString("base64")}"><figcaption>${escapeHtml(label)}</figcaption></figure>`).join("");
  const html = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>body{margin:0;padding:32px;background:#ececea;font:13px -apple-system,"PingFang SC",sans-serif;color:#555}
main{display:flex;gap:24px;align-items:flex-start}figure{margin:0;width:${cell}px}img{width:100%;display:block;border-radius:12px;box-shadow:0 1px 3px #0002}
figcaption{margin-top:10px}</style><main>${figures}</main>`;
  const tmp = browser.tempFile("sheet.html");
  writeFileSync(tmp, html);
  const width = items.length * cell + (items.length - 1) * 24 + 64;
  await setViewport(width, Math.round((cell * h) / w) + 120, 1);
  await open(`file://${tmp}`);
  return screenshot(file, true);
}

// ---------- 对比图：截图还原时和参考图并排、叠加、出差异热图 ----------
const IMAGE_TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };
const CELLS = ["左上", "中上", "右上", "左中", "正中", "右中", "左下", "中下", "右下"];
async function compare(buildPath, refPath, file) {
  const ref = `data:${IMAGE_TYPES[extname(refPath).toLowerCase()]};base64,${readFileSync(refPath).toString("base64")}`;
  const build = `data:image/png;base64,${readFileSync(buildPath).toString("base64")}`;
  const html = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>body{margin:0;padding:28px;background:#ececea;font:13px -apple-system,"PingFang SC",sans-serif;color:#555}
main{display:grid;grid-template-columns:repeat(2,720px);gap:24px 20px;align-items:start}figure{margin:0}
canvas{width:100%;display:block;border-radius:8px;box-shadow:0 1px 3px #0002;background:#fff}figcaption{margin-top:8px}</style>
<main><figure><canvas id="ref"></canvas><figcaption>参考</figcaption></figure><figure><canvas id="build"></canvas><figcaption>当前</figcaption></figure>
<figure><canvas id="overlay"></canvas><figcaption>叠加（当前 50% 盖在参考上）</figcaption></figure><figure><canvas id="diff"></canvas><figcaption id="note">差异</figcaption></figure></main>
<script>(async () => {
  const load = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error("参考图打不开")); i.src = src; });
  const [ref, build] = await Promise.all([load(${JSON.stringify(ref)}), load(${JSON.stringify(build)})]);
  const W = build.naturalWidth, refH = Math.round(ref.naturalHeight * W / ref.naturalWidth), H = Math.min(refH, build.naturalHeight);
  const paint = (id, fn) => { const c = document.getElementById(id); c.width = W; c.height = H; const x = c.getContext("2d"); fn(x); return x; };
  paint("ref", (x) => x.drawImage(ref, 0, 0, W, refH));
  paint("build", (x) => x.drawImage(build, 0, 0));
  paint("overlay", (x) => { x.drawImage(ref, 0, 0, W, refH); x.globalAlpha = 0.5; x.drawImage(build, 0, 0); });
  // 缩到 480 宽再逐像素比颜色：任一通道差超过 0.1 算“有差异”，忽略抗锯齿和一两像素的错位
  const sw = 480, sh = Math.max(1, Math.round(H * sw / W));
  const sample = (img) => { const c = document.createElement("canvas"); c.width = sw; c.height = sh; const x = c.getContext("2d", { willReadFrequently: true });
    const k = img.naturalWidth / W; x.drawImage(img, 0, 0, img.naturalWidth, H * k, 0, 0, sw, sh); return x.getImageData(0, 0, sw, sh).data; };
  const a = sample(ref), b = sample(build);
  const lum = (d, i) => (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
  const heat = new ImageData(sw, sh), sums = Array(9).fill(0), counts = Array(9).fill(0);
  let total = 0;
  for (let y = 0; y < sh; y++) for (let x = 0; x < sw; x++) {
    const i = (y * sw + x) * 4, d = Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2])) / 255, cell = Math.min(2, Math.floor(y * 3 / sh)) * 3 + Math.min(2, Math.floor(x * 3 / sw));
    const hit = d > 0.1 ? 1 : 0;
    total += hit; sums[cell] += hit; counts[cell]++;
    const g = lum(b, i) * 255 * 0.35 + 150;
    heat.data[i] = hit ? 225 : g; heat.data[i + 1] = hit ? 40 : g; heat.data[i + 2] = hit ? 60 : g; heat.data[i + 3] = 255;
  }
  const small = document.createElement("canvas"); small.width = sw; small.height = sh; small.getContext("2d").putImageData(heat, 0, 0);
  const cells = sums.map((s, i) => +(100 * s / Math.max(1, counts[i])).toFixed(1));
  paint("diff", (x) => {
    x.drawImage(small, 0, 0, W, H);
    x.strokeStyle = "#0006"; x.lineWidth = Math.max(1, W / 420); x.fillStyle = "#111"; x.font = "600 " + Math.round(W / 22) + "px -apple-system,sans-serif";
    for (let i = 0; i < 9; i++) { const cx = (i % 3) * W / 3, cy = Math.floor(i / 3) * H / 3; x.strokeRect(cx, cy, W / 3, H / 3); x.fillText(cells[i] + "%", cx + W / 60, cy + W / 18); }
  });
  window.__compare = { overall: +(100 * total / (sw * sh)).toFixed(1), cells, refHeight: refH, buildHeight: build.naturalHeight };
})().catch((e) => { window.__compare = { error: e.message }; });</script>`;
  const tmp = browser.tempFile("compare.html");
  writeFileSync(tmp, html);
  await setViewport(2 * 720 + 20 + 56, 900, 1);
  await open(`file://${tmp}`);
  let result = null;
  for (let i = 0; i < 50 && !result; i++) { result = await evaluate(`window.__compare || null`); if (!result) await sleep(100); }
  if (!result || result.error) throw new Error(`对比图没做出来：${result?.error || "超时"}`);
  await screenshot(file, true);
  const worst = result.cells.map((v, i) => ({ v, i })).sort((x, y) => y.v - x.v).slice(0, 3).map(({ v, i }) => `${CELLS[i]} ${v}%`);
  const gap = Math.abs(result.refHeight - result.buildHeight) / result.buildHeight > 0.05
    ? `；参考图按宽度缩放后高 ${result.refHeight}px，截图高 ${result.buildHeight}px，只比了重叠部分` : "";
  return { file: basename(file), overall: result.overall, cells: Object.fromEntries(CELLS.map((c, i) => [c, result.cells[i]])),
    message: `${basename(file)}：差异明显的像素占 ${result.overall}%，最多的格子 ${worst.join("、")}${gap}` };
}

// 外部编码也异步运行，浏览器断开时不会被同步编码挡住。
function runFfmpeg(args, timeout) {
  return new Promise((ok) => {
    const child = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
    encoders.add(child);
    let stderr = "", done = false;
    const finish = (status, error) => {
      if (done) return; done = true; clearTimeout(timer); encoders.delete(child);
      ok({ status, stderr, error });
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(null, { code: "ETIMEDOUT" });
      child.stderr.destroy();
    }, timeoutMs(timeout));
    child.stderr.on("data", (data) => { stderr = (stderr + data).slice(-16384); });
    child.once("error", (error) => finish(null, error));
    child.once("close", (code) => finish(code));
  });
}

// ---------- 录屏 ----------
// Keep finite animation intervals even after a short feedback has finished. Runs before page scripts.
function recordTiming() {
  let baseline = new Set(), start = null, end = null, raf, active = true;
  function sample() {
    for (const a of document.getAnimations()) {
      if (baseline.has(a) || !a.effect || !a.playbackRate || typeof a.startTime !== "number") continue;
      const timing = a.effect.getComputedTiming(), rate = a.playbackRate;
      if (!Number.isFinite(timing.endTime) || a.playState === "paused" || !["DocumentTimeline", undefined].includes(a.timeline?.constructor.name)) continue;
      const zero = performance.timeOrigin + a.startTime;
      const first = Math.min(zero + timing.delay / rate, zero + timing.endTime / rate);
      const last = Math.max(zero + timing.delay / rate, zero + timing.endTime / rate);
      start = start === null ? first : Math.min(start, first);
      end = end === null ? last : Math.max(end, last);
    }
  }
  function tick() { if (!active) return; sample(); raf = requestAnimationFrame(tick); }
  window.__oilRecordTiming = {
    reset() { baseline = new Set(document.getAnimations()); start = end = null; },
    read() { if (active) sample(); return { start, end }; },
    stop() { active = false; cancelAnimationFrame(raf); },
  };
  tick();
}
async function frameDifference(first, second) {
  return evaluate(`(async () => {
    const load = (data) => new Promise((ok, no) => { const img = new Image(); img.onload = () => ok(img); img.onerror = () => no(new Error("录屏末帧无法解码")); img.src = "data:image/jpeg;base64," + data; });
    const a = await load(${JSON.stringify(readFileSync(first).toString("base64"))});
    const b = await load(${JSON.stringify(readFileSync(second).toString("base64"))});
    if (a.width !== b.width || a.height !== b.height) return { different: true, dimensions: [a.width, a.height, b.width, b.height] };
    const canvas = document.createElement("canvas"); canvas.width = a.width; canvas.height = a.height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(a, 0, 0); const p = ctx.getImageData(0, 0, a.width, a.height).data;
    ctx.clearRect(0, 0, a.width, a.height); ctx.drawImage(b, 0, 0); const q = ctx.getImageData(0, 0, b.width, b.height).data;
    const cols = Math.ceil(a.width / 32), tiles = new Uint32Array(cols * Math.ceil(a.height / 32));
    let changed = 0;
    for (let y = 0; y < a.height; y++) for (let x = 0; x < a.width; x++) {
      const i = (y * a.width + x) * 4;
      if ((Math.abs(p[i] - q[i]) + Math.abs(p[i + 1] - q[i + 1]) + Math.abs(p[i + 2] - q[i + 2])) / 3 > 32) {
        changed++; tiles[Math.floor(y / 32) * cols + Math.floor(x / 32)]++;
      }
    }
    const maxTile = tiles.reduce((n, v) => Math.max(n, v), 0);
    return { different: changed >= 32 && (changed / (a.width * a.height) > .005 || maxTile >= 48), changedPixels: changed, maxTilePixels: maxTile, pixelRatio: changed / (a.width * a.height) };
  })()`);
}
function sequenceFrames(frames, finished, count) {
  const start = frames[0].t, duration = Math.max(0, finished - start);
  let index = 0;
  return Array.from({ length: count }, (_, i) => {
    const time = start + duration * i / (count - 1);
    // A screencast emits only changed images: hold the preceding frame, never a future one.
    while (index + 1 < frames.length && frames[index + 1].t <= time) index++;
    return { path: frames[index].name, timeMs: Math.round((time - start) * 1000), sourceTimeMs: Math.max(0, Math.round((frames[index].t - start) * 1000)) };
  });
}
function screencastList(frames, finished) {
  // JPEG's default 25fps time base rounds timestamps and can discard a short feedback frame.
  // Use the same millisecond precision as the durations before resampling the video to 30fps.
  const file = (frame) => `file '${basename(frame.name)}'\noption framerate 1000`;
  // Keep a full 30fps output frame of the final still even when recording ends between ticks.
  return frames.map((f, i) => `${file(f)}\nduration ${Math.max(i === frames.length - 1 ? 0.034 : 0.016, ((frames[i + 1]?.t ?? finished) - f.t)).toFixed(3)}`).join("\n") + `\n${file(frames.at(-1))}\n`;
}
async function record(url, w, h, { steps = [], name = "", entry = flags.has("entry"), zoom = zooms[0] } = {}) {
  const video = `record${name ? "-" + name : ""}.mp4`;
  const motion = `motion${name ? "-" + name : ""}`;
  const frames = [];
  const dir = join(out, name ? `frames-${name}` : "frames");
  mkdirSync(dir, { recursive: true }); temporaryFrames.add(dir);
  let identifier, actionStart, actionEnd, beforeAction, painted = 0;
  const lastAction = steps.findLastIndex((s) => ["click", "dblclick", "drag", "type", "fill", "select", "key"].includes(s.action));
  const captureFrame = async (label) => {
    const { data } = await cdp("Page.captureScreenshot", { format: "jpeg", quality: 88 });
    const frame = { name: join(dir, `${label}.jpg`), t: Date.now() / 1000, source: "Page.captureScreenshot" };
    writeFileSync(frame.name, Buffer.from(data, "base64")); return frame;
  };
  const onFrame = (m) => {
    if (transportFailure || m.sessionId !== sessionId || m.method !== "Page.screencastFrame") return;
    const name = join(dir, `f${String(frames.length).padStart(4, "0")}.jpg`);
    writeFileSync(name, Buffer.from(m.params.data, "base64"));
    frames.push({ name, t: Math.max(frames.at(-1)?.t || 0, m.params.metadata.timestamp), source: "Page.screencastFrame" });
    cdp("Page.screencastFrameAck", { sessionId: m.params.sessionId }).catch(() => {});
  };
  try {
    await setViewport(w, h, zoom);
    ({ identifier } = await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(${recordTiming.toString()})()` }));
    if (entry) {
      // 起始的空白页自己写明白底：系统是深色主题时，浏览器会把 about:blank 画成深灰，同一段录屏换台机器开头就不一样。
      await open("data:text/html,<html style='background:%23fff'>", 0);
      // Seed the video with a painted blank page, never the preceding evidence item.
      frames.push(await captureFrame("blank"));
    } else await open(url);
    listeners.push(onFrame);
    await cdp("Page.startScreencast", { format: "jpeg", quality: 88, everyNthFrame: 1 });
    if (entry) {
      await sleep(50);
      await open(url);
      painted = await evaluate(`(() => { const p = performance.getEntriesByName("first-contentful-paint")[0] || performance.getEntriesByType("paint")[0]; return (performance.timeOrigin + (p?.startTime || 0)) / 1000; })()`);
    } else await sleep(500);
    await runSteps(steps, {
      step: async (step, i) => {
        // A later hover or scroll can have its own animation; it is not this action's feedback.
        if (lastAction >= 0 && i > lastAction && ["hover", "scroll"].includes(step.action)) await evaluate(`(__oilRecordTiming.stop(), true)`);
      },
      before: async (_, i) => {
        if (i !== lastAction) return;
        beforeAction = await captureFrame("before-action");
        await evaluate(`(__oilRecordTiming.reset(), true)`);
        actionStart = Date.now() / 1000;
      },
      after: async (_, i) => { if (i === lastAction) actionEnd = Date.now() / 1000; },
    });
    if (entry && lastAction < 0) await settleAnimations(2000);
    await sleep(Number(opt.hold));
    const finished = Date.now() / 1000;
    const final = await captureFrame("hold-end");
    if (final) final.t = finished;
    const streamEnd = frames.filter((frame) => frame.t <= finished).at(-1);
    const warnings = [];
    let consistency = { status: "unavailable", reference: `${motion}-end.jpg` };
    if (streamEnd) {
      const difference = await frameDifference(streamEnd.name, final.name);
      consistency = { status: "matched", reference: `${motion}-end.jpg`, ...difference };
      if (difference.different) {
        // Confirm the page is still before attributing the mismatch to the stream. No frame comparison can prove intermediate motion is correct.
        await sleep(100);
        const verification = await captureFrame("verification");
        const stability = await frameDifference(final.name, verification.name);
        consistency.status = stability.different ? "moving" : "mismatch";
        if (!stability.different) {
          const original = `record${name ? "-" + name : ""}-stream-end.jpg`;
          writeFileSync(join(out, original), readFileSync(streamEnd.name));
          consistency.original = original;
          warnings.push(`录屏末帧与静止截图差异明显，可能没拍全；静止终态以 ${motion}-end.jpg 为准，已补为录像最后一帧，原末帧保留在 ${original}；过渡请单独重录：${currentRetryCommand} --hold 2000`);
        }
      }
    }
    const feedback = await evaluate(`__oilRecordTiming.read()`);
    const issues = await check();
    await cdp("Page.stopScreencast");
    listeners.splice(listeners.indexOf(onFrame), 1);
    if (!frames.length) throw new Error("录屏没有拿到画面");
    if (final) {
      // The stream may deliver a frame from after --hold while checks are running.
      while (frames.length > 1 && frames.at(-1).t > finished) frames.pop();
      // Plain recordings keep their original head/middle/tail samples when the two paths agree.
      if (entry || lastAction >= 0 || consistency.different) frames.push(final);
    }
    const nearest = (time, pool = frames) => pool.reduce((best, f) => Math.abs(f.t - time) < Math.abs(best.t - time) ? f : best);
    let pick, sampling;
    if (lastAction >= 0) {
      const from = Math.max(actionStart, (feedback.start ?? actionStart * 1000) / 1000);
      const to = Math.max(from, Math.min(finished, (feedback.end ?? (actionEnd * 1000 + 200)) / 1000));
      const candidates = [...frames.filter((f) => f.t >= actionStart && f.t <= finished), final];
      pick = { start: beforeAction, mid: nearest((from + to) / 2, candidates), end: final };
      sampling = { mode: "action", step: lastAction + 1, action: steps[lastAction].action, raw: steps[lastAction].raw };
    } else if (entry) {
      const content = frames.filter((f) => f.t >= painted);
      const from = content[0]?.t ?? final.t;
      const to = Math.max(from, Math.min(finished, (feedback.end ?? finished * 1000) / 1000));
      pick = { start: content[0] || final, mid: nearest((from + to) / 2, [...content, final]), end: final };
      sampling = { mode: "entry" };
    } else {
      pick = { start: frames[0], mid: frames[Math.floor(frames.length / 2)], end: frames[frames.length - 1] };
      sampling = { mode: "recording" };
    }
    for (const [k, f] of Object.entries(pick)) writeFileSync(join(out, `${motion}-${k}.jpg`), readFileSync(f.name));
    const frameReport = Object.fromEntries(Object.entries(pick).map(([k, f]) => [k, {
      file: `${motion}-${k}.jpg`, source: f.source, timeMs: Math.max(0, Math.round((f.t - frames[0].t) * 1000)),
    }]));
    const details = { frames: frameReport, sampling, consistency, warnings, durationMs: Math.round((finished - frames[0].t) * 1000) };
    let sequenceMessage = "";
    if (opt.frames !== undefined) {
      const samples = sequenceFrames(frames, finished, Number(opt.frames));
      const sequence = await during(`${currentContext} / 录屏多帧序列`, () => composeImages(samples.map((frame) => ({ ...frame, label: `${(frame.timeMs / 1000).toFixed(3)} s` })), join(out, `${motion}-sequence.png`), Number(opt.columns || Math.min(4, samples.length))));
      details.sequence = { ...sequence, frames: samples.map(({ path, ...time }) => time) };
      sequenceMessage = ` 和 ${sequence.file}`;
    }
    if (opt.frames !== undefined && !flags.has("record")) return { issues, ...details, message: `序列图：${details.sequence.file}（${(finished - frames[0].t).toFixed(1)} 秒），未编码视频` };
    const ffmpeg = (await runFfmpeg(["-version"], 5000)).status === 0;
    if (!ffmpeg) return { issues, ...details, failed: true, message: `录屏：没装 ffmpeg，只留了 ${motion}-start/mid/end.jpg 三帧${sequenceMessage}` };
    // Generated basenames are safe for concat's quoting, even when --out contains an apostrophe.
    // Keep the final still frame through the end of --hold; screencasts only emit changed frames.
    const list = screencastList(frames, finished);
    writeFileSync(join(dir, "list.txt"), list);
    const r = await runFfmpeg(["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", join(dir, "list.txt"),
      "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30", "-pix_fmt", "yuv420p", join(out, video)], 60000);
    if (r.status !== 0) return { issues, ...details, failed: true, message: `录屏：ffmpeg 合成失败（${r.error?.code === "ETIMEDOUT" ? `${60 * timeoutScale} 秒内没有合成完成` : r.error?.message || r.stderr.trim().split("\n").pop()}），已保留 ${motion}-start/mid/end.jpg 三帧${sequenceMessage}` };
    rmSync(dir, { recursive: true, force: true });
    return { issues, ...details, message: `录屏：${video}（${(finished - frames[0].t).toFixed(1)} 秒）和 ${motion}-start/mid/end.jpg${sequenceMessage}` };
  } finally {
    const index = listeners.indexOf(onFrame); if (index >= 0) listeners.splice(index, 1);
    try { if (!transportFailure && !browserNeedsRestart) await cdp("Page.stopScreencast"); }
    finally {
      try {
        if (!transportFailure && !browserNeedsRestart) {
          await evaluate(`(window.__oilRecordTiming?.stop(), delete window.__oilRecordTiming, true)`);
          if (identifier) await cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier });
        }
      } finally { rmSync(dir, { recursive: true, force: true }); temporaryFrames.delete(dir); }
    }
  }
}


// ---------- 动效探测 ----------
// Runs before page scripts: records which elements animate in each phase and how far they move.
const MOTION_PROBE = `(() => {
  if (window.__oilMotion) return;
  const tracked = new Map();
  let phase = "load";
  const seen = new Set();
  function touch(el, source) {
    if (!(el instanceof Element) || el.id === "oil-mask") return;
    let t = tracked.get(el);
    if (!t) { if (tracked.size >= 400) return; t = { phases: {} }; tracked.set(el, t); }
    let p = t.phases[phase];
    if (!p) p = t.phases[phase] = { first: null, last: null, frames: 0, move: 0, size: 0, opacity: 0, sources: new Set() };
    p.sources.add(source);
    if (source.startsWith("js:")) t.lastJs = performance.now();
  }
  addEventListener("animationstart", (e) => touch(e.target, "css:" + e.animationName), true);
  addEventListener("transitionrun", (e) => touch(e.target, "transition:" + e.propertyName), true);
  new MutationObserver((list) => { for (const m of list) touch(m.target, "js:" + m.attributeName); })
    .observe(document, { subtree: true, attributes: true, attributeFilter: ["style", "transform", "viewBox", "d", "x", "y", "cx", "cy", "r", "points", "opacity", "stroke-dashoffset"] });
  // 首屏阶段按视口坐标量：被固定住的舞台不算在动，舞台里的层次变化才算。
  function read(el) {
    const r = el.getBoundingClientRect();
    const page = phase === "hero" ? 0 : 1;
    return { x: r.left + scrollX * page, y: r.top + scrollY * page, w: r.width, h: r.height, o: +getComputedStyle(el).opacity };
  }
  function sample() {
    if (document.getAnimations) for (const a of document.getAnimations()) {
      if (a.playState !== "running" || !a.effect || !a.effect.target) continue;
      const tl = a.timeline && a.timeline.constructor && a.timeline.constructor.name;
      const scrollLinked = tl === "ScrollTimeline" || tl === "ViewTimeline";
      if (scrollLinked) touch(a.effect.target, "scroll-timeline:" + (a.animationName || "animation"));
      else if (!seen.has(a)) { seen.add(a); if (!a.animationName && !a.transitionProperty) touch(a.effect.target, "waapi"); }
    }
    for (const [el, t] of tracked) {
      const p = t.phases[phase];
      if (!p || !el.isConnected) continue;
      const now = read(el);
      if (!p.first) { p.first = p.last = now; continue; }
      const l = p.last;
      if (Math.abs(now.x - l.x) + Math.abs(now.y - l.y) + Math.abs(now.w - l.w) + Math.abs(now.h - l.h) > 0.1 || Math.abs(now.o - l.o) > 0.005) p.frames++;
      p.last = now;
      p.move = Math.max(p.move, Math.hypot(now.x - p.first.x, now.y - p.first.y));
      p.size = Math.max(p.size, Math.abs(now.w - p.first.w) / Math.max(1, p.first.w), Math.abs(now.h - p.first.h) / Math.max(1, p.first.h));
      p.opacity = Math.max(p.opacity, Math.abs(now.o - p.first.o));
    }
    requestAnimationFrame(sample);
  }
  requestAnimationFrame(sample);
  window.__oilMotion = {
    setPhase(next) { phase = next; },
    summary(name) {
      const items = [];
      for (const [el, t] of tracked) {
        const p = t.phases[name];
        if (!p) continue;
        const label = el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\\s+/).slice(0, 2).join(".") : "");
        const infinite = el.getAnimations ? el.getAnimations().some((a) => a.effect && a.effect.getTiming && a.effect.getTiming().iterations === Infinity) : false;
        const loop = infinite || (t.lastJs && performance.now() - t.lastJs < 250);
        if (p.frames < 3) continue; // one-off jumps are state writes, not motion
        items.push({ el: label, move: Math.round(p.move), size: +p.size.toFixed(3), opacity: +p.opacity.toFixed(2), loop: !!loop, sources: [...p.sources].slice(0, 3) });
      }
      const visible = items.filter((i) => ((name !== "scroll" && name !== "hero") || !i.loop) && (i.move >= 1 || i.size >= 0.005 || i.opacity >= 0.05 || i.sources.some((s) => s.startsWith("scroll-timeline"))));
      visible.sort((a, b) => (b.move + b.size * 400 + b.opacity * 40) - (a.move + a.size * 400 + a.opacity * 40));
      return {
        elements: visible.length,
        loops: visible.filter((i) => i.loop).length,
        maxMove: Math.max(0, ...visible.map((i) => i.move)),
        maxSize: Math.max(0, ...visible.map((i) => i.size)),
        maxOpacity: Math.max(0, ...visible.map((i) => i.opacity)),
        top: visible.slice(0, 8),
      };
    },
  };
})()`;

async function probeMotion(url, w, h, steps = []) {
  const { identifier } = await cdp("Page.addScriptToEvaluateOnNewDocument", { source: MOTION_PROBE });
  try {
    problems = [];
    await setViewport(w, h, 1);
    await open(url);
    await sleep(1200);
    const phases = { load: await evaluate(`__oilMotion.summary("load")`) };
    if (steps.length) {
      await evaluate(`__oilMotion.setPhase("steps"), true`);
      await runSteps(steps);
      await sleep(900);
      phases.steps = await evaluate(`__oilMotion.summary("steps")`);
    }
    await evaluate(`(scrollTo(0, 0), __oilMotion.setPhase("hero"), true)`);
    await sleep(150);
    const height = await evaluate(`document.documentElement.scrollHeight - innerHeight`);
    const scrollable = height > 4;
    const heroEnd = Math.min(height, Math.round(h * 1.5));
    for (let y = 0; y <= heroEnd; y += Math.round(h / 10)) { await evaluate(`scrollTo(0, ${y}), true`); await sleep(70); }
    await sleep(400);
    phases.hero = await evaluate(`__oilMotion.summary("hero")`);
    await evaluate(`(__oilMotion.setPhase("scroll"), true)`);
    for (let y = heroEnd; y < height; y += Math.round(h / 4)) { await evaluate(`scrollTo(0, ${y}), true`); await sleep(90); }
    await evaluate(`scrollTo(0, ${height}), true`);
    await sleep(600);
    phases.scroll = await evaluate(`__oilMotion.summary("scroll")`);

    const issues = [];
    const names = { load: "首次进入", steps: "--steps 动作", hero: "首屏滚动", scroll: "从头滚到底" };
    const weak = (p) => p.maxMove < 4 && p.maxSize < 0.02 && p.maxOpacity < 0.3;
    for (const [k, p] of Object.entries(phases)) {
      // 首屏景深是可选手法：只报告层数和幅度，供选了它的页面核对，不记为问题。
      if (k === "hero") {
        p.layers = p.top.filter((i) => i.size >= 0.05 || i.move >= h * 0.05).length;
        continue;
      }
      if (k === "scroll") {
        p.scrollable = scrollable;
        if (!p.elements && scrollable) issues.push("滚动：没有检测到随滚动出现的变化；落地页、品牌页、发布页和展览页需要一段滚动叙事");
        continue;
      }
      if (!p.elements) issues.push(`${names[k]}：没有检测到动画${k === "load" && !steps.length ? "；交互动效要配 --steps 才能探测到" : ""}`);
      else if (p.loops === p.elements) issues.push(`${names[k]}：只有持续循环的动画，没有一次性的${k === "load" ? "出场" : "反馈"}`);
      else if (weak(p)) issues.push(`${names[k]}：动画幅度太小，看不出来（最大位移 ${p.maxMove}px，尺寸变化 ${(p.maxSize * 100).toFixed(1)}%，透明度变化 ${p.maxOpacity}）`);
    }
    const brief = (k, p) => k === "scroll" && !p.scrollable ? "页面不滚动，跳过滚动检查" : k === "hero" ? `首屏滚动 ${p.layers} 层在变，最大缩放 ${(p.maxSize * 100).toFixed(1)}%，最大位移 ${p.maxMove}px`
      : `${names[k]} ${p.elements} 个元素在动，最大位移 ${p.maxMove}px，透明度变化 ${p.maxOpacity}`;
    return { phases, issues: [...problems, ...issues], message: "动效探测：" + Object.entries(phases).map(([k, p]) => brief(k, p)).join("；") };
  } finally { await cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier }); }
}

// ---------- 主流程 ----------
const bases = [];
for (const candidate of targets) bases.push(await resolveTarget(candidate.target));
let base = bases[0], activeTarget = targets[0];
const withState = (s) => {
  const u = new URL(base);
  const query = new URLSearchParams(opt.query || "");
  for (const key of new Set(query.keys())) u.searchParams.delete(key);
  for (const [key, value] of query) u.searchParams.append(key, value);
  if (s) u.searchParams.set(opt.param, s);
  return u.toString();
};
const report = [], lines = [];
const usedFiles = new Set();
const targetShots = [];
const autoSheet = targets.length > 1 && !flags.has("no-sheet") && (!captureMotion || flags.has("evidence"));
if (autoSheet) usedFiles.add("sheet.png");
const candidatePrefix = () => batchMode ? targetStem(activeTarget) : "";
function reserveFamily(preferred, files) {
  let name = preferred, n = 2;
  while (files(name).some((file) => usedFiles.has(file))) name = `${preferred ? preferred + "-" : ""}${n++}`;
  files(name).forEach((file) => usedFiles.add(file));
  if (name !== preferred) notices.push(`文件名冲突，已区分：${files(preferred)[0]} → ${files(name)[0]}`);
  return name;
}
saveFatalReport = (error) => {
  report.push({ file: "browser", failed: true, issues: [...problems, error.message] });
  writeFileSync(join(out, "report.json"), JSON.stringify(report, null, 2));
};
const evidence = flags.has("evidence");
// One completed item produces one stderr progress line; stdout keeps its existing summary.
let completed = 0, progressTotal = 0;
function progress(file, failed = false) {
  console.error(`[${++completed}/${progressTotal}] ${file} ${failed === "skipped" ? "跳过，已记入报告" : failed ? "失败，已记入报告" : "完成"}`);
}
function skipped(file, metadata, reason) {
  report.push({ file, ...metadata, skipped: true, issues: [reason] });
  lines.push(`${file}  ⚠ 跳过：${reason}`); progress(file, "skipped");
}
function retryItem(file, metadata, extra = "") {
  const group = groups.find((g) => g.reportName === (metadata.group || "") && !(evidence && file.endsWith(".png")));
  const steps = group?.steps.length ? (group.reportName ? group.reportName + ": " : "") + group.steps.map((s) => s.raw).join("; ") : "";
  const variant = file.endsWith("-masked.png") ? " --mask" : file.endsWith("-marked.png") ? ` --mark ${quoteArg(opt.mark)}` : file.endsWith("-compare.png") ? ` --compare ${quoteArg(refImage)}` : "";
  const isSheet = file.endsWith(".png") && metadata.state === undefined && states.length > 1;
  if (autoSheet && file === "sheet.png") return `node ${quoteArg(resolve(process.argv[1]))} ${args.map(quoteArg).join(" ")} --timeout-scale 2`;
  const command = stitching ? retryCommand : `node ${quoteArg(resolve(process.argv[1]))} ${quoteArg(activeTarget.target)} --timeout-scale 2`;
  return command + ` --out ${quoteArg(out)}${metadata.size ? ` --size ${quoteArg(metadata.size)}` : ""}${metadata.zoom ? ` --zoom ${metadata.zoom}` : ""}` +
    (metadata.state !== null && metadata.state !== undefined ? ` --states ${quoteArg(metadata.state)} --param ${quoteArg(opt.param)}` : "") +
    (isSheet ? ` --states ${quoteArg(states.join(","))} --param ${quoteArg(opt.param)} --sheet` : "") + variant +
    (opt.selector ? ` --selector ${quoteArg(opt.selector)}` : "") + (flags.has("thumb") ? " --thumb" : "") +
    (opt.query ? ` --query ${quoteArg(opt.query)}` : "") + (steps ? ` --steps ${quoteArg(steps)}` : "") +
    (file.startsWith("motion-probe") ? " --motion" : extra) + (flags.has("full") && file.endsWith(".png") ? " --full" : "");
}
async function item(file, metadata, work, extra = "") {
  currentRetryCommand = retryItem(file, metadata, extra);
  let failed = false;
  const firstResult = report.length;
  const reopened = browserNeedsRestart;
  if (reopened) await restartBrowser();
  try { await during(file, () => work(reopened)); }
  catch (error) {
    if (transportFailure) throw error;
    report.push({ file, ...metadata, failed: true, issues: [...problems, error.message] });
    lines.push(`${file}  ⚠ 失败：${error.message}`); process.exitCode = 1; failed = true;
    // Ordinary one-item failures retain their old stderr diagnostic; batches can finish the rest.
    console.error(`shoot：${error.message}`);
  }
  progress(file, failed || report.slice(firstResult).some((r) => r.failed));
}
async function captureBatch(selectedStates, selectedZooms, selectedGroups, useMask, useSheet) {
  for (const { w, h } of sizes) for (const zoom of selectedZooms) for (const group of selectedGroups) {
    const shots = [], masked = [];
    const suffix = [group.id, sizes.length > 1 ? `${w}x${h}` : "", zoom !== 1 ? `@${zoom}x` : ""].filter(Boolean).join("-");
    for (const stateIndex of selectedStates) {
      const state = states[stateIndex];
      const preferred = [candidatePrefix(), batchMode && state === null ? "" : stateIds[stateIndex], suffix].filter(Boolean).join("-");
      const name = reserveFamily(preferred, (stem) => [`${stem}.png`, ...(useMask ? [`${stem}-masked.png`] : []), ...(marks.length ? [`${stem}-marked.png`] : []), ...(refImage ? [`${stem}-compare.png`] : [])]);
      const meta = { ...(batchMode ? { target: activeTarget.target, name: activeTarget.name || targetStem(activeTarget) } : {}), state, size: `${w}x${h}`, zoom, ...(group.reportName ? { group: group.reportName } : {}) };
      const thumb = flags.has("thumb");
      const settleBudget = thumb ? 300 : 2000;
      const prepare = async () => {
        problems = [];
        await setViewport(w, h, zoom); await open(withState(state));
        let waited = await settleAnimations(settleBudget);
        await runSteps(group.steps);
        waited += await settleAnimations(settleBudget - waited); return waited;
      };
      let entry;
      const file = join(out, `${name}.png`);
      await item(`${name}.png`, meta, async () => {
        const animationWaitMs = await prepare();
        await screenshot(file, flags.has("full"), selector ? await selectorClip() : thumb ? { x: 0, y: 0, width: w, height: h, scale: 0.5 } : null);
        const issues = await check(), hints = thumb ? [] : await lint();
        entry = { file: basename(file), ...meta, ...(thumb ? { thumb: true } : {}), animationWaitMs, issues, lint: hints };
        lines.push(`${basename(file)}${issues.length ? "  ⚠ " + issues.join("；") : ""}${hints.length ? "  ◇ 可读性提示：" + lintLine(hints) : ""}`);
        report.push(entry); shots.push({ path: file, label: state || "page" });
        if (batchMode) targetShots.push({ path: file, label: [meta.name, state, suffix].filter(Boolean).join(" · ") });
      });
      if (!shots.some((shot) => basename(shot.path) === `${name}.png`)) {
        for (const extra of [marks.length && "marked", useMask && "masked", refImage && "compare"].filter(Boolean)) {
          skipped(`${name}-${extra}.png`, meta, `原截图 ${name}.png 失败，无法生成这一项`);
        }
        continue;
      }
      if (marks.length) await item(`${name}-marked.png`, meta, async (retried) => {
        if (retried) await prepare();
        try { await mark(); lines.push(basename(await screenshot(join(out, `${name}-marked.png`), flags.has("full"), selector ? await selectorClip() : null))); }
        finally { if (!browserNeedsRestart) await unmark(); }
      });
      if (useMask) await item(`${name}-masked.png`, meta, async (retried) => {
        if (retried) await prepare();
        try {
          await mask(); await sleep(60);
          masked.push({ path: await screenshot(join(out, `${name}-masked.png`), flags.has("full"), selector ? await selectorClip() : null), label: state || "page" });
          lines.push(`${name}-masked.png`);
        } finally { if (!browserNeedsRestart) await evaluate(`(document.getElementById("oil-mask")?.remove(), true)`); }
      });
      if (refImage) await item(`${name}-compare.png`, meta, async () => {
        const result = await compare(file, refImage, join(out, `${name}-compare.png`));
        entry.compare = { file: result.file, overall: result.overall, cells: result.cells }; lines.push(result.message);
      });
    }
    if (useSheet && !flags.has("no-sheet") && selectedStates.length > 1) {
      const sheetSuffixParts = [group.id, sizes.length > 1 ? `${w}x${h}` : "", selectedZooms.length > 1 && zoom !== 1 ? `@${zoom}x` : ""].filter(Boolean);
      const preferred = `${candidatePrefix() ? candidatePrefix() + "-" : ""}sheet${sheetSuffixParts.length ? "-" + sheetSuffixParts.join("-") : ""}`;
      const sheetName = reserveFamily(preferred, (stem) => [`${stem}.png`, ...(useMask ? [`${stem}-masked.png`] : [])]);
      const meta = { size: `${w}x${h}`, zoom, ...(group.reportName ? { group: group.reportName } : {}) };
      if (shots.length > 1) await item(`${sheetName}.png`, meta, async () => {
        lines.push(basename(await sheet(shots, join(out, `${sheetName}.png`), w, h)));
      });
      else skipped(`${sheetName}.png`, meta, `只收到 ${shots.length} 张成功截图，并排图至少需要 2 张`);
      if (useMask) {
        if (masked.length > 1) await item(`${sheetName}-masked.png`, meta, async () => {
          lines.push(basename(await sheet(masked, join(out, `${sheetName}-masked.png`), w, h)));
        });
        else skipped(`${sheetName}-masked.png`, meta, `只收到 ${masked.length} 张成功遮字图，并排图至少需要 2 张`);
      }
    }
  }
}
async function motionBatch() {
  for (const group of groups.length ? groups : [{ id: "", reportName: "", steps: [] }]) {
    const file = `${candidatePrefix() ? candidatePrefix() + "-" : ""}motion-probe${group.id ? "-" + group.id : ""}`;
    const meta = { state: states[0], size: `${sizes[0].w}x${sizes[0].h}`, zoom: 1, ...(group.reportName ? { group: group.reportName } : {}) };
    await item(file, meta, async () => {
      const result = await probeMotion(withState(states[0]), sizes[0].w, sizes[0].h, group.steps);
      lines.push(result.message + (result.issues.length ? "  ⚠ " + result.issues.join("；") : ""));
      report.push({ file, ...meta, motion: result.phases, issues: result.issues });
    });
  }
}
async function recording(group, entry, zoom, multipleZooms = false) {
  const preferred = [candidatePrefix(), group.id, multipleZooms && zoom !== 1 ? `@${zoom}x` : ""].filter(Boolean).join("-");
  const name = reserveFamily(preferred, (stem) => [`record${stem ? "-" + stem : ""}.mp4`, ...["start", "mid", "end"].map((frame) => `motion${stem ? "-" + stem : ""}-${frame}.jpg`), ...(opt.frames !== undefined ? [`motion${stem ? "-" + stem : ""}-sequence.png`] : [])]);
  const file = `motion${name ? "-" + name : ""}-end.jpg`;
  const meta = { state: states[0], size: `${sizes[0].w}x${sizes[0].h}`, zoom,
    ...((group.reportName || group.id) ? { group: group.reportName || group.id } : {}) };
  await item(file, meta, async () => {
    problems = [];
    const result = await record(withState(states[0]), sizes[0].w, sizes[0].h, { name, steps: group.steps, entry, zoom });
    lines.push(result.message);
    for (const warning of result.warnings || []) lines.push(`⚠ ${warning}`);
    report.push({ file, ...meta, issues: result.issues, frames: result.frames, sampling: result.sampling, durationMs: result.durationMs, ...(result.sequence ? { sequence: result.sequence } : {}), ...(result.consistency ? { consistency: result.consistency } : {}), ...(result.warnings?.length ? { warnings: result.warnings } : {}), ...(result.failed ? { failed: true } : {}) });
    if (evidence && result.failed) { report.at(-1).issues.push(result.message); process.exitCode = 1; }
  }, `${opt.frames !== undefined ? ` --frames ${opt.frames}` : ""}${flags.has("record") || opt.frames === undefined ? " --record" : ""}${entry ? " --entry" : ""}`);
}
const shotCount = (n, z, g, mask, sheet) => sizes.length * z * g * (n * (1 + Number(mask) + Number(marks.length > 0) + Number(!!refImage)) + (sheet && !flags.has("no-sheet") && n > 1 ? 1 + Number(mask) : 0));
const batchMask = states.length > 1 || flags.has("mask");
progressTotal = evidence
  ? (suppliedOptions.has("zoom") ? shotCount(states.length, zooms.length, 1, batchMask, states.length > 1) : shotCount(states.length, 1, 1, batchMask, states.length > 1) + shotCount(1, 1, 1, flags.has("mask"), false)) + Math.max(1, groups.length) + 1 + groups.length
  : (flags.has("motion") ? Math.max(1, groups.length) : 0) + (captureMotion ? zooms.length * Math.max(1, groups.length) : shotCount(states.length, zooms.length, Math.max(1, groups.length), flags.has("mask"), flags.has("sheet")));
progressTotal = progressTotal * Math.max(1, targets.length) + Number(autoSheet);
try {
  if (stitching) {
    progressTotal = 1;
    await item("stitch.png", {}, async () => {
      const result = await composeImages(stitchInputs, join(out, "stitch.png"), Number(opt.columns || 2), opt.crop);
      report.push({ ...result, issues: [] });
      lines.push(`拼图：${result.file}（${result.width}×${result.height}，${result.columns} 列）`);
    });
  } else {
    for (const [index, candidate] of targets.entries()) {
      base = bases[index]; activeTarget = candidate;
      if (evidence) {
        const plain = [{ id: "", reportName: "", steps: [] }];
        if (suppliedOptions.has("zoom")) {
          await captureBatch(states.map((_, i) => i), zooms, plain, states.length > 1 || flags.has("mask"), states.length > 1);
        } else {
          await captureBatch(states.map((_, i) => i), [1], plain, states.length > 1 || flags.has("mask"), states.length > 1);
          await captureBatch([0], [2], plain, flags.has("mask"), false);
        }
        await motionBatch();
        // Avoid collisions with a user group named entry.
        let entryId = "entry";
        while (groups.some((g) => g.id === entryId)) entryId += "-appearance";
        await recording({ id: entryId, reportName: entryId, steps: [] }, true, 1);
        for (const group of groups) await recording(group, false, 1);
      } else {
        if (flags.has("motion")) await motionBatch();
        if (captureMotion) {
          for (const zoom of zooms) for (const group of groups.length ? groups : [{ id: "", reportName: "", steps: [] }]) await recording(group, flags.has("entry"), zoom, zooms.length > 1);
        } else await captureBatch(states.map((_, i) => i), zooms, groups.length ? groups : [{ id: "", reportName: "", steps: [] }], flags.has("mask"), flags.has("sheet"));
      }
    }
    if (autoSheet) {
      if (targetShots.length > 1) await item("sheet.png", {}, async () => {
        const result = await composeImages(targetShots, join(out, "sheet.png"), targetShots.length);
        report.push({ ...result, issues: [] }); lines.push("sheet.png");
      });
      else skipped("sheet.png", {}, `只收到 ${targetShots.length} 张成功截图，并排图至少需要 2 张`);
    }
  }
} catch (error) { if (!transportFailure) console.error(`shoot：${error.message}`); process.exitCode = 1; }
writeFileSync(join(out, "report.json"), JSON.stringify(report, null, 2));
console.log(`输出目录：${out}`);
for (const notice of notices) console.log(`- ${notice}`);
for (const l of lines) console.log(`- ${l}`);
const total = report.reduce((n, r) => n + r.issues.length, 0);
if (report.length) console.log(total ? `发现 ${total} 个问题，详见 report.json` : `检查通过：没有控制台错误、横向溢出或加载失败的图片${flags.has("motion") ? "，三段动效都检测到了" : ""}`);
const hinted = [...new Set(report.flatMap((r) => (r.lint || []).map((i) => i.label)))];
if (hinted.length) console.log(`可读性与渲染提示 ${hinted.length} 类：${hinted.join("、")}。详见 report.json 的 lint`);
const reviewerManual = resolve(dirname(process.argv[1]), "../references/reviewer-manual.md");
if (evidence && existsSync(reviewerManual)) console.log(`评审交接：将 ${reviewerManual} 与证据目录 ${out} 传给独立评审子 Agent`);
finishing = true;
await cleanup();
process.exit(process.exitCode || 0);
