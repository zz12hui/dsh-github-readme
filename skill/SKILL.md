---
name: github-readme-optimize
description: Use when pushing/uploading any repository to GitHub, creating a GitHub repo, publishing a plugin/package, or optimizing a repo README. Rewrites README into the unified DSH-Market style (banner + process diagram + numbered sections + tables), renders assets with readme_assets, checks layout with readme_lint, self-audits copy with deai_audit, then commits and pushes with readme_publish. Also triggers on 上传 GitHub / 推仓库 / 发仓库 / 优化 README / README 排版 / 加首图 / 加过程图.
---

# GitHub 仓库 README 优化（github-readme-optimize）

默认规则：**只要这次会话要往 GitHub 推东西（新建仓库、git push、发布插件/仓库），先跑一遍本流程再推**。用户明确说「别改 README，直接推」才跳过。

## 用到的工具

插件 `dsh-local-github-readme` 提供四个模型可见工具：

| 工具 | 作用 | 关键输入 |
|---|---|---|
| `readme_scan` | 扫本地仓库或 GitHub 链接，返回写 README 需要的事实（package.json、README 现状、目录树、图片、环境变量、git 状态） | `path` 或 `url` |
| `readme_assets` | 按 plan 渲染首图 `banner.png` 和过程图 `flow.png` | `plan`（含 `outDir`） |
| `readme_lint` | 检查图片/链接、章节编号、表格分隔行、必需章节、首图 | `path`（README.md 或仓库根） |
| `readme_publish` | git add → commit → push（网络失败自动退避重试，绝不 force） | `path`、`message` |

工具没加载时（旧会话 / 还没重启 DSH）：直接跑脚本，路径 `~/.dsh/profiles/desktop/node_modules/dsh-local-github-readme/scripts/render_readme_assets.py`，其余步骤手动按本技能做。

## 标准流程（7 步）

1. **扫描事实**：`readme_scan({ path: "<仓库根>" })`；远端仓库用 `{ url: "https://github.com/owner/repo" }`（会浅克隆到 `~/.dsh/github-readme/repos`）。后面所有数字、版本、路径只从这里或代码里来。
2. **定章节**：按 `references/README-模板.md` 的编号骨架，删掉不适用章节；编号必须 1..N 连续。
3. **重写 README**：首图 + badges + `## 1. …` 到 `## N. …`；参数、路径、版本、命令全部表格化；补上「我们自己的描述」——真实数字、实测结果、设计取舍。
4. **生成素材**：`readme_assets({ plan })`。banner 必做；有 3 步以上流程就做 flow。plan 模板见 `references/素材-plan示例.json`，主题按项目选（blue / green / violet / orange）。
5. **看图**：`read_image` 检查两张图——文字溢出、标签打架、留白过多、断行难看。有问题改 plan 重渲染，别直接交付。
6. **校验**：
   - `readme_lint({ path })`：error 清零，warn 逐条判断；
   - `deai_audit`（genre 用 `report`，偏产品介绍可用 `article`）：总分 ≤25，且没有「标签式开头 / 空泛词 / 一眼 AI」打标；不达标按打标改，只改打标句，不删事实。
7. **推送**：先 `readme_publish({ path, message, dryRun: true })` 看 diff stat，再正式 `readme_publish({ path, message })`。返回 `ok:false` 时看 `error`：认证错误不要重试，网络错误脚本已自动退避。

## README 硬性规范

- 开头用 banner 当封面，不写 `#` 大标题（和 dsh-market 一致）：
  `<p align="center"><img src="./assets/readme/banner.png" width="100%" alt="项目名 —— 一句话说明"></p>`
- 紧跟一行居中 badges（DSH 版本 / 核心特性 / License），然后 `---` 分隔。
- 章节：`## 1. 它是什么`、`## 2. 效果预览`、`## 3. 过程/原理`、`## 4. 快速开始`、`## 5. 工具/命令`、`## 6. 配置与目录`、`## 7. 设计取舍`、`## 8. 手动排查`、`## 9. 卸载回滚`、`## 10. 常见问题`、`## 11. License`（可按项目增删，编号连续）。
- 表格必须 `|---|` 分隔行；表格比大段 bullet 好读。
- 版本号、安装命令、路径必须和代码一致：能实测就实测，不能实测就写「未验证」，不编。
- 中文写成「技术同事能照着复现」的样子，少形容词、多具体动作与数字。

## 图片规范

- banner：1200×600；左栏图标 + 小卡，右栏标题、卖点 bullet、标签 chips。
- flow：1200 宽、高度自适应；3–6 步，每步「标题 + 标签 + 一句说明」，最后可带产物条和提示条。
- 主题四选一，相邻项目换色区分；图标 glyph 可选 `play / check / doc / branch / bolt / puzzle`。
- 图片一律放 `assets/readme/`，README 用相对路径引用；仓库里已有 `docs/` 示例图就保留引用。

## 常见坑

- host 插件和技能都只在 DSH **启动时**加载：装完/更新后必须重启（含托盘退出），刷新页面不算。
- Consolas 等英文字体没有中文字形，中英混排不要用 mono，否则变方块。
- flow 标题太长会和右上角标签打架；渲染器会自动缩字号，但标题尽量 ≤ 26 字。
- `readme_lint` 报「章节编号不连续」时，先看是不是把 TOC 或「## 2.1」当成了编号章节。
- 推送失败：认证错误（403 / could not read username）不重试；网络错误（failed to connect / timeout）脚本会退避 3–4 次。
- 不改仓库原有事实：License、安装命令、版本号保持准确，README 只重排表达。

## 交付检查清单

- [ ] banner 首屏可见；流程型项目有 flow
- [ ] 编号 1..N 连续，表格分隔行齐全
- [ ] 图片、相对链接目标都真实存在（readme_lint 无 error）
- [ ] deai_audit ≤25，无「标签式开头 / 空泛词 / 一眼 AI」打标
- [ ] readme_publish 成功，拿到 commit hash
- [ ] 回复里给仓库链接、改了哪几块、commit hash
