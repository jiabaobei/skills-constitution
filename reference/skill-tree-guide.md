# 技能树构建指南（使用者必读 · v2.18.0）

> **为什么要重建？** 仓库内的 `skill_tree.json` 是**作者机器的快照（示例）**，只包含作者本机的技能（如 757 个）。
> 你安装后若直接用作者快照，**你自己的技能不在树里 → Agent 查树即"无匹配"→ 走通用能力**，
> 宪法的"按分支定位省 token"就失效了。**安装后第一步：重建你自己的技能树。**

---

## 一、完整命令（带 SKILLS_DIR，三平台通用）

```bash
# 进入技能目录（以 WorkBuddy 为例；Claude Code 用 ~/.claude/skills 等）
cd ~/.workbuddy/skills/skills-constitution

# 重建技能树：SKILLS_DIR 指向【你自己的】技能根目录（不是本仓库目录）
SKILLS_DIR="$HOME/.workbuddy/skills" \
BINARIES_DIR="$HOME/.workbuddy/binaries" \
python scripts/build_skill_tree.py
```

**各平台 SKILLS_DIR 示例**：

| 平台 | SKILLS_DIR |
|------|-----------|
| WorkBuddy | `~/.workbuddy/skills` |
| Claude Code | `~/.claude/skills` |
| Cursor | `~/.cursor/skills`（或项目 `.cursor/skills`） |
| Windows（Git Bash） | `C:/Users/<用户名>/.workbuddy/skills` |

> `BINARIES_DIR` 可选：想把你已装的 Python 库/工具也编进索引（🧩 libs 分类）就设置，否则可省略。

## 二、重建后确认成功（3 步）

1. **看自检输出**：末尾出现 `✓ 自检通过: 技能分类 N >= total M` 才算成功；出现 `✗ 自检失败` 说明数据不一致，需要排查
2. **对比 total**：`cat skill_tree.json | python -c "import json,sys; print(json.load(sys.stdin)['total'])"`
   —— total **应 ≈ 你的实际技能数**（`ls $SKILLS_DIR | wc -l`），如果远小于（如还是作者快照的 402），说明 SKILLS_DIR 没生效或跑错目录
3. **确认 skills_dir 字段**：`skill_tree.json` 顶层 `"skills_dir"` 应指向你的目录，不是作者路径

## 三、常见问题（FAQ）

**Q1：跑完 total 还是作者快照的数字？**
→ SKILLS_DIR 没生效：确认命令里带了 `SKILLS_DIR=`，且在**技能仓库目录**下执行 `python scripts/build_skill_tree.py`（脚本输出到其父目录）。

**Q2：很多技能落到 `general` 分类？**
→ 正常。分类规则（CATEGORY_RULES）没覆盖到的技能默认归 general，不影响使用（仍会进树、可被检索）；想细化可自行编辑 `scripts/build_skill_tree.py` 的分类关键词。

**Q3：Windows 上报"技能目录不存在"？**
→ 用 Git Bash 执行（`C:/Users/...` 正斜杠），或确认 SKILLS_DIR 用的是 Windows 绝对路径（`C:\Users\...` 反斜杠在 bash 里要转义，建议正斜杠）。

**Q4：能自动重建吗？**
→ 可以：在 CI 或会话启动钩子（SessionStart）里加一行重建命令即可；也可定期运行保持索引与技能库同步。

**Q5：我改了技能描述/新增技能，要重建吗？**
→ 要。索引是预生成快照，技能库变化后重建才能反映最新；重建很快（秒级），建议作为安装/更新流程的一部分。

---

> 主文件 `SKILL.md` 技能树章节 → Load `reference/skill-tree-guide.md`（本文）
