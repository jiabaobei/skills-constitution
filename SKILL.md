---
name: skills-constitution
description: "当 Agent 接到专业任务（编码/爬虫/文件操作/API调用/数据分析/文档/部署/推送等）时，强制先查记忆层和技能索引，有匹配必用、无匹配必搜、答复时自动推荐（排除已装）。用于防止 Agent 跳过技能直接硬扛通用能力。跨平台通用（WorkBuddy/Claude/ChatGPT/Cursor/Gemini 等 20+ 框架）。完整版本史见 CHANGELOG.md。"
version: 2.27.4
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
> **v2.27.4（当前）** — 钩子注册补全：UserPromptSubmit 补注册注入保活钩子（pre-hook --hook-mode），修复"注入只在 SessionStart 做一次、长会话过期后 Agent 拿不到记忆+技能树 → 该调技能不调技能"的防线缺口；注册脚本全面直调 python（本机实测 bash 包装层单次 2.5~12.9s 是宿主 20s 超时元凶，pre-hook 本身仅 0.19s，直调后热路径门禁+注入合计 ≈3.5s）；MARKERS 收编 pre-hook.py，幂等替换/卸载可识别手工添加的注入钩子。回归 +3 条（13.6 注册完整性）。
> **v2.27.3** — 门禁状态文件写入健壮性修复（用户钦定"宪法不起作用"真因）：① 并发 tmp 重名 —— 三个钩子进程共用固定名 `state.json.tmp`，互相截断后被 `os.replace` 换回主文件；改为 tmp 名带 pid。② Windows `os.replace` 遇 PermissionError 时 v2.27.0 兜底 open(w) 直写会截断主文件 → 改为只做短重试，仍失败放弃写入保留旧文件。③ 兜底语义纠偏 —— 损坏即静默放行导致门禁**永久失效**；改为降级放行（不阻断、打印提示、不签通行证），下次任务开始自动重置恢复。附陈旧 tmp 清理 + 5 条回归用例（并发压测 0 损坏）。
> **v2.27.2** — 测试修正（零功能变更）：过时断言对齐 v2.27.0 单进程架构——13.0c 改断言单进程委托在位+嵌套自愈已删除、13.3 阈值 10s→18s（慢机器+Defender 首扫实测 6~18s 波动，热路径均值 ~7s）、13.1/13.3 超时捕获记失败不崩套件。
> **v2.27.1** — 技能图谱补全与降噪：① 自愈路径（refresh_injection）接入图谱候选（v2.27.0 曾漏传 []，导致 hook-mode 自愈产出的注入块缺「🕸️ 技能图谱」段）；② cluster 候选降噪——超采样 3 倍后，同簇成员必须与任务有词面交集（名称/描述，overlap_score>0）才收录，结构边（chains_to/co_anchor）与 alternative 保持原样；实测"写爬虫"任务候选 8→1（adobe-* 无关同簇成员全灭），注入块 4199→3458 字符，无关任务宁缺毋滥（0 候选）。
> **v2.27.0** — 钩子单进程化 + 门禁「任务开始拦一次、中途不再拦」真实生效：① 门禁状态文件改原子写入（修复 UserPromptSubmit/PreToolUse/Stop 三钩子并发写截断 → 通行证丢失 → 中途误拦，用户钦定 bug）；② 注入上下文过期(>24h)时门禁进程内自动刷新（修复任务开始拿不到通行证）；③ user-prompt-submit.sh 热路径进程启动 9 次→1 次、session-start.sh 6 次→1 次（解释器缓存 + builtin 读取 + exec 单次 python --hook-mode），慢机器实测 33~39s → 预期 <8s，不再触发宿主 20s 超时；④ bash 兜底注入块禁止引导 Agent 整读技能树文件（可达数十万字符），改为 pre-hook 按任务过滤约 3 千字符（省 token）。
> **v2.26.0** — 一键更新脚本 `scripts/update.sh` / `scripts/update.ps1`：把「更新前先去 GitHub 下载最新版、更新完成后自动在本地安装最新版」固化为脚本——下载最新 main 包（codeload + api 双保险）→ 完整性校验（半残包保持旧版不毁旧装）→ 透传参数跑新版安装器自动安装。
> **v2.25.1** — 钩子挂起修复：两条钩子的解释器检测加 3s 存活探针（修复 Windows 上 Microsoft Store 占位别名启动即挂起、被宿主 20s 强杀的卡死），stdin 读取限时 2s、自愈限时 10s，超时一律降级 fail-open，钩子永不卡任务。
> **v2.25.0** — 第五条「答复推荐」极度省 token 改造：推荐来源从"每次全盘搜 GitHub"改为**读本地排行榜快照**（`data/skill_rankings.json` + `scripts/recommend_skills.py` —— 零网络、约 20KB、纯确定性规则匹配 + 自动排除已装）；新增 `scripts/update_skill_rankings.py` 低频抓取权威排行榜（quemsah/awesome-claude-plugins，索引 3.6 万+ 仓库）重建快照，过期（>30 天）只提示不自动拉取；step5 新增推荐来源标注软校验（标注"本地排行榜快照"=省 token 最佳实践）。
> **v2.24.0** — 隐形技能治理 + 门禁「一次三查全程放行」+ 轻量索引。实测修复五项：
> ① `parse_frontmatter` 支持 YAML 块标量（`>`/`|` 及折叠变体）——旧版把 ponytail 全套等 137 个技能的 description 解析成单个 `>` 字符，检索永远命中不到（典型：用户装了 GitHub 116k★ 的 ponytail 却从未被调用）；
> ② 索引描述上限 200→2000——触发词（如 ponytail 的 lazy mode，位于第 400+ 字符）不再被截断丢弃；
> ③ 门禁任务级通行证——任务开始时三查通过（平台注入或 step1 PASS）即全程放行，拦截前移为任务开始时的一次性提醒（用户明确要求：任务开始已三查，中途不得再拦）；
> ④ 新增 `scripts/skill_doctor.py`：隐形/损坏技能自动诊断（8 类检查）+ `--fix` 自动修复 + `--quarantine` 隔离损坏 + `--emit-min-index` 轻量索引（约完整索引 20% 体积，截断部分保留长尾触发词，冷门技能省 token 仍可命中）；
> ⑤ 图谱锚点抽取固定用前 200 字符 + 停用词三批扩容 + DF 上限 0.05→0.035——描述放宽后锚点暴增曾产生 752 节点巨簇，现恢复 ≤80 纪律（回归测试 106/106）。
> **v2.23.0** — 技能图谱（借鉴 GitNexus 预计算关系智能）：技能树之上叠加确定性关系图（`skill_graph.json`，随技能树重建自动产出）。三种边全部零依赖确定性抽取——`chains_to`（registry 的输出→输入 schema 交集）/ `co_anchor`（共享实体锚点，含停用词与文档频率过滤）/ `alternative`（同分类高重叠替代方案）；确定性标签传播聚成功能簇。三处落地：① 注入块从“整分类清单”收窄到“锚点技能的任务线图谱”（带“为什么相关”溯源，更省 token）；② 门禁 step3 新增 Layer F 图证据校验——引用的技能必须与任务锚点图谱连通，零连通带簇证据判 FAIL；③ 替代边不做放行凭证、不参与聚簇（纪律同 GitNexus 只对结构边做社区检测）。图缺失时全部链路行为与旧版一致（只加不删）。
>
> 完整版本史见 `CHANGELOG.md`。

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
- 技能树索引应包含**技能（独立 + 插件，v2.21.0）与已装 Python 库/工具**（🧩 分类），一个入口查全
- 任务开始需**显式汇报「宪法三查」结果**，让流程可见、可被用户监督。**v2.11.0 强制：②技能树必须列出命中的技能名清单（名称+依据），禁止只写"已读技能树"**：
  ```
  【宪法三查】
  ① 记忆 ✅ 已查（用户级/项目/今日流水）
  ② 技能树 ✅ 已读（命中技能清单：`git-workflow-and-versioning`（代码/部署）、`web-deploy-github`（GitHub 推送）…）
  ③ 匹配 ✅ 命中 X → 用它执行；无命中 → 说明"技能树无匹配"再走通用能力/文件系统
  ```
