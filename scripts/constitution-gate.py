#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
constitution-gate —— Skills 宪法门禁 Hook 脚本（WorkBuddy 宿主级拦截）v2.24.0
======================================================================
挂到 ~/.workbuddy/settings.json 的 hooks 字段，让"宪法三查"从自觉变成强制：

事件:
  UserPromptSubmit  任务提交:简单任务打豁免标记;追加式短消息不重置(防中途干扰);
                    专业任务重置门禁状态 + 记录任务 + 标记注入证据 + 注入上轮违规警告
  PreToolUse        写代码/写文件前:本任务内三查证据链完整 → 放行;否则阻断(exit 2)。
                    同时拦截对门禁自身状态文件的篡改(防伪造豁免)。
  Stop              任务收尾:本任务内已有证据链 → 不再重复文本校验(防误记违规);
                    无证据链才校验最终回复,违规写入 .constitution-violations.json

用法(由宿主 hook 调用,stdin 传入 JSON payload):
  python constitution-gate.py UserPromptSubmit
  python constitution-gate.py PreToolUse
  python constitution-gate.py Stop

exit code 语义(兼容 Claude Code / WorkBuddy 同源 hook):
  0  = 放行
  1  = 阻断并显示错误
  2  = 阻断该次工具调用(PreToolUse 专用,不报错)

v2.22.0 三查证据链升级(2026-09-01),修三类真实问题:
  A. 防绕过(门禁可被骗):
     1. 门禁自身文件保护 —— `.constitution-state.json` / `.constitution-simple` /
        `.constitution-violations.json` / `injected-context.json` 禁止被 Agent
        经 Write/Edit/Bash(重定向/tee/rm/mv/sed -i) 篡改。旧版 Agent 写一个
        `.constitution-simple` 文件即可全局豁免、改 state 即可伪造 PASS。
     2. Bash 写文件检测补 `sed -i`(就地改文件也是写文件)。
     3. step1 PASS 必须 level==PASS(只认 constitution-check 真实判定结果)。
  B. 防干扰(任务中途被门禁误拦):
     1. 注入即查 —— UserPromptSubmit 检测平台注入上下文
        (hooks/injected-context.json status=ready)时,记忆+技能树视为已查,
        state 标记 injected;PreToolUse 接受"注入 + 本任务内实际调用过技能"
        (PreToolUse 观察到 Skill 工具调用自动记录)作为完整证据链,
        无需 Agent 再手动跑 constitution-check。
     2. 追加式消息不重置 —— "继续/好的/下一步"等追加式短消息不再重置门禁状态,
        同一任务内的三查证据持续有效,消除"任务开始已查过、中途又被拦"。
     3. Stop 防误记 —— 本任务内已有证据链时跳过最终回复的重复文本校验,
        不再因"收尾回复没复述三查"误记违规、下任务开头误注入警告。
  C. 省 token —— 阻断提示文案精简约一半。

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

# v2.27.5 修复: Windows GBK 控制台下 print 中文/emoji 可能崩溃,强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

EVENT = sys.argv[1] if len(sys.argv) > 1 else ""

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, ".constitution-state.json")
SIMPLE_FLAG = os.path.join(BASE, ".constitution-simple")
VIOLATIONS = os.path.join(BASE, ".constitution-violations.json")
CHECK = os.path.join(BASE, "scripts", "constitution-check")
INJECTED_CONTEXT = os.path.join(BASE, "hooks", "injected-context.json")

# 简单任务关键词(零号条款:翻译/润色/概念解释/一般知识问答)
# v2.19.0:仅作兜底 —— 正常路径统一走 pre-hook.classify_task(单一词表),
# 修复 gate 与 --classify 两套词表不同步(如"介绍一下")的问题。
SIMPLE_KW = [
    "翻译", "润色", "解释", "概念", "什么意思", "是什么意思", "怎么理解",
    "translate", "paraphrase", "explain", "meaning", "什么是", "介绍一下",
]

# 需要"先查技能"的执行型工具(写代码/写文件)
EXEC_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# v2.22.0:门禁自身文件保护 —— 这些文件的状态就是门禁判定依据,
# 允许 Agent 写改等于允许它给自己发通行证(实测绕过路径)。
GATE_PROTECTED_NAMES = (
    ".constitution-state.json",
    ".constitution-simple",
    ".constitution-violations.json",
    "injected-context.json",
)

