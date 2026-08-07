---
name: skills-constitution
description: "Skills 宪法 —— 凌驾于全部技能/工具之上的元规则。强制 Agent 在执行任何任务前先查能力清单，有匹配必用、无匹配必搜、答复时自动推荐。解决 Agent 不调用已装 Skill、调用混乱、幻觉式硬扛任务三大痛点。跨平台通用：WorkBuddy / Claude Code / ChatGPT / Codex / Gemini / Cursor / Windsurf / Cline 等主流 Agent 框架均可适配。"
version: 2.0.0
license: MIT
author: jiabaobei
github: https://github.com/jiabaobei/skills-constitution
display_name: "Skills 宪法"
display_name_en: "Skills Constitution"
description_zh: "Skills 宪法 —— 凌驾于全部技能之上的元规则，强制 Agent 先查后用、有匹配必用，跨平台通用"
description_en: "Skills Constitution — universal meta-rule governing all skill/tool invocations across agent platforms (ChatGPT, Claude, Codex, Gemini, WorkBuddy, Cursor, etc.)"
visibility: "public"
agent_created: true
---

# Skills 宪法（Skills Constitution）

> **一句话定位**：这是凌驾于全部技能/工具/插件之上的**元规则**。无论用什么 Agent 框架，所有能力调用都必须先过这一关。

## 痛点

当前 Agent 生态最大的浪费：**装了一堆无敌的 Skill/工具/插件，但 Agent 傻傻的硬扛任务**——明明有更专业的能力可用，却靠通用能力瞎猜，导致：

| 痛点 | 表现 | 后果 |
|------|------|------|
| **不调用** | 任务来了直接干，不扫能力清单 | 装了 100 个技能只用了 3 个 |
| **调用幻觉** | 凭印象选技能，不看描述是否匹配 | 用错技能、答非所问 |
| **调用混乱** | 多个技能都能做，随机挑一个 | 结果不稳定、质量不可控 |
| **能力误判** | 感觉"做不到"就直接拒绝 | 从不检查有没有技能能做 |
| **无复盘** | 做完就走，不看有没有更好技能 | 技能库长期闲置、越装越乱 |

## 核心概念（平台无关）

本宪法使用以下**通用术语**，各平台的具体对应物见【平台映射表】：

| 通用术语 | 含义 | 各平台叫法举例 |
|----------|------|----------------|
| **能力注册表** | Agent 当前可用的全部技能/工具/插件清单 | available_skills / tools / plugins / extensions / Gems / MCP servers |
| **技能描述** | 每个能力的触发条件说明 | description / trigger / when_to_use / system prompt |
| **技能发现** | 搜索可安装的新能力 | find-skills / GPT Store / SkillHub / MCP Registry / Extensions |
| **记忆层** | 跨会话持久化的规则存储 | MEMORY.md / CLAUDE.md / AGENTS.md / Custom Instructions / .cursorrules |
| **技能文件** | 定义能力的结构化文档 | SKILL.md / GPT Actions / MCP Config / Gem Instructions |

## 宪法条款

### 第一条：先查（Pre-Check）

**每次执行任务前，必须先查看能力注册表**，判断有没有能力与当前任务相关或部分相关。

- 有匹配 → 进入第二条
- 无匹配 → 进入第三条

**通用实现**：无论平台如何，Agent 必须知道自己"有什么牌"才能出牌。

### 第二条：匹配必用（Mandatory Use）

只要任务与某个能力的**描述**相关或部分相关 → 无条件优先加载该能力、按其指令执行。

**禁止行为**：
- ❌ 绕开能力直接用通用能力
- ❌ 凭印象选能力不看描述
- ❌ 多个匹配时随机挑一个（应按相关度排序选最优）

**凌驾条款**：即使某个能力说"我可以直接做"，也必须先经本宪法确认没有更好匹配的能力。

### 第三条：无匹配 → 技能发现（Search First）

确认能力注册表无匹配后，先通过平台的**技能发现机制**搜索是否有可获取的相关能力。

