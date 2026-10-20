/**
 * dsh-local-github-readme：GitHub 仓库 README 优化工具集。
 *
 * 注册四个模型可见工具：
 *   readme_scan    —— 扫本地仓库或 GitHub 链接，返回写 README 需要的事实清单
 *   readme_assets  —— 按 plan 渲染首图 banner / 过程图 flow（Pillow，2x 超采样）
 *   readme_lint    —— 检查 README 的图片/链接/章节标号/表格/必需章节
 *   readme_publish —— git add / commit / push（失败自动退避重试，绝不 force）
 *
 * 依赖：Python + Pillow（优先用 DSH 自带运行时，见 pythonPath()）。
 * 数据目录：~/.dsh/github-readme（可用 GITHUB_README_HOME 覆盖）。
 */
import { existsSync, mkdirSync, writeFileSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { homedir } from 'node:os';
import { dirname, join, relative, extname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'tool-github-readme';
export const inject = ['tools'];

const PKG_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT_ASSETS = join(PKG_DIR, 'scripts', 'render_readme_assets.py');
const DATA_HOME = process.env.GITHUB_README_HOME || join(homedir(), '.dsh', 'github-readme');
const REPOS_DIR = join(DATA_HOME, 'repos');
const WORK_DIR = join(DATA_HOME, 'work');

const SKIP_DIRS = new Set(['.git', 'node_modules', 'dist', 'build', 'out', '.next', '.venv',
  'venv', '__pycache__', 'coverage', 'target', 'vendor', 'assets']);
const TEXT_EXT = new Set(['.js', '.mjs', '.cjs', '.ts', '.py', '.json', '.yml', '.yaml',
  '.toml', '.ps1', '.sh', '.md', '.txt']);
const IMG_EXT = new Set(['.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif']);

/* ---------------- 基础执行 ---------------- */
function pythonPath() {
  if (process.env.GITHUB_README_PYTHON) return process.env.GITHUB_README_PYTHON;
  const bundled = join(homedir(), '.dsh', 'dsh-runtimes', 'dsh-primary-runtime',
    'dependencies', 'python', 'python.exe');
  if (existsSync(bundled)) return bundled;
  return process.platform === 'win32' ? 'python.exe' : 'python3';
}

function run(cmd, args, { cwd, timeoutMs = 60000, env, signal } = {}) {
  return new Promise((resolvePromise) => {
    let child;
    let done = false;
    let onAbort = null;
    const finish = (value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (signal && onAbort) signal.removeEventListener('abort', onAbort);
      resolvePromise(value);
    };
    const abort = () => {
      if (done) return;
      try { child.kill(); } catch { /* ignore */ }
      finish({ code: -1, stdout: '', stderr: 'aborted by host', aborted: true });
    };
    try {
      child = spawn(cmd, args, {
        cwd,
        windowsHide: true,
        env: { ...process.env, ...(env || {}) },
      });
    } catch (err) {
      done = true;
      resolvePromise({ code: -1, stdout: '', stderr: String(err.message || err) });
      return;
    }
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      if (done) return;
      try { child.kill(); } catch { /* ignore */ }
      finish({ code: -1, stdout, stderr, timedOut: true });
    }, timeoutMs);
    child.stdout.on('data', (b) => { stdout += b.toString('utf8'); });
    child.stderr.on('data', (b) => {
      stderr += b.toString('utf8');
      if (stderr.length > 20000) stderr = stderr.slice(-20000);
    });
    child.on('error', (err) => finish({ code: -1, stdout, stderr: String(err.message || err) }));
    child.on('close', (code) => finish({ code, stdout, stderr }));
    if (signal) {
      if (signal.aborted) {
        abort();
      } else {
        onAbort = abort;
        signal.addEventListener('abort', onAbort, { once: true });
      }
    }
  });
}

