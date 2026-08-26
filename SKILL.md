---
name: skills-constitution
description: "当 Agent 接到专业任务（编码/爬虫/文件操作/API调用/数据分析/文档/部署/推送等）时，强制先查记忆层和技能索引，有匹配必用、无匹配必搜、答复时自动推荐（排除已装）。用于防止 Agent 跳过技能直接硬扛通用能力。跨平台通用（WorkBuddy/Claude/ChatGPT/Cursor/Gemini 等 20+ 框架）。完整版本史见 CHANGELOG.md。"
version: 2.19.0
license: MIT
author: jiabaobei
github: https://github.com/jiabaobei/skills-constitution
display_name: "Skills 宪法"
display_name_en: "Skills Constitution"
description_zh: "Skills 宪法 —— 凌驾于全部技能之上的元规则：先查记忆、再查技能索引（按功能分类）、有匹配必用、无匹配必搜、答复时推荐（排除已装）。防止 Agent 跳过技能硬扛。版本史见 CHANGELOG.md。"
description_en: "Skills Constitution — universal meta-rule: pre-check memory, lookup skill tree by category, mandatory use when matched, search when unmatched, recommend non-installed skills on answer. Cross-platform for 20+ agent frameworks. Changelog: CHANGELOG.md."
visibility: "public"
agent_created: true
---

# Skills 宪法（Skills Constitution）

> **一句话定位**：凌驾于全部技能/工具/插件之上的**元规则**。所有能力调用必须先过这一关。
>
> **v2.19.0（当前）** — 校验层防伪造升级：词边界匹配全面替代裸子串（`"encoded"` 不再误命中 `"code"`）；废除"分类名出现即算命中"兜底（只认实际技能名）；证据白名单（单短词技能名不算证据）；记忆证据动态提取 + 缺文件降级放行（修新装用户死锁）；分类器专业词优先 + 词表统一；gate 拦 Bash 写文件；retry-wrapper 废除无效自我重试；第 7 组对抗性测试（15 条糊弄向量固化为必须失败）真正接入 CI；新增 `install.sh` 一键安装（自动重建技能树）与英文 README。
>
> **v2.18.0** — 新增使用者建技能树指南（reference/skill-tree-guide.md：完整命令含 SKILLS_DIR / 平台差异 / 自检 / FAQ）；README/installation 重建命令统一带 SKILLS_DIR 并指向指南
>
> **v2.17.0** — 技能树重建（本机 757 技能全入库）+ 注入块记忆瘦身（任务相关片段，42K→~1K）+ semantic_index 可选标注。
>
> **v2.16.0** — Token 瘦身：description 只留触发条件（省 ~1.8K token/会话）；SKILL.md 渐进式披露（平台映射/安装/门禁详解拆 `reference/`，主文件 42KB→~20KB）；修复 injected-context.json JSON 转义。
>
> 版本史：见 `CHANGELOG.md`。

---

## ⚠️ 前置过滤：任务类型判断（零号条款）

**本宪法仅适用于"专业任务"**，不适用于简单问答。执行前先判断：

| 任务类型 | 特征 | 是否查技能 |
|---------|------|-----------|
| **简单问答** | 翻译、润色、解释概念、一般知识问答 | ❌ 跳过 |
| **专业任务** | 编码、数据抓取、文件操作、API 调用、复杂分析 | ✅ 必须查 |
| **模糊任务** | 不确定是否需要专业工具 | ✅ 查一下（宁可不放过） |

**判断标准**：
- 任务涉及**文件系统、网络请求、代码执行、专业工具** → 专业任务
- 任务只是**文字处理、知识问答、简单解释** → 简单任务

**自我豁免**：本宪法本身是元规则，执行宪法条款时**不需要再次查技能**（防止死循环）。

