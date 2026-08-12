# Skills Constitution

> **Skills 宪法** —— 凌驾于全部技能/工具之上的元规则，强制 Agent 先查后用、有匹配必用、无匹配必搜。跨平台通用（WorkBuddy / Claude / ChatGPT / Cursor / Gemini / ...）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.6.0-blue.svg)](SKILL.md)
[![Skills Indexed](https://img.shields.io/badge/skills_indexed-688-green.svg)](SKILL_TREE.md)

## 🚀 快速开始

### 一键注入（任何平台）

把下面这段复制到你的 Agent 的规则/指令/记忆层中：

````markdown
## Skills 宪法（Skills Constitution）v2.6.0

本规则优先级高于全部技能/工具/插件。任何能力调用必须先过这一关。

执行路径：
1. 先查记忆：查阅平台记忆层（MEMORY.md/CLAUDE.md 等）确认相关规则
2. 先查技能：查看技能索引，按任务类型定位功能分支
3. 匹配必用：有匹配则无条件优先使用该能力
4. 无匹配必搜：先搜索可获取的能力，再考虑通用能力
5. 能力边界：说"做不到"前必须先搜索确认无能力可用
6. 答复推荐：任务完成后自动搜索全网能力库，推荐更优能力给用户

违规判定：跳过查记忆/技能清单直接干 / 有匹配但不用 / 未搜索就拒绝 / 无复盘推荐
````

### WorkBuddy / CodeBuddy

```bash
# 克隆仓库
git clone https://github.com/jiabaobei/skills-constitution.git

# 安装技能
cp -r skills-constitution ~/.workbuddy/skills/skills-constitution/

# 生成技能树索引
python scripts/build_skill_tree.py
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

## 📋 宪法条款（v2.6.0）

### 第零条：查记忆（Pre-Check Memory）
执行前查阅平台记忆层，确认相关规则和历史上下文。

### 第一条：先查（Pre-Check）
每次执行专业任务前，查看能力注册表，判断有没有匹配的能力。

### 第二条：匹配必用（Mandatory Use）
有匹配则无条件优先加载该能力，禁止绕开直接用通用能力。

### 第三条：无匹配必搜（Search First）
无匹配时先通过技能发现机制搜索，再考虑通用能力。

### 第四条：能力边界（Honest Boundary）
说"做不到"前必须通过技能发现机制确认无能力可用。

### 第五条：答复推荐（Auto-Discovery）
任务完成后自动搜索全网能力库，推荐更优能力给用户。

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

**完整索引**：查看 [SKILL_TREE.md](SKILL_TREE.md) 或 [skill_tree.json](skill_tree.json)

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

## 🔒 门禁自检（v2.6.0 新增）

把「靠 Agent 自觉」变成「可校验、可拦截」。5 个 step 独立校验，状态文件链式依赖，默认软校验 + `--strict` 可选阻断。

> ⚠️ **仅适用专业任务**：简单问答（翻译/润色/概念解释）按零号条款跳过，用 `--simple` 声明，不跑门禁。

```bash
# 全量软校验（FAIL 只警告）
python scripts/constitution-check --input output.txt

# 严格模式（FAIL 即阻断，exit 1）
python scripts/constitution-check --input output.txt --strict

# 简单任务豁免（零号条款）
python scripts/constitution-check --simple

# 单步校验（如推荐板块）
python scripts/constitution-check --step 5 --input output.txt
```

| Step | 校验内容 | 对应条款 |
|------|---------|---------|
| 1 | 宪法三查已汇报 | 第零/一条 |
| 2 | 技能树已读或无匹配声明 | 第一条 |
| 3 | 命中技能已调用 | 第二条 |
| 4 | 交付自检（非版本类自动跳过） | 全文件核查 |
| 5 | 推荐板块含 GitHub 链接+star 数 | 第五条 |

> ⚠️ 设计边界：脚本是"增强层"，宪法正文永远是行为规则兜底。**禁止**把"必须先跑脚本"写进正文——在跑不了脚本的环境会被 Agent 判为"不可满足"而整体跳过宪法。

---

## 🏗️ 项目结构

```
skills-constitution/
├── SKILL.md                    # 宪法文档（主文件）
├── README.md                   # 本文件
├── CHANGELOG.md                # 版本日志
├── SKILL_TREE.md               # 技能树索引（人类可读）
├── skill_tree.json             # 技能树索引（机器可读）
├── scripts/
│   ├── build_skill_tree.py     # 分类脚本
│   ├── constitution-check      # 门禁校验主入口（v2.6.0）
│   ├── steps/                  # 5 个 step 独立校验脚本
│   │   ├── step1-check.py      # 三查汇报
│   │   ├── step2-check.py      # 技能树已读
│   │   ├── step3-check.py      # 技能调用
│   │   ├── step4-check.py      # 交付自检
│   │   └── step5-check.py      # 推荐板块
│   └── lib/                    # 状态文件 + 文本工具
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