async function runPython(args, timeoutMs = 180000, cwd, signal) {
  const py = pythonPath();
  if (py.includes('python') && !existsSync(py) && py !== 'python.exe' && py !== 'python3') {
    throw new Error(`找不到 Python 解释器：${py}（可用 GITHUB_README_PYTHON 指定）`);
  }
  if (!existsSync(SCRIPT_ASSETS)) throw new Error(`渲染脚本缺失：${SCRIPT_ASSETS}`);
  const r = await run(py, [SCRIPT_ASSETS, ...args], { cwd: cwd || DATA_HOME, timeoutMs, signal });
  return r;
}

function lastResultJson(stdout) {
  const line = String(stdout || '').split(/\r?\n/).reverse()
    .find((l) => l.startsWith('RESULT_JSON:'));
  if (!line) return null;
  try {
    return JSON.parse(line.slice('RESULT_JSON:'.length));
  } catch {
    return null;
  }
}

/* ---------------- 仓库扫描 ---------------- */
function safeReadJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function walk(root, depth, maxEntries) {
  const out = [];
  const walkDir = (dir, level) => {
    if (out.length >= maxEntries) return;
    let items;
    try {
      items = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const it of items) {
      if (out.length >= maxEntries) return;
      const p = join(dir, it.name);
      const rel = relative(root, p).replace(/\\/g, '/');
      if (it.isDirectory()) {
        if (SKIP_DIRS.has(it.name)) continue;
        out.push(`${rel}/`);
        if (level < depth) walkDir(p, level + 1);
      } else {
        let size = 0;
        try { size = statSync(p).size; } catch { /* ignore */ }
        out.push({ path: rel, bytes: size });
      }
    }
  };
  walkDir(root, 1);
  return out;
}

function collectImages(root, deps) {
  const out = [];
  const walkDir = (dir, level) => {
    if (out.length >= 60 || level > deps) return;
    let items;
    try {
      items = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const it of items) {
      const p = join(dir, it.name);
      if (it.isDirectory()) {
        if (SKIP_DIRS.has(it.name) && it.name !== 'assets') continue;
        walkDir(p, level + 1);
      } else if (IMG_EXT.has(extname(it.name).toLowerCase())) {
        let size = 0;
        try { size = statSync(p).size; } catch { /* ignore */ }
        out.push({ path: relative(root, p).replace(/\\/g, '/'), bytes: size });
      }
    }
  };
  walkDir(root, 1);
  return out;
}

function findEnvVars(root, entries) {
  const hits = new Map();
  let scanned = 0;
  for (const e of entries) {
    if (typeof e !== 'object' || !e.path) continue;
    const ext = extname(e.path).toLowerCase();
    if (!TEXT_EXT.has(ext) || e.bytes > 200000) continue;
    if (scanned >= 120) break;
    let text;
    try {
      text = readFileSync(join(root, e.path), 'utf8');
    } catch {
      continue;
    }
    scanned += 1;
    const patterns = [
      /process\.env\.([A-Z][A-Z0-9_]{2,40})/g,
      /os\.environ(?:\.get)?\(\s*["']([A-Z][A-Z0-9_]{2,40})["']/g,
      /ENV\s+([A-Z][A-Z0-9_]{2,40})/g,
    ];
    for (const re of patterns) {
      let m;
      while ((m = re.exec(text)) !== null) {
        const key = m[1];
        if (!hits.has(key)) hits.set(key, new Set());
        hits.get(key).add(e.path);
      }
    }
  }
  return [...hits.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(0, 60)
    .map(([key, files]) => ({ key, files: [...files].slice(0, 3) }));
}

function parseReadmeFacts(readmePath, root) {
  if (!existsSync(readmePath)) return null;
  const text = readFileSync(readmePath, 'utf8');
  const headings = [];
  for (const line of text.split(/\r?\n/)) {
    const m = /^(#{1,3})\s+(.+)$/.exec(line.trim());
    if (m) headings.push({ level: m[1].length, text: m[2].trim() });
  }
  const images = [];
  const imgRe = /!\[([^\]]*)\]\(([^)\s]+)\)|<img[^>]+src=["']([^"']+)["']/g;
  let m;
  while ((m = imgRe.exec(text)) !== null) {
    images.push((m[2] || m[3] || '').trim());
  }
  const links = [];
  const linkRe = /\[[^\]]+\]\(([^)\s]+)\)/g;
  while ((m = linkRe.exec(text)) !== null) {
    const t = m[1].trim();
    if (t.startsWith('#') || /^[a-z]+:/i.test(t)) continue;
    links.push(t);
  }
  return {
    path: readmePath,
    bytes: Buffer.byteLength(text, 'utf8'),
    lines: text.split(/\r?\n/).length,
    chars: text.length,
    headings,
    images: [...new Set(images)],
    relativeLinks: [...new Set(links)],
    hasBanner: /banner\.(png|webp|jpg)/i.test(text),
    hasFlow: /(process-flow|audit-flow|flow)\.(png|webp|jpg)/i.test(text),
    numberedHeadings: headings.filter((h) => h.level === 2 && /^\d+[.、]\s*/.test(h.text))
      .map((h) => h.text),
  };
}

