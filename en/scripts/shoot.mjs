#!/usr/bin/env node
// Screenshot, record, and run basic checks on design previews. Needs only Node 22+ and a local Chrome / Chromium / Edge.
// Usage is in references/tools.md; `node shoot.mjs --help` prints the same text.
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";

const HELP = `Usage: node shoot.mjs <page URL or file> [options]

  --out <dir>           Output directory, default ./shots
  --size <WxH,...>      Viewport, default 390x844; several allowed, for example 390x844,1280x900
  --states <a,b,...>    Open ?state=<name> for each and take one screenshot per state
  --param <name>        Name of the state parameter, default state
  --zoom <factor>       Device pixel ratio, default 1; 2 means a 200% screenshot
  --full                Capture the full page; the default captures the viewport only
  --mask                Also save a version with all text masked out
  --sheet               Stitch all states into one side-by-side sheet (with --mask, a masked sheet too)
  --mark "1=<selector>;..." Also save a marked version: a box around each group of elements, labeled
                        with the given number; without numbers they are labeled 1, 2, 3 in order.
                        Every element a selector matches gets a box; the number sits on the first
  --steps "<actions>"   Actions to run before the screenshot, separated by semicolons:
                        click <selector> | hover <selector> | drag <selector> <dx> <dy>
                        Quote selectors that contain spaces: click ".nav .item"
                        type <selector> <text> | key <key> | scroll <dy> | wait <ms>
  --record              Record the --steps run; writes record.mp4 and start, middle, and end frames
  --entry               With --record: start recording before opening the page, to capture the first-load entrance
  --hold <ms>           How long to keep recording after the actions finish, default 1200
  --motion              Probe motion: whether anything animates on first load, during --steps actions,
                        in the first-screen scroll, and from top to bottom, and how far; none or too small
                        counts as an issue. Layers changing within 1.5 screens of the first-screen scroll
                        are reported only, for pages that chose first-screen depth; when the page itself
                        cannot scroll (a single-screen app) the scroll check is skipped
  --compare <image>     For screenshot recreation: one comparison image per screenshot against the
                        reference (png, jpg, webp) with four cells, reference, current, overlay, and
                        difference heatmap, plus the share of differing pixels per 3x3 cell; the reference
                        is scaled to the screenshot width, so set --size to the reference's logical size
  --wait <ms>           How long to wait after load before capturing, default 400

Every screenshot is checked for console errors, horizontal overflow, and failed images; results go to report.json.
A set of model default patterns and readability problems (eyebrow labels, colored single-side borders,
nested cards, contrast, and so on) is also checked and written to the lint field of report.json.`;

const args = process.argv.slice(2);
if (!args.length || args.includes("--help") || args.includes("-h")) {
  console.log(HELP);
  process.exit(args.length ? 0 : 1);
}
if (typeof WebSocket !== "function") fail("Node 22 or newer is required.");

const opt = { out: "shots", size: "390x844", param: "state", zoom: "1", hold: "1200", wait: "400" };
const options = [...HELP.matchAll(/^  (--\S+)/gm)].map((m) => m[1]);
const flags = new Set();
let target = null;
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--force") continue;
  if (["--full", "--mask", "--sheet", "--record", "--motion", "--entry"].includes(a)) flags.add(a.slice(2));
  else if (a.startsWith("--")) {
    if (!options.includes(a)) fail(`Unknown option ${a}\nAvailable options: ${options.join(" ")}`);
    if (i + 1 >= args.length || args[i + 1].startsWith("--")) fail(`${a} needs a value`);
    opt[a.slice(2)] = args[++i];
  } else target = a;
}
if (!target) fail("Missing page URL or file.");

const sizes = opt.size.split(",").map((s) => {
  const m = s.trim().match(/^(\d+)x(\d+)$/);
  if (!m) fail(`Write sizes as WIDTHxHEIGHT, for example 390x844: ${s}`);
  return { w: +m[1], h: +m[2] };
});
const states = opt.states ? opt.states.split(",").map((s) => s.trim()).filter(Boolean) : [null];
const stateIds = states.map((s, i) => !s ? "page" : /^[A-Za-z0-9_-]{1,80}$/.test(s) ? s :
  `state-${i + 1}-${createHash("sha256").update(s).digest("hex").slice(0, 12)}`);
const zoom = Number(opt.zoom) || 1;
const refImage = opt.compare ? resolve(opt.compare) : null;
if (refImage && !existsSync(refImage)) fail(`Reference image not found: ${opt.compare}`);
if (refImage && !/\.(png|jpe?g|webp)$/i.test(refImage)) fail("--compare only accepts png, jpg or webp");
if (refImage && flags.has("record")) fail("--compare works on screenshots, not with --record");
const out = resolve(opt.out);
mkdirSync(out, { recursive: true });

function fail(message) {
  console.error(`shoot: ${message}`);
  process.exit(1);
}

// ---------- Local files are served by a static server bound to localhost so module scripts and fetch work ----------
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
const privatePath = (path) => path.split(/[\\/]/).some((part) => part.startsWith(".")
  || /^(?:credentials?|secrets?|id_(?:rsa|dsa|ecdsa|ed25519))(?:[._-]|$)/i.test(part));
