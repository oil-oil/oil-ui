#!/usr/bin/env node
// Optional oiloil image CLI for hosts without image tools. Node 22+, no dependencies.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ACCOUNT = 'https://ui.oiloil.org/account/?tab=images';
const LOGIN = 'npx github:oil-oil/oil-cli login';
const MIME_EXT = { 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp' };
const EXT_MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp' };
const MAX_REF = 2 * 1024 * 1024;
const HELP = `用法：node <skill>/scripts/oiloil-image.mjs <image|balance|status|pref> [选项]
需要 Node 22+，无第三方依赖。image 使用 oiloil 积分生图；加 --ref 则改图。

常用命令：
  node <skill>/scripts/oiloil-image.mjs image "<图片说明>" --out assets/generated.png
  node <skill>/scripts/oiloil-image.mjs image --prompt "<图片说明>" --size 2k --out assets/generated.webp
  node <skill>/scripts/oiloil-image.mjs image "<修改说明>" --ref assets/input.png --size 1024x1536
  node <skill>/scripts/oiloil-image.mjs image "<物件说明>" --background transparent --out assets/cutout.webp
  node <skill>/scripts/oiloil-image.mjs balance
  node <skill>/scripts/oiloil-image.mjs status <幂等键>
  node <skill>/scripts/oiloil-image.mjs pref
  node <skill>/scripts/oiloil-image.mjs pref set <oiloil|host>
  node <skill>/scripts/oiloil-image.mjs pref clear

image 选项：
  --prompt, -p <说明>   也可直接写在命令后；未加引号的多段文字会用空格连接
  --size, -s <尺寸>     1K|2K|4K 或 宽x高，默认 1K；大小写、X 和 × 均可
                        自定义宽高须为 16 的倍数，长边 ≤ 3840，比例 ≤ 3:1，
                        总像素 655360..8294400
  --out, -o <文件>      默认 assets/generated.png；目录自动创建
  --ref, -r <文件>      仅一张本地 PNG/JPEG/WebP，最多 2 MiB；按文件内容识别格式
  --background, -b <值> transparent 生成透明底素材（也可写“透明”）；opaque 或 auto 同接口

status 选项：
  只接受一个 image 请求使用过的幂等键，查询 running、completed 或 failed 状态。
  --out, -o <文件>      恢复已完成请求的原图；不加时只查询，不写入图片。
                        成功结果保留 24 小时；过期或早期请求只能查询状态。

pref 说明：
  读写本机生图工具偏好，不需要登录，也不发起网络请求：
  pref                  查看当前生图偏好（未设置时为 unset）
  pref set oiloil|host  保存偏好（oiloil 使用内置生图工具；host 使用宿主原生生图工具）
  pref clear            清除已保存的生图偏好
  保存在与 config.json 同目录的 preferences.json，不读取或修改 config.json。

通用选项：
  --timeout <毫秒>      请求超时，image 默认 250000，balance/status 默认 10000；1..900000
  --help, -h           打印帮助
选项可放在子命令前后，可用 --名字=值、--名字 值；-- 之后按位置参数读取。
不提供画质参数，服务端固定 medium。已有文件不覆盖，自动加序号；
--out 后缀与返回格式不符时按实际格式保存，成功输出实际绝对路径、扣除积分和剩余积分。
可能已生成或结果不确定的响应保留供恢复；输出写入失败时保存到备用目录。
生成请求不自动重试；网络中断后用 status 查询原请求，避免重复生成。

令牌先读 OIL_TOKEN，再读 oil CLI config.json 的 token：
  macOS/Linux：$XDG_CONFIG_HOME/oil/config.json，未设时用 ~/.config/oil/config.json
  Windows：%APPDATA%\\oil\\config.json，未设时用用户目录的 AppData\\Roaming\\oil\\config.json
脚本不登录，也不读取配置中的 api；登录命令：${LOGIN}
余额与充值：${ACCOUNT}
OIL_IMAGE_API 可覆盖图像 API 根地址（默认 https://api.oiloil.org，不含 /v1）。
OIL_API 仍只用于画廊、oil CLI 和更新检查，不改变图像 API 地址。
令牌、图片说明和参考图只发给图像 API；脚本不输出令牌，也不把请求头写入恢复文件。

退出码：0 成功；1 本地读写失败；2 参数错误；3 未登录；4 余额不足；
5 登录失效；6 网络错误或超时；7 接口或响应异常；8 保存失败（保留响应）。
成功写到标准输出，说明和错误写到标准错误，不打印堆栈。`;

class CliError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
const usage = message => { throw new CliError(2, `${message}。用 node <skill>/scripts/oiloil-image.mjs --help 查看用法。`); };
const quoted = value => JSON.stringify(value);
export function shellQuote(value, platform = process.platform) {
  const text = String(value);
  return platform === 'win32' ? `'${text.replaceAll("'", "''")}'` : `'${text.replaceAll("'", "'\\''")}'`;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const PREF_VALUES = ['oiloil', 'host'];

export function parseArgs(argv) {
  const flags = argv.slice(0, argv.includes('--') ? argv.indexOf('--') : argv.length);
  if (!argv.length || flags.includes('--help') || flags.includes('-h')) return { help: true };
  const aliases = { p: 'prompt', s: 'size', o: 'out', r: 'ref', b: 'background' };
  const opts = {}, words = [];
  let command, literal = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!literal && arg === '--') { literal = true; continue; }
    if (!literal && arg.startsWith('-')) {
      const match = arg.match(/^(?:--([a-z-]+)|-([psorb]))(?:=(.*))?$/s);
      const key = match && (match[1] ?? aliases[match[2]]);
      if (!['prompt', 'size', 'out', 'ref', 'background', 'timeout'].includes(key)) usage(`不支持选项 ${arg}`);
      if (key in opts) usage(`--${key} 只能写一次${key === 'ref' ? '，参考图仅支持一张' : ''}`);
      const value = match[3] ?? argv[++i];
      if (!value?.trim() || (match[3] === undefined && value.startsWith('-'))) usage(`--${key} 缺少值`);
      opts[key] = value;
    } else if (!command) {
      if (!['image', 'balance', 'status', 'pref'].includes(arg)) usage(`未知命令 ${arg}`);
      command = arg;
    } else words.push(arg);
  }
  if (!command) usage('缺少 image、balance、status 或 pref 子命令');
  if (command === 'pref') {
    if (Object.keys(opts).length) usage('pref 不接受选项，用法：pref | pref set <oiloil|host> | pref clear');
    if (words.length === 0) {
      opts.action = 'get';
    } else if (words.length === 1 && words[0] === 'clear') {
      opts.action = 'clear';
    } else if (words.length === 2 && words[0] === 'set') {
      if (!PREF_VALUES.includes(words[1])) usage('pref set 只接受 oiloil 或 host');
      opts.action = 'set';
      opts.value = words[1];
    } else {
      usage('pref 用法：pref | pref set <oiloil|host> | pref clear');
    }
    return { command, opts };
  }
  if (command === 'status') {
    if (Object.keys(opts).some(key => !['timeout', 'out'].includes(key))) usage('status 只接受一个幂等键、--out 和 --timeout');
    if (words.length !== 1 || !UUID_RE.test(words[0])) usage('status 需要一个有效的 image 请求幂等键');
    if (opts.out && /[\\/]$/.test(opts.out)) usage('--out 应为文件路径');
    if (opts.out) opts.out = path.resolve(opts.out);
    opts.key = words[0];
  } else if (command === 'balance') {
    if (words.length || Object.keys(opts).some(key => key !== 'timeout')) usage('balance 只接受 --timeout');
  } else {
    if (opts.prompt && words.length) usage('说明文字请用位置参数或 --prompt 中的一种');
    opts.prompt = (opts.prompt ?? words.join(' ')).trim();
    if (!opts.prompt) usage('image 缺少图片说明');
    const size = (opts.size ?? '1K').trim().toUpperCase();
    const dimensions = size.match(/^([1-9]\d*)\s*[X×]\s*([1-9]\d*)$/);
    if (!['1K', '2K', '4K'].includes(size) && !dimensions) usage('--size 应为 1K、2K、4K 或 宽x高');
    if (dimensions) {
      const width = Number(dimensions[1]), height = Number(dimensions[2]);
      const pixels = width * height;
      if (width % 16 !== 0 || height % 16 !== 0 || Math.max(width, height) > 3840
        || Math.max(width, height) / Math.min(width, height) > 3
        || pixels < 655360 || pixels > 8294400) {
        usage('自定义 --size 需满足：宽高为 16 的倍数，长边不超过 3840，比例不超过 3:1，总像素为 655360..8294400');
      }
    }
    opts.size = dimensions ? `${dimensions[1]}x${dimensions[2]}` : size;
    if (opts.background !== undefined) {
      const bg = opts.background.trim().toLowerCase();
      opts.background = bg === '透明' ? 'transparent' : bg;
      if (!['transparent', 'opaque', 'auto'].includes(opts.background)) usage('--background 应为 transparent、opaque 或 auto');
    }
    if (opts.out && /[\\/]$/.test(opts.out)) usage('--out 应为文件路径');
    opts.out = path.resolve(opts.out ?? 'assets/generated.png');
  }
  opts.timeout = Number(opts.timeout ?? (command === 'image' ? 250000 : 10000));
  if (!Number.isInteger(opts.timeout) || opts.timeout < 1 || opts.timeout > 900000) usage('--timeout 应为 1..900000 的整数');
  return { command, opts };
}

