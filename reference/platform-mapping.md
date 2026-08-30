# 平台映射表（渐进式披露·附录）

> 按需加载：仅当讨论跨平台适配/具体平台机制时引用本文件。

---

## 平台映射表

将本宪法的通用术语映射到各主流 Agent 平台的具体机制：

### 国际平台

| 平台 | 能力注册表 | 技能发现 | 记忆层 / 持久化 | 适配方式 |
|------|-----------|----------|----------------|----------|
| **ChatGPT** (OpenAI) | Custom GPT 的 Actions + Knowledge | GPT Store | Custom Instructions | 将宪法核心条款写入 Custom Instructions；GPT Actions 即"能力" |
| **Claude** (Anthropic) | Claude Code skills + MCP servers | MCP Registry / skill 市场 | CLAUDE.md | 将宪法写入 CLAUDE.md 或 `.claude/skills/`；MCP servers 即"能力" |
| **Codex** (OpenAI) | AGENTS.md 中定义的工具链 | 无内置市场，靠 AGENTS.md 声明 | AGENTS.md | 将宪法写入 AGENTS.md；通过 AGENTS.md 声明可用工具 |
| **Gemini** (Google) | Gems + Extensions | Extensions Gallery | Gem Instructions | 将宪法写入 Gem Instructions；Extensions 即"能力" |
| **Cursor** | .cursor/rules/ + MCP | MCP Registry | .cursorrules | 将宪法写入 `.cursor/rules/skills-constitution.md` |
| **Windsurf** | .windsurfrules + MCP | MCP Registry | .windsurfrules | 将宪法写入 `.windsurfrules` |
| **ZCode** | 用户技能 `~/.zcode/skills` + **插件技能**（插件缓存，调用名 `插件名:技能名`） | 插件市场 + 技能目录 | AGENTS.md（用户级/项目根） | 复制到 `~/.zcode/skills/`（`install.sh --platform zcode`）；技能树自动编入插件技能（v2.21.0） |
| **DeepSeek Harness (dsh)** | **一切皆插件**（Cordis：技能/工具/模型均为插件） | GitHub `dsh-plugin` 生态（700+ 仓库） | AGENTS.md / Harness 主目录配置 | 宪法写入 AGENTS.md；技能随插件分发，`PLUGIN_CACHE_DIRS` 指向其插件目录即可入树（v0.1 路径未定型，如实标注） |
| **Cline** | .clinerules + MCP | MCP Registry | .clinerules | 将宪法写入 `.clinerules` |
| **GitHub Copilot** | Agent Mode + MCP | GitHub Marketplace | .github/copilot/instructions.md | 将宪法写入 Copilot 指令文件 |

### 国内平台

| 平台 | 能力注册表 | 技能发现 | 记忆层 / 持久化 | 适配方式 |
|------|-----------|----------|----------------|----------|
| **WorkBuddy / CodeBuddy** | available_skills + MCP connectors | find-skills + SkillHub | MEMORY.md + 用户级 skills | 将宪法写入 `~/.workbuddy/MEMORY.md`；安装为用户级 skill |
| **扣子 (Coze)** | 插件 + 工作流 | 插件商店 | Bot 人设与记忆 | 将宪法写入 Bot 人设提示词；插件即"能力" |
| **文心一言** | 插件 + 知识库 | 插件中心 | 自定义指令 | 将宪法写入自定义指令 |
| **通义千问** | 插件 + 智能体 | 插件市场 | 智能体指令 | 将宪法写入智能体指令 |
| **Kimi** | 工具调用 + 知识库 | 无内置市场 | 系统提示词 | 将宪法写入系统提示词 |
| **豆包** | 插件 + 工作流 | 插件商店 | Bot 人设 | 将宪法写入 Bot 人设提示词 |
| **智谱清言** | 插件 + 知识库 | 插件中心 | 自定义指令 | 将宪法写入自定义指令 |
| **月之暗面** | 插件 + 工具 | 插件市场 | 系统提示词 | 将宪法写入系统提示词 |
| **Dify** | 工具 + 工作流 | 插件市场 | 系统 Prompt | 将宪法写入系统 Prompt |

**支持级别说明**（诚实声明，v2.3.0 新增）：

| 级别 | 含义 | 平台 |
|------|------|------|
| ✅ **完全支持** | 有本地文件系统 + 可访问的能力注册表/技能文件，宪法可真正执行"查索引→加载技能→执行" | WorkBuddy / Claude Code / ZCode / Cursor / Windsurf / Cline / Codex |
| ⚠️ **建议型** | 无本地文件系统、无技能文件机制，只能将宪法条款注入提示词/人设，作为行为建议执行，无法真正加载技能文件 | ChatGPT / Kimi / 豆包 / 文心一言 / 通义千问 / 智谱清言 / 月之暗面 / Dify / 扣子 |

**双机制平台（v2.21.0 新增）**：ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力注册表 = **独立技能 ∪ 插件技能**（两条平行机制）。查技能树时两条通道同权重；插件技能按完整调用名（`插件名:技能名`，如 `document-skills:docx`）调用；`build_skill_tree.py` 已自动扫描插件缓存（ZCode / Claude Code 内置已知路径，ZCode 侧还会按其 config 的插件启用表排除停用项、`.DISABLED` 市场整棵跳过），其他平台用 `PLUGIN_CACHE_DIRS` 环境变量或仓库根 `plugin_roots.json` 接入。

> 说明：对"建议型"平台，请勿期待 file-ops / find-skills 等本地技能机制生效；宪法在这些平台上以提示词约束的形式工作，效果取决于平台对系统提示词的遵循程度。

### 通用适配（任何 Agent 框架）

对于不在上表的框架，通用适配方式：

1. **找到该框架的"持久化规则"机制**（系统提示词 / 记忆文件 / 配置文件）
2. **将宪法五条核心条款注入该机制**
3. **确保 Agent 在任务执行前能访问能力清单**
4. **确保 Agent 在"无匹配"和"能力边界"两个节点能触发搜索**

---

