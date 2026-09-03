#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""register_hooks —— 宪法钩子自动注册（v2.20.0）

把"手工编辑 settings.json 的 50 行钩子配置"变成一条命令。
支持两个支持钩子的宿主平台（格式同源，见 reference/installation.md）：
  - workbuddy: ~/.workbuddy/settings.json
  - claude:    ~/.claude/settings.json

安全设计：
  - 写入前备份: <settings>.constitution-backup-<时间戳>
  - 原文件存在但 JSON 损坏 → 拒绝写入（不动用户配置）
  - 写入后重载校验，失败自动回滚备份
  - 幂等：重复执行只替换宪法自己的钩子条目，不影响用户其它配置
  - 只注册 python 命令钩子（跨平台）；bash 的 SessionStart 注入钩子仅在
    检测到 bash 时附加（Windows 无 Git Bash 时优雅跳过）

用法:
  python3 register_hooks.py                      # 自动探测平台
  python3 register_hooks.py --platform claude
  python3 register_hooks.py --platform workbuddy --settings /path/settings.json
  python3 register_hooks.py --dry-run            # 只预览不落盘
  python3 register_hooks.py --uninstall          # 移除宪法钩子(保留其它配置)
"""
import argparse
import json
import os
import shutil
import sys
import time

MARKERS = ("constitution-gate.py", "session-start.sh", "pre-hook.py")  # 识别"我们注册的条目"


def detect_platform():
    if os.path.isdir(os.path.expanduser("~/.workbuddy/skills")):
        return "workbuddy"
    return "claude"


def default_paths(platform):
    if platform == "workbuddy":
        base = os.path.expanduser("~/.workbuddy")
    else:
        base = os.path.expanduser("~/.claude")
    return (os.path.join(base, "settings.json"),
            os.path.join(base, "skills", "skills-constitution"))


def is_ours(cmd):
    return any(m in (cmd or "") for m in MARKERS)


def build_entries(platform, skills_dir):
    """构造要注册的钩子条目（依据 reference/installation.md 官方格式）"""
    py = sys.executable or shutil.which("python3") or shutil.which("python")
    gate = os.path.join(skills_dir, "scripts", "constitution-gate.py")
    session_sh = os.path.join(skills_dir, "hooks", "session-start.sh")
    q = '"'  # settings.json 命令里的路径加引号,防空格路径

    entries = {}
    # UserPromptSubmit: 重置门禁状态 + 记录任务 + 注入上轮违规警告
    # v2.27.4: 补注册注入保活钩子(pre-hook --hook-mode,直调 python 不走 bash——
    # 本机实测 bash 层吃 2.5~12.9s 是宿主 20s 超时元凶,直调仅 ~1.5s)。
    # 此前漏注册:注入只在 SessionStart 做一次,长会话过期后 Agent 拿不到
    # 记忆+技能树注入,"该调技能时不调技能"的防线随之失效。
    pre_hook = os.path.join(skills_dir, "scripts", "pre-hook.py")
    entries["UserPromptSubmit"] = [{
        "hooks": [{
            "type": "command",
            "command": f"{q}{py}{q} {q}{gate}{q} UserPromptSubmit",
            "timeout": 15,
            "description": "宪法 UserPromptSubmit：重置门禁状态 + 记录任务 + 注入上轮违规警告",
        }]
    }, {
        "hooks": [{
            "type": "command",
            "command": f"{q}{py}{q} {q}{pre_hook}{q} --hook-mode",
            "timeout": 15,
            "description": "宪法 UserPromptSubmit：任务分类 + 注入上下文保活(过期自动刷新)",
        }]
    }]
    # PreToolUse: 写文件前校验本任务内三查新鲜 PASS
    # v2.19.0 起 matcher 含 Bash —— gate 会检测 Bash 写文件(重定向/tee/heredoc)
    entries["PreToolUse"] = [{
        "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
        "hooks": [{
            "type": "command",
            "command": f"{q}{py}{q} {q}{gate}{q} PreToolUse",
            "timeout": 10,
            "description": "宪法 PreToolUse：写文件前校验本任务内三查新鲜 PASS（含 Bash 写文件检测）",
        }]
    }]
    # Stop: 校验最终回复，违规写入档案
    entries["Stop"] = [{
        "hooks": [{
            "type": "command",
            "command": f"{q}{py}{q} {q}{gate}{q} Stop",
            "timeout": 30,
            "description": "宪法 Stop：校验最终回复三查+技能名，违规写入 .constitution-violations.json",
        }]
    }]
    # SessionStart: 记忆+技能树注入（bash 钩子，仅检测到 bash 时注册）
    if shutil.which("bash") and os.path.exists(session_sh):
        entries["SessionStart"] = [{
            "hooks": [{
                "type": "command",
                "command": f"bash {q}{session_sh}{q}",
                "timeout": 30,
                "description": "宪法 SessionStart：注入记忆+技能树上下文",
            }]
        }]
    return entries


def strip_ours(hook_list):
    """从某事件的钩子列表中移除宪法条目（保留用户其它钩子）"""
    kept = []
    for group in hook_list or []:
        new_hooks = [h for h in group.get("hooks", [])
                     if not is_ours(h.get("command", ""))]
        if new_hooks:
            g = dict(group)
            g["hooks"] = new_hooks
            kept.append(g)
        # 整组只剩宪法条目 → 丢弃该组
    return kept


def main():
    ap = argparse.ArgumentParser(description="宪法钩子自动注册")
    ap.add_argument("--platform", choices=["workbuddy", "claude"], default=None)
    ap.add_argument("--settings", default=None, help="settings.json 路径(默认按平台推断)")
    ap.add_argument("--skills-dir", default=None, help="宪法安装目录(默认按平台推断)")
    ap.add_argument("--dry-run", action="store_true", help="只预览不落盘")
    ap.add_argument("--uninstall", action="store_true", help="移除宪法钩子")
    a = ap.parse_args()

    platform = a.platform or detect_platform()
    d_settings, d_skills = default_paths(platform)
    settings_path = a.settings or d_settings
    skills_dir = a.skills_dir or d_skills

    if not a.uninstall and not os.path.isdir(skills_dir):
        print(f"✗ 宪法未安装到 {skills_dir}，请先运行 bash install.sh", file=sys.stderr)
        return 1

    # 读取现有配置
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"✗ {settings_path} 无法解析({e})。为保护你的配置，已中止。"
                  "请手工修复该文件后重试。", file=sys.stderr)
            return 1

    hooks = settings.get("hooks", {})

    # 先移除旧的宪法条目（幂等替换）
    for ev in list(hooks.keys()):
        hooks[ev] = strip_ours(hooks.get(ev))
        if not hooks[ev]:
            del hooks[ev]

    if not a.uninstall:
        for ev, groups in build_entries(platform, skills_dir).items():
            hooks[ev] = hooks.get(ev, []) + groups

    settings["hooks"] = hooks
    out = json.dumps(settings, ensure_ascii=False, indent=2)

    # 落盘前自校验（生成的 JSON 必须可解析且包含/不包含宪法条目）
    parsed = json.loads(out)
    if a.uninstall:
        assert not any(is_ours(h.get("command", ""))
                       for ev in parsed.get("hooks", {}).values()
                       for g in ev for h in g.get("hooks", [])), "卸载不完整"
    else:
        assert any("constitution-gate.py" in h.get("command", "")
                   for ev in parsed.get("hooks", {}).values()
                   for g in ev for h in g.get("hooks", [])), "注册内容缺失"

    if a.dry_run:
        print("[dry-run] 将写入以下内容:")
        print(json.dumps(parsed.get("hooks", {}), ensure_ascii=False, indent=2))
        return 0

    # 备份 → 写入 → 重载校验 → 失败回滚
    backup = None
    if os.path.exists(settings_path):
        backup = settings_path + ".constitution-backup-" + time.strftime("%Y%m%d%H%M%S")
        shutil.copy2(settings_path, backup)
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        with open(settings_path, encoding="utf-8") as f:
            json.load(f)  # 重载校验
    except Exception as e:
        if backup:
            shutil.copy2(backup, settings_path)
            print(f"✗ 写入失败已回滚({e})，原配置已恢复: {backup}", file=sys.stderr)
        return 1

    action = "移除" if a.uninstall else "注册"
    print(f"✅ 已{action}宪法钩子 → {settings_path}")
    if backup:
        print(f"   备份: {backup}")
    if not a.uninstall:
        evs = sorted(k for k in parsed.get("hooks", {}))
        print(f"   事件: {', '.join(evs)}")
        print("   ⚠ 重启宿主(或新开会话)后生效；确认已启用钩子信任(如 WorkBuddy 需 Trust)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
