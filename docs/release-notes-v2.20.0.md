# Release v2.20.0 — 安装全平台分流 + 钩子自动注册 + Windows 支持

> 主题：**把"能装的平台"扩展到"文档宣称的全部平台形态"，并把最痛的 50 行手工钩子配置变成一条命令。**

## ⚠️ 升级必读

- 已安装用户：重跑 `bash install.sh` 即可原地更新（自动重建技能树逻辑不变）
- 想让门禁从"建议"升级为"强制拦截"：`bash install.sh --register-hooks` 或单独 `python skills-constitution/scripts/register_hooks.py`
- Windows 用户：新增 `install.ps1`（本版本首次提供，**未经真机实测**，首跑有问题请提 Issue）

## 🚀 安装全平台分流（install.sh）

| 平台形态 | 命令 | 效果 |
|---------|------|------|
| 技能目录型（WorkBuddy / Claude Code） | `bash install.sh` | 复制 + 自动重建技能树 + 自检 |
| 同上 + 强制拦截 | `bash install.sh --register-hooks` | 装完自动注册四个宿主钩子 |
| 规则文件型（Cursor / Windsurf / Cline） | `bash install.sh --platform cursor --target-dir <项目>` | 宪法写入规则文件，如实声明建议级 |
| 纯注入型（ChatGPT / Gemini / 扣子等） | `bash install.sh --platform prompt` | 自动提取注入模板供粘贴 |
| Windows | `powershell -File install.ps1` | 同技能目录型流程 |

- 规则文件型：windsurf/cline 单文件规则用 BEGIN/END 标记块追加，重装幂等替换不重复
- 安装收尾新增**记忆层平台对照**（各平台记忆文件位置 + `--memory` 指向方式）

## 🔌 钩子自动注册（scripts/register_hooks.py）

WorkBuddy 与 Claude Code 双平台同源格式（严格依据 reference/installation.md 官方样例）：

- 注册四事件：`UserPromptSubmit` / `PreToolUse` / `Stop`（python，跨平台）+ `SessionStart`（检测到 bash 才装）
- `PreToolUse` matcher 含 Bash（配合 v2.19.0 的 Bash 写文件检测，堵住绕行通道）
- **安全设计**：写前备份（带时间戳）→ 原 JSON 损坏拒写（不动用户配置）→ 写后重载校验失败自动回滚 → 幂等（重复执行只替换宪法条目，你的其它配置和钩子原样保留）
- `--dry-run` 预览 / `--uninstall` 干净移除（保留你的其它钩子）

## 🪟 Windows

新增 `install.ps1`：探测平台 → 复制 → 重建技能树 → 自检 → 可选 `-RegisterHooks` → 记忆层指引。
如实声明：开发环境无 Windows，**需真机首验**；钩子的 SessionStart 注入需 Git Bash（可选，不装不影响其余三钩子）。

## 升级方式

```bash
# 已安装用户
bash install.sh --register-hooks      # 更新 + 顺手把强制拦截装上

# 新用户
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh --register-hooks
```

---

*完整改动逐条见 [CHANGELOG](https://github.com/jiabaobei/skills-constitution/blob/main/CHANGELOG.md)；本版本补齐外部测评指出的全部 5 个平台适配缺口（规则文件型覆盖 / 注入型入口 / 钩子自动注册 / Windows / 记忆层提示），其中 4 项本机实测通过，Windows 脚本如实标注待真机首验。*