async function gitInfo(root, signal) {
  const info = {};
  const remote = await run('git', ['-C', root, 'remote', 'get-url', 'origin'], { timeoutMs: 15000, signal });
  if (remote.code === 0) info.remote = remote.stdout.trim();
  const branch = await run('git', ['-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'], { timeoutMs: 15000, signal });
  if (branch.code === 0) info.branch = branch.stdout.trim();
  const log = await run('git', ['-C', root, 'log', '--oneline', '-5'], { timeoutMs: 15000, signal });
  if (log.code === 0) info.recentCommits = log.stdout.trim().split(/\r?\n/).filter(Boolean);
  const status = await run('git', ['-C', root, 'status', '--porcelain'], { timeoutMs: 15000, signal });
  if (status.code === 0) {
    const lines = status.stdout.trim().split(/\r?\n/).filter(Boolean);
    info.dirty = lines.length > 0;
    info.dirtyFiles = lines.slice(0, 20);
  }
  return info;
}

async function cloneRepo(url, signal) {
  const m = /github\.com[/:]([^/]+)\/([^/.]+?)(?:\.git)?\/?$/.exec(url.trim());
  if (!m) throw new Error(`无法识别 GitHub 仓库地址：${url}`);
  const owner = m[1];
  const repo = m[2];
  const target = join(REPOS_DIR, `${owner}__${repo}`);
  mkdirSync(REPOS_DIR, { recursive: true });
  if (existsSync(join(target, '.git'))) {
    const pull = await run('git', ['-C', target, 'fetch', '--depth', '1', 'origin'], { timeoutMs: 120000, signal });
    return { repoRoot: target, cloned: false, fetched: pull.code === 0, url: `https://github.com/${owner}/${repo}` };
  }
  const tmp = `${target}.tmp-${Date.now()}`;
  let lastErr = '';
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const r = await run('git', ['clone', '--depth', '1', url, tmp], { timeoutMs: 180000, signal });
    if (r.code === 0) {
      try {
        if (existsSync(target)) {
          const { rmSync } = await import('node:fs');
          rmSync(target, { recursive: true, force: true });
        }
        const { renameSync } = await import('node:fs');
        renameSync(tmp, target);
        return { repoRoot: target, cloned: true, fetched: true, url: `https://github.com/${owner}/${repo}` };
      } catch (err) {
        lastErr = String(err.message || err);
      }
    } else {
      lastErr = (r.stderr || r.stdout || '').trim().split(/\r?\n/).slice(-3).join(' ');
      await new Promise((res) => setTimeout(res, attempt * 3000));
    }
  }
  throw new Error(`clone 失败（重试 3 次）：${lastErr}`);
}

