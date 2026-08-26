#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
constitution-gate —— Skills 宪法门禁 Hook 脚本（WorkBuddy 宿主级拦截）v2.14.0
======================================================================
挂到 ~/.workbuddy/settings.json 的 hooks 字段，让"宪法三查"从自觉变成强制：

事件:
  UserPromptSubmit  任务提交:简单任务打豁免标记;专业任务重置门禁状态 + 记录任务 + 注入上轮违规警告
  PreToolUse        写代码/写文件前:三查(step1)必须在本任务内"新鲜" PASS → 阻断(exit 2)
  Stop              任务收尾:校验最终回复是否含三查+任务相关技能名,违规写入 .constitution-violations.json

用法(由宿主 hook 调用,stdin 传入 JSON payload):
  python constitution-gate.py UserPromptSubmit
  python constitution-gate.py PreToolUse
  python constitution-gate.py Stop

exit code 语义(兼容 Claude Code / WorkBuddy 同源 hook):
  0  = 放行
  1  = 阻断并显示错误
  2  = 阻断该次工具调用(PreToolUse 专用,不报错)

v2.14.0 修复"假装查技能"漏洞(2026-08-24):
  1. PreToolUse 新鲜度校验: step1 的 ts 必须 >= 本任务 UserPromptSubmit 写入的 reset_ts,
     防止"上次任务的旧 PASS"一次通过、后续所有 Write/Edit 永久放行。
  2. Stop 硬记录: 校验 last_assistant_message 是否含【宪法三查】+ 任务相关技能名(Layer C),
     FAIL 写入 .constitution-violations.json(累计计数+原因+任务)。
  3. UserPromptSubmit 注入违规警告: 有违规记录时输出到 stdout(平台注入 Agent 上下文),
     让 Agent 在下个任务开头就看到上次假查被抓,形成"事前拦+事后记+下次警"闭环。
  4. UserPromptSubmit 记录 last_task, Stop 用它做 Layer C 任务相关校验。

设计原则:
  - fail-open:脚本自身异常一律 exit 0,绝不因 bug 卡死正常使用
  - 防死锁:执行"constitution-check"命令的 Bash 调用放行
  - 简单任务豁免:命中翻译/润色/概念解释关键词 → 全流程放行
