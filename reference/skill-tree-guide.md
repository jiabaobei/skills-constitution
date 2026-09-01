# 技能树构建指南（使用者必读 · v2.22.0）

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
| ZCode | `~/.zcode/skills` |
| Cursor | `~/.cursor/skills`（或项目 `.cursor/skills`） |
| Windows（Git Bash） | `C:/Users/<用户名>/.workbuddy/skills` |

> `BINARIES_DIR` 可选：想把你已装的 Python 库/工具也编进索引（🧩 libs 分类）就设置，否则可省略。

## 二、重建后确认成功（3 步）

1. **看自检输出**：末尾出现 `✓ 自检通过: 技能分类 N >= total M` 才算成功；出现 `✗ 自检失败` 说明数据不一致，需要排查
2. **对比 total**：`cat skill_tree.json | python -c "import json,sys; print(json.load(sys.stdin)['total'])"`
   —— total **应 ≈ 你的实际技能数**（`ls $SKILLS_DIR | wc -l`），如果远小于（如还是作者快照的 402），说明 SKILLS_DIR 没生效或跑错目录
3. **确认 skills_dir 字段**：`skill_tree.json` 顶层 `"skills_dir"` 应指向你的目录，不是作者路径

## 三、插件技能扫描（双机制平台，v2.21.0）

ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力来自**两条平行机制**：独立技能（技能目录）+ 插件技能（插件包内置）。重建时会**自动扫描插件缓存**把插件技能也编入树（条目带 `source: "plugin"` 与 `qualified_name` 完整调用名字段）：

| 接入方式 | 说明 |
|---------|------|
| 自动发现 | ZCode（`~/.zcode/cli/plugins/cache`，且按其 config 启用表排除停用插件）与 Claude Code（`~/.claude/plugins/cache`）已知路径，无需配置 |
| `PLUGIN_CACHE_DIRS` | 环境变量，多目录用系统路径分隔符（Windows `;` / POSIX `:`）——**任何新 agent 的插件缓存免改代码接入**（如 DeepSeek Harness，其路径规范在 v0.1 预览期未定型） |
| `plugin_roots.json` | 仓库根放 `{"cache_dirs": ["..."]}`，持久化自定义目录（不想每次设环境变量时用） |
| `PLUGIN_SCAN=0` | 整体关闭插件扫描 |

扫描布局无关：只要插件包内含 `skills/`（或 `bundled-skills/`）技能目录即可识别；同一插件多版本去重取最高；`.DISABLED` 停用市场整棵跳过；打包层目录（如 `payload/`）不干扰插件名推导。

**验证插件技能已入树**：`python -c "import json; t=json.load(open('skill_tree.json',encoding='utf-8')); print(t['plugin_skills_count'])"`，或在 SKILL_TREE.md 里看 `插件名:技能名` 格式的条目。

## 四、常见问题（FAQ）

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

**Q6：我用的 agent 也是"技能+插件"双机制（如 DeepSeek Harness），插件技能怎么入树？**
→ 用 `PLUGIN_CACHE_DIRS` 环境变量指向其插件缓存目录（多目录用路径分隔符隔开）后重建即可，扫描布局无关、无需改代码；想持久化就把目录写进仓库根 `plugin_roots.json`。注意确认其"停用插件"的记录方式——若与已知平台不同，停用插件也会入树（宁可多入不入漏，匹配由描述相关度把关）。

---

> 主文件 `SKILL.md` 技能树章节 → Load `reference/skill-tree-guide.md`（本文）