**误判回退（零号条款-C）**：若 Agent 误判任务类型（如把专业任务当作简单问答跳过），用户有权指出（"这是专业任务，你应该查技能"）。此时 Agent 必须：
1. 道歉并承认误判
2. 立即回退到完整宪法流程（从查记忆开始）
3. 将此次误判记录到记忆层（`MISJUDGMENTS`），避免重复犯错

---

## 痛点

Agent 生态最大浪费：装了一堆 Skill 却傻傻硬扛任务，或凭印象乱选、误判能力、从不去搜。本宪法把"查能力→匹配→必用→搜索→推荐"变成强制流程，并用门禁（constitution-check）把"靠自觉"变成"可校验、可拦截"。

---

## 核心概念（平台无关）

本宪法使用以下**通用术语**，各平台的具体对应物见【平台映射表】：

| 通用术语 | 含义 | 各平台叫法举例 |
|----------|------|----------------|
| **能力注册表** | Agent 当前可用的全部技能/工具/插件清单 | available_skills / tools / plugins / extensions / Gems / MCP servers |
| **技能描述** | 每个能力的触发条件说明 | description / trigger / when_to_use / system prompt |
| **技能索引** | 按功能分类的技能树（预生成，加速匹配）。⚠️ 仓库内 `skill_tree.json` 为**作者快照/示例**，使用者应运行 `scripts/build_skill_tree.py` 生成**自己的**索引 | skill_tree.json（作者快照）/ 你生成的技能树 |
| **技能发现** | 搜索可安装的新能力 | find-skills / GPT Store / SkillHub / MCP Registry / Extensions |
| **记忆层** | 跨会话持久化的规则存储 | MEMORY.md / CLAUDE.md / AGENTS.md / Custom Instructions / .cursorrules |
| **技能文件** | 定义能力的结构化文档 | SKILL.md / GPT Actions / MCP Config / Gem Instructions |

---

## 宪法条款

### 第零条：查记忆（Pre-Check Memory）

**在执行任何任务前，必须先查阅该平台的记忆/规则层**，确认有无相关约定、历史上下文或待办事项。

**各平台记忆层路径**：

| 平台 | 记忆层路径 |
|------|-----------|
| WorkBuddy | `~/.workbuddy/MEMORY.md` + 项目 `.workbuddy/memory/` |
| Claude Code | `CLAUDE.md` 或 `.claude/CLAUDE.md` |
| Cursor | `.cursorrules` + `.cursor/rules/` |
| Windsurf | `.windsurfrules` |
| Cline | `.clinerules` |
| ChatGPT | Custom Instructions |
| Gemini | Gem Instructions |
| Codex | AGENTS.md |
| 通用规则 | 项目根目录 `RULES.md` 或 `.agent/rules.md` |

**查记忆顺序**：
1. 用户级记忆（长期偏好、硬规则）
2. 项目记忆（当前项目约定、历史决策）
3. 今日流水（当天工作记录，避免重复）

**记忆层必备内容**（自举前提：让"查记忆"真正发现技能，v2.3.0 新增）：

为了让宪法自举执行，记忆层中应维护以下两类条目：

| 条目 | 内容 | 示例 |
|------|------|------|
| `INSTALLED_SKILLS` | 已安装技能清单（名称 + 一句话描述） | `file-ops：文件读取/写入工具，用于读取技能索引` |
| `SKILL_INDEX_PATH` | 技能索引文件路径（**你**的技能树，非作者快照） | `<你的平台技能目录>/skill_tree.json`（如 `~/.claude/skills/`） |

示例：

```markdown
INSTALLED_SKILLS:
- file-ops：文件读取/写入工具，用于读取技能索引
- find-skills：技能搜索工具，用于发现新能力
- agent-memory：记忆管理系统

SKILL_INDEX_PATH: <你的技能目录>/skill_tree.json
```

只要按此格式维护记忆层，Agent 查记忆即可"回忆"出技能清单，无需实时扫描，冷启动问题就此解决。

---