# v2.22.0:追加式消息标记 —— 命中即视为同一任务的延续,不重置门禁状态。
# 只认开头(防"帮我写一个可以运行的脚本"这类含子串的新任务被误判延续)。
CONTINUATION_MARKERS = [
    "继续", "接着", "下一步", "再来", "还有呢", "好的", "可以,", "没问题",
    "对,", "嗯", "ok", "okay", "yes", "yep", "sure", "go on", "continue",
    "proceed", "对的", "就这样",
]

# v2.19.0:Bash 写文件模式检测 —— 旧版只拦 Write/Edit,Agent 用
# `cat > file <<EOF` / 重定向 / tee 写文件完全绕过门禁,
# 而"推送代码/跑爬虫"这类专业任务恰恰主要走 Bash。
# 注意排除 >/dev/null(丢弃输出,不产生文件)。
# v2.22.0:补 `sed -i` 就地改写。
import re as _re
_BASH_WRITE_RE = _re.compile(
    r">>?\s*(?!/dev/null)[\w\.\-/~][^\s|&;]*"   # cmd > file / cmd >> file
    r"|\btee\s+(?:-a\s+)?[\w\.\-/~]"            # cmd | tee file
    r"|\bcat\s+<<"                               # heredoc: cat <<EOF
    r"|\b(?:cp|mv|touch|mkdir)\s+"              # 文件操作命令
    r"|\bsed\s+(?:-[a-zA-Z]*i[a-zA-Z]*\s|--inplace)"  # v2.22.0: sed -i 就地改写
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


def required_categories_via_pre_hook(task):
    """v2.22.0:任务必需分类(复用 pre-hook 确定性映射)。加载失败返回 None"""
    try:
        import importlib.util as _ilu
        ph_path = os.path.join(BASE, "scripts", "pre-hook.py")
        spec = _ilu.spec_from_file_location("pre_hook_gate_req_mod", ph_path)
        ph = _ilu.module_from_spec(spec)
        spec.loader.exec_module(ph)
        return ph.required_categories_for_task(task or "")
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


def state_broken(data):
    """v2.27.3:状态文件损坏/丢失判定。

    任何一次专业任务的 UserPromptSubmit 都会写入 reset_ts;状态文件被并发
    写截断/丢失时 load_state 返回 {"steps": {}},没有 reset_ts —— 据此区分
    "本任务刚重置"与"状态不可读"两种情况。
    """
    return not data.get("reset_ts")


def degraded_pass(reason):
    """v2.27.3:降级放行 —— 不阻断(agent 不被卡死),但不签通行证。

    与 v2.27.0 无条件静默放行的区别:本次放行后 task_cleared 仍为空,
    下次任务开始 UserPromptSubmit 会重置状态并重新走三查,门禁自动恢复,
    不会像 v2.27.0 那样一旦损坏就永久失效。
    """
    print(
        "[constitution-gate] 提示: 本任务三查状态不可读(%s),本次放行不阻断;"
        "下次任务开始将重新校验三查。" % reason,
        file=sys.stderr,
    )
    sys.exit(0)


def _cleanup_stale_tmp(path):
    """v2.27.3:清理陈旧 tmp(进程被强杀时 finally 来不及清理的残留)。

    只清理 5 分钟前就停止更新的 tmp,避免误删正在写入的其他进程文件。
    """
    try:
        base = os.path.basename(path)
        d = os.path.dirname(path) or "."
        for n in os.listdir(d):
            if n.startswith(base) and n.endswith(".tmp"):
                fp = os.path.join(d, n)
                if time.time() - os.path.getmtime(fp) > 300:
                    os.remove(fp)
    except Exception:
        pass


def _atomic_write_json(path, data):
    """v2.27.3:原子写入 JSON(进程唯一 temp + os.replace)。

    修复用户钦定 bug:"任务开始拦一次,中途不得再拦"失效的根因 ——
    UserPromptSubmit/PreToolUse/Stop 三个钩子进程并发 open(w)+dump 同一
    状态文件,互相截断 → load_state 读到损坏 JSON 返回空 → 通行证
    (task_cleared)与 injected 标记丢失 → PreToolUse 每次写文件都误拦。

    v2.27.3 修正 v2.27.0 的修复漏洞:v2.27.0 用固定名 `path + ".tmp"`,
    三个并发进程仍会 open(w) 同一个 tmp 互相截断,只是把截断从主文件挪到
    tmp,再被 os.replace 换回主文件(2026-09-03 实测:状态文件停在
    `"last_task": ` 被写残 → 兜底放行 → 门禁整体失效)。
    tmp 名带 pid 后各进程写各自文件,os.replace 仍是原子替换,读方永远
    看到完整文件。

    Windows 专有坑(v2.27.3 修复):目标文件正被另一进程读取时 os.replace
    抛 PermissionError。v2.27.0 此时的兜底是 `open(path,"w")` 直接写 ——
    而 open(w) 会先截断主文件,其他进程恰在此时读到半截 JSON → 状态损坏
    → 门禁整体失效(2026-09-03 实测)。v2.27.3:replace 失败只做短重试,
    仍失败则**放弃本次写入、保留旧文件** —— 状态略微陈旧最多多拦一次,
    下次任务开始 UserPromptSubmit 会重写,远好过写残导致门禁永久失效。
    """
    blob = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    _cleanup_stale_tmp(path)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
            except OSError:
                time.sleep(0.02)
        # 重试耗尽:放弃写入,保留旧文件(绝不退回 open(w) 直接写)
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def save_state(data):
    _atomic_write_json(STATE, data)


def load_violations():
    try:
        with open(VIOLATIONS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"count": 0, "last_ts": None, "last_reason": None, "task": None}


def save_violations(data):
    _atomic_write_json(VIOLATIONS, data)


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


def is_continuation(text):
    """v2.22.0:追加式消息判定 —— 同一任务的延续,不应重置门禁状态

    旧版每条用户消息都重置三查状态 → 任务中途的每条追加消息都要求重新三查,
    造成"任务开始已查过记忆/技能/调用过技能,中途仍被门禁拦"的干扰。
    规则(保守,只认开头):超短消息(≤8字符)或以追加标记开头 → 延续。
    """
    t = (text or "").strip()
    if not t:
        return False
    if len(t) <= 8:
        return True
    tl = t.lower()
    return any(tl.startswith(m) for m in CONTINUATION_MARKERS)


def is_bash_file_write(tool, tool_input):
    """v2.19.0:Bash 是否在写文件(重定向/tee/heredoc/文件操作命令)"""
    if tool != "Bash":
        return False
    cmd = ""
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command", "") or ""
    return bool(_BASH_WRITE_RE.search(cmd or ""))


def gate_file_targeted(tool, tool_input):
    """v2.22.0:本次工具调用是否在篡改门禁自身文件

    Write/Edit/MultiEdit/NotebookEdit:看 file_path/notebook_path;
    Bash:命令含门禁文件名且是写操作(写重定向/tee/rm/mv/sed -i 等)。
    读取门禁文件不拦(只读不改变判定依据)。
    """
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool in EXEC_TOOLS:
        path = (tool_input.get("file_path")
                or tool_input.get("path")
                or tool_input.get("notebook_path") or "")
        return any(name in path for name in GATE_PROTECTED_NAMES)
    if tool == "Bash":
        cmd = tool_input.get("command", "") or ""
        if not any(name in cmd for name in GATE_PROTECTED_NAMES):
            return False
        if bool(_BASH_WRITE_RE.search(cmd)):
            return True
        # rm 不在写文件正则里,单独补
        return bool(_re.search(r"\brm\b", cmd))
    return False


def is_check_command(text):
    """是否在跑宪法门禁自身(防死锁)"""
    return "constitution-check" in (text or "")


def injection_ready():
    """v2.22.0:平台注入上下文是否就绪(注入即查:记忆+技能树已由平台注入)

    读 hooks/injected-context.json(SessionStart 钩子产出)。
    24 小时内的 ready 才算本会话证据;解析失败一律 fail-open 返回 False
    (注入证据缺失只是回到"手动三查"路径,不会卡任务)。
    """
    try:
        with open(INJECTED_CONTEXT, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("status") != "ready":
            return False
        ts = (data.get("timestamp") or "")[:19]
        if ts:
            then = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
            if time.time() - then > 24 * 3600:
                return False
        return True
    except Exception:
        return False


def refresh_injection_via_pre_hook(task_text):
    """v2.27.0:注入上下文缺失/过期时进程内自动刷新(复用 pre-hook.refresh_injection)

    旧逻辑:injection_ready()(24h 内 ready)为 False 就不签发通行证 →
    安装副本带着过期上下文文件时,每个专业任务开始都拿不到通行证,
    中途写操作被迫补证据(用户钦定 bug 的第二个根因)。
    现改为:过期即进程内刷新(零额外进程,秒级),成功即视为已注入,
    任务开始签发通行证,中途写操作一路绿灯。
    """
    try:
        import importlib.util as _ilu2
        ph_path = os.path.join(BASE, "scripts", "pre-hook.py")
        spec = _ilu2.spec_from_file_location("pre_hook_gate_refresh", ph_path)
        ph = _ilu2.module_from_spec(spec)
        spec.loader.exec_module(ph)
        if hasattr(ph, "refresh_injection"):
            return bool(ph.refresh_injection((task_text or "")[:2000]))
    except Exception:
        return False
    return False


def is_fresh(ts, reset_ts):
    """证据时间戳是否属于本任务(字符串字典序=时间序,同格式)"""
    return (not reset_ts) or (ts or "") >= reset_ts


def issue_task_clearance(data, reason):
    """v2.24.0:签发"任务级通行证" —— 本任务三查已过,中途写操作一路绿灯

    只在本函数内签发(两种情形),且状态文件受 GATE_PROTECTED 保护,
    Agent 无法自写文件伪造:
      ① injected —— 平台已强制注入记忆+技能树(注入即查)
      ② step1    —— 本任务内 constitution-check step1 真实 PASS
    """
    data["task_cleared"] = {"ts": now_ts(), "reason": reason}
    return data


def task_cleared_ok(data):
    """v2.24.0:本任务是否已持通行证(签发于本任务 reset 之后)

    用户诉求(2026-09-01):"每一次任务,只要任务开始时执行了三查,任务中途,
    门禁系统不得再拦截"。通行证在任务开始时签发,中途一律放行,
    直到 UserPromptSubmit 判定为新任务(非追加式消息)才重置。
    """
    cl = data.get("task_cleared") or {}
    if not cl.get("ts"):
        return False
    return is_fresh(cl.get("ts", ""), data.get("reset_ts", ""))


def task_evidence_ok(data):
    """v2.22.0:本任务内三查证据链是否完整(供 PreToolUse/Stop 共用)

    满足其一即完整:
      ① step1 在本任务内新鲜 PASS(手动跑过 constitution-check 且硬校验通过)
      ② 平台已注入(记忆+技能树视为已查) 且 本任务内实际调用过技能
      ③ v2.24.0:本任务已持通行证(注入即查 或 step1 通过时签发)
    """
    reset_ts = data.get("reset_ts", "")
    s1 = data.get("steps", {}).get("step1", {})
    if (bool(s1.get("passed")) and s1.get("level", "PASS") == "PASS"
            and is_fresh(s1.get("ts", ""), reset_ts)):
        # 证据成立即补发通行证,后续步骤不再重复举证
        issue_task_clearance(data, "step1")
        save_state(data)
        return True
    if task_cleared_ok(data):
        return True
    if data.get("injected"):
        sk = data.get("skill_invoked", {})
        if sk.get("ts") and is_fresh(sk["ts"], reset_ts):
            return True
    return False


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    # ---------- UserPromptSubmit ----------
    if EVENT == "UserPromptSubmit":
        prompt = payload.get("prompt", "") or ""
        if not prompt.strip():
            sys.exit(0)
        if is_simple(prompt):
            with open(SIMPLE_FLAG, "w", encoding="utf-8") as f:
                f.write("simple")
            sys.exit(0)
        # v2.22.0:追加式消息不重置 —— 同一任务内的三查证据持续有效
        if is_continuation(prompt):
            sys.exit(0)
        # 专业任务:清除豁免标记 + 重置门禁状态(含 reset_ts / last_task),要求新任务重新走三查
        try:
            if os.path.exists(SIMPLE_FLAG):
                os.remove(SIMPLE_FLAG)
        except Exception:
            pass
        data = load_state()
        data["steps"] = {}
        data.pop("skill_invoked", None)
        data.pop("required_categories", None)  # v2.27.5:新任务重置必需分类缓存
        data["reset_ts"] = now_ts()
        data["last_task"] = (prompt or "")[:2000]
        # v2.22.0:注入即查 —— 平台注入上下文就绪则记忆+技能树视为已查
        injected = injection_ready()
        if not injected:
            # v2.27.0:上下文缺失/过期 → 进程内自动刷新后再判
            # (修复任务开始拿不到通行证、中途被拦的用户钦定 bug)
            injected = refresh_injection_via_pre_hook(prompt)
        data["injected"] = injected
        # v2.24.0:注入成功即在任务开始时签发通行证 —— 记忆+技能树已由平台
        # 强制注入,本任务中途的写操作不再重复拦截(用户明确要求:
        # "只要任务开始时执行了三查,任务中途,门禁系统不得再拦截")。
        # 未注入(降级 bash 兜底)时不签发,回到既有的 step1/Skill 调用路径。
        if injected:
            issue_task_clearance(data, "injected")
            # v2.24.0:拦截前移为提醒 —— 任务开始时一次性注入"本任务该看哪些
            # 技能",中途写操作不再阻断。既满足"任务开始三查后中途不得再拦",
            # 又保留"有匹配必用"的引导(约束从阻断降级为提示,不打断执行流)。
            try:
                req = required_categories_via_pre_hook(prompt)
                if req:
                    # v2.27.5:缓存本任务必需分类,供 Stop 收尾判"是否欠三查"零开销复用
                    data["required_categories"] = req
                    print(
                        "【宪法·注入即查】记忆与技能树已由平台注入,本任务必需分类: "
                        + "、".join(req)
                        + "。命中技能请先用 Skill 工具调用再动手。",
                        file=sys.stdout,
                    )
            except Exception:
                pass
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
        # v2.22.0:记录技能调用(证据链一环)。Skill 调用本身不拦,记录后放行。
        if tool == "Skill":
            data = load_state()
            skill_name = ""
            if isinstance(tool_input, dict):
                skill_name = (tool_input.get("skill")
                              or tool_input.get("command") or "")
            data["skill_invoked"] = {"ts": now_ts(), "skill": str(skill_name)[:80]}
            save_state(data)
            sys.exit(0)
        # v2.22.0:门禁自身文件保护 —— 任何情况下禁止篡改门禁状态文件
        if gate_file_targeted(tool, tool_input):
            print(
                "【宪法门禁·拦截】禁止直接修改门禁状态文件"
                "(宪法三查证据必须由 constitution-check 真实校验产生).",
                file=sys.stderr,
            )
            sys.exit(2)
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
        # 核心:本任务内三查证据链完整即放行
        # (① step1 新鲜 PASS;② 注入+技能调用 —— v2.22.0)
        data = load_state()
        # v2.27.3:状态文件损坏/丢失但注入证据就绪 → 降级放行(提醒,不阻断)
        # (防"任务开始已通行、状态文件被截断后中途误拦";
        #  同时防 v2.27.0 静默放行导致门禁永久失效)
        if state_broken(data) and injection_ready():
            degraded_pass("状态文件损坏或丢失")
        if task_evidence_ok(data):
            sys.exit(0)
        # v2.22.0:注入已就绪且任务无必需分类 —— 记忆+技能树已注入,无技能可匹配
        if data.get("injected"):
            req = required_categories_via_pre_hook(data.get("last_task", ""))
            if req is not None and not req:
                sys.exit(0)
        task_hint = ("；任务: " + data.get("last_task", "")[:60]) if data.get("last_task") else ""
        msg = (
            "【宪法门禁·拦截】写文件前本任务的宪法三查证据不足{}.\n"
            "补救任选其一: ① 平台已注入记忆+技能树时,先用 Skill 工具调用命中的技能再写;"
            "② 运行 constitution-check --step 1 --input '<宪法三查汇报(含命中技能名)>'"
            " --strict --task '<当前任务>'."
        ).format(task_hint)
        print(msg, file=sys.stderr)
        sys.exit(2)

    # ---------- Stop ----------
    if EVENT == "Stop":
        msg = payload.get("last_assistant_message", "") or ""
        if not msg or os.path.exists(SIMPLE_FLAG):
            sys.exit(0)
        data = load_state()
        # v2.27.3:状态文件损坏/丢失但注入证据就绪 → 降级放行(不记违规,防误记)
        if state_broken(data) and injection_ready():
            sys.exit(0)
        # v2.22.0:本任务内已有证据链 → 跳过重复文本校验(防误记违规)。
        # 旧版对最终回复再做一遍三查文本校验,任务开头已查过、收尾回复没复述
        # 三查就被误记违规,下个任务开头被误注入警告。
        if task_evidence_ok(data):
            # v2.27.5:强证据才免检 —— step1 真实 PASS 或本任务内真调过技能。
            # 仅"注入即签"的弱通行证 → 收尾回复仍须过三查文本校验,
            # 堵"无视注入提示、全程零举证零追责"漏洞(用户钦定 2026-09-03)。
            _sk = data.get("skill_invoked", {})
            _strong = (
                data.get("task_cleared", {}).get("reason") == "step1"
                or bool(_sk.get("ts") and is_fresh(_sk["ts"], data.get("reset_ts", "")))
            )
            if _strong or not data.get("required_categories"):
                sys.exit(0)
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