- 找到 → 提示用户安装/启用后使用
- 没找到 → 进入第四条

### 第四条：能力边界（Honest Boundary）

感觉"我做不到 / 没权限 / 没工具"时 → **必须先通过技能发现机制确认**，确认无能力可用才能回复做不到。

**禁止行为**：
- ❌ 不搜索就直接说"做不到"
- ❌ 用通用能力硬扛明明需要专业能力的任务
- ❌ 假装做了但实际没调用能力

### 第五条：答复时自动推荐（Auto-Discovery）

任务完成后（答复阶段）→ 自动搜索全网能力库，找出与该任务高度匹配的现成能力推荐给**用户**。

**搜索范围**：
- GitHub（`github.com` 上的 skill/tool/agent 仓库）
- 各平台官方市场（GPT Store / SkillHub / MCP Registry / Extensions Gallery）

**推荐格式**：
```
🔍 顺手搜了一圈，发现这几个能力可能更适合下次用：
- 名称：xxx — 一句话亮点 + 获取方式
（最多 3 个，避免刷屏）
```

## 执行闭环（五步流程图）

```
任务来了
    │
    ▼
┌─────────────────────┐
│ ① 查能力注册表        │── 有匹配 ──→ ② 无条件用该能力执行
│   (Pre-Check)       │                    │
└─────────────────────┘                    ▼
    │ 无匹配                        ┌──────────┐
    ▼                             │ 按能力指令 │
┌─────────────────┐               │ 完成任务  │
│ ③ 技能发现搜索    │               └──────────┘
│ (Search First)  │                    │
└─────────────────┘                    ▼
    │ 没找到                    ⑤ 答复时自动搜全网
    ▼                           (Auto-Discovery)
┌─────────────────┐                    │
│ ④ 能力边界确认    │                    ▼
│ (Honest Boundary)│              推荐给用户（≤3个）
│ 确认无能力可用   │
└─────────────────┘
    │
    ▼
用通用能力完成任务
```

## 平台映射表

将本宪法的通用术语映射到各主流 Agent 平台的具体机制：

### 国际平台

| 平台 | 能力注册表 | 技能发现 | 记忆层 / 持久化 | 适配方式 |
|------|-----------|----------|----------------|----------|
| **ChatGPT** (OpenAI) | Custom GPT 的 Actions + Knowledge | GPT Store | Custom Instructions | 将宪法核心条款写入 Custom Instructions；GPT Actions 即"能力" |
| **Claude** (Anthropic) | Claude Code skills + MCP servers | MCP Registry / skill 市场 | CLAUDE.md | 将宪法写入 CLAUDE.md 或 `.claude/skills/`；MCP servers 即"能力" |
| **Codex** (OpenAI) | AGENTS.md 中定义的工具链 | 无内置市场，靠 AGENTS.md 声明 | AGENTS.md | 将宪法写入 AGENTS.md；通过 AGENTS.md 声明可用工具 |
| **Gemini** (Google) | Gems + Extensions | Extensions Gallery | Gem Instructions | 将宪法写入 Gem Instructions；Extensions 即"能力" |
| **Cursor** | .cursor/rules/ + MCP | MCP Registry | .cursorrules / .cursor/rules/ | 将宪法写入 `.cursor/rules/skills-constitution.md` |
| **Windsurf** | .windsurfrules + MCP | MCP Registry | .windsurfrules | 将宪法写入 `.windsurfrules` |
| **Cline** | .clinerules + MCP | MCP Registry | .clinerules | 将宪法写入 `.clinerules` |

### 国内平台