- **v2.11.0 任务相关硬校验（Layer C）**：任务含「代码/编码/编程/开发/写一个/实现/git/github/push/commit/deploy/部署/爬虫/抓取/网页/前端/文档/数据/邮件/图片/视频」等关键词时，**输出必须引用 skill_tree.json 对应分类下的实际技能名**（如 `git-workflow-and-versioning`），仅写"已查 skills-constitution"或"已读技能树"而无具体技能名 → 门禁 FAIL
- 简单问答豁免（翻译/润色/概念解释）

**第一条补充：双机制平台覆盖（v2.21.0）**

ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力同时来自**两条平行机制**——独立技能（技能目录下的 SKILL.md）与**插件技能**（插件包内的 SKILL.md）。本宪法所称"能力注册表 / 技能库 / 技能树"**一律同时覆盖两者**：

1. **同权重**：插件技能与独立技能在"先查 → 匹配必用"流程中地位完全相同，**禁止以"它是插件不是技能"为由绕过匹配**
2. **完整调用名**：插件技能的调用名通常为 `插件名:技能名`（如 `document-skills:docx`、`computer-use:computer-use`），命中后必须按完整调用名调用（双机制平台上裸技能名可能无法被 Skill 机制加载）
3. **自动入树**：`build_skill_tree.py` 自动扫描插件缓存编入技能树并标注调用名（已知平台路径自动发现；其他平台用环境变量 `PLUGIN_CACHE_DIRS` 或仓库根 `plugin_roots.json` 指定缓存目录；停用的市场/插件自动排除）
4. **插件附带能力同规则**：插件提供的斜杠命令 / MCP 工具同样属于"能力注册表"，有现成能力时禁止用通用能力重复造轮子

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