async function scanRepo({ path: localPath, url }, signal) {
  let repoRoot;
  let cloneMeta = null;
  if (url) {
    cloneMeta = await cloneRepo(url, signal);
    repoRoot = cloneMeta.repoRoot;
  } else if (localPath) {
    repoRoot = resolve(localPath);
    if (!existsSync(repoRoot)) throw new Error(`路径不存在：${repoRoot}`);
  } else {
    throw new Error('path 和 url 至少给一个');
  }
  const pkg = safeReadJson(join(repoRoot, 'package.json'));
  const readmePath = ['README.md', 'Readme.md', 'readme.md', 'README.zh-CN.md']
    .map((f) => join(repoRoot, f)).find((f) => existsSync(f)) || join(repoRoot, 'README.md');
  const entries = walk(repoRoot, 2, 220);
  const files = entries.filter((e) => typeof e === 'object');
  const extCount = {};
  for (const f of files) {
    const ext = extname(f.path).toLowerCase() || '(none)';
    extCount[ext] = (extCount[ext] || 0) + 1;
  }
  return {
    ok: true,
    repoRoot,
    clone: cloneMeta,
    name: pkg?.name || basename(repoRoot),
    description: pkg?.description || '',
    version: pkg?.version || '',
    license: pkg?.license || (existsSync(join(repoRoot, 'LICENSE')) ? 'LICENSE 文件存在' : ''),
    keywords: pkg?.keywords || [],
    scripts: pkg?.scripts || {},
    dsh: pkg?.dsh || null,
    packagePath: existsSync(join(repoRoot, 'package.json')) ? join(repoRoot, 'package.json') : '',
    src: (pkg?.repository && (pkg.repository.url || pkg.repository)) || '',
    homepage: pkg?.homepage || '',
    readme: parseReadmeFacts(readmePath, repoRoot),
    tree: entries.slice(0, 160),
    files: { total: files.length, byExt: Object.entries(extCount).sort((a, b) => b[1] - a[1]).slice(0, 12) },
    images: collectImages(repoRoot, 3),
    envVars: findEnvVars(repoRoot, files),
    git: await gitInfo(repoRoot, signal),
    suggested: {
      readmePath,
      assetsDir: join(repoRoot, 'assets', 'readme'),
      deaiGenre: 'report',
    },
  };
}

/* ---------------- 工具参数 ---------------- */
const SCAN_PARAMS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    path: { type: 'string', description: '本地仓库根目录（绝对或相对路径）。' },
    url: { type: 'string', description: 'GitHub 仓库地址，例如 https://github.com/owner/repo；会浅克隆到 ~/.dsh/github-readme/repos。' },
  },
};

const ASSETS_PARAMS = {
  type: 'object',
  additionalProperties: false,
  required: ['plan'],
  properties: {
    plan: {
      type: 'object',
      additionalProperties: true,
      description:
        '渲染计划。必填 outDir；可选 style（10 种首图风格 split/band/topbar/diagonal/center/terminal/editorial/cards/wave/minimal，省略则随机）、'
        + 'palette（ocean/emerald/violet/amber/rose/cyan/indigo/slate/lime/sunset，省略则按风格随机）、seed（固定随机组合）、'
        + 'theme（旧字段兼容）、banner、flow。banner 支持 title/mono/headline/bullets/chips/note/icon/leftTop/leftCard/leftCaption/footerLeft/footerRight；'
        + 'flow 支持 title/subtitle/badge/steps(title,tag,desc)/products(name,detail,color)/productsTitle/highlight/footerLeft/footerRight。',
    },
  },
};

const LINT_PARAMS = {
  type: 'object',
  additionalProperties: false,
  required: ['path'],
  properties: {
    path: { type: 'string', description: 'README.md 路径，或仓库根目录（自动找 README.md）。' },
    required: {
      type: 'array',
      items: { type: 'string' },
      description: '必需章节关键词，默认 ["它是什么","快速开始","License"]。',
    },
  },
};

const PUBLISH_PARAMS = {
  type: 'object',
  additionalProperties: false,
  required: ['path', 'message'],
  properties: {
    path: { type: 'string', description: '本地 git 仓库根目录。' },
    message: { type: 'string', description: 'commit 信息，写清改了什么。' },
    branch: { type: 'string', description: '推送分支，默认当前分支。' },
    files: { type: 'array', items: { type: 'string' }, description: '只提交这些路径（相对仓库根）；省略则 git add -A。' },
    dryRun: { type: 'boolean', description: 'true 时只返回 git status 和 diff --stat，不提交不推送。' },
    retries: { type: 'number', description: 'push 最大尝试次数，默认 4。' },
  },
};