let server = null;
async function resolveTarget(t) {
  if (/^https?:\/\//.test(t)) return t;
  const file = resolve(t);
  if (!existsSync(file)) fail(`File not found: ${t}`);
  const root = realpathSync(statSync(file).isDirectory() ? file : dirname(file));
  const page = statSync(file).isDirectory() ? "index.html" : basename(file);
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
  return `http://127.0.0.1:${server.address().port}/${encodeURIComponent(page)}`;
}

// ---------- Launch a separate temporary browser; never touch the user's own browser data ----------
function findChrome() {
  const env = process.env.CHROME_PATH;
  if (env && existsSync(env)) return env;
  const candidates = {
    darwin: [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
    win32: [
      `${process.env["PROGRAMFILES"]}\\Google\\Chrome\\Application\\chrome.exe`,
      `${process.env["PROGRAMFILES(X86)"]}\\Google\\Chrome\\Application\\chrome.exe`,
      `${process.env["PROGRAMFILES(X86)"]}\\Microsoft\\Edge\\Application\\msedge.exe`,
    ],
  }[process.platform];
  for (const c of candidates || []) if (c && existsSync(c)) return c;
  for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]) {
    const r = spawnSync("which", [name], { encoding: "utf8" });
    if (r.status === 0 && r.stdout.trim()) return r.stdout.trim();
  }
  fail("Chrome, Chromium or Edge not found; install one, or set CHROME_PATH.");
}