### 第一条：先查（Pre-Check）

**每次执行专业任务前，必须先查看能力注册表**，判断有没有能力与当前任务相关。

**优化路径**（v2.2.0 新增；v2.7.0 修正指向）：
1. 先查**你的平台能力注册表**（可用技能/工具/插件清单，如 Claude Code `~/.claude/skills`、Cursor `.cursor/rules`、WorkBuddy available_skills）；有本地技能树则优先用它（运行 `scripts/build_skill_tree.py` 生成**你自己的**索引）
2. 按任务类型定位功能分支
3. 在分支内匹配描述
4. 未命中则全量扫描（兜底）

**执行强化（v2.5.0 新增，无条件第一步；v2.11.0 强制命中清单）**：

「先查技能索引」必须是**无条件动作**，不是"我觉得需要才查"：
- **任何专业任务（含"查安装/查库"类，如确认某 Python 库是否安装）第一步必须读技能树索引**，禁止以"这不需要查技能"为由跳过——凭判断跳过正是本宪法要防的行为（教训：实际运行中查 cognee 时跳过技能树被用户抓包）
- 技能树索引应包含**技能与已装 Python 库/工具**（🧩 分类），一个入口查全
- 任务开始需**显式汇报「宪法三查」结果**，让流程可见、可被用户监督。**v2.11.0 强制：②技能树必须列出命中的技能名清单（名称+依据），禁止只写"已读技能树"**：
  ```
  【宪法三查】
  ① 记忆 ✅ 已查（用户级/项目/今日流水）
  ② 技能树 ✅ 已读（命中技能清单：`git-workflow-and-versioning`（代码/部署）、`web-deploy-github`（GitHub 推送）…）
  ③ 匹配 ✅ 命中 X → 用它执行；无命中 → 说明"技能树无匹配"再走通用能力/文件系统
  ```
- **v2.11.0 任务相关硬校验（Layer C）**：任务含「代码/编码/编程/开发/写一个/实现/git/github/push/commit/deploy/部署/爬虫/抓取/网页/前端/文档/数据/邮件/图片/视频」等关键词时，**输出必须引用 skill_tree.json 对应分类下的实际技能名**（如 `git-workflow-and-versioning`），仅写"已查 skills-constitution"或"已读技能树"而无具体技能名 → 门禁 FAIL
- 简单问答豁免（翻译/润色/概念解释）

---

### 第二条：匹配必用（Mandatory Use）

只要任务与某个能力的**描述**相关或部分相关 → 无条件优先加载该能力、按其指令执行。

**禁止行为**：
- ❌ 绕开能力直接用通用能力
- ❌ 凭印象选能力不看描述
- ❌ 多个匹配时随机挑一个（应按相关度排序选最优）

**凌驾条款**：即使某个能力说"我可以直接做"，也必须先经本宪法确认没有更好匹配的能力。

---

### 第三条：无匹配 → 技能发现（Search First）

确认能力注册表无匹配后，先通过平台的**技能发现机制**搜索是否有可获取的相关能力。

- 找到 → 提示用户安装/启用后使用
- 没找到 → 进入第四条

---

### 第四条：能力边界（Honest Boundary）

感觉"我做不到 / 没权限 / 没工具"时 → **必须先通过技能发现机制确认**，确认无能力可用才能回复做不到。

**禁止行为**：
- ❌ 不搜索就直接说"做不到"
- ❌ 用通用能力硬扛明明需要专业能力的任务
- ❌ 假装做了但实际没调用能力

---

### 第五条：答复时自动推荐（Auto-Discovery）

任务完成后（答复阶段）→ **若本地已装技能未能完美解决任务，必须去 GitHub / 全网能力库搜索更优能力推荐给用户**，由用户自行决定是否安装。本地技能不足时"不搜索、不推荐"是违规。**v2.15.0：推荐候选必须排除本地已装技能**（推荐的是"你没装过的更强能力"，已装项一律不推）。