function oilConfigDir(env = process.env, platform = process.platform, home = os.homedir()) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  const root = platform === 'win32'
    ? env.APPDATA || p.join(home, 'AppData', 'Roaming')
    : env.XDG_CONFIG_HOME || p.join(home, '.config');
  return p.join(root, 'oil');
}

export function tokenConfigPath(env = process.env, platform = process.platform, home = os.homedir()) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  return p.join(oilConfigDir(env, platform, home), 'config.json');
}

export function preferencesPath(env = process.env, platform = process.platform, home = os.homedir()) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  return p.join(oilConfigDir(env, platform, home), 'preferences.json');
}

async function readPreferencesObject(file) {
  let raw;
  try { raw = await fs.readFile(file, 'utf8'); }
  catch (error) {
    if (error.code === 'ENOENT') return { exists: false, data: {} };
    throw error;
  }
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { exists: true, data: Object.fromEntries(Object.entries(parsed)) };
    }
    return { exists: true, data: {} };
  } catch {
    return { exists: true, data: {} };
  }
}

async function writePreferencesAtomic(file, data) {
  const dir = path.dirname(file);
  await fs.mkdir(dir, { recursive: true });
  const tmp = path.join(dir, `.preferences.${process.pid}.${randomUUID()}.tmp`);
  let handle;
  try {
    handle = await fs.open(tmp, 'wx', 0o600);
    await handle.writeFile(`${JSON.stringify(data, null, 2)}\n`, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    await fs.chmod(tmp, 0o600).catch(() => {});
    await fs.rename(tmp, file);
  } catch (error) {
    await handle?.close().catch(() => {});
    await fs.rm(tmp, { force: true }).catch(() => {});
    throw error;
  }
}

async function handlePref(opts) {
  const file = preferencesPath();
  const { exists, data } = await readPreferencesObject(file);
  if (opts.action === 'get') {
    const value = Object.hasOwn(data, 'image_tool') && PREF_VALUES.includes(data.image_tool) ? data.image_tool : null;
    if (value === 'oiloil') console.log('当前生图偏好：oiloil（优先使用内置 oiloil 生图工具）。');
    else if (value === 'host') console.log('当前生图偏好：host（优先使用宿主自带生图工具）。');
    else console.log('当前生图偏好：未设置（unset）。');
    return;
  }
  if (opts.action === 'set') {
    await writePreferencesAtomic(file, { ...data, image_tool: opts.value });
    if (opts.value === 'oiloil') console.log('已保存生图偏好：oiloil（优先使用内置 oiloil 生图工具）。');
    else console.log('已保存生图偏好：host（优先使用宿主自带生图工具）。');
    return;
  }
  if (!exists) {
    console.log('当前生图偏好：未设置（unset），无需清除。');
    return;
  }
  const rest = Object.fromEntries(Object.entries(data).filter(([key]) => key !== 'image_tool'));
  if (Object.keys(rest).length === 0) {
    await fs.rm(file, { force: true });
  } else {
    await writePreferencesAtomic(file, rest);
  }
  console.log('已清除生图偏好（当前为 unset）。');
}

export async function readOilToken(env = process.env, platform = process.platform, home = os.homedir()) {
  if (env.OIL_TOKEN?.trim()) return env.OIL_TOKEN.trim();
  try {
    const config = JSON.parse(await fs.readFile(tokenConfigPath(env, platform, home), 'utf8'));
    return typeof config?.token === 'string' ? config.token.trim() : '';
  } catch { return ''; }
}

function apiRoot() {
  try {
    const url = new URL(process.env.OIL_IMAGE_API?.trim() || 'https://api.oiloil.org');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
    return url.href.replace(/\/+$/, '');
  } catch { usage('OIL_IMAGE_API 应为不带凭据、查询参数或片段的 HTTP(S) 根地址'); }
}

async function referenceImage(file) {
  try {
    const info = await fs.stat(file);
    if (!info.isFile()) usage('--ref 应为本地图片文件');
    if (info.size > MAX_REF) usage('oiloil 参考图上限为 2 MiB，请缩小图片或去掉 --ref');
    const bytes = await fs.readFile(file);
    if (bytes.length > MAX_REF) usage('oiloil 参考图上限为 2 MiB，请缩小图片或去掉 --ref');
    const mime = bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ? 'image/png'
      : bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255 ? 'image/jpeg'
        : bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP' ? 'image/webp' : null;
    if (!mime) usage('--ref 仅支持 PNG、JPEG 或 WebP 文件');
    return `data:${mime};base64,${bytes.toString('base64')}`;
  } catch (error) {
    if (error instanceof CliError) throw error;
    throw new CliError(1, '无法读取参考图，请检查 --ref 路径和文件权限；本次未发送生成请求。');
  }
}

// Reserve writable recovery storage BEFORE sending a potentially charged request.
async function prepareOutput(out, idempotencyKey) {
  let dir, handle, requestHandle;
  try {
    await fs.mkdir(path.dirname(out), { recursive: true });
    const info = await fs.lstat(out).catch(error => { if (error.code !== 'ENOENT') throw error; });
    if (info?.isDirectory()) usage('--out 应为文件路径');
    dir = await fs.mkdtemp(path.join(os.tmpdir(), 'oiloil-image-'));
    const requestFile = path.join(dir, 'request.json');
    requestHandle = await fs.open(requestFile, 'wx', 0o600);
    await requestHandle.writeFile(JSON.stringify({ endpoint: 'images', idempotency_key: idempotencyKey }), 'utf8');
    await requestHandle.sync();
    await requestHandle.close();
    requestHandle = undefined;
    const file = path.join(dir, 'response.json');
    handle = await fs.open(file, 'wx', 0o600);
    return { dir, file, requestFile, handle, idempotencyKey, out };
  } catch (error) {
    await requestHandle?.close().catch(() => {});
    await handle?.close().catch(() => {});
    if (dir) await fs.rm(dir, { recursive: true, force: true }).catch(() => {});
    if (error instanceof CliError) throw error;
    throw new CliError(1, '无法准备输出或恢复目录，请检查 --out 和临时目录的权限及可用空间；本次未发送生成请求。');
  }
}

const UNSAFE_DETAIL_RE = /(?:上游|模型服务|供应商|渠道|线路)|(?:zenmux|openai|anthropic|gemini|aigocode|cloudflare)|(?:^|[^a-z])(?:yir|vertex)|(?:^|[^a-z])(?:google|replicate|midjourney|provider|upstream|traceback|stack|exception|syntaxerror|typeerror|referenceerror|econnreset|etimedout|enotfound|socket)(?:$|[^a-z])|(?:https?:|file:|at\s+\S+\s*\(|<\/?[a-z]|\\n)/i;

function apiErrorCode(raw) {
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === 'object' && !Array.isArray(data)
      && typeof data.request_id === 'string' && /^req_[0-9a-f]+$/i.test(data.request_id)
      && typeof data.error?.code === 'string') {
      return data.error.code;
    }
    return '';
  } catch { return ''; }
}