/* ---------------- 渲染输出 ---------------- */
function renderScan(_args, v) {
  const lines = [
    `仓库：${v.name}${v.version ? ' v' + v.version : ''}　路径：${v.repoRoot}`,
    `描述：${v.description || '（无）'}`,
  ];
  if (v.clone) lines.push(`克隆：${v.clone.cloned ? '新克隆' : '复用缓存'} ${v.clone.url || ''}`);
  if (v.git?.remote) lines.push(`remote：${v.git.remote}　分支：${v.git.branch || '?'}　${v.git.dirty ? '有未提交改动' : '工作区干净'}`);
  if (v.readme) {
    lines.push(`README：${v.readme.lines} 行 / ${v.readme.bytes} 字节；标题 ${v.readme.headings.length} 个；图片 ${v.readme.images.length} 张；编号章节 ${v.readme.numberedHeadings.length} 个`);
    if (v.readme.images.length) lines.push(`  现有图片：${v.readme.images.slice(0, 8).join('、')}`);
  } else {
    lines.push('README：不存在');
  }
  lines.push(`文件：${v.files.total} 个，主要类型 ${v.files.byExt.map(([e, n]) => `${e}:${n}`).join(' / ')}`);
  if (v.envVars.length) lines.push(`环境变量（${v.envVars.length}）：${v.envVars.slice(0, 12).map((e) => e.key).join('、')}`);
  lines.push(`建议：README=${v.suggested.readmePath}；素材目录=${v.suggested.assetsDir}`);
  return [{ type: 'text', text: lines.join('\n') }];
}

function renderAssets(_args, v) {
  const lines = ['已生成素材：'];
  for (const img of v.images) lines.push(`  ${img.kind}: ${img.path}（${Math.round(img.bytes / 1024)} KB）`);
  if (v.banner) {
    lines.push(`首图：风格 ${v.banner.style}（${v.banner.styleName}）· 配色 ${v.banner.palette} · seed ${v.banner.seed}${v.banner.random ? '（随机）' : ''}`);
  }
  lines.push('README 里用相对路径引用，例如 assets/readme/banner.png。');
  return [{ type: 'text', text: lines.join('\n') }];
}

function renderLint(_args, v) {
  const lines = [
    `README 检查：${v.ok ? '通过' : '有问题'}（error ${v.errors.length} / warn ${v.warnings.length}）`,
    `章节 ${v.stats.headings} 个，编号章节 ${v.stats.numbered} 个；图片 ${v.stats.images}，相对链接 ${v.stats.links}`,
  ];
  for (const e of v.errors.slice(0, 20)) lines.push(`  ✗ [error] L${e.line || '?'} ${e.message}`);
  for (const w of v.warnings.slice(0, 20)) lines.push(`  ! [warn] L${w.line || '?'} ${w.message}`);
  if (v.ok && v.warnings.length === 0) lines.push('没有发现问题。');
  return [{ type: 'text', text: lines.join('\n') }];
}

function renderPublish(_args, v) {
  if (v.dryRun) {
    return [{ type: 'text', text: `dryRun：${v.dirty ? '有改动' : '没有改动'}\n${v.diffStat || v.status || ''}`.trim() }];
  }
  const lines = [
    v.ok ? '已推送。' : '推送失败。',
    `仓库：${v.repoRoot}`,
    v.commit ? `commit：${v.commit}` : '',
    v.pushed ? `push：${v.remote || ''} ${v.branch}` : '',
    v.attempts ? `尝试次数：${v.attempts}` : '',
    v.error ? `错误：${v.error}` : '',
  ].filter(Boolean);
  return [{ type: 'text', text: lines.join('\n') }];
}