任务完成后（答复阶段）→ **若本地已装技能未能完美解决任务，优先读本地排行榜快照推荐更优能力**，由用户自行决定是否安装。本地技能不足时"不推荐"是违规。**v2.15.0：推荐候选必须排除本地已装技能**（推荐的是"你没装过的更强能力"，已装项一律不推）。**v2.25.0：推荐来源改为「本地排行榜快照优先」，极度省 token —— 每次答复不再全盘搜索 GitHub**。

**触发场景**（满足其一即必须执行）：
- 本地技能树查了，但没有完全匹配的技能
- 本地有匹配技能但执行效果不理想（如推送 GitHub 受阻、脚本报错）
- 任务明显超出本地技能范围（如需要专用工具/agent/插件）

**推荐来源（v2.25.0 优先级）**：
1. **本地排行榜快照（第一优先，零网络、零搜索）**：读 `data/skill_rankings.json`（仓库自带作者快照），跑 `python scripts/recommend_skills.py --task "<任务>"` —— 纯本地匹配关键词 + 按星数排序 + **自动排除本地已装技能**，输出 3 条（每条含 GitHub 链接 + star 数 + 获取方式，天然满足 step5 校验）。
2. **GitHub 搜索（仅快照无匹配时兜底）**：快照条目与任务零相关时，才用 WebSearch/WebFetch 搜 `github.com` 高 Star 仓库，**并在推荐板块标注"来源: GitHub 搜索"**。
3. **快照过期处理**：快照超过 `stale_days`（默认 30 天）未更新，推荐时顶部提示运行 `python scripts/update_skill_rankings.py` 刷新 —— **只提示不自动拉取**（省 token）。

**推荐格式**：
```
🔍 本次相关技能推荐（来源: 本地排行榜快照 data/skill_rankings.json, 更新于 2026-09-01）:
- 名称：xxx — 一句话亮点 + GitHub 链接 + Star 数 + 获取方式（是否要安装由你决定）
（最多 3 个，避免刷屏）
```

**执行细则（v2.6.0 强化；v2.11.0 修正定位；v2.15.0 排除已装；v2.25.0 快照优先）**：
- **推荐核心**：必须是 **GitHub 高 Star 数** skill/tool/agent 仓库（含 star 数 + 链接 + 获取方式）——这是用户决定是否安装的依据；数据来源优先本地排行榜快照（`recommend_skills.py` 输出），其次 GitHub 搜索
- **省 token 铁律（v2.25.0）**：推荐环节**默认零网络**——只读本地 `data/skill_rankings.json`（约 20KB）跑确定性规则匹配；只有快照缺失或任务与快照零相关时，才允许发起 GitHub 搜索
- **快照刷新（低频）**：`python scripts/update_skill_rankings.py` 从权威排行榜仓库（quemsah/awesome-claude-plugins 等）抓取 Top100 重建快照；建议每次发布会/每周跑一次，平时不跑
- **允许**在推荐前简要说明"本地已查过哪些技能、为何不足"（如"本地已装 `git-workflow-and-versioning` 但网络受阻"），帮助用户理解为什么需要新技能
- **禁止**以"本地已装技能清单"替代推荐（本地技能仅作背景说明）
- **v2.15.0 排除已装（硬性动作）**：推荐前必须先核对本地已装清单（如 `ls ~/.workbuddy/skills/`），**候选仓库若与本地已装技能同名/同源，一律不推**——包括"搜索结果恰好命中已装仓库"的情况（如 addyosmani/agent-skills 已装时不得再推荐）。`recommend_skills.py` 已内置该排除（含 `_<name>-references` 框架标记）；GitHub 搜索路径同样必须人工核对。仅可作背景说明（"本地已有 X，若需更强可看 Y"）。
- 可配合门禁 `constitution-check --step 5` 自动校验推荐板块是否合规（含 `github.com/owner/repo` 链接 + star 数标记 + 获取方式 + **v2.15.0 Layer E 本地已装排除校验** + **v2.25.0 推荐来源标注**：标注"本地排行榜快照"为省 token 最佳实践）

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