const chromePath = findChrome();
const profile = mkdtempSync(join(tmpdir(), "oil-shoot-"));
const chrome = spawn(chromePath, [
  "--headless=new", "--enable-unsafe-swiftshader", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run",
  "--no-default-browser-check", "--hide-scrollbars", "--mute-audio", "--disable-extensions", "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });

let cleaning;
function cleanup() {
  return cleaning ||= (async () => {
    if (chrome.exitCode === null && chrome.signalCode === null) {
      await new Promise((ok) => {
        const timer = setTimeout(() => { chrome.kill("SIGKILL"); ok(); }, 3000);
        chrome.once("close", () => { clearTimeout(timer); ok(); });
        chrome.kill();
      });
    }
    server?.close();
    rmSync(profile, { recursive: true, force: true });
  })();
}
// Early startup failures still use process.exit; its handlers must clean up synchronously.
process.on("exit", () => {
  try { chrome.kill(); } catch {}
  try { server?.close(); } catch {}
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
});
process.on("SIGINT", async () => { await cleanup(); process.exit(130); });
process.on("SIGTERM", async () => { await cleanup(); process.exit(143); });
chrome.on("error", (error) => fail(`Browser failed to start: ${error.message}`));

const wsUrl = await new Promise((ok) => {
  let buf = "";
  const timer = setTimeout(() => fail("The browser did not start within 15 seconds."), 15000);
  chrome.stderr.on("data", (d) => {
    buf += d;
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(timer); ok(m[1]); }
  });
});

// ---------- Chrome DevTools Protocol ----------
const ws = new WebSocket(wsUrl);
await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = () => no(new Error("Could not connect to the browser")); });
let seq = 0;
const pending = new Map();
const listeners = [];
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { ok, no } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? no(new Error(msg.error.message)) : ok(msg.result);
  } else if (msg.method) listeners.forEach((fn) => fn(msg));
};
const send = (method, params = {}, sessionId) => new Promise((ok, no) => {
  const id = ++seq;
  pending.set(id, { ok, no });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
const cdp = (method, params) => send(method, params, sessionId);
await cdp("Page.enable");
await cdp("Runtime.enable");
await cdp("Log.enable");
// Record WebGL contexts that failed to create or were lost: the screenshot still succeeds, but the canvas is blank.
// A page that tries webgl2 and falls back to webgl is not a failure; only the final outcome counts.
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

let problems = [];
listeners.push((m) => {
  if (m.sessionId !== sessionId) return;
  if (m.method === "Runtime.exceptionThrown") problems.push(`Script error: ${m.params.exceptionDetails?.exception?.description?.split("\n")[0] || m.params.exceptionDetails?.text}`);
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") problems.push(`Console error: ${m.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200)}`);
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") problems.push(`Load error: ${m.params.entry.text.slice(0, 200)} ${m.params.entry.url || ""}`.trim());
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

async function open(url) {
  const loaded = new Promise((ok) => {
    const fn = (m) => { if (m.sessionId === sessionId && m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(fn), 1); ok(); } };
    listeners.push(fn);
  });
  const nav = await cdp("Page.navigate", { url });
  if (nav.errorText) throw new Error(`Could not open ${url}: ${nav.errorText}`);
  await Promise.race([loaded, sleep(15000)]);
  await evaluate(`document.fonts ? document.fonts.ready.then(() => true) : true`);
  await sleep(Number(opt.wait));
}

async function check() {
  const found = await evaluate(`(() => {
    const out = [];
    const doc = document.documentElement;
    if (doc.scrollWidth > innerWidth + 1) out.push("Horizontal overflow: page is " + doc.scrollWidth + "px wide, viewport " + innerWidth + "px");
    for (const img of document.images) if (img.complete && img.naturalWidth === 0) out.push("Image failed to load: " + (img.getAttribute("src") || "").slice(0, 120));
    const gl = window.__oilWebgl;
    if (gl) {
      const blank = new Set(gl.failed.filter((c) => !gl.ok.includes(c))).size;
      if (blank) out.push("WebGL: " + blank + " canvas(es) could not create a drawing context; the screenshot shows them blank");
      if (gl.lost) out.push("WebGL: drawing context lost " + gl.lost + " time(s)");
    }
    return out;
  })()`);
  return [...problems, ...found];
}

// ---------- Default-pattern hints: the model default patterns and readability problems a script can judge ----------
// Runs inside the page, so it cannot reference outer variables. Reports only, never blocks: fix each hit, or give the reason in the delivery notes.
function lintPage() {
  const LABELS = {
    eyebrow: "eyebrow label above a heading", numbered: "numbered label above a heading", sideStripe: "colored single-side border",
    gradientText: "gradient text", nestedCards: "nested cards", emojiIcon: "emoji as icons",
    englishLabel: "English all-caps labels in a Chinese interface", contrastLow: "text contrast below threshold (body under 4.5:1, large text under 3:1)", grayOnColor: "gray text on a colored background",
    smallText: "body text under 13px", tightLeading: "tight line height in multi-line body text", longMeasure: "body line too long",
    stuck: "first-screen content stuck transparent (entrance animation never fired?)", headingSpacing: "heading closer to the text above than below",
  };
  const found = new Map();
  const describe = (el) => {
    const cls = typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 24);
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + cls + (text ? ' "' + text + '"' : "");
  };
  const add = (rule, el, note) => {
    let r = found.get(rule);
    if (!r) found.set(rule, r = { rule, label: LABELS[rule], count: 0, examples: [] });
    r.count++;
    if (r.examples.length < 3) r.examples.push(describe(el) + (note ? " (" + note + ")" : ""));
  };
  const css = (el, pseudo) => getComputedStyle(el, pseudo);
  const shown = (el) => {
    const r = el.getBoundingClientRect(), s = css(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  // Paint every color onto a canvas and read it back, so oklch, color-mix and similar notations compare too.
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
  const chroma = ({ r, g, b }) => (Math.max(r, g, b) - Math.min(r, g, b)) / 255;
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a), a: 1,
  });
  const media = [...document.querySelectorAll("img,video,canvas,picture,iframe,svg image")]
    .filter(shown).map((m) => m.getBoundingClientRect()).filter((r) => r.width * r.height > 2000);
  const overMedia = (r) => media.some((m) => {
    const w = Math.min(r.right, m.right) - Math.max(r.left, m.left), h = Math.min(r.bottom, m.bottom) - Math.max(r.top, m.top);
    return w > 0 && h > 0 && w * h > r.width * r.height * 0.3;
  });
  // The backdrop behind text: composite up through the ancestors; a background image, gradient, or media means unknown.
  const backdrop = (el) => {
    const layers = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const s = css(node);
      if (s.backgroundImage !== "none") return null;
      const c = rgba(s.backgroundColor);
      if (c.a > 0) { layers.push(c); if (c.a >= 0.99) break; }
    }
    return layers.reverse().reduce((base, c) => over(c, base), { r: 255, g: 255, b: 255, a: 1 });
  };
  const ownText = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
  const all = [...document.body.querySelectorAll("*")].slice(0, 8000)
    .filter((el) => !el.closest("svg,script,style,noscript,template,head,[aria-hidden='true'],#oil-mark"));
  const texts = all.filter((el) => ownText(el).length >= 2 && shown(el));
  const cjkCount = (document.body.innerText.match(/[一-鿿]/g) || []).length;
  const latinCount = (document.body.innerText.match(/[A-Za-z]/g) || []).length;
  const chinese = cjkCount > 120 && cjkCount > latinCount / 2;

  // Eyebrow and numbered labels: one short line right above a heading, much smaller than it
  const flaggedAbove = new Set();
  const headings = [...document.querySelectorAll("h1,h2,h3")].filter(shown);
  for (const h of headings) {
    const hs = parseFloat(css(h).fontSize);
    if (hs < 20) continue;
    let prev = h.previousElementSibling, node = h;
    while (!prev && node.parentElement && node.parentElement !== document.body) { node = node.parentElement; prev = node.previousElementSibling; }
    if (!prev || !shown(prev) || prev.closest("nav,[aria-label*='readcrumb' i],[class*='breadcrumb' i]")) continue;
    if (prev.querySelector("a,button,input,select,textarea,img,video,canvas") || /^(A|BUTTON|INPUT|IMG)$/.test(prev.tagName)) continue;
    const text = (prev.innerText || "").trim();
    if (!text || text.length > 48 || text.includes("\n")) continue;
    let holder = prev;
    while (!ownText(holder) && holder.children.length === 1) holder = holder.children[0];
    const s = css(holder), size = parseFloat(s.fontSize);
    if (size > 16 || size > hs * 0.6) continue;
    const pr = prev.getBoundingClientRect(), hr = h.getBoundingClientRect();
    if (pr.bottom > hr.top + 4 || hr.top - pr.bottom > Math.max(32, hs * 1.2) || pr.right < hr.left || pr.left > hr.right) continue;
    const caps = s.textTransform === "uppercase" || (/[A-Z]{3}/.test(text) && text === text.toUpperCase());
    const tracked = parseFloat(s.letterSpacing) / size >= 0.05;
    const mono = /mono|courier|consolas|menlo/i.test(s.fontFamily);
    const ps = css(prev);
    const pill = parseFloat(ps.borderTopLeftRadius) >= pr.height / 3 && (rgba(ps.backgroundColor).a > 0.1 || parseFloat(ps.borderTopWidth) >= 1);
    const numbered = /^0\d$/.test(text) || /^(?:0?\d{1,2}|[IVX]{1,4})(?:\s*[\/·—–|]\s*|[.:]\s+)\S/.test(text);
    if (numbered) { add("numbered", prev); flaggedAbove.add(h); }
    else if (caps || tracked || mono || pill) { add("eyebrow", prev); flaggedAbove.add(h); }
  }

  // A heading should sit closer to the text below than above: it belongs to what follows
  for (const h of headings) {
    if (flaggedAbove.has(h)) continue;
    const parent = css(h.parentElement);
    if (parent.display.includes("grid") || (parent.display.includes("flex") && !parent.flexDirection.startsWith("column"))) continue;
    let prev = h.previousElementSibling, next = h.nextElementSibling;
    while (prev && !shown(prev)) prev = prev.previousElementSibling;
    while (next && !shown(next)) next = next.nextElementSibling;
    if (!prev || !next) continue;
    const hr = h.getBoundingClientRect();
    const above = hr.top - prev.getBoundingClientRect().bottom, below = next.getBoundingClientRect().top - hr.bottom;
    if (above >= 0 && below >= 12 && above + 4 < below) add("headingSpacing", h, "above " + Math.round(above) + "px, below " + Math.round(below) + "px");
  }

  for (const el of all) {
    const s = css(el);
    if (s.display === "none") continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;

    // Colored single-side border: a border or an edge-hugging pseudo-element; neutral structural dividers do not count
    const sides = { left: parseFloat(s.borderLeftWidth), right: parseFloat(s.borderRightWidth), top: parseFloat(s.borderTopWidth), bottom: parseFloat(s.borderBottomWidth) };
    for (const side of ["left", "right"]) {
      const w = sides[side], others = Math.max(sides[side === "left" ? "right" : "left"], sides.top, sides.bottom);
      const c = rgba(s[side === "left" ? "borderLeftColor" : "borderRightColor"]);
      if (w >= 2 && w >= others * 2 && /solid|double/.test(s[side === "left" ? "borderLeftStyle" : "borderRightStyle"])
        && c.a >= 0.4 && chroma(c) >= 0.15 && r.height >= 16 && r.width > sides.left + sides.right + 24 && r.height < innerHeight * 0.8) add("sideStripe", el, w + "px");
    }
    for (const pseudo of ["::before", "::after"]) {
      const p = css(el, pseudo);
      if (p.content === "none" || p.position !== "absolute") continue;
      const pw = parseFloat(p.width), ph = parseFloat(p.height), c = rgba(p.backgroundColor);
      if (pw >= 2 && pw <= 8 && ph >= r.height * 0.6 && r.height >= 24 && r.width > 60 && c.a >= 0.4 && chroma(c) >= 0.15
        && (parseFloat(p.left) <= 2 || parseFloat(p.right) <= 2)) add("sideStripe", el, pseudo);
    }

    if (/text/.test(s.backgroundClip + " " + s.getPropertyValue("-webkit-background-clip")) && /gradient/.test(s.backgroundImage) && (el.textContent || "").trim()) add("gradientText", el);
  }

  // Nested cards: a rounded block with a border or shadow inside another rounded block
  const card = (el, inner) => {
    const s = css(el), r = el.getBoundingClientRect();
    if (r.width < 120 || r.height < 56 || /^(BUTTON|A|INPUT|SELECT|TEXTAREA|IMG|VIDEO|CANVAS|LABEL|SUMMARY|PRE|CODE)$/.test(el.tagName)) return false;
    if (parseFloat(s.borderTopLeftRadius) < 6) return false;
    const border = ["Top", "Right", "Bottom", "Left"].every((k) => parseFloat(s["border" + k + "Width"]) >= 1 && rgba(s["border" + k + "Color"]).a > 0.05);
    const shadow = s.boxShadow !== "none";
    const fill = rgba(s.backgroundColor).a > 0.05;
    if (inner) return border || (shadow && fill);
    return (border || shadow || fill) && r.width * r.height < innerWidth * innerHeight * 0.6;
  };
  for (const el of all) {
    if (!card(el, true)) continue;
    for (let up = el.parentElement, depth = 0; up && up !== document.body && depth < 8; up = up.parentElement, depth++) {
      if (card(up, false)) { add("nestedCards", el, "outer " + describe(up).split(' "')[0]); break; }
    }
  }

  const emoji = /^(?:\p{Emoji_Presentation}|\p{Extended_Pictographic}️)(?:‍\p{Extended_Pictographic}️?)*$/u;
  const emojiHits = texts.filter((el) => emoji.test(ownText(el)) && !el.closest("p,blockquote,li > p"));
  if (emojiHits.length >= 2) emojiHits.forEach((el) => add("emojiIcon", el));

  if (chinese) {
    const labels = texts.filter((el) => {
      const t = (el.innerText || "").trim();
      if (!t || t.length > 40 || /[一-鿿]/.test(t) || el.closest("code,pre,kbd,samp")) return false;
      const letters = (t.match(/[A-Za-z]/g) || []).length;
      const upper = css(el).textTransform === "uppercase" || (/[A-Z]{2}/.test(t) && t === t.toUpperCase());
      return upper && (letters >= 8 || /[A-Za-z]{2,}\s+[A-Za-z]{2,}/.test(t));
    });
    if (labels.length >= 2) labels.forEach((el) => add("englishLabel", el));
  }

  for (const el of texts) {
    const s = css(el), r = el.getBoundingClientRect();
    if (el.closest("button:disabled,[disabled],[aria-disabled='true'],input,textarea,select,option")) continue;
    const size = parseFloat(s.fontSize);
    let alpha = 1;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) alpha *= parseFloat(css(node).opacity);
    const bg = overMedia(r) ? null : backdrop(el);
    const fg = rgba(s.color);
    if (bg && alpha > 0.05 && fg.a > 0) {
      const color = over({ ...fg, a: fg.a * alpha }, bg);
      const contrast = ratio(color, bg);
      const large = size >= 24 || (size >= 18.6 && parseInt(s.fontWeight, 10) >= 700);
      // Below 1.5:1 the text is nearly invisible, which usually means an undetected layer sits behind it (a slider, an absolutely positioned backing); skip it
      if (contrast < 1.5) continue;
      if (contrast < (large ? 3 : 4.5)) add("contrastLow", el, contrast.toFixed(2) + ":1");
      else if (chroma(bg) >= 0.25 && chroma(color) < 0.06 && luminance(color) > 0.08 && luminance(color) < 0.6) add("grayOnColor", el);
    }
    // Body text: paragraphs of two or more lines
    const text = ownText(el);
    const zh = /[一-鿿]/.test(text);
    if (text.length < (zh ? 30 : 60) || el.closest("code,pre,table,nav,button,label,figcaption,kbd")) continue;
    const lh = s.lineHeight === "normal" ? size * 1.2 : parseFloat(s.lineHeight);
    if (r.height < lh * 1.8) continue;
    if (size < 12.5) add("smallText", el, size + "px");
    if (lh / size < (zh ? 1.4 : 1.3)) add("tightLeading", el, (lh / size).toFixed(2));
    const perLine = zh ? r.width / size : r.width / (size * 0.5);
    if (perLine > (zh ? 46 : 95)) add("longMeasure", el, "about " + Math.round(perLine) + " characters per line");
  }

  // First-screen content stuck transparent: when an entrance animation never fires, the screenshot is missing a piece
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
  // Wait for one-off animations to finish so content that is still fading in is not mistaken for stuck
  await evaluate(`(() => {
    const running = document.getAnimations ? document.getAnimations().filter((a) => a.playState === "running" && a.timeline === document.timeline
      && a.effect && a.effect.getTiming && a.effect.getTiming().iterations !== Infinity) : [];
    return Promise.race([Promise.all(running.map((a) => a.finished.catch(() => {}))), new Promise((ok) => setTimeout(ok, 2500))]).then(() => true);
  })()`);
  try {
    return await evaluate(`(${lintPage.toString()})()`);
  } catch (error) {
    return [{ rule: "lintError", label: "default-pattern check did not finish", count: 1, examples: [error.message.slice(0, 160)] }];
  }
}
const lintLine = (items) => items.map((i) => `${i.label}: ${i.count} (${i.examples.join(", ")})`).join("; ");