/* ---------------- README lint ---------------- */
function lintReadme({ path: p, required }) {
  let readmePath = resolve(p);
  if (!existsSync(readmePath)) throw new Error(`路径不存在：${readmePath}`);
  if (statSync(readmePath).isDirectory()) {
    const candidates = ['README.md', 'Readme.md', 'readme.md', 'README.zh-CN.md'];
    readmePath = candidates.map((f) => join(readmePath, f)).find((f) => existsSync(f)) || '';
    if (!readmePath) throw new Error('目录里没有 README.md');
  }
  const root = dirname(readmePath);
  const lines = readFileSync(readmePath, 'utf8').split(/\r?\n/);
  const errors = [];
  const warnings = [];
  const push = (list, message, line) => list.push({ message, line });
  const rel = (target) => {
    const clean = target.replace(/^\.\//, '').replace(/[?#].*$/, '');
    return resolve(root, clean);
  };

  let headings = 0;
  let numbered = 0;
  let images = 0;
  let links = 0;
  let firstH2 = -1;
  let hasBanner = false;
  const nums = [];
  const tableRows = [];

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    const lineNo = idx + 1;
    const h = /^(#{1,3})\s+(.+)$/.exec(line);
    if (h) {
      headings += 1;
      if (h[1].length === 2) {
        if (firstH2 === -1) firstH2 = lineNo;
        const m = /^(\d+)[.、]\s*/.exec(h[2]);
        if (m) {
          numbered += 1;
          nums.push({ n: Number(m[1]), text: h[2], line: lineNo });
        }
      }
    }
    if (!hasBanner && idx < (firstH2 === -1 ? lines.length : firstH2)) {
      if (/!\[[^\]]*\]\([^)]*banner[^)]*\)|<img[^>]+src=["'][^"']*banner/i.test(line)) hasBanner = true;
    }
    const imgRe = /!\[([^\]]*)\]\(([^)\s]+)\)|<img[^>]+src=["']([^"']+)["']/g;
    let m;
    while ((m = imgRe.exec(line)) !== null) {
      images += 1;
      const src = (m[2] || m[3] || '').trim();
      if (/^https?:/i.test(src)) continue;
      if (!existsSync(rel(src))) push(errors, `图片不存在：${src}`, lineNo);
    }
    const linkRe = /\[([^\]]+)\]\(([^)\s]+)\)/g;
    while ((m = linkRe.exec(line)) !== null) {
      const t = m[2].trim();
      if (/^https?:|^#|^mailto:/i.test(t)) continue;
      links += 1;
      if (!existsSync(rel(t))) push(errors, `链接目标不存在：${t}`, lineNo);
    }
    if (/^\|/.test(line)) tableRows.push({ line: line, lineNo });
  });

  // 表格分隔行：只看每个表格的第一行
  for (const row of tableRows) {
    const prevLine = (lines[row.lineNo - 2] || '').trim();
    if (/^\|/.test(prevLine)) continue;
    const nextLine = (lines[row.lineNo] || '').trim();
    if (!/^\|?\s*:?-{2,}/.test(nextLine)) {
      push(warnings, '表格缺少分隔行（|---|）', row.lineNo);
    }
  }

  // 编号连续性
  if (nums.length >= 2) {
    const sorted = [...nums].sort((a, b) => a.n - b.n);
    for (let i = 0; i < sorted.length; i += 1) {
      const expect = i + 1;
      if (sorted[i].n !== expect) {
        push(errors, `章节编号不连续：第 ${i + 1} 个编号章节是 ${sorted[i].n}「${sorted[i].text}」`, sorted[i].line);
        break;
      }
    }
  } else if (nums.length === 0) {
    push(warnings, '没有编号章节（建议 ## 1. … ## N.）', firstH2 > 0 ? firstH2 : undefined);
  }

  if (firstH2 > 1 && !hasBanner) {
    push(warnings, '首屏没有 banner 图（建议 assets/readme/banner.png）', 1);
  }

  const want = (required && required.length ? required : ['它是什么', '快速开始', 'License']);
  const headingText = lines.filter((l) => /^#{1,3}\s+/.test(l.trim())).join('\n');
  for (const w of want) {
    if (!headingText.includes(w)) push(warnings, `缺少必需章节关键词：${w}`, undefined);
  }

  const ok = errors.length === 0;
  return {
    ok,
    readmePath,
    errors,
    warnings,
    stats: { headings, numbered, images, links },
  };
}