**触发场景**（满足其一即必须执行）：
- 本地技能树查了，但没有完全匹配的技能
- 本地有匹配技能但执行效果不理想（如推送 GitHub 受阻、脚本报错）
- 任务明显超出本地技能范围（如需要专用工具/agent/插件）

**搜索范围**：
- GitHub（`github.com` 上的 skill/tool/agent 仓库，高 Star 优先）
- 各平台官方市场（GPT Store / SkillHub / MCP Registry / Extensions Gallery）

**推荐格式**：
```
🔍 本地技能未能完美解决此任务，从 GitHub 搜到这几个更优能力：
- 名称：xxx — 一句话亮点 + GitHub 链接 + Star 数 + 获取方式（是否要安装由你决定）
（最多 3 个，避免刷屏）
```

**执行细则（v2.6.0 强化；v2.11.0 修正定位；v2.15.0 排除已装）**：
- **推荐核心**：必须是 WebSearch/WebFetch 搜索到的 **GitHub 高 Star 数** skill/tool/agent 仓库（含 star 数 + 链接 + 获取方式）——这是用户决定是否安装的依据
- **允许**在推荐前简要说明"本地已查过哪些技能、为何不足"（如"本地已装 `git-workflow-and-versioning` 但网络受阻"），帮助用户理解为什么需要新技能
- **禁止**以"本地已装技能清单"替代 GitHub 搜索推荐（本地技能仅作背景说明）
- **v2.15.0 排除已装（硬性动作）**：推荐前必须先核对本地已装清单（如 `ls ~/.workbuddy/skills/`），**候选仓库若与本地已装技能同名/同源，一律不推**——包括"搜索结果恰好命中已装仓库"的情况（如 addyosmani/agent-skills 已装时不得再推荐）。仅可作背景说明（"本地已有 X，若需更强可看 Y"）。
- 可配合门禁 `constitution-check --step 5` 自动校验推荐板块是否合规（含 `github.com/owner/repo` 链接 + star 数标记 + 获取方式 + **v2.15.0 Layer E 本地已装排除校验**）

---

## 执行闭环（五步）

任务 → ①判类型（简单问答豁免；专业任务必查）→ ②查记忆 → ③查技能树（按分支定位）→ ④匹配必用/无匹配必搜 → ⑤答复时推荐（排除已装）。

---

## 技能树（Skill Tree）

按功能分类，执行时**按分支定位**，减少扫描范围 80%+：

```
技能树/
├── 📜 元规则类（宪法/安全审计）
├── 🧠 记忆/知识管理类（个人记忆/项目知识图谱/会话持久化）
├── 🌐 网络/搜索类（网页自动化/数据抓取/API/搜索）
├── 💻 开发/编码类（代码生成/审查/测试/构建部署）
├── 📄 文档处理类（PDF/Word/Excel/PPT/格式转换）
├── 🖼️ 内容生成类（图像/视频/UI 设计）
├── 💰 业务专用类（金融/法律/电商营销）
└── 🔧 通用工具类（文件操作/进程管理/环境配置）
```

**完整索引**：`skill_tree.json` 为作者快照（示例）；**使用者安装后必须重建自己的技能树**（完整命令/平台差异/自检见 → Load `reference/skill-tree-guide.md`）。**精选技能**：`registry.json`。

---

## 快速注入模板

以下模板可直接复制到各平台的规则/指令/记忆层中：