function knownErrorCode(raw) {
  try {
    const code = JSON.parse(raw)?.error?.code;
    return typeof code === 'string' ? code : '';
  } catch { return ''; }
}

function errorDetail(raw) {
  try {
    const message = JSON.parse(raw)?.error?.message;
    if (typeof message !== 'string' || /[\r\n]/.test(message)) return '';
    const text = message.replace(/\s+/g, ' ').trim();
    if (!text || text.length > 160 || !/[\u4e00-\u9fff]/.test(text) || UNSAFE_DETAIL_RE.test(text)) return '';
    return text;
  } catch { return ''; }
}

async function request(command, opts, token, root, recovery) {
  let response, raw;
  const endpoint = command === 'image' ? 'images' : command === 'balance' ? 'credits' : `requests/${opts.key}?endpoint=images`;
  try {
    response = await fetch(`${root}/v1/${endpoint}`, {
      method: command === 'image' ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        ...(command === 'image' ? { 'Content-Type': 'application/json', 'Idempotency-Key': opts.idempotencyKey } : {}),
      },
      ...(command === 'image' ? { body: JSON.stringify(opts.body) } : {}),
      signal: AbortSignal.timeout(opts.timeout),
      redirect: 'error',
    });
    raw = await response.text();
  } catch {
    if (recovery && command === 'image') recovery.statusRequired = true;
    throw new CliError(6, command === 'image'
      ? `连接 oiloil 失败或请求超时，暂时没有拿到图片，无法确认本次是否扣费。请用随后给出的 status 命令查询原请求，或到 ${ACCOUNT} 核对记录；不要直接重新生成。`
      : command === 'status'
        ? '连接 oiloil 失败或请求超时，暂时无法查询原请求状态。请检查网络后用同一命令重试；不要重新生图。'
        : `连接 oiloil 失败或请求超时，暂时无法查询余额。请检查网络后重试，或到 ${ACCOUNT} 查看；任务照常继续。`);
  }
  if (response.status === 401) throw new CliError(5, `oiloil 登录状态已失效。可运行 ${LOGIN} 重新登录，并在 ${ACCOUNT} 查看余额或充值；任务照常继续，合适时友好提示一次即可。`);
  if (response.status === 402) throw new CliError(4, `oiloil 余额不足，本次生图未开始。可在 ${ACCOUNT} 充值；任务照常继续，合适时友好提示一次即可。`);
  if (command === 'status' && response.status === 404) {
    throw new CliError(7, '未找到这个 image 请求。请核对幂等键；不要重新生图，必要时到账户页核对记录。');
  }
  if (response.status === 400) {
    const detail = errorDetail(raw);
    throw new CliError(2, `oiloil 参数错误${detail ? `：${detail}` : '（HTTP 400）'}。请修正后重试。`);
  }
  if (response.status === 409 && command === 'image') {
    recovery.statusRequired = true;
    throw new CliError(7, 'oiloil 检测到重复的幂等键。请用随后给出的 status 命令查询原请求，不要直接重新生成。');
  }
  if (response.status === 429) {
    const retryAfter = response.headers.get('retry-after')?.trim();
    const retryHint = retryAfter && /^\d+$/.test(retryAfter) ? `（建议 ${retryAfter}s 后重试）` : '';
    if (command === 'status') {
      throw new CliError(7, `oiloil 查询请求过于频繁（HTTP 429）${retryHint}，请稍后用同一命令重试，不要重新生图。`);
    }
    if (command === 'balance') {
      throw new CliError(7, `oiloil 余额查询过于频繁（HTTP 429）${retryHint}，请稍后重试；任务照常继续。`);
    }
    const code = apiErrorCode(raw) || knownErrorCode(raw);
    if (code === 'rate_limit_exceeded') {
      throw new CliError(7, `oiloil 请求过于频繁（HTTP 429）${retryHint}，本次未收到图片且未扣费。请稍后重试。`);
    }
    if (code === 'cost_budget_exceeded') {
      throw new CliError(7, `oiloil 当前生图额度已达上限（HTTP 429）${retryHint}，本次未收到图片且未扣费。请稍后重试。`);
    }
    const detail = errorDetail(raw);
    throw new CliError(7, `oiloil 请求频率或额度受限（HTTP 429）${detail ? `：${detail}` : ''}${retryHint}，本次未收到图片且未扣费。请稍后重试。`);
  }
  if (response.status >= 400 && response.status < 500) {
    throw new CliError(7, `oiloil 拒绝了请求（HTTP ${response.status}），未收到图片。请检查请求后重试。`);
  }
  if (!response.ok) {
    if (command === 'image') {
      const code = response.status >= 500 ? apiErrorCode(raw) : '';
      if (response.status === 504 && code === 'timeout') {
        throw new CliError(7, 'oiloil 生成超时（HTTP 504），本次未收到图片且未扣费。请稍后重试。');
      }
      if (response.status === 502 && code === 'upstream_error') {
        throw new CliError(7, 'oiloil 服务暂时繁忙或不可用（HTTP 502），本次未收到图片且未扣费。请稍后重试。');
      }
      if (recovery) recovery.statusRequired = true;
      throw new CliError(7, `oiloil 服务响应异常（HTTP ${response.status}），暂时无法确认本次是否扣费。请用随后给出的 status 命令查询原请求，或到 ${ACCOUNT} 核对记录；不要直接重新生成。`);
    }
    if (command === 'status') {
      throw new CliError(7, `oiloil 服务响应异常（HTTP ${response.status}），暂时无法查询原请求状态。请稍后用同一命令重试，或到 ${ACCOUNT} 核对记录；不要重新生图。`);
    }
    throw new CliError(7, `oiloil 服务响应异常（HTTP ${response.status}），暂时无法查询余额。请稍后重试，或到 ${ACCOUNT} 查看；任务照常继续。`);
  }
  if (recovery) {
    // Persist only 2xx responses before validating image/usage, so a malformed paid result is recoverable.
    try {
      await recovery.handle.writeFile(raw, 'utf8');
      await recovery.handle.sync();
    } catch {
      // A second filesystem may still be writable; do not throw away the in-memory result.
      try { recovery.extra = await writeUnique(path.join(path.dirname(opts.out), `oiloil-response-${randomUUID()}.json`), Buffer.from(raw), 0o600); }
      catch { recovery.writeFailed = true; }
    }
    recovery.received = true;
  }
  try { return JSON.parse(raw); }
  catch { throw new CliError(7, 'oiloil 返回了无法解析的响应，未自动重试；请先核对账户记录。'); }
}