/* ---------------- 发布 ---------------- */
const NETWORK_HINTS = /(could not resolve|failed to connect|connection (reset|timed out)|timed out|network is unreachable|unable to access|early eof|rpc failed)/i;
const AUTH_HINTS = /(authentication failed|could not read username|permission denied|403 forbidden|invalid username or password)/i;

async function publish({ path: p, message, branch, files, dryRun, retries }, signal) {
  const root = resolve(p);
  if (!existsSync(join(root, '.git'))) throw new Error(`不是 git 仓库：${root}`);
  if (!message) throw new Error('message 不能为空');
  const status = await run('git', ['-C', root, 'status', '--porcelain'], { timeoutMs: 30000, signal });
  if (status.code !== 0) throw new Error(`git status 失败：${status.stderr.trim()}`);
  const statusText = status.stdout.trim();
  if (dryRun) {
    const diff = await run('git', ['-C', root, 'diff', '--stat'], { timeoutMs: 30000, signal });
    return {
      ok: true,
      dryRun: true,
      repoRoot: root,
      dirty: Boolean(statusText),
      status: statusText,
      diffStat: diff.stdout.trim(),
    };
  }
  let addArgs;
  if (Array.isArray(files) && files.length) {
    addArgs = ['-C', root, 'add', '--', ...files];
  } else {
    addArgs = ['-C', root, 'add', '-A'];
  }
  const add = await run('git', addArgs, { timeoutMs: 60000, signal });
  if (add.code !== 0) throw new Error(`git add 失败：${add.stderr.trim()}`);
  const staged = await run('git', ['-C', root, 'diff', '--cached', '--name-only'], { timeoutMs: 30000, signal });
  const stagedFiles = staged.stdout.trim().split(/\r?\n/).filter(Boolean);
  if (stagedFiles.length === 0) {
    return { ok: true, repoRoot: root, nothingToCommit: true, branch: branch || '', message };
  }
  const commit = await run('git', ['-C', root, 'commit', '-m', message], { timeoutMs: 60000, signal });
  if (commit.code !== 0) {
    throw new Error(`git commit 失败：${commit.stderr.trim() || commit.stdout.trim()}`);
  }
  const branchName = branch
    || (await run('git', ['-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'], { timeoutMs: 15000, signal })).stdout.trim();
  const remote = (await run('git', ['-C', root, 'remote', 'get-url', 'origin'], { timeoutMs: 15000, signal })).stdout.trim();
  const maxAttempts = Math.max(1, Math.min(8, Number(retries) || 4));
  let attempts = 0;
  let lastErr = '';
  let pushed = false;
  for (let i = 1; i <= maxAttempts; i += 1) {
    attempts = i;
    const r = await run('git', ['-C', root, 'push', 'origin', `HEAD:${branchName}`], {
      timeoutMs: 180000,
      env: { GIT_TERMINAL_PROMPT: '0' },
      signal,
    });
    if (r.code === 0) {
      pushed = true;
      break;
    }
    lastErr = (r.stderr || r.stdout || '').trim().split(/\r?\n/).slice(-4).join(' ');
    if (AUTH_HINTS.test(lastErr) || i === maxAttempts) break;
    if (!NETWORK_HINTS.test(lastErr) && r.code !== -1) break;
    await new Promise((res) => setTimeout(res, i * 5000));
  }
  const head = await run('git', ['-C', root, 'rev-parse', '--short', 'HEAD'], { timeoutMs: 15000, signal });
  return {
    ok: pushed,
    repoRoot: root,
    branch: branchName,
    remote,
    commit: head.stdout.trim(),
    stagedFiles,
    attempts,
    pushed,
    error: pushed ? '' : lastErr,
  };
}

