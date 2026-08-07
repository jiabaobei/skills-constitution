# Skills 宪法（Skills Constitution）

> **项目简介**：一条凌驾于全部技能/工具/插件之上的元规则，强制 Agent 执行专业任务前必须扫描能力清单、有匹配必用、无匹配必搜、答复时自动推荐。解决 Agent 不调用已装 Skill、调用混乱、幻觉式硬扛任务三大痛点。自带任务类型过滤（简单问答跳过，专业任务强制），跨平台通用（ChatGPT / Claude / Codex / Gemini / WorkBuddy / Cursor / Windsurf / Cline 等 12+ 框架）。
>
> **Project Description**: A meta-rule governing all skill/tool/plugin invocations, forcing Agents to scan capability lists before executing professional tasks — mandatory use when matched, search when not, auto-recommend at reply. Solves three pain points: Agent ignoring installed skills, chaotic invocation, hallucination-based workarounds. Built-in task type filtering (skips simple Q&A, mandates for professional tasks), cross-platform compatible (ChatGPT / Claude / Codex / Gemini / WorkBuddy / Cursor / Windsurf / Cline and 12+ frameworks).

> 凌驾于全部技能/工具/插件之上的元规则 —— 强制 Agent 先查后用、有匹配必用、无匹配必搜

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platforms](https://img.shields.io/badge/Platforms-10+-blue.svg)](#-支持的平台)

## 为什么需要这个？

你有没有遇到过这种情况：

```
装了 100 个无敌 Skill/插件/工具 → Agent 傻傻硬扛任务 → 只用了 3 个 → 还不如不装
```

**Skills 宪法**就是解决这个问题的。它是一条凌驾于全部能力之上的元规则，**跨平台通用**，强制 Agent 在执行任何任务前必须：

1. **先查** —— 扫描能力清单，看有没有匹配的
2. **必用** —— 有匹配就无条件加载执行，禁止绕开
3. **必搜** —— 没匹配就先搜索可获取的能力，再考虑通用能力
4. **诚实** —— 说"做不到"之前，必须先确认没有能力能做
5. **复盘** —— 答复时自动搜索全网能力库，推荐更好的给用户

## 解决的三大痛点

| 痛点 | 表现 | 后果 |
|------|------|------|
| 😴 **不调用** | 任务来了直接干，不扫能力清单 | 能力库长期闲置 |
| 🤪 **调用幻觉** | 凭印象选能力，不看描述 | 用错能力、答非所问 |
| 🌀 **调用混乱** | 多个能力都能做，随机挑一个 | 结果不稳定 |

## 🌐 支持的平台

### 国际

| 平台 | 适配方式 | 持久化位置 |
|------|----------|-----------|
| **ChatGPT** | Custom Instructions / GPT System Prompt | Custom Instructions |
| **Claude** | `.claude/skills/` 或 CLAUDE.md | CLAUDE.md |
| **Codex** | AGENTS.md | AGENTS.md |
| **Gemini** | Gem Instructions | Gem Instructions |
| **Cursor** | `.cursor/rules/` | .cursorrules |
| **Windsurf** | `.windsurfrules` | .windsurfrules |
| **Cline** | `.clinerules` | .clinerules |

### 国内

| 平台 | 适配方式 | 持久化位置 |
|------|----------|-----------|
| **WorkBuddy / CodeBuddy** | `~/.workbuddy/skills/` + MEMORY.md | MEMORY.md |
| **扣子 (Coze)** | Bot 人设提示词 | Bot 人设 |
| **文心一言** | 自定义指令 | 自定义指令 |
| **通义千问** | 智能体指令 | 智能体指令 |
| **Kimi** | 系统提示词 | 系统提示词 |

> 不在列表中的框架？把[快速注入模板](#快速注入模板)复制到该框架的规则/记忆层即可。

## 快速开始

### 一键注入（任何平台）

把下面这段复制到你的 Agent 的规则/指令/记忆层中：

```markdown
## Skills 宪法 v2.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查：每次任务前必须查看可用能力清单
2. 匹配必用：有匹配则无条件优先使用该能力
3. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
4. 能力边界：说"做不到"前必须先搜索确认无能力可用
5. 答复推荐：任务完成后自动搜索全网能力库，推荐更优能力给用户

违规判定：跳过查清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 无复盘推荐
```

### WorkBuddy / CodeBuddy

```bash
# 用户级安装（跨项目生效）
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
cp skills-constitution/SKILL.md .cursor/rules/skills-constitution.md
```

### ChatGPT / Gemini / 其他

打开平台的 Custom Instructions / Gem Instructions / 系统提示词，粘贴上面的快速注入模板。

## 执行闭环

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

## 与其他规则的关系

```
优先级从高到低：

1. 🔴 系统安全规则（不可违反）
2. 📜 Skills 宪法（本规则）—— 凌驾于全部技能/工具/插件之上
3. 🔧 具体能力的执行指令
4. 🤖 Agent 通用能力
```

## 文件结构

```
skills-constitution/
├── SKILL.md          # 核心技能文件（宪法条款全文 + 平台映射表）
├── README.md          # 本文件
└── LICENSE            # MIT License
```

## 配套建议

- **能力作者**：描述写准，它是能力被匹配的唯一依据
- **框架开发者**：确保能力清单在任务执行前可访问，技能发现在关键节点可调用
- **用户**：定期检查能力库的描述质量，写歪了 = 白装

## License

[MIT](LICENSE) — 随意使用、修改、分发。

## 作者

**jiabaobei** — [GitHub](https://github.com/jiabaobei)

---

如果这个规则帮你解决了 Agent 不调用能力的问题，欢迎 ⭐ Star 收藏，转发给身边被 Agent 气到的朋友！