"""
import json
import os
import subprocess
import sys
import time

EVENT = sys.argv[1] if len(sys.argv) > 1 else ""

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, ".constitution-state.json")
SIMPLE_FLAG = os.path.join(BASE, ".constitution-simple")
VIOLATIONS = os.path.join(BASE, ".constitution-violations.json")
CHECK = os.path.join(BASE, "scripts", "constitution-check")

# 简单任务关键词(零号条款:翻译/润色/概念解释/一般知识问答)
# v2.19.0:仅作兜底 —— 正常路径统一走 pre-hook.classify_task(单一词表),
# 修复 gate 与 --classify 两套词表不同步(如"介绍一下")的问题。
SIMPLE_KW = [
    "翻译", "润色", "解释", "概念", "什么意思", "是什么意思", "怎么理解",
    "translate", "paraphrase", "explain", "meaning", "什么是", "介绍一下",
]

# 需要"先查技能"的执行型工具(写代码/写文件)
EXEC_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# v2.19.0:Bash 写文件模式检测 —— 旧版只拦 Write/Edit,Agent 用
# `cat > file <<EOF` / 重定向 / tee 写文件完全绕过门禁,
# 而"推送代码/跑爬虫"这类专业任务恰恰主要走 Bash。
# 注意排除 >/dev/null(丢弃输出,不产生文件)。
import re as _re
_BASH_WRITE_RE = _re.compile(
    r">>?\s*(?!/dev/null)[\w\.\-/~][^\s|&;]*"   # cmd > file / cmd >> file
    r"|\btee\s+(?:-a\s+)?[\w\.\-/~]"            # cmd | tee file
    r"|\bcat\s+<<"                               # heredoc: cat <<EOF
    r"|\b(?:cp|mv|touch|mkdir)\s+"              # 文件操作命令
)


def classify_via_pre_hook(text):
    """复用 pre-hook.classify_task(单一词表,零号条款确定性分类器)。

    加载失败时返回 None,调用方走本地兜底(保持 fail-open)。
    """
    try:
        import importlib.util as _ilu
        ph_path = os.path.join(BASE, "scripts", "pre-hook.py")
        spec = _ilu.spec_from_file_location("pre_hook_gate_mod", ph_path)
        ph = _ilu.module_from_spec(spec)
        spec.loader.exec_module(ph)
        return ph.classify_task(text)
    except Exception:
        return None


def now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"steps": {}}


def save_state(data):
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_violations():
    try:
        with open(VIOLATIONS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"count": 0, "last_ts": None, "last_reason": None, "task": None}


def save_violations(data):
    try:
        with open(VIOLATIONS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def is_simple(text):
    """零号条款简单任务判定。

    v2.19.0:优先走 pre-hook.classify_task(与 --classify 单一词表,含词边界
    匹配与"专业词优先"规则);加载失败退回本地词表兜底。
    """
    verdict = classify_via_pre_hook(text)
    if verdict is not None:
        return verdict == "simple"
    low = (text or "").lower()
    return any(k.lower() in low for k in SIMPLE_KW)


def is_bash_file_write(tool, tool_input):
    """v2.19.0:Bash 是否在写文件(重定向/tee/heredoc/文件操作命令)"""
    if tool != "Bash":
        return False
    cmd = ""
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command", "") or ""
    return bool(_BASH_WRITE_RE.search(cmd or ""))


def is_check_command(text):
    """是否在跑宪法门禁自身(防死锁)"""
    return "constitution-check" in (text or "")


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    # ---------- UserPromptSubmit ----------
    if EVENT == "UserPromptSubmit":
        prompt = payload.get("prompt", "") or ""
        if is_simple(prompt):
            with open(SIMPLE_FLAG, "w", encoding="utf-8") as f:
                f.write("simple")
        else:
            # 专业任务:清除豁免标记 + 重置门禁状态(含 reset_ts / last_task),要求新任务重新走三查
            try:
                if os.path.exists(SIMPLE_FLAG):
                    os.remove(SIMPLE_FLAG)
            except Exception:
                pass
            data = load_state()
            data["steps"] = {}
            data["reset_ts"] = now_ts()
            data["last_task"] = (prompt or "")[:2000]
            save_state(data)
            # 注入上轮违规警告(v2.14.0): stdout 会被平台注入 Agent 上下文
            vio = load_violations()
            if vio.get("count", 0) > 0:
                print(
                    "【宪法违规警告】检测到上轮专业任务未通过宪法三查校验"
                    "(累计 {} 次;最近时间:{};原因:{})."
                    "本次任务必须:① 真正读取记忆;② 真正读取技能树并列出命中的技能名"
                    "(禁止只写\"已读\");③ 有匹配必用. 若再次违规将累计记录."
                    .format(vio.get("count", 0), vio.get("last_ts", "?"),
                            (vio.get("last_reason") or "?")[:200]),
                    file=sys.stdout,
                )
        sys.exit(0)

    # ---------- PreToolUse ----------
    if EVENT == "PreToolUse":
        tool = payload.get("tool_name", "") or ""
        tool_input = payload.get("tool_input", {})
        # v2.19.0:Bash 写文件(重定向/tee/heredoc)视同 Write/Edit 一并拦截
        if tool not in EXEC_TOOLS and not is_bash_file_write(tool, tool_input):
            sys.exit(0)
        # 跑门禁自身不拦(防死锁)
        tinput = json.dumps(tool_input, ensure_ascii=False)
        if is_check_command(tinput):
            sys.exit(0)
        # 简单任务豁免
        if os.path.exists(SIMPLE_FLAG):
            sys.exit(0)
        # 核心:三查(step1)必须在本任务内"新鲜" PASS(v2.14.0 新鲜度校验)
        data = load_state()
        s1 = data.get("steps", {}).get("step1", {})
        reset_ts = data.get("reset_ts", "")
        passed = bool(s1.get("passed"))
        # 字符串比较: ts 与 reset_ts 同为 "%Y-%m-%d %H:%M:%S" 格式,字典序=时间序
        fresh = (not reset_ts) or (s1.get("ts", "") >= reset_ts)
        if passed and fresh:
            sys.exit(0)
        task_hint = ("；任务: " + data.get("last_task", "")[:80]) if data.get("last_task") else ""
        msg = (
            "【宪法门禁·PreToolUse 阻断】调用 {} 前未完成本任务内的宪法三查声明"
            "(或声明来自旧任务,已过期){}.\n"
            "请先执行: constitution-check --step 1 --input '<宪法三查汇报>' --strict --task '<当前任务>'\n"
            "      然后: constitution-check --step 2 --input '<技能树声明>' --strict\n"
            "      然后: constitution-check --step 3 --input '<技能调用声明>' --strict"
        ).format(tool, task_hint)
        print(msg, file=sys.stderr)
        sys.exit(2)

    # ---------- Stop ----------
    if EVENT == "Stop":
        msg = payload.get("last_assistant_message", "") or ""
        if not msg or os.path.exists(SIMPLE_FLAG):
            sys.exit(0)
        data = load_state()
        last_task = data.get("last_task", "")
        try:
            cmd = [sys.executable, CHECK, "--input", "-", "--strict", "--step", "1"]
            if last_task:
                cmd += ["--task", last_task]
            r = subprocess.run(
                cmd,
                input=msg.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            out = (r.stdout or b"").decode("utf-8", errors="ignore").strip()
            vio = load_violations()
            if r.returncode == 0:
                # 通过:清除违规标记(已合规,不再警告)
                if vio.get("count", 0) > 0:
                    save_violations({"count": 0, "last_ts": None,
                                     "last_reason": None, "task": None})
            else:
                # FAIL:累计违规记录(v2.14.0 硬记录,下次任务注入警告)
                vio["count"] = vio.get("count", 0) + 1
                vio["last_ts"] = now_ts()
                vio["last_reason"] = (out or "无输出")[-300:]
                vio["task"] = (last_task or "")[:200]
                save_violations(vio)
                print(
                    "[constitution-gate:Stop] 【宪法违规记录】上轮回复未通过三查校验: "
                    + ((out[-500:] if out else "无输出")),
                    file=sys.stderr,
                )
        except Exception:
            pass
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