```markdown
## Skills 宪法（Skills Constitution）v2.12.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查记忆：查阅平台记忆层（MEMORY.md/CLAUDE.md 等）确认相关规则
2. 先查技能：查看技能索引，按任务类型定位功能分支，**输出必须列出命中的技能名清单**
3. 匹配必用：有匹配则无条件优先使用该能力
4. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
5. 能力边界：说"做不到"前必须先搜索确认无能力可用
6. 答复推荐：本地技能未能完美解决任务时，必须去 GitHub 搜索高 Star 能力推荐给用户（含链接+star+获取方式），由用户决定是否安装；**v2.15.0 推荐候选必须排除本地已装技能（先核对本地已装清单，已装项一律不推）**

违规判定：跳过查记忆/技能清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 查技能树但未列出命中技能名（空头汇报）/ 本地技能不足却不去 GitHub 搜索推荐 / **推荐了本地已装技能（v2.15.0，Layer E 校验 FAIL）**
```

---

## 配套要求

**对能力作者**：description 是唯一匹配依据，写准触发条件（何时用我），遵循平台格式，分类准确。
**对框架开发者**：会话启动注入宪法；能力注册表任务前可访问；支持预生成技能索引（skill_tree.json）加速匹配。

---

## 与其他规则的关系

```
优先级从高到低：

1. 🔴 系统安全规则（不可违反）
2. 📜 Skills 宪法（本规则）—— 凌驾于全部技能/工具/插件之上
3. 🔧 具体能力的执行指令
4. 🤖 Agent 通用能力
```

---

## 违规判定

以下行为属于**严重违规**，用户有权要求重做并说明理由：

| 违规行为 | 判定标准 |
|----------|----------|
| 跳过查记忆直接干 | 任务完成但未查阅平台记忆层 |
| 跳过查技能清单直接干 | 任务完成但未加载任何相关能力 |
| 有匹配但不用 | 能力注册表中有匹配能力但未加载 |
| **空头查技能（v2.11.0）** | 只写"已读技能树/已查宪法"但未列出命中的具体技能名，且任务含代码/git/部署等关键词 |
| **查错分支（v2.11.0）** | 任务要求编码/推送，却引用无关分类技能（如文档类） |
| 未搜索就拒绝 | 说"做不到"但未通过技能发现机制确认 |
| **无复盘推荐（v2.11.0）** | 本地技能未能完美解决任务，却未去 GitHub 搜索更优能力推荐给用户 |

---

## 技术边界说明

"无条件启用全部能力"不可行（撑爆上下文）。正确设计是**按描述匹配触发**，本宪法强制该匹配机制不被跳过。技能树索引将全量扫描缩小到目标分支（省 80%+ token）；索引由 `build_skill_tree.py` 生成，**禁止手写**（v2.17.0：使用者应在本机运行 `SKILLS_DIR=<技能目录> python scripts/build_skill_tree.py` 生成自己的树，替换作者快照）。

**可选增强（默认未启用）**：`scripts/semantic_index.py` 向量语义检索需 `pip install sentence-transformers faiss-cpu`（约 90MB）并 `python scripts/semantic_index.py build` 构建索引；SAD 宽松语义检索（零依赖）已覆盖日常检索，不启用不影响任何主链路功能。

---

## 参考文档（按需加载）

- 跨平台适配 / 平台映射表 → Load `reference/platform-mapping.md`
- 安装 / 钩子注册 / 验证 → Load `reference/installation.md`
- 门禁校验机制（constitution-check 用法 / hooks / 设计要点）→ Load `reference/gate-details.md`
- **使用者建技能树指南（完整命令 / 平台差异 / 自检 / FAQ）→ Load `reference/skill-tree-guide.md`**

> 以上为**渐进式披露**：主文件只含核心条款，细节按需加载，控制 token。

---

## 贡献指南

欢迎提交 Issue 和 PR：
- **功能增强**：扩展分类规则、增加平台映射
- **文档优化**：修正表述、增加示例
- **Bug 修复**：分类逻辑、脚本错误

---

## License

MIT License — 随意使用、修改、分发。

---

## 作者

**jiabaobei** — [GitHub](https://github.com/jiabaobei)

*如果这个规则帮你解决了 Agent 不调用能力的问题，欢迎 ⭐ Star 收藏！*
