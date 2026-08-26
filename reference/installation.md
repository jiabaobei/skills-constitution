# 安装与验证（渐进式披露·附录）

> 按需加载：仅当执行安装/排查钩子时引用本文件。

---

## 安装

### WorkBuddy / CodeBuddy（用户级，跨项目生效）
```bash
cp -r skills-constitution ~/.workbuddy/skills/skills-constitution/
# 重建技能树（必做：生成你自己的索引，替换作者快照；SKILLS_DIR 指向你的技能根目录）
SKILLS_DIR="$HOME/.workbuddy/skills" python scripts/build_skill_tree.py
# 完整命令/平台差异/自检/FAQ 见 reference/skill-tree-guide.md
```

**WorkBuddy 钩子注册（v2.14.0 必读）**：WorkBuddy 的钩子注册点在 `~/.workbuddy/settings.json` 的 `hooks` 字段（**不是**技能目录里的 `hooks/hooks.json`——那是 CodeBuddy/Claude Code 插件机制用的）。

**v2.20.0 起推荐自动注册**（一条命令，带备份/校验/回滚/幂等，WorkBuddy 与 Claude Code 通用）：

```bash
python scripts/register_hooks.py              # 自动探测平台
python scripts/register_hooks.py --dry-run    # 只预览不落盘
python scripts/register_hooks.py --uninstall  # 移除宪法钩子(保留你的其它配置)
```

或安装时直接 `bash install.sh --register-hooks`。以下是自动注册的等价手工格式（路径换成你的实际 python.exe 与技能路径；改完**重启宿主生效**）：

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "bash \"<你的技能路径>/hooks/session-start.sh\"",
        "timeout": 30,
        "description": "宪法 SessionStart：注入记忆+技能树上下文"
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [
        {
          "type": "command",
          "command": "\"<你的python.exe>\" \"<你的技能路径>/scripts/constitution-gate.py\" UserPromptSubmit",
          "timeout": 15,
          "description": "宪法 UserPromptSubmit：重置门禁状态 + 记录任务 + 注入上轮违规警告"
        },
        {
          "type": "command",
          "command": "bash \"<你的技能路径>/hooks/user-prompt-submit.sh\"",
          "timeout": 20,
          "description": "宪法 UserPromptSubmit：任务分类（简单→A跳过 | 专业→B强制校验）"
        }
      ]
    }],
    "PreToolUse": [{
      "matcher": "Write|Edit|MultiEdit|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "\"<你的python.exe>\" \"<你的技能路径>/scripts/constitution-gate.py\" PreToolUse",
        "timeout": 10,
        "description": "宪法 PreToolUse：写文件前校验本任务内三查新鲜 PASS（v2.14.0 防旧 PASS 放行）"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "\"<你的python.exe>\" \"<你的技能路径>/scripts/constitution-gate.py\" Stop",
        "timeout": 30,
        "description": "宪法 Stop：校验最终回复三查+技能名，违规写入 .constitution-violations.json"
      }]
    }]
  }
}
```
> 排坑：① hooks 脚本内的路径已支持环境变量 `CODEBUDDY_PLUGIN_ROOT` 优先 + 脚本自定位兜底，不再写死机器路径；② `bash` 需在 PATH（Windows Git Bash 自带）；③ 旧版 settings.json 若残留 `constitution-gate.py PreToolUse` 之外的重复注册，先删掉再写。CodeBuddy 平台则用 `hooks/hooks.json`（走 `ruler apply` 分发）。

### Claude Code
```bash
# 项目级
cp -r skills-constitution .claude/skills/skills-constitution/
# 用户级
cp -r skills-constitution ~/.claude/skills/skills-constitution/
```

### Cursor
```bash
# 将宪法写入规则目录
cp SKILL.md .cursor/rules/skills-constitution.md
```

### ChatGPT / Gemini / 其他
将【快速注入模板】中的内容复制到：
- ChatGPT → Custom Instructions 或 GPT 的 System Prompt
- Gemini → Gem 的 Instructions
- 其他 → 系统提示词 / 记忆层

---

## 验证安装

### WorkBuddy
```bash
# 检查技能是否加载
ls ~/.workbuddy/skills/skills-constitution/SKILL.md

# 重建技能树索引（SKILLS_DIR 指向你的技能根目录）
SKILLS_DIR="$HOME/.workbuddy/skills" python scripts/build_skill_tree.py

# 查看索引（应出现 "✓ 自检通过"；total 应 ≈ 你的实际技能数）
cat skill_tree.json | jq '.total'
```

### 通用
执行任意专业任务，观察是否先查记忆、再查技能、后有匹配必用。

---