async function writeUnique(target, bytes, mode = 0o644) {
  const ext = path.extname(target), stem = target.slice(0, target.length - ext.length);
  for (let suffix = 0; ; suffix++) {
    const file = suffix ? `${stem}-${suffix}${ext}` : target;
    let handle;
    try { handle = await fs.open(file, 'wx', mode); }
    catch (error) { if (error.code === 'EEXIST') continue; throw error; }
    try {
      await handle.writeFile(bytes);
      await handle.sync();
      await handle.close();
      return file;
    } catch (error) {
      await handle.close().catch(() => {});
      await fs.rm(file, { force: true }).catch(() => {});
      throw error;
    }
  }
}

const validNumber = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;

function decodeImage(result) {
  const mime = result?.image?.mime_type, data = result?.image?.data;
  const ext = Object.hasOwn(MIME_EXT, mime) ? MIME_EXT[mime] : null;
  if (!ext || typeof data !== 'string' || !data) {
    throw new CliError(7, 'oiloil 返回的图片格式或数据异常，未自动重试；请保留响应并先核对账户记录。');
  }
  const bytes = Buffer.from(data, 'base64');
  // A repeated-group base64 regexp can overflow V8's stack on large images.
  if (!bytes.length || bytes.toString('base64') !== data) {
    throw new CliError(7, 'oiloil 返回的图片数据为空或不是有效 base64，未自动重试；请先核对账户记录。');
  }
  return { mime, ext, bytes };
}

