# Release v2.21.0 — 双机制平台覆盖：技能 + 插件

> 主题：**把宪法"查技能库"从单通道扩成双通道 —— 能力注册表 = 独立技能 ∪ 插件技能，对齐 ZCode / Claude Code / DeepSeek Harness 这类"技能 + 插件"双机制平台。**

## ⚠️ 升级必读

- 已安装用户：重跑 `bash install.sh` 即可原地更新（技能树重建现在会自动带上插件技能）
- 只想刷新技能树：`SKILLS_DIR=<你的技能目录> python scripts/build_skill_tree.py`（无需重装）
- 双机制平台上，**插件技能要用完整调用名**（`插件名:技能名`，如 `document-skills:docx`）才能被 Skill 机制加载——注入块现在会自动标注，旧习惯里"裸技能名"的调用方式在插件技能上会失效

## 🧩 解决什么问题

ZCode 实测发现：技能与插件是**两条平行机制**——用户级技能目录（`~/.zcode/skills`）与插件缓存（`~/.zcode/cli/plugins/cache`，本机含 2286 个 SKILL.md，其中大部分位于已停用的市场目录）互不相通。宪法原"查技能库"只扫第一条通道，`document-skills` / `computer-use` / `zcode-guide` 等插件通道的能力对 Agent 不可见，"有匹配必用"在插件技能上失灵。

## 🚀 核心改动

| 改动 | 说明 |
|------|------|
| 布局无关插件扫描 | `build_skill_tree.py` 自动发现 ZCode / Claude Code 插件缓存；**任何新 agent 免改代码接入**：`PLUGIN_CACHE_DIRS` 环境变量或仓库根 `plugin_roots.json` |
| 停用插件不入树 | ZCode 侧读取其 config 启用表（`plugins.enabledPlugins`），`.DISABLED` 停用市场整棵子树跳过 |
| 完整调用名 | 插件条目带 `qualified_name`（`插件名:技能名`），pre-hook 注入块与 SAD 候选自动标注（插件）并按完整名渲染 |
| 宪法条款 | SKILL.md 新增"第一条补充：双机制平台覆盖"——插件技能与独立技能同权重，禁止以"它是插件"为由绕过；违规判定新增对应条款 |
| 安装脚本 | install.sh / install.ps1 技能目录型新增 `zcode` 平台（自动探测顺序 WorkBuddy > ZCode > Claude Code），自检口径改"独立 + 插件" |
| DeepSeek Harness | "一切皆插件"（Cordis 架构），扫描器天然兼容其"目录 + 装载器"形态；v0.1 插件路径未定型，暂用 `PLUGIN_CACHE_DIRS` / `plugin_roots.json` 接入（文档如实标注），路径稳定后加入已知表 |

## 🧪 验证（本机实测）

- 真机 ZCode 插件缓存：启用插件技能 15 个全部入树，停用插件（mimosa / cloudbase-skills 等）零残留
- 修复实测漏洞：`mimosa/1.0.3/payload/skills/...` 打包层 `payload` 曾被误当插件名、漏过停用过滤——推导规则已修复并用测试固化
- `install.sh --platform zcode` 沙箱全流程通过；回归测试 58/58（新增第 8 组 19 条）

## 升级方式

```bash
# 已安装用户
bash install.sh                          # 原地更新 + 重建含插件技能的树

# 新用户
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh
```

---

*完整改动逐条见 [CHANGELOG](https://github.com/jiabaobei/skills-constitution/blob/main/CHANGELOG.md)；本版本回应 ZCode 真机使用中发现的"技能与插件双平行机制"覆盖缺口，全部改动本机实测通过。*