/* ---------------- 工具注册 ---------------- */
export function apply(ctx) {
  ctx.tools.register({
    name: 'readme_scan',
    description:
      'Scan a local repository or a GitHub repo URL and return the facts needed to rewrite its README: '
      + 'package.json fields, current README structure, file tree, images, env vars, scripts, git remote/branch/status. '
      + 'Read-only. Use it before rewriting a README or generating README assets. '
      + 'For a GitHub URL it does a shallow clone into ~/.dsh/github-readme/repos.',
    parameters: SCAN_PARAMS,
    timeoutMs: 600000,
    output: { schema: { type: 'object', additionalProperties: true }, render: renderScan },
    async execute(args, exec) {
      return scanRepo(args || {}, exec?.signal);
    },
  });

  ctx.tools.register({
    name: 'readme_assets',
    description:
      'Render README assets (banner 1200×600 and/or process flow diagram, auto height) from a structured plan, '
      + 'using Pillow with 2x supersampling. 10 banner styles are built in (split / band / topbar / diagonal / center / '
      + 'terminal / editorial / cards / wave / minimal) with 10 palettes (ocean / emerald / violet / amber / rose / cyan / '
      + 'indigo / slate / lime / sunset); if plan.style or plan.palette is omitted they are picked at random, and plan.seed '
      + 'reproduces the same combination. Writes PNGs into plan.outDir (usually <repo>/assets/readme); the result reports the '
      + 'style/palette/seed actually used. Reference images from README with relative paths like assets/readme/banner.png. '
      + 'Plan banner fields: title, mono, headline, bullets, chips, note, icon, leftTop, leftCard, leftCaption, footerLeft, footerRight; '
      + 'flow fields: title, subtitle, badge, steps[{title,tag,desc}], products[{name,detail,color}], highlight{title,text}, footerLeft, footerRight.',
    parameters: ASSETS_PARAMS,
    timeoutMs: 240000,
    output: { schema: { type: 'object', additionalProperties: true }, render: renderAssets },
    async execute(args, exec) {
      const plan = (args && args.plan) || {};
      if (!plan.outDir) throw new Error('plan.outDir 不能为空');
      mkdirSync(WORK_DIR, { recursive: true });
      mkdirSync(plan.outDir, { recursive: true });
      const planFile = join(WORK_DIR, `assets-${Date.now()}.json`);
      writeFileSync(planFile, JSON.stringify(plan, null, 2), 'utf8');
      const r = await runPython(['--plan-file', planFile], 180000, DATA_HOME, exec?.signal);
      const parsed = lastResultJson(r.stdout);
      if (!parsed) {
        throw new Error(`渲染脚本没有返回结果（exit ${r.code}）：${(r.stderr || r.stdout).trim().split(/\r?\n/).slice(-5).join(' ')}`);
      }
      if (!parsed.ok) throw new Error(parsed.error || '渲染失败');
      return { ...parsed, planFile };
    },
  });

  ctx.tools.register({
    name: 'readme_lint',
    description:
      'Check a README before publishing: relative image/link targets exist, numbered section headings are consecutive, '
      + 'tables have separator rows, required section keywords exist, and a banner image is present. '
      + 'Returns errors (must fix) and warnings (should fix). Accepts a README.md path or a repo root directory.',
    parameters: LINT_PARAMS,
    timeoutMs: 60000,
    isConcurrencySafe: () => true,
    output: { schema: { type: 'object', additionalProperties: true }, render: renderLint },
    async execute(args) {
      return lintReadme(args || {});
    },
  });

  ctx.tools.register({
    name: 'readme_publish',
    description:
      'Commit and push a repository update for GitHub: git add (all or selected files) → commit → push with retry/backoff '
      + 'on network failures (never force push). Use it after README/assets changes have been checked (readme_lint + deai audit). '
      + 'Set dryRun:true to preview status and diff stat first. Returns commit hash, pushed flag, attempts and last error.',
    parameters: PUBLISH_PARAMS,
    timeoutMs: 900000,
    output: { schema: { type: 'object', additionalProperties: true }, render: renderPublish },
    async execute(args, exec) {
      return publish(args || {}, exec?.signal);
    },
  });
}

export default { name, inject, apply };
