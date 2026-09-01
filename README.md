# Skills Constitution

> **Skills 宪法** —— 凌驾于全部技能/工具之上的元规则，强制 Agent 先查后用、有匹配必用、无匹配必搜。跨平台通用（WorkBuddy / Claude / ChatGPT / Cursor / Gemini / ...）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.23.0-blue.svg)](SKILL.md)
[![Skills Indexed](https://img.shields.io/badge/skills__indexed-author__snapshot-green.svg)](SKILL_TREE.md)

**English**: [README_EN.md](README_EN.md)

## 🚀 快速开始

### 一键安装（推荐，v2.21.0 全平台分流）

```bash
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh                 # 自动探测平台，装完自动重建技能树
```

脚本按平台机制自动分流（v2.21.0）：

| 平台形态 | 命令 | 效果 |
|---------|------|------|
| 技能目录型（WorkBuddy / Claude Code / ZCode） | `bash install.sh` | 复制 + **自动重建技能树（含插件技能）** + 自检 |
| 同上 + 强制拦截 | `bash install.sh --register-hooks` | 装完自动注册四个宿主钩子（带备份/回滚/幂等） |
| 规则文件型（Cursor / Windsurf / Cline） | `bash install.sh --platform cursor --target-dir <项目>` | 宪法写入规则文件（建议级） |
| 纯注入型（ChatGPT / Gemini / 扣子等） | `bash install.sh --platform prompt` | 自动提取注入模板供粘贴 |
| Windows | `powershell -File install.ps1` | 同技能目录型流程（需真机首验） |

**双机制平台覆盖（v2.21.0）**：ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力同时来自「独立技能 + 插件」两条平行通道。技能树重建会自动把**插件缓存里的插件技能**编入索引（ZCode / Claude Code 已知路径自动发现，停用插件自动排除；其他平台用 `PLUGIN_CACHE_DIRS` 环境变量或仓库根 `plugin_roots.json` 接入），插件技能在树中标注完整调用名（如 `document-skills:docx`），宪法条款同步覆盖：**命中插件技能与命中独立技能同权重，必须按完整调用名调用**。

钩子注册也可以单独跑：`python skills-constitution/scripts/register_hooks.py`（`--dry-run` 预览 / `--uninstall` 移除）。

### 一键注入（任何平台）

把下面这段复制到你的 Agent 的规则/指令/记忆层中：

````markdown
## Skills 宪法（Skills Constitution）v2.23.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查记忆：查阅平台记忆层（MEMORY.md/CLAUDE.md 等）确认相关规则
2. 先查技能：查看技能索引，按任务类型定位功能分支，**输出必须列出命中的技能名清单**
   （技能索引含独立技能与插件技能（v2.21.0）：命中插件技能按其完整调用名 `插件名:技能名` 调用）
3. 匹配必用：有匹配则无条件优先使用该能力
4. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
5. 能力边界：说"做不到"前必须先搜索确认无能力可用
6. 答复推荐：本地技能未能完美解决任务时，必须去 GitHub 搜索高 Star 能力推荐给用户（含链接+star+获取方式），由用户决定是否安装

双通道（v2.10.0）：简单任务（翻译/润色/解释）→ 零号条款豁免直接通用能力；
专业任务（编码/爬虫/API）→ pre-hook 强制注入记忆+技能树，未汇报【宪法三查】即被拦截。

任务相关硬校验（v2.11.0）：任务含"代码/git/部署"等关键词时，输出必须引用 skill_tree.json
对应分类的实际技能名（如 `git-workflow-and-versioning`），只写"已查宪法/已读技能树"而无技能名 → FAIL。

违规判定：跳过查记忆/技能清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 查技能树未列出命中技能名（空头汇报）/ 本地技能不足却不去 GitHub 搜索推荐 / **命中插件技能却以"它是插件"为由绕过（v2.21.0）**
````

### WorkBuddy / CodeBuddy

```bash
# 克隆仓库
git clone https://github.com/jiabaobei/skills-constitution.git

# 安装技能
cp -r skills-constitution ~/.workbuddy/skills/skills-constitution/

# 重建技能树（必做：生成你自己的索引，替换作者快照；完整命令/平台差异见 reference/skill-tree-guide.md）
SKILLS_DIR="$HOME/.workbuddy/skills" python scripts/build_skill_tree.py
```

### Claude Code

```bash
# 用户级
cp -r skills-constitution ~/.claude/skills/skills-constitution/
```

### Cursor / Windsurf / Cline

```bash
# 将宪法写入规则目录
cp SKILL.md .cursor/rules/skills-constitution.md
# 或
cp SKILL.md .windsurfrules
# 或
cp SKILL.md .clinerules
```

### ChatGPT / Gemini / 其他

将【快速注入模板】中的内容复制到：
- ChatGPT → Custom Instructions 或 GPT 的 System Prompt
- Gemini → Gem 的 Instructions
- 其他 → 系统提示词 / 记忆层

---

## 📋 宪法条款（v2.18.0）

### 第零条：任务分类（零号条款）
前置过滤：简单问答（翻译/润色/解释）→ 跳过查技能；专业任务（编码/爬虫/API）→ 必须查；模糊任务 → 查一下（宁可不放过）。v2.10.0 由 `pre-hook.py --classify` 确定性分类器执行，不依赖 Agent 自觉。

### 第一条：先查（Pre-Check）
每次执行专业任务前，查看能力注册表，判断有没有匹配的能力。v2.10.0 由 `pre-hook.py` 任务开始前强制注入记忆+技能树；v2.11.0 强制输出**命中技能名清单**（名称+依据），且任务含代码/git/部署等关键词时硬校验必须命中对应分类技能（Layer C）。

### 第二条：匹配必用（Mandatory Use）
有匹配则无条件优先加载该能力，禁止绕开直接用通用能力。v2.11.0：匹配判定必须引用实际技能名（step3 Layer C 校验）。

### 第三条：无匹配必搜（Search First）
无匹配时先通过技能发现机制搜索，再考虑通用能力。

### 第四条：能力边界（Honest Boundary）
说"做不到"前必须通过技能发现机制确认无能力可用。

### 第五条：答复推荐（Auto-Discovery）
本地技能未能完美解决任务时，必须去 GitHub / 全网搜索高 Star 相关能力推荐给用户（含链接+star+获取方式），由用户自行决定是否安装。本地不足却不去搜索 → 违规（v2.11.0 修正定位）。

---

## 🌲 技能树（Skill Tree）

按功能类型分类全部技能，Agent 执行时**按分支定位**，减少 80% 扫描量：

| 分类 | 说明 | 示例技能 |
|------|------|---------|
| 📜 元规则类 | 宪法、规则定义、安全审计 | `skills-constitution`, `skills-security-check` |
| 🧠 记忆管理类 | 个人记忆、项目知识、会话持久化 | `aiweko-memory-reports`, `agent-memory` |
| 🌐 网络/搜索类 | 网页自动化、数据抓取、API 调用 | `browser-skill`, `agent-browser`, `anysearch` |
| 💻 开发/编码类 | 代码生成、审查、测试、构建 | `code-review`, `pr-review`, `git-ops` |
| 📄 文档处理类 | PDF、Word、Excel、PowerPoint | `pdf`, `docx`, `xlsx`, `pptx` |
| 🖼️ 内容生成类 | 图像、视频、UI 设计 | `agnes-video-generator`, `image-to-ui` |
| 💰 业务专用类 | 金融、法律、电商、营销 | `配网规划评审器`, `wind-finance` |
| 🔧 通用工具类 | 文件操作、进程管理、环境配置 | `file-ops`, `process-manager` |

**完整索引**：仓库内 [SKILL_TREE.md](SKILL_TREE.md) / [skill_tree.json](skill_tree.json) 为**作者快照（示例）**；使用者在自己的环境运行 `scripts/build_skill_tree.py` 生成**自己的**技能树（或用平台自身能力清单）。**安装后必须重建**——完整命令（含 SKILLS_DIR）/平台差异/自检/FAQ 见 `reference/skill-tree-guide.md`

---

## 📦 技能注册表（registry.json）

精选开源技能/工具索引（作者整理），解决"装什么、从哪装"的问题。**按需安装，不打包全量**：

```bash
# 方式 1：直接 clone 来源仓库，复制技能目录到你的平台技能目录
git clone https://github.com/anthropics/skills.git
cp -r skills/skills/docx ~/.claude/skills/

# 方式 2：用包管理器（gh skill / sk 等）
gh skill install anthropics/skills docx
```

| 字段 | 说明 |
|------|------|
| `name` | 技能名 |
| `repo` | 来源仓库（`owner/repo`） |
| `path` | 技能在仓库内的目录（可选，以仓库 README 为准） |
| `description` | 一句话功能 |
| `category` | 分类（framework/documents/development/testing/security/discovery/ai-tools） |

条目均来自真实开源仓库，见 [registry.json](registry.json)。

---

## 🎯 解决的痛点

| 痛点 | 表现 | 宪法解决 |
|------|------|---------|
| **不调用** | 装了 100 个技能只用了 3 个 | 强制先查能力清单 |
| **调用幻觉** | 凭印象选技能，不看描述 | 必须匹配 description |
| **调用混乱** | 多个技能都能做，随机挑 | 按相关度排序选最优 |
| **能力误判** | 感觉"做不到"就直接拒绝 | 先搜索确认无能力 |
| **无复盘** | 做完就走，不看有没有更好技能 | 答复时自动推荐 |
| **扫描全量** | 每次任务扫全部技能 | 按技能树分支定位 |

---

## 📊 优先级规则

```
优先级从高到低：

1. 🔴 系统安全规则（不可违反）
2. 📜 Skills 宪法（本规则）—— 凌驾于全部技能/工具/插件之上
3. 🔧 具体能力的执行指令
4. 🤖 Agent 通用能力
```

---

## 🔍 执行流程

```
任务来了
    │
    ▼
┌─────────────────────┐
│ ① 查记忆层          │── 读取平台规则/历史上下文
│ (Pre-Check Memory)  │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ ② 查技能索引        │── 按任务类型定位分支
│ (Skill Tree Lookup) │
└─────────────────────┘
    │
    ├── 命中分类 → ③ 加载该分支技能描述
    │
    └── 未命中 → ④ 全量扫描 description 匹配
```

---

## 📝 违规判定

以下行为属于**严重违规**，用户有权要求重做并说明理由：

| 违规行为 | 判定标准 |
|----------|----------|
| 跳过查记忆直接干 | 任务完成但未查阅平台记忆层 |
| 跳过查技能清单直接干 | 任务完成但未加载任何相关能力 |
| 有匹配但不用 | 能力注册表中有匹配能力但未加载 |
| 未搜索就拒绝 | 说"做不到"但未通过技能发现机制确认 |
| 无复盘 | 答复时未搜索全网能力库（当任务与能力库明显相关时） |

---

## 🔒 门禁自检（v2.6.0 新增；v2.9.0 两层校验；v2.10.0 输入拦截+双通道；v2.11.0 任务相关硬校验；v2.22.0 三查证据链）

把「靠 Agent 自觉」变成「可校验、可拦截」。5 个 step 独立校验，状态文件链式依赖，默认软校验 + `--strict` 可选阻断。

> ⚠️ **仅适用专业任务**：简单问答（翻译/润色/解释概念）按零号条款跳过，用 `--simple` 声明，不跑门禁。

### 双通道分流（v2.10.0）+ 任务相关硬校验（v2.11.0）

```
任务进入
  ├─ pre-hook.py --classify（零号条款确定性分类器）
  │    ├─ 简单关键词（翻译/润色/解释/概念）→ 【通道A】跳过门禁，直接通用能力
  │    └─ 专业关键词（编码/爬虫/API/文件/部署）→ 【通道B】强制注入校验
  │         ├─ v2.11.0: --task 提取任务必需分类（代码/git/部署→code 分类）
  │         ├─ 未输出【宪法三查】→ BLOCKED（任务开始前被拦截，exit 1）
  │         ├─ 未引用任务对应分类技能名（如 git-workflow-and-versioning）→ BLOCKED
  │         └─ 已输出三查 + 已命中任务分类技能 → 继续 step1-5 全量校验
  └─ 模糊任务 → 宁可不放过，按通道B处理（零号条款：模糊任务查一下）
```

### 用法

```bash
# 双通道分流（推荐入口）：自动判定任务类型
python scripts/constitution-check --classify --input task.txt

# 双通道 + 任务相关硬校验（v2.11.0：专业任务必须引用对应分类技能名）
python scripts/constitution-check --classify --task "推送github代码" --input output.txt --strict

# 输入拦截：先校验开场是否已注入三查，未注入即阻断
python scripts/constitution-check --pre-hook --input output.txt --strict

# 生成注入块（任务开始前喂给 Agent；v2.11.0 含任务必需技能清单）
python scripts/pre-hook.py --task "推送github代码"

# 全量软校验（FAIL 只警告）
python scripts/constitution-check --input output.txt

# 严格模式（FAIL 即阻断，exit 1）
python scripts/constitution-check --input output.txt --strict

# 简单任务豁免（零号条款）
python scripts/constitution-check --simple

# Post-hook 重试循环（v2.9.0：失败自动注入提示重试，最多3次）
python scripts/retry-wrapper.py --input output.txt --max-retries 3

# 单步校验（如推荐板块）
python scripts/constitution-check --step 5 --input output.txt
```

| Step | 校验内容 | 对应条款 | 版本 |
|------|---------|---------|------|
| classify | 双通道分流：简单/专业/模糊 | 零号条款 | v2.10.0 |
| pre-hook | 输入拦截：开场已注入三查？任务必需技能命中？ | 第零/一条 | v2.10.0 / v2.11.0 |
| 1 | 宪法三查已汇报（软+硬+Layer C 任务相关） | 第零/一条 | v2.9.0 / v2.11.0 |
| 2 | 技能树已读或无匹配声明（软+硬+Layer C） | 第一条 | v2.9.0 / v2.11.0 |
| 3 | 命中技能已调用（软+硬+Layer C+Layer F 图证据） | 第二条 | v2.9.0 / v2.11.0 / v2.23.0 |
| 4 | 交付自检（非版本类自动跳过） | 全文件核查 | v2.6.0 |
| 5 | 推荐板块含 GitHub 链接+star 数（软+硬两层） | 第五条 | v2.9.0 |

> ⚠️ 设计边界：脚本是"增强层"，宪法正文永远是行为规则兜底。**禁止**把"必须先跑脚本"写进正文——在跑不了脚本的环境会被 Agent 判为"不可满足"而整体跳过宪法。

### 三查证据链（v2.22.0）

宿主钩子（`constitution-gate.py`）认两种"三查已完成"证据，满足其一即放行写操作、收尾不重复校验：① 本任务内 `constitution-check --step 1` 真实校验通过；② 平台已注入记忆+技能树（注入上下文 ready）且本任务内实际调用过命中技能（Skill 调用自动记录）。同任务追加式消息不重置证据；门禁自身状态/豁免/违规文件禁止被 Agent 篡改（篡改即拦截）。

---

## 📝 改版说明（CHANGELOG 摘要）

### v2.23.0（2026-09-01）— 技能图谱：技能树之上的确定性关系图（GitNexus 启发）
- **技能图谱 `skill_graph.json`**：重建技能树时自动产出（也可单跑 `scripts/build_skill_graph.py`）。三种边全部零依赖确定性抽取：`chains_to`（registry 输出→输入 schema 交集，原 step4 临时数据固化成图）/ `co_anchor`（共享实体锚点——含套话停用词表 + 文档频率过滤，实测滤掉 268 节点巨簇）/ `alternative`（同分类高重叠替代方案）
- **确定性标签传播聚类**（GitNexus 社区检测的零依赖简化形）：技能聚成功能簇（如 code/browser/word/email/部署线）；**纪律**：替代边不并簇、不做门禁放行凭证，只有结构边参与聚类和连通判断
- **注入按任务线收窄（省 token）**：注入块新增「🕸️ 技能图谱」段——任务锚点技能（SAD 排名精选）的同簇+一跳邻居，每条带"为什么相关"的边证据；轮转填充防单簇吃光预算
- **门禁 Layer F 图证据校验（step3）**：任务含必需关键词时，引用的技能必须与任务锚点图谱连通（同簇/结构边一跳），零连通带簇归属证据判 FAIL（溯源）；图缺失/引用不在图中 → 降级放行不误杀
- **作者快照图谱**：独立 457 节点 / 737 边 / 25 簇（最大簇 46）
- **测试组 10**（22 条）：锚点抽取/三种边/聚类纪律/确定性复现/门禁图证据/注入集成，全量 99 条零回归

### v2.22.0（2026-09-01）— 门禁双向修正：防绕过 + 防干扰 + 省 token
- **防绕过（门禁被骗）**：门禁自身状态文件（三查记录 / 豁免旗标 / 违规记录 / 注入上下文）禁止被 Agent 经 Write/Edit/Bash（重定向/tee/rm/mv/sed -i）篡改——旧版写一个豁免旗标文件即可全局豁免；Bash 写文件检测补 `sed -i`；step1 只认 `level=PASS` 的真实校验结果
- **防干扰（门禁误拦）**：门禁认可「平台已注入记忆+技能树 + 本任务内实际调用过技能」为完整三查证据链（Skill 调用自动记录），不再强求手动跑校验命令；同一任务的追加式消息（继续/好的/下一步…）不重置门禁；收尾阶段对已有证据链的任务不再重复文本校验、不再误记违规
- **注入自愈**：`user-prompt-submit.sh` 注入上下文缺失/过期时现场重跑 SessionStart 注入（幂等），不再直接【宪法拦截】挡任务
- **省 token**：注入块默认瘦身约 30%（SAD 候选 6→4、描述截断 60→40 字、每分类清单 12→8、记忆片段 1200→900 字、执行要求文案精简）；`hooks.json` 约 8KB 关键词 matcher 精简为 `.*`（分类在 hook 脚本内做）；SKILL.md 顶部多版本史压缩为一行移入 CHANGELOG
- **测试组 9**（19 条）：门禁文件保护 / 写检测 / 追加式消息 / 证据链放行 / 瘦身断言，全量 77 条零回归
- 端到端实测：无证据写文件被拦、篡改豁免旗标被拦、注入+调用技能后放行、追加消息不重置、收尾不误记违规，全部符合预期

### v2.21.0（2026-08-30）— 双机制平台覆盖：技能 + 插件
- **能力注册表 = 独立技能 ∪ 插件技能**：ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力来自两条平行机制，宪法条款（第一条补充）明确插件技能与独立技能同权重、命中必按完整调用名（`插件名:技能名`）调用，禁止以"它是插件"为由绕过
- **`build_skill_tree.py` 布局无关插件扫描**：已知平台路径自动发现（ZCode 含启用表过滤——config 里停用的插件不入树，`.DISABLED` 市场整棵跳过，打包层目录如 `payload/` 不干扰插件名推导）；其他平台用 `PLUGIN_CACHE_DIRS` 环境变量或仓库根 `plugin_roots.json` 免改代码接入
- **pre-hook 注入升级**：注入块与 SAD 候选展示插件技能完整调用名，`load_skill_aliases()` 输出调用名映射
- **install.sh/ps1 技能目录型新增 ZCode**（自动探测顺序 WorkBuddy > ZCode > Claude Code），自检口径改"独立+插件"
- **测试组 8**（18 条）：布局无关扫描/版本去重/停用过滤/打包层/入树集成/调用名渲染/环境变量接入，全量 58 条零回归
- 本机实测：ZCode 插件缓存扫描 15 个启用插件技能入树（`document-skills:docx` 等），沙箱安装 `--platform zcode` 全流程通过

### v2.20.0（2026-08-26）— 安装全平台分流 + 钩子自动注册
- **install.sh 按平台机制分流**：技能目录型自动重建树 / 规则文件型（Cursor/Windsurf/Cline）写入规则文件 / 注入型自动提取模板；新增 Windows 版 `install.ps1`
- **`register_hooks.py` 一条命令注册双平台钩子**：带备份/回滚/幂等/卸载，50 行手工配置成为历史

### v2.19.0（2026-08-26）— 校验层防伪造升级
- **词边界匹配 + 废除分类名兜底 + 证据白名单**：一个 `"encoded"` 子串打穿 Layer C 的漏洞被堵死，糊弄向量固化进 CI 对抗测试
- **修复新装用户死锁/崩溃**，gate 拦 Bash 写文件，retry-wrapper 废除无效自我重试

### v2.18.0（2026-08-24）— 使用者建技能树指南
- **新增 `reference/skill-tree-guide.md`**：为什么必须重建 / 完整命令（SKILLS_DIR+BINARIES_DIR，四平台）/ 3 步自检 / 5 条 FAQ
- **重建命令统一带 SKILLS_DIR**（README / installation 原裸命令会扫默认目录），SKILL.md 技能树章节改"安装后必须重建"

### v2.17.0（2026-08-24）— 技能树重建 + 注入记忆瘦身
- **技能树重建**：本机跑 `build_skill_tree.py`，**402 → 757 技能全入库**（替换 HUAWEI 快照，`skills_dir` 指向本机），修"查树即无匹配"
- **注入块记忆瘦身**：`extract_memory_relevant` 按任务相关性注入（铁律+top2 相关 section），**MEMORY.md 42KB → 注入 ~1KB**
- **semantic_index 明确可选（默认未启用）**：三处文档标注启用方式（sentence-transformers + faiss-cpu，约 90MB）

### v2.16.0（2026-08-24）— Token 瘦身
- **description 瘦身**：2069 字符 → ~415 字符，版本历史移出（放 CHANGELOG），只留触发条件——每次对话省 ~1.8K token
- **SKILL.md 渐进式披露**：平台映射表/安装验证/门禁详解拆 `reference/` 三文件，主文件 682 行/42KB → 327 行/8.4KB（省 80%），契约式引用按需加载
- **修复 injected-context.json JSON 转义**（heredoc 反斜杠导致钩子误报"宪法拦截"），改用 json.dump
- 注入去重确认：SessionStart 注入一次，无重复

### v2.15.0（2026-08-24）— 推荐排除已装技能
- **第五条补硬性条款**："推荐候选必须排除本地已装技能"——推荐前先核对本地已装清单（`ls ~/.workbuddy/skills/`），已装项一律不推（含"搜索结果恰好命中已装仓库"场景），仅可作背景说明
- **step5-check.py 新增 Layer E 本地已装排除校验**：推荐仓库名与本地技能目录同名（E1）或与本地 `_<name>-references` 已装框架标记匹配（E2）→ FAIL。修复真实案例：addyosmani/agent-skills 已装 24 技能仍被列入推荐
- **违规判定新增**："推荐了本地已装技能（Layer E 校验 FAIL）"
- AGENTS.md / 快速注入模板 / README 模板同步

### v2.14.0（2026-08-24）— 假查漏洞修复 + 跨机器可用
- **constitution-gate.py 回归**：作为 WorkBuddy settings.json 钩子的正式实现（UserPromptSubmit / PreToolUse / Stop 三事件），补齐 v2.13.x 缺的 WorkBuddy 宿主钩子
- **PreToolUse 新鲜度校验**：step1 的 ts 必须 ≥ 本任务 UserPromptSubmit 写入的 reset_ts，旧任务 PASS 不再赦免任何 Write/Edit（修复"一次 PASS 永久放行"）
- **Stop 违规硬记录**：最终回复未含【宪法三查】+ 任务相关技能名（Layer C）→ 写入 `.constitution-violations.json` 累计计数 + stderr 警告
- **UserPromptSubmit 违规警告注入**：有违规记录时输出到 stdout（平台注入 Agent 上下文），下个任务开头 Agent 即见警告，形成"事前拦 + 事后记 + 下次警"闭环
- **去掉 HUAWEI 硬编码**：`hooks/session-start.sh`、`hooks/user-prompt-submit.sh`、SKILL.md frontmatter 三处改为环境变量 `CODEBUDDY_PLUGIN_ROOT` 优先 + 脚本自定位兜底（定位失败报错/放行），跨机器不再静默失效
- **WorkBuddy 注册文档**：SKILL.md 安装章节新增 settings.json 三步注册示例（SessionStart / UserPromptSubmit / PreToolUse / Stop）

### v2.13.3（2026-08-21）— 失败可定位 + 兜底文案动态化
- **python 分支 stderr 不再被丢弃**：捕获进 `debug.pre_hook_stderr`（injected-context.json），失败原因可定位
- **兜底文案按真实原因动态化**：`fallback_reason` 区分「无 python」vs「python 分支失败」，bash 降级时给用户准确提示
- **injected-context.json 新增字段**：`python_branch_ok` / `fallback_reason`，供 UserPromptSubmit 钩子诊断
- 技能树索引重建：total=402

### v2.13.2（2026-08-21）— hooks 执行链路三大根因修复 + 版本号修正
- **解释器检测修复**：`python3/python/py` 逐个尝试，不再硬编码 python3（hook 环境 PATH 无 python3 导致 skill_tree.json 计数归零）
- **注入块输出到 stdout**：pre-hook.py 生成的完整注入块改为输出到 stdout，平台才能注入 Agent 上下文（此前只有统计行，无任何可执行内容）
- **版本号修正**：SKILL.md frontmatter / description_zh / description_en 三处版本标注统一为 v2.13.2
- 技能树索引重建：total=401

### v2.13.0（2026-08-21）— hooks 强制拦截上线
- **hooks.json 注册钩子**：`SessionStart`（启动注入）+ `UserPromptSubmit`（提交校验），WorkBuddy settings.json 一键注册
- **Ruler 跨平台分发**：一键将宪法安装到 10 个主流平台（Claude Code / Cursor / Windsurf / Cline / ChatGPT / Gemini / WorkBuddy / 扣子 / 文心 / 通义）
- **pre-hook --task 参数修复**：`bash user-prompt-submit.sh "$USER_PROMPT"` 支持直接传参（不再依赖 stdin JSON）
- **Windows 路径转换**：`to_win()` 函数将 Git Bash `/c/...` → `C:/...`，解决 python 在 Windows 下不认 `/c/` 路径的问题
- 完整细节见 [CHANGELOG.md](CHANGELOG.md)

### v2.12.0（2026-08-19）— SkillWeaver 启发：语义增强 + 防蒙混升级
- **任务同义词扩展**（`TASK_SYNONYM_MAP`）：口语表达不再漏判——"我要把代码传上去"（无 git 关键词）也能命中 code 必需分类，Layer C 恢复生效
- **SAD 宽松语义检索**：SkillWeaver 反馈循环的确定性实现——pre-hook 按 token 重叠度（零依赖）检索 top-K 候选技能注入，Agent 起草方案时带着候选完成用词对齐，token 再降一档
- **Layer D 语义相关性校验**（step3）：引用的技能必须与任务语义相关（overlap ≥ 0.10），杜绝"引用真实存在但与任务无关的技能"蒙混过关
- **多技能编排兼容性检查**（step4 + registry.json schema）：识别技能链 `A → B`，校验相邻技能 output→input 兼容
- **可选语义向量索引**（`scripts/semantic_index.py`）：sentence-transformers + FAISS 的完整实现作为可选增强层；缺依赖明确提示，主链路永远零依赖。**⚠️ v2.17.0 明确标注：默认未启用**——需要者自行 `pip install sentence-transformers faiss-cpu`（约 90MB）后运行 `python scripts/semantic_index.py build`；不启用不影响任何主链路功能（SAD 宽松语义检索为零依赖确定性实现，已覆盖检索需求）
- **分类子串误杀修复**：英文关键词改词边界匹配，`code` 不再误杀 `encode`、`search` 不再误杀 `research`
- 顺手修复 4 个已核实 Bug（正文版本号残留/CHANGELOG 链接/CI 死代码/badge 失真）
- 完整细节见 [CHANGELOG.md](CHANGELOG.md)

### v2.11.0（2026-08-16）— 任务相关硬校验（Layer C）+ 命中清单强制 + 推荐定位修正
- **新增 Layer C 任务相关硬校验**：任务含"代码/编码/编程/开发/写一个/实现/git/github/push/commit/deploy/部署/爬虫/抓取/网页/前端/文档/数据/邮件/图片/视频"等关键词时，输出必须引用 skill_tree.json 对应分类下的**实际技能名**（如 `git-workflow-and-versioning`）——彻底杜绝"查了 skills-constitution 就算查了技能"的空头汇报
- **三查汇报强制命中清单**：②技能树必须列出命中的技能名（名称+依据），禁止只写"已读技能树"
- **pre-hook.py 增强**：新增 `required_categories_for_task()` / `required_skills_for_task()` 确定性映射（任务关键词→必需分类→候选技能），注入块自动附加「任务必需技能」清单
- **step1/2/3 增加 Layer C**：未引用任务对应分类技能名 → FAIL；constitution-check 新增 `--task` 参数
- **第五条推荐定位修正**：本地技能未能完美解决任务时，必须去 GitHub 搜索高 Star 技能推荐给用户（含链接+star+获取方式），由用户自行决定是否安装；本地不足却不去搜索 → 违规
- 完整细节见 [CHANGELOG.md](CHANGELOG.md)

### v2.10.0（2026-08-16）— 输入拦截 + 双通道执行
- **新增 `pre-hook.py`**：任务开始前强制读取 MEMORY.md + skill_tree.json 生成注入块，Agent 上下文"被迫"已有记忆规则和技能树分类
- **双通道分流**：`--classify` 确定性分类器（零号条款协调）——简单任务（翻译/润色/解释）→ 通道A 零号条款豁免直接通用能力；专业任务（编码/爬虫/API）→ 通道B 强制注入校验 + step1-5 全量校验；模糊任务 → 宁可不放过按通道B
- **关键设计**：分类器是确定性代码，不依赖 Agent 自觉判断任务类型，杜绝"把专业任务误判为简单任务"逃逸
- 完整细节见 [CHANGELOG.md](CHANGELOG.md)

### v2.9.0（2026-08-16）— 三明治架构两层校验
- **Pre-hook 层**：Step1/2 硬校验，验证回复是否真实引用 MEMORY.md / skill_tree.json 内容（杜绝空头汇报）
- **Post-hook 层**：`retry-wrapper.py` 重试循环，失败自动注入错误提示并重试（最多3次），超限转人工
- **两层校验**：软校验（文本关键词）+ 硬校验（验证实际文件内容引用）


---

## 🏗️ 项目结构

```
skills-constitution/
├── SKILL.md                    # 宪法文档（主文件）
├── README.md                   # 本文件
├── CHANGELOG.md                # 版本日志
├── SKILL_TREE.md               # 技能树索引（人类可读）
├── skill_tree.json             # 技能树索引（机器可读）
├── skill_graph.json            # 技能图谱（v2.23.0：边+簇，随技能树重建）
├── scripts/
│   ├── build_skill_tree.py     # 分类脚本（v2.12.0 词边界匹配修复子串误杀；v2.21.0 插件技能扫描；v2.23.0 顺带重建图谱）
│   ├── build_skill_graph.py    # 技能图谱重建（从现有树+registry，v2.23.0）
│   ├── pre-hook.py             # 输入拦截+任务分类器（v2.10.0）；任务必需技能映射（v2.11.0）；同义词扩展+SAD 宽松检索（v2.12.0）；插件技能完整调用名注入（v2.21.0）；图谱候选注入（v2.23.0）
│   ├── semantic_index.py       # 可选语义向量索引（v2.12.0，sentence-transformers 可选依赖）
│   ├── constitution-check      # 门禁校验主入口（v2.6.0；v2.10.0 支持 --classify/--pre-hook；v2.11.0 支持 --task）
│   ├── retry-wrapper.py        # Post-hook 重试循环（v2.9.0）
│   ├── steps/                  # 5 个 step 独立校验脚本
│   │   ├── step1-check.py      # 三查汇报（软+硬+Layer C 任务相关，v2.11.0）
│   │   ├── step2-check.py      # 技能树已读（软+硬+Layer C，v2.11.0）
│   │   ├── step3-check.py      # 技能调用（软+硬+Layer C+Layer D 语义相关+Layer F 图证据，v2.23.0）
│   │   ├── step4-check.py      # 交付自检+多技能编排兼容性（v2.12.0）
│   │   └── step5-check.py      # 推荐板块（软+硬两层）
│   ├── tests/
│   │   └── run_tests.py        # 零依赖回归测试（v2.12.0，CI 可跑）
│   └── lib/                    # 状态文件 + 文本工具 + 图谱（v2.23.0 graph.py）
└── .github/
    └── workflows/
        └── build-skill-tree.yml  # 自动更新
```

---

## 📚 平台适配指南

详细适配指南见 [SKILL.md](SKILL.md) 中的【平台映射表】章节。

### 支持的框架

- **国际**：ChatGPT, Claude, Codex, Gemini, Cursor, Windsurf, Cline, GitHub Copilot
- **国内**：WorkBuddy, 扣子 (Coze), 文心一言, 通义千问, Kimi, 豆包, 智谱, 月之暗面, Dify
- **双机制平台（技能 + 插件，v2.21.0 完整覆盖）**：ZCode, Claude Code, DeepSeek Harness (dsh)

---

## 🤝 贡献

欢迎提交 Issue 和 PR：
- **功能增强**：扩展分类规则、增加平台映射
- **文档优化**：修正表述、增加示例
- **Bug 修复**：分类逻辑、脚本错误

---

## 📄 License

[MIT License](LICENSE) — 随意使用、修改、分发。

---

## 👤 作者

**jiabaobei** — [GitHub](https://github.com/jiabaobei)

*如果这个规则帮你解决了 Agent 不调用能力的问题，欢迎 ⭐ Star 收藏，转发给身边被 Agent 气到的朋友！*