async function screenshot(file, full) {
  let clip;
  if (full) {
    const { contentSize } = await cdp("Page.getLayoutMetrics");
    clip = { x: 0, y: 0, width: Math.ceil(contentSize.width), height: Math.ceil(contentSize.height), scale: 1 };
  }
  const { data } = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: !!full, ...(clip ? { clip } : {}) });
  writeFileSync(file, Buffer.from(data, "base64"));
  return file;
}

// Keep color intact: SVG icons and CSS decorations may use currentColor.
const MASK_CSS = `*,*::before,*::after{text-shadow:none!important;-webkit-text-fill-color:transparent!important;caret-color:transparent!important}
::placeholder{color:transparent!important}svg text,svg tspan{fill:transparent!important;stroke:transparent!important}`;
const mask = () => evaluate(`(() => { const s = document.createElement("style"); s.id = "oil-mask"; s.textContent = ${JSON.stringify(MASK_CSS)}; document.head.append(s); return true; })()`);

// Marked version: boxes and numbers are drawn on the topmost layer in document coordinates, so they line up in full-page shots too.
const marks = (opt.mark ? opt.mark.split(";").map((s) => s.trim()).filter(Boolean) : []).map((s, i) => {
  const m = s.match(/^(\d+)\s*=\s*(.+)$/);
  return m ? { label: m[1], selector: m[2].trim() } : { label: String(i + 1), selector: s };
});
async function mark() {
  const result = await evaluate(`((selectors) => {
    const layer = document.createElement("div");
    layer.id = "oil-mark";
    layer.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none";
    const color = "#e8175d";
    const missing = [];
    selectors.forEach(({ label, selector }) => {
      let found;
      try { found = [...document.querySelectorAll(selector)]; } catch { missing.push(selector + " (bad selector)"); return; }
      const boxes = found.map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
      if (!boxes.length) { missing.push(selector + (found.length ? " (element not visible)" : "")); return; }
      boxes.forEach((r, j) => {
        const box = document.createElement("div");
        box.style.cssText = "position:absolute;box-sizing:border-box;border:2px solid " + color + ";border-radius:3px;" +
          "left:" + (r.left + scrollX - 4) + "px;top:" + (r.top + scrollY - 4) + "px;width:" + (r.width + 8) + "px;height:" + (r.height + 8) + "px";
        if (j === 0) {
          // On small elements the number goes outside the box so it does not cover the element; if the left has no room, use the right.
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
  if (result.length) throw new Error(`--mark could not find elements: ${result.join("; ")}`);
}
const unmark = () => evaluate(`(document.getElementById("oil-mark")?.remove(), true)`);

// ---------- Actions ----------
function tokenize(text) {
  return [...text.matchAll(/"([^"]*)"|'([^']*)'|(\S+)/g)].map((m) => m[1] ?? m[2] ?? m[3]);
}
const KEYS = { ArrowUp: 38, ArrowDown: 40, ArrowLeft: 37, ArrowRight: 39, Enter: 13, Escape: 27, Tab: 9, " ": 32, Space: 32, Home: 36, End: 35, PageUp: 33, PageDown: 34, Backspace: 8 };
async function center(selector) {
  const box = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return null; el.scrollIntoView({ block: "center", inline: "center" }); const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  if (!box) throw new Error(`Element not found: ${selector}`);
  return box;
}
const mouse = (type, x, y, extra = {}) => cdp("Input.dispatchMouseEvent", { type, x, y, button: "left", pointerType: "mouse", ...extra });
async function runSteps(text) {
  for (const raw of (text || "").split(";").map((s) => s.trim()).filter(Boolean)) {
    const [verb, ...rest] = tokenize(raw);
    const arity = { click: 1, hover: 1, drag: 3 }[verb];
    if (arity && rest.length !== arity) throw new Error(`Bad action arguments: ${raw}. Quote selectors that contain spaces, for example ${verb} ".nav .item"${verb === "drag" ? " 0 -80" : ""}`);
    if (verb === "wait") await sleep(Number(rest[0]) || 0);
    else if (verb === "click") { const p = await center(rest[0]); await mouse("mouseMoved", p.x, p.y); await mouse("mousePressed", p.x, p.y, { clickCount: 1 }); await mouse("mouseReleased", p.x, p.y, { clickCount: 1 }); await sleep(120); }
    else if (verb === "hover") { const p = await center(rest[0]); await mouse("mouseMoved", p.x, p.y); await sleep(200); }
    else if (verb === "drag") {
      const p = await center(rest[0]); const dx = Number(rest[1]) || 0; const dy = Number(rest[2]) || 0;
      await mouse("mouseMoved", p.x, p.y); await mouse("mousePressed", p.x, p.y, { clickCount: 1, buttons: 1 });
      for (let i = 1; i <= 24; i++) { await mouse("mouseMoved", p.x + (dx * i) / 24, p.y + (dy * i) / 24, { buttons: 1 }); await sleep(16); }
      await mouse("mouseReleased", p.x + dx, p.y + dy, { clickCount: 1 }); await sleep(150);
    } else if (verb === "type") {
      await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(rest[0])}); if (!el) throw new Error(${JSON.stringify("Element not found: " + rest[0])}); el.focus(); return true; })()`);
      await cdp("Input.insertText", { text: rest.slice(1).join(" ") }); await sleep(120);
    } else if (verb === "key") {
      const key = rest[0] === "Space" ? " " : rest[0]; const code = KEYS[rest[0]] ?? key.toUpperCase().charCodeAt(0);
      await cdp("Input.dispatchKeyEvent", { type: "keyDown", key, code: rest[0], windowsVirtualKeyCode: code });
      await cdp("Input.dispatchKeyEvent", { type: "keyUp", key, code: rest[0], windowsVirtualKeyCode: code }); await sleep(80);
    } else if (verb === "scroll") { await evaluate(`scrollBy(0, ${Number(rest[0]) || 0}), true`); await sleep(200); }
    else throw new Error(`Unknown action: ${raw}`);
  }
}