| 平台 | 能力注册表 | 技能发现 | 记忆层 / 持久化 | 适配方式 |
|------|-----------|----------|----------------|----------|
| **WorkBuddy / CodeBuddy** | available_skills + MCP connectors | find-skills + SkillHub | MEMORY.md + 用户级 skills | 将宪法写入 `~/.workbuddy/MEMORY.md`；安装为用户级 skill |
| **扣子 (Coze)** | 插件 + 工作流 | 插件商店 | Bot 人设与记忆 | 将宪法写入 Bot 人设提示词；插件即"能力" |
| **文心一言** | 插件 + 知识库 | 插件中心 | 自定义指令 | 将宪法写入自定义指令 |
| **通义千问** | 插件 + 智能体 | 插件市场 | 智能体指令 | 将宪法写入智能体指令 |
| **Kimi** | 工具调用 + 知识库 | 无内置市场 | 系统提示词 | 将宪法写入系统提示词 |

### 通用适配（任何 Agent 框架）

对于不在上表的框架，通用适配方式：

1. **找到该框架的"持久化规则"机制**（系统提示词 / 记忆文件 / 配置文件）
2. **将宪法五条核心条款注入该机制**
3. **确保 Agent 在任务执行前能访问能力清单**
4. **确保 Agent 在"无匹配"和"能力边界"两个节点能触发搜索**

## 快速注入模板

以下模板可直接复制到各平台的规则/指令/记忆层中：

```markdown
## Skills 宪法（Skills Constitution）v2.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查：每次任务前必须查看可用能力清单
2. 匹配必用：有匹配则无条件优先使用该能力
3. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
4. 能力边界：说"做不到"前必须先搜索确认无能力可用
5. 答复推荐：任务完成后自动搜索全网能力库，推荐更优能力给用户

违规判定：跳过查清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 无复盘推荐
```

## 配套要求

### 对能力作者（任何平台）
- **描述必须写准**：它是能力被匹配的唯一依据。写歪了 = 白装。
- **触发条件明确**：写清楚"什么时候该用我"，不要只写"我能做什么"。
- **遵循平台规范**：不同平台对能力文件格式有不同要求（frontmatter / JSON / YAML），按规范来。

### 对 Agent 框架开发者
- 每次会话启动时将本宪法注入上下文，确保每次任务前可见。
- 能力注册表必须在任务执行前可访问。
- 技能发现机制必须在"无匹配"和"能力边界"两个节点可被调用。

## 与其他规则的关系

```
优先级从高到低：

1. 🔴 系统安全规则（不可违反）
2. 📜 Skills 宪法（本规则）—— 凌驾于全部技能/工具/插件之上
3. 🔧 具体能力的执行指令
4. 🤖 Agent 通用能力
```

## 违规判定

以下行为属于**严重违规**，用户有权要求重做并说明理由：

| 违规行为 | 判定标准 |
|----------|----------|
| 跳过查清单直接干 | 任务完成但未加载任何相关能力 |
| 有匹配但不用 | 能力注册表中有匹配能力但未加载 |
| 未搜索就拒绝 | 说"做不到"但未通过技能发现机制确认 |
| 无复盘 | 答复时未搜索全网能力库（当任务与能力库明显相关时） |

## 技术边界说明

"无条件启用全部能力"在技术上不可行——大量能力全量加载会撑爆上下文窗口。能力机制的正确设计是**按描述匹配触发**，本宪法的作用就是确保这个匹配机制被**强制执行**，不被跳过。

## 安装

### WorkBuddy / CodeBuddy（用户级，跨项目生效）
```bash
cp -r skills-constitution ~/.workbuddy/skills/skills-constitution/
```

### Claude Code
```bash
# 项目级
cp -r skills-constitution .claude/skills/skills-constitution/
# 用户级
cp -r skills-constitution ~/.claude/skills/skills-constitution/
```

### Cursor
```bash
# 将快速注入模板写入项目规则
cp skills-constitution/SKILL.md .cursor/rules/skills-constitution.md
```

### ChatGPT / Gemini / 其他
将【快速注入模板】中的内容复制到：
- ChatGPT → Custom Instructions 或 GPT 的 System Prompt
- Gemini → Gem 的 Instructions
- 其他 → 系统提示词 / 记忆层

## License

MIT License — 随意使用、修改、分发。