**技能图谱（v2.23.0）**：树是"行政区划"（人为分类），图谱是"自然聚落"（关系驱动）。`build_skill_tree.py` 重建技能树时自动产出 `skill_graph.json`（也可单独跑 `scripts/build_skill_graph.py` 从现有树重建）：节点=技能，边= `chains_to`（输出→输入 schema 衔接）/ `co_anchor`（共享实体锚点）/ `alternative`（替代方案），确定性标签传播聚成功能簇（如"代码发布"簇 = git 工作流 + 审查 + 部署）。用途：注入按任务线收窄、门禁 Layer F 图证据、推荐时说明技能间关系。

---

## 快速注入模板

以下模板可直接复制到各平台的规则/指令/记忆层中：

```markdown
## Skills 宪法（Skills Constitution）v2.25.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查记忆：查阅平台记忆层（MEMORY.md/CLAUDE.md 等）确认相关规则
2. 先查技能：查看技能索引，按任务类型定位功能分支，**输出必须列出命中的技能名清单**
   （技能索引含独立技能与插件技能（v2.21.0）：命中插件技能按其完整调用名 `插件名:技能名` 调用）
3. 匹配必用：有匹配则无条件优先使用该能力
4. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
5. 能力边界：说"做不到"前必须先搜索确认无能力可用
6. 答复推荐（v2.25.0 快照优先，极度省 token）：本地技能未能完美解决任务时，**优先读本地排行榜快照** `python scripts/recommend_skills.py --task "<任务>"`（零网络、自动排除已装、出 3 条含链接+star+获取方式）；快照无匹配时才去 GitHub 搜索；快照过期（>30 天）跑 `python scripts/update_skill_rankings.py` 刷新；**v2.15.0 推荐候选必须排除本地已装技能（先核对本地已装清单，已装项一律不推）**

违规判定：跳过查记忆/技能清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 查技能树但未列出命中技能名（空头汇报）/ 本地技能不足却不去推荐（快照优先） / **推荐了本地已装技能（v2.15.0，Layer E 校验 FAIL）** / **命中插件技能却以"它是插件"为由绕过（v2.21.0）**
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
| **无复盘推荐（v2.11.0；v2.25.0 快照优先）** | 本地技能未能完美解决任务，却未做推荐（优先读本地排行榜快照 `recommend_skills.py`） |

---

## 技术边界说明

"无条件启用全部能力"不可行（撑爆上下文）。正确设计是**按描述匹配触发**，本宪法强制该匹配机制不被跳过。技能树索引将全量扫描缩小到目标分支（省 80%+ token）；索引由 `build_skill_tree.py` 生成，**禁止手写**（v2.17.0：使用者应在本机运行 `SKILLS_DIR=<技能目录> python scripts/build_skill_tree.py` 生成自己的树，替换作者快照）。

**门禁证据链（v2.22.0）**：门禁（constitution-gate）认两种"三查已完成"证据，满足其一即放行写操作、收尾不重复校验：① 本任务内 `constitution-check --step 1` 真实校验通过（手动路径）；② 平台已注入记忆+技能树（注入上下文 ready）**且**本任务内实际调用过命中技能（Skill 调用由门禁自动记录）。同任务内的追加式消息不重置证据；门禁自身的状态/豁免/违规文件禁止被 Agent 篡改（篡改即拦截）。

**插件技能扫描（v2.21.0）**：双机制平台（ZCode / Claude Code / DeepSeek Harness 等）上，技能树同时编入插件缓存里的插件技能——已知平台路径自动发现（ZCode 会进一步按其 config 的插件启用表排除停用项）；其他平台用 `PLUGIN_CACHE_DIRS` 环境变量（多个目录用系统路径分隔符）或仓库根 `plugin_roots.json`（`{"cache_dirs": ["..."]}`）指定缓存目录；`PLUGIN_SCAN=0` 可整体关闭。插件条目带 `qualified_name`（完整调用名）字段，pre-hook 注入时自动标注。

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