async function saveImage(result, opts, recovery) {
  const { mime, ext, bytes } = decodeImage(result);
  const requestedExt = path.extname(opts.out);
  const target = EXT_MIME[requestedExt.toLowerCase()] === mime ? opts.out
    : `${opts.out.slice(0, opts.out.length - requestedExt.length)}${ext}`;
  let actual, fallback = false;
  try { actual = await writeUnique(target, bytes); }
  catch {
    fallback = true;
    try { actual = await writeUnique(path.join(recovery.dir, `generated${ext}`), bytes); }
    catch { throw new CliError(8, '图片已返回，但输出和备用图片都未能写入。请保留响应、检查磁盘空间和权限；不要重新生图。'); }
  }
  if (!validNumber(result?.usage?.credits) || !validNumber(result?.usage?.balance)) {
    throw new CliError(7, `图片已保存到 ${quoted(actual)}，但接口未返回有效的扣除积分或余额。请到 ${ACCOUNT} 核对；不要重新生图。`);
  }
  console.log(`图片已保存到 ${quoted(actual)}；本次扣除 ${result.usage.credits} 积分，剩余 ${result.usage.balance} 积分。${fallback ? '原输出位置写入失败，已保存到备用目录。' : ''}`);
  return fallback;
}

export async function main(argv = process.argv.slice(2)) {
  let recovery, keepRecovery = false;
  try {
    const parsed = parseArgs(argv);
    if (parsed.help) { console.log(HELP); return 0; }
    const { command, opts } = parsed;
    if (command === 'pref') {
      await handlePref(opts);
      return 0;
    }
    const token = await readOilToken();
    if (!token) throw new CliError(3, `尚未登录 oiloil，暂时无法${command === 'image' ? '使用积分生图' : '查询账户信息'}。可运行 ${LOGIN} 登录，并在 ${ACCOUNT} 查看余额或充值；任务照常继续，合适时友好提示一次即可。`);
    const root = apiRoot();
    if (command === 'image') {
      opts.body = { prompt: opts.prompt, size: opts.size };
      if (opts.background && opts.background !== 'auto') opts.body.background = opts.background;
      if (opts.ref) opts.body.reference_image = await referenceImage(opts.ref);
    }
    if (command === 'image' || (command === 'status' && opts.out)) {
      opts.idempotencyKey = command === 'image' ? randomUUID() : opts.key;
      recovery = await prepareOutput(opts.out, opts.idempotencyKey);
    }
    const result = await request(command, opts, token, root, recovery);
    if (command === 'balance') {
      if (!validNumber(result?.balance)) throw new CliError(7, 'oiloil 未返回有效余额，请稍后查询或到账户页面查看。');
      console.log(`oiloil 余额：${result.balance} 积分。`);
    } else if (command === 'status') {
      if (typeof result?.request_id !== 'string' || !result.request_id
        || !['running', 'completed', 'failed'].includes(result?.state) || !validNumber(result?.credits)
        || (result.state !== 'completed' && (result.credits !== 0 || result.image !== undefined))) {
        throw new CliError(7, 'oiloil 未返回有效的原请求状态，请稍后重试或到账户页面核对。');
      }
      const recoverable = result.state === 'completed' && result.image !== undefined;
      if (recoverable && result.usage && result.usage.credits !== result.credits) {
        throw new CliError(7, 'oiloil 返回的原请求积分不一致，请先到账户页面核对；不要重新生图。');
      }
      if (result.state === 'completed' && !recoverable && opts.out) {
        if (recovery) recovery.received = false;
        throw new CliError(7, '原请求已完成，但原图已过期或该请求早于结果恢复功能，无法通过 status 取回；请先核对账户记录，不要直接重新生图。');
      }
      if (recoverable && !opts.out) {
        if (!validNumber(result.usage?.credits) || !validNumber(result.usage?.balance)) throw new CliError(7, 'oiloil 未返回有效的原请求积分，请稍后重试或到账户页面核对。');
        decodeImage(result);
      }
      const note = result.state === 'running' ? '请求仍在处理，请勿重新生成。'
        : result.state === 'failed' ? '需要重试时请使用新的幂等键。'
          : recoverable ? (opts.out ? '' : '原图可恢复；用同一命令加 --out <文件> 保存。')
            : '原图已过期或该请求早于结果恢复功能，无法通过 status 取回。';
      if (!recoverable || !opts.out) console.log(`原请求状态：${result.state}；请求编号：${result.request_id}；已结算 ${result.credits} 积分。${note}`);
      if (recoverable && opts.out) keepRecovery = await saveImage(result, opts, recovery);
    } else keepRecovery = await saveImage(result, opts, recovery);
    return 0;
  } catch (error) {
    const failure = error instanceof CliError ? error : new CliError(1, '本地操作失败，请检查文件路径、权限和可用空间。');
    console.error(failure.message);
    keepRecovery = Boolean(recovery && (recovery.received || recovery.statusRequired));
    if (recovery?.received) console.error(`生成响应保留在 ${quoted(recovery.extra ?? recovery.file)}${recovery.writeFailed ? '（写入未完成，请检查磁盘空间）' : ''}；请先恢复已返回的结果，不要重新生图。`);
    if (recovery?.statusRequired) console.error(`原请求幂等键：${recovery.idempotencyKey}。可运行 node <skill>/scripts/oiloil-image.mjs status ${recovery.idempotencyKey}${recovery.out ? ` --out ${shellQuote(recovery.out.replaceAll(path.sep, '/'))}` : ''} 查询并恢复原图；请求信息保留在 ${quoted(recovery.requestFile)}。`);
    return failure.code;
  } finally {
    await recovery?.handle.close().catch(() => {});
    if (recovery && !recovery.received) await fs.rm(recovery.file, { force: true }).catch(() => {});
    if (recovery && !keepRecovery) {
      await fs.rm(recovery.dir, { recursive: true, force: true }).catch(() => {});
      if (recovery.extra) await fs.rm(recovery.extra, { force: true }).catch(() => {});
    }
  }
}

const real = file => fs.realpath(file).catch(() => path.resolve(file));
if (process.argv[1] && await real(process.argv[1]) === await real(fileURLToPath(import.meta.url))) {
  process.exitCode = await main();
}