// ---------- Sheet: lay the screenshots out side by side in the same browser ----------
async function sheet(items, file, w, h) {
  const cell = Math.min(w, 420);
  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const figures = items.map(({ path, label }) =>
    `<figure><img src="data:image/png;base64,${readFileSync(path).toString("base64")}"><figcaption>${escapeHtml(label)}</figcaption></figure>`).join("");
  const html = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>body{margin:0;padding:32px;background:#ececea;font:13px -apple-system,"PingFang SC",sans-serif;color:#555}
main{display:flex;gap:24px;align-items:flex-start}figure{margin:0;width:${cell}px}img{width:100%;display:block;border-radius:12px;box-shadow:0 1px 3px #0002}
figcaption{margin-top:10px}</style><main>${figures}</main>`;
  const tmp = join(profile, "sheet.html");
  writeFileSync(tmp, html);
  const width = items.length * cell + (items.length - 1) * 24 + 64;
  await setViewport(width, Math.round((cell * h) / w) + 120, 1);
  await open(`file://${tmp}`);
  return screenshot(file, true);
}

// ---------- Comparison image: for screenshot recreation, show the reference side by side, overlaid, and as a difference heatmap ----------
const IMAGE_TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };
const CELLS = ["top-left", "top-center", "top-right", "middle-left", "center", "middle-right", "bottom-left", "bottom-center", "bottom-right"];
async function compare(buildPath, refPath, file) {
  const ref = `data:${IMAGE_TYPES[extname(refPath).toLowerCase()]};base64,${readFileSync(refPath).toString("base64")}`;
  const build = `data:image/png;base64,${readFileSync(buildPath).toString("base64")}`;
  const html = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>body{margin:0;padding:28px;background:#ececea;font:13px -apple-system,"PingFang SC",sans-serif;color:#555}
main{display:grid;grid-template-columns:repeat(2,720px);gap:24px 20px;align-items:start}figure{margin:0}
canvas{width:100%;display:block;border-radius:8px;box-shadow:0 1px 3px #0002;background:#fff}figcaption{margin-top:8px}</style>
<main><figure><canvas id="ref"></canvas><figcaption>Reference</figcaption></figure><figure><canvas id="build"></canvas><figcaption>Current</figcaption></figure>
<figure><canvas id="overlay"></canvas><figcaption>Overlay (current at 50% over reference)</figcaption></figure><figure><canvas id="diff"></canvas><figcaption id="note">Difference</figcaption></figure></main>
<script>(async () => {
  const load = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error("Reference image could not be opened")); i.src = src; });
  const [ref, build] = await Promise.all([load(${JSON.stringify(ref)}), load(${JSON.stringify(build)})]);
  const W = build.naturalWidth, refH = Math.round(ref.naturalHeight * W / ref.naturalWidth), H = Math.min(refH, build.naturalHeight);
  const paint = (id, fn) => { const c = document.getElementById(id); c.width = W; c.height = H; const x = c.getContext("2d"); fn(x); return x; };
  paint("ref", (x) => x.drawImage(ref, 0, 0, W, refH));
  paint("build", (x) => x.drawImage(build, 0, 0));
  paint("overlay", (x) => { x.drawImage(ref, 0, 0, W, refH); x.globalAlpha = 0.5; x.drawImage(build, 0, 0); });
  // Scale to 480 wide, then compare colors pixel by pixel: any channel differing by more than 0.1 counts as different, which ignores anti-aliasing and offsets of a pixel or two
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
  const tmp = join(profile, "compare.html");
  writeFileSync(tmp, html);
  await setViewport(2 * 720 + 20 + 56, 900, 1);
  await open(`file://${tmp}`);
  let result = null;
  for (let i = 0; i < 50 && !result; i++) { result = await evaluate(`window.__compare || null`); if (!result) await sleep(100); }
  if (!result || result.error) throw new Error(`Comparison image failed: ${result?.error || "timed out"}`);
  await screenshot(file, true);
  const worst = result.cells.map((v, i) => ({ v, i })).sort((x, y) => y.v - x.v).slice(0, 3).map(({ v, i }) => `${CELLS[i]} ${v}%`);
  const gap = Math.abs(result.refHeight - result.buildHeight) / result.buildHeight > 0.05
    ? `; reference scaled to ${result.refHeight}px tall, screenshot ${result.buildHeight}px, only the overlap was compared` : "";
  return { file: basename(file), overall: result.overall, cells: Object.fromEntries(CELLS.map((c, i) => [c, result.cells[i]])),
    message: `${basename(file)}: ${result.overall}% of pixels differ clearly, worst cells ${worst.join(", ")}${gap}` };
}

// ---------- Recording ----------
async function record(url, w, h) {
  const frames = [];
  const dir = join(out, "frames");
  mkdirSync(dir, { recursive: true });
  const onFrame = (m) => {
    if (m.sessionId !== sessionId || m.method !== "Page.screencastFrame") return;
    const name = join(dir, `f${String(frames.length).padStart(4, "0")}.jpg`);
    writeFileSync(name, Buffer.from(m.params.data, "base64"));
    frames.push({ name, t: m.params.metadata.timestamp });
    cdp("Page.screencastFrameAck", { sessionId: m.params.sessionId }).catch(() => {});
  };
  await setViewport(w, h, zoom);
  const entry = flags.has("entry");
  if (!entry) await open(url);
  listeners.push(onFrame);
  await cdp("Page.startScreencast", { format: "jpeg", quality: 88, everyNthFrame: 1 });
  if (entry) {
    await open(url);
    // Drop the blank frames before the page first paints, so the start frame is where the entrance begins
    const painted = await evaluate(`(() => { const p = performance.getEntriesByName("first-contentful-paint")[0] || performance.getEntriesByType("paint")[0]; return p ? (performance.timeOrigin + p.startTime) / 1000 : 0; })()`);
    if (painted) { const firstPainted = frames.findIndex((f) => f.t >= painted - 0.02); if (firstPainted > 0) frames.splice(0, firstPainted); }
  } else await sleep(500);
  await runSteps(opt.steps);
  await sleep(Number(opt.hold));
  const finished = Date.now() / 1000;
  const issues = await check();
  await cdp("Page.stopScreencast");
  listeners.splice(listeners.indexOf(onFrame), 1);
  if (!frames.length) throw new Error("Recording captured no frames");
  const pick = { start: frames[0], mid: frames[Math.floor(frames.length / 2)], end: frames[frames.length - 1] };
  for (const [k, f] of Object.entries(pick)) writeFileSync(join(out, `motion-${k}.jpg`), readFileSync(f.name));
  const ffmpeg = spawnSync("ffmpeg", ["-version"]).status === 0;
  if (!ffmpeg) return { issues, message: `Recording: ffmpeg is not installed, kept ${frames.length} frames and motion-start/mid/end.jpg` };
  // Generated basenames are safe for concat's quoting, even when --out contains an apostrophe.
  // Keep the final still frame through the end of --hold; screencasts only emit changed frames.
  const list = frames.map((f, i) => `file '${basename(f.name)}'\nduration ${Math.max(0.016, ((frames[i + 1]?.t ?? finished) - f.t)).toFixed(3)}`).join("\n") + `\nfile '${basename(frames.at(-1).name)}'\n`;
  writeFileSync(join(dir, "list.txt"), list);
  const r = spawnSync("ffmpeg", ["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", join(dir, "list.txt"),
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30", "-pix_fmt", "yuv420p", join(out, "record.mp4")], { encoding: "utf8" });
  if (r.status !== 0) return { issues, message: `Recording: ffmpeg failed (${r.stderr.trim().split("\n").pop()}), frames kept in frames/` };
  rmSync(dir, { recursive: true, force: true });
  return { issues, message: `Recording: record.mp4 (${(finished - frames[0].t).toFixed(1)} s) and motion-start/mid/end.jpg` };
}


// ---------- Motion probe ----------
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
  // The first-screen phase measures in viewport coordinates: a pinned stage does not count as moving, only the layers changing inside it.
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

async function probeMotion(url, w, h) {
  const { identifier } = await cdp("Page.addScriptToEvaluateOnNewDocument", { source: MOTION_PROBE });
  problems = [];
  await setViewport(w, h, 1);
  await open(url);
  await sleep(1200);
  const phases = { load: await evaluate(`__oilMotion.summary("load")`) };
  if (opt.steps) {
    await evaluate(`__oilMotion.setPhase("steps"), true`);
    await runSteps(opt.steps);
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
  await cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier });

  const issues = [];
  const names = { load: "first load", steps: "--steps actions", hero: "first-screen scroll", scroll: "scroll to bottom" };
  const weak = (p) => p.maxMove < 4 && p.maxSize < 0.02 && p.maxOpacity < 0.3;
  for (const [k, p] of Object.entries(phases)) {
    // First-screen depth is optional: report only the layer count and range for pages that chose it; never an issue.
    if (k === "hero") {
      p.layers = p.top.filter((i) => i.size >= 0.05 || i.move >= h * 0.05).length;
      continue;
    }
    if (k === "scroll") {
      p.scrollable = scrollable;
      if (!p.elements && scrollable) issues.push("Scroll: no change detected while scrolling; landing, brand, launch and exhibition pages need a scroll narrative");
      continue;
    }
    if (!p.elements) issues.push(`${names[k]}: no animation detected`);
    else if (p.loops === p.elements) issues.push(`${names[k]}: only looping animation, no one-off ${k === "load" ? "entrance" : "feedback"}`);
    else if (weak(p)) issues.push(`${names[k]}: animation too small to see (max movement ${p.maxMove}px, size change ${(p.maxSize * 100).toFixed(1)}%, opacity change ${p.maxOpacity})`);
  }
  const brief = (k, p) => k === "scroll" && !p.scrollable ? "page does not scroll, skipped the scroll check" : k === "hero" ? `first-screen scroll: ${p.layers} layers changing, max scale ${(p.maxSize * 100).toFixed(1)}%, max movement ${p.maxMove}px`
    : `${names[k]}: ${p.elements} elements moving, max movement ${p.maxMove}px, opacity change ${p.maxOpacity}`;
  return { phases, issues: [...problems, ...issues], message: "Motion probe: " + Object.entries(phases).map(([k, p]) => brief(k, p)).join("; ") };
}

// ---------- Main flow ----------
const base = await resolveTarget(target);
const withState = (s) => {
  if (!s) return base;
  const u = new URL(base);
  u.searchParams.set(opt.param, s);
  return u.toString();
};
const report = [];
const lines = [];
try {
  if (flags.has("motion")) {
    const result = await probeMotion(withState(states[0]), sizes[0].w, sizes[0].h);
    lines.push(result.message + (result.issues.length ? "  ⚠ " + result.issues.join("; ") : ""));
    report.push({ file: "motion-probe", state: states[0], size: `${sizes[0].w}x${sizes[0].h}`, zoom: 1, motion: result.phases, issues: result.issues });
  }
  if (flags.has("record")) {
    const result = await record(withState(states[0]), sizes[0].w, sizes[0].h);
    lines.push(result.message);
    report.push({ file: "motion-end.jpg", state: states[0], size: `${sizes[0].w}x${sizes[0].h}`, zoom, issues: result.issues });
  } else {
    for (const { w, h } of sizes) {
      const shots = [], masked = [];
      for (const [stateIndex, s] of states.entries()) {
        problems = [];
        await setViewport(w, h, zoom);
        await open(withState(s));
        if (opt.steps) await runSteps(opt.steps);
        const name = [stateIds[stateIndex], sizes.length > 1 ? `${w}x${h}` : "", zoom !== 1 ? `@${zoom}x` : ""].filter(Boolean).join("-");
        const file = await screenshot(join(out, `${name}.png`), flags.has("full"));
        const issues = await check();
        const hints = await lint();
        const entry = { file: basename(file), state: s, size: `${w}x${h}`, zoom, issues, lint: hints };
        report.push(entry);
        shots.push({ path: file, label: s || "page" });
        lines.push(`${basename(file)}${issues.length ? "  ⚠ " + issues.join("; ") : ""}${hints.length ? "  ◇ Default-pattern hints: " + lintLine(hints) : ""}`);
        if (marks.length) {
          await mark();
          lines.push(basename(await screenshot(join(out, `${name}-marked.png`), flags.has("full"))));
          await unmark();
        }
        if (flags.has("mask")) {
          await mask();
          await sleep(60);
          masked.push({ path: await screenshot(join(out, `${name}-masked.png`), flags.has("full")), label: s || "page" });
        }
        if (refImage) {
          const result = await compare(file, refImage, join(out, `${name}-compare.png`));
          entry.compare = { file: result.file, overall: result.overall, cells: result.cells };
          lines.push(result.message);
        }
      }
      if (flags.has("sheet") && shots.length > 1) {
        const suffix = sizes.length > 1 ? `-${w}x${h}` : "";
        lines.push(basename(await sheet(shots, join(out, `sheet${suffix}.png`), w, h)));
        if (masked.length) lines.push(basename(await sheet(masked, join(out, `sheet${suffix}-masked.png`), w, h)));
      }
    }
  }
  writeFileSync(join(out, "report.json"), JSON.stringify(report, null, 2));
} catch (error) {
  console.error(`shoot: ${error.message}`);
  process.exitCode = 1;
}
console.log(`Output directory: ${out}`);
for (const l of lines) console.log(`- ${l}`);
const total = report.reduce((n, r) => n + r.issues.length, 0);
if (report.length) console.log(total ? `Found ${total} issue(s), see report.json` : `Checks passed: no console errors, horizontal overflow, or failed images${flags.has("motion") ? ", and all three motion phases were detected" : ""}`);
const hinted = [...new Set(report.flatMap((r) => (r.lint || []).map((i) => i.label)))];
if (hinted.length) console.log(`Default-pattern hints, ${hinted.length} kind(s): ${hinted.join(", ")}. Fix the readability items (contrast below threshold, body under 13px, tight line height, stuck transparent). Fix the rest, or state in the delivery notes how each serves the direction; note false positives in one line too. Details in report.json under lint`);
ws.close();
await cleanup();
process.exit(process.exitCode || 0);
