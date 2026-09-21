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

# ======================= v2.31.0 抗崩溃层 =======================
# 背景(2026-09-21 事故,用户三次截图):
#   勾子在 UserPromptSubmit 超时 → 平台直接 block 整条用户消息
#   ("operation blocked by hook: Hook timed out after 15000ms/20000ms")
#   → 用户发什么都进不来,表现为"系统崩溃"。
#   实测本机 python 解释器启动 2.2-2.5s(正常机器 ~0.1s),每轮要跑 2 个
#   python 钩子 → 固定成本 5s 起,机器一忙必然顶穿 15s/20s 上限。
#   → 结论:门禁必须"宁可放行,绝不阻塞";且必须有一键断电能力。
#
# 五条不可违反的防灾规则(写进 SKILL.md):
#   R1 拉闸优先:拉闸开关存在 → 任何事件在任何逻辑之前直接放行。
#   R2 异常放行:门禁自身任何异常 → 退出码 0,永不因自身故障拦人。
#   R3 自修复豁免:门禁不得拦截对门禁自身的修复(破"自锁死")。
#   R4 写失败可见 + 自动断电:状态写不进去要留痕,连续失败即自动拉闸。
#   R5 耗时预算:单次钩子超预算即放弃剩余工作并放行,绝不拖到被平台杀。
KILL_SWITCH = os.path.join(BASE, ".constitution-off")
HEALTH_LOG = os.path.join(BASE, ".constitution-health.log")
# 单次钩子自设预算(ms)。平台给的上限是 15000ms,这里留足 2.5 倍安全余量。
BUDGET_MS = 6000
# 实测耗时超过该值即记"slow",连续 2 次 → 自动拉闸(远超预算 = 即将超时)
SLOW_MS = 9000
# 状态写入连续失败达该次数 → 自动拉闸(状态不可信时门禁不该继续拦人)
WRITE_FAIL_LIMIT = 3
# R3 自修复豁免:这些是门禁自身源码,永远可写(状态文件仍永久禁写)
SELF_REPAIR_NAMES = (
    "constitution-gate.py", "pre-hook.py", "constitution-check",
    "session-start.sh", "user-prompt-submit.sh", "hooks.json",
    "SKILL.md", "README.md", "CHANGELOG.md",
)
SELF_REPAIR_DIRS = ("scripts", "hooks", "tests")
# ==============================================================

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

# v2.31.0:提取"真实写入目标"的正则(只看目标位置,不看命令里是否提到某文件名)。
# 事故(2026-09-21):旧版 Bash 判定 = "命令含受保护文件名" 且 "命令含任意写动作"
# 即拦 —— 于是 `printf ... >> .gitignore`(文本里提到 .constitution-state.json)
# 被误判成"篡改状态文件"直接拦死。误拦正常任务正是用户第一优先级要消除的事故。
_BASH_WRITE_TARGET_RES = (
    _re.compile(r">>?\s*(?!/dev/null)([^\s|&;]+)"),
    _re.compile(r"\btee\s+(?:-a\s+)?([^\s|&;]+)"),
    _re.compile(r"\b(?:cp|mv)\s+[^\s|&;]+\s+([^\s|&;]+)"),
    _re.compile(r"\b(?:touch|rm|mkdir|rmdir)\s+(?:-[^\s]+\s+)*([^\s|&;]+)"),
    _re.compile(r"\bsed\s+(?:-[a-zA-Z]*i[a-zA-Z]*|--inplace)\s+"
                r"(?:'[^']*'|\"[^\"]*\"|[^\s]+)\s+([^\s|&;]+)"),
)


def bash_write_targets(cmd):
    """Bash 命令里"真正被写的路径"清单(用于精确判定,避免误拦)"""
    out = []
    for rx in _BASH_WRITE_TARGET_RES:
        for m in rx.finditer(cmd or ""):
            out.append(m.group(1).strip("'\""))
    return out


# ======================= v2.31.0 抗崩溃层函数 =======================


def health_log(kind, detail=""):
    """R4:轻量追加健康日志(纯 append,不走原子写,失败也不抛)。

    只留最近 200 行,便于事后定位"哪一步开始异常/变慢"。
    """
    try:
        line = "%s\t%s\t%s\tpid=%d\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), kind,
            (detail or "")[:300].replace("\n", " "), os.getpid())
        with open(HEALTH_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def trip_switch(reason):
    """R1/R4:自动拉闸 —— 写下开关文件,门禁从此对任何事件放行。

    只写文件、不做别的动作:即使这一刻磁盘/权限异常,也不能让本函数抛出
    异常影响调用方(调用方在钩子热路径上)。
    """
    try:
        if os.path.exists(KILL_SWITCH):
            return
        with open(KILL_SWITCH, "w", encoding="utf-8") as f:
            f.write("自动拉闸 %s\n原因: %s\n恢复: 删除本文件,或运行 "
                    "scripts/emergency-on.sh\n" % (now_ts(), reason))
        health_log("auto_trip", reason)
    except Exception:
        pass


def kill_switch_active():
    """R1:拉闸判定。文件开关优先,其次环境变量。返回原因(空串=未拉闸)。"""
    try:
        if os.path.exists(KILL_SWITCH):
            return "文件开关 %s" % KILL_SWITCH
    except Exception:
        pass
    try:
        v = (os.environ.get("CONSTITUTION_OFF") or "").strip().lower()
        if v and v not in ("0", "false", "no", "off"):
            return "环境变量 CONSTITUTION_OFF=%s" % v
    except Exception:
        pass
    return ""


def write_fail_streak():
    """R4:最近连续 write_fail 次数(尾部连续计数,遇到其它记录即重置)。"""
    n = 0
    try:
        with open(HEALTH_LOG, encoding="utf-8", errors="ignore") as f:
            for ln in f.read().splitlines()[::-1]:
                if "\twrite_fail\t" in ln:
                    n += 1
                elif n:
                    break
    except Exception:
        return 0
    return n


def self_repair_targeted(tool, tool_input, cmd_text=""):
    """R3:目标是否是对门禁自身的修复(是→必须放行,破自锁死)。

    只放行门禁源码/文档/测试;GATE_PROTECTED_NAMES(状态文件)不在其列 ——
    状态文件仍然永久禁写,防 Agent 给自己伪造通行证。
    """
    try:
        cands = []
        if isinstance(tool_input, dict):
            for k in ("file_path", "path", "notebook_path", "target_file"):
                v = tool_input.get(k)
                if isinstance(v, str) and v:
                    cands.append(v)
            for k in ("command", "cmd"):
                v = tool_input.get(k)
                if isinstance(v, str) and v:
                    cands.append(v)
        if cmd_text:
            cands.append(cmd_text)
        base_norm = os.path.normcase(os.path.abspath(BASE))
        for c in cands:
            c_norm = os.path.normcase(c.replace("\\", "/"))
            # 命令里出现拉闸/合闸/钩子文件 => 一律放行(断电权高于一切)
            if ".constitution-off" in c_norm or "emergency-" in c_norm:
                return True
            if "skills-constitution" in c_norm and (
                    "hooks.json" in c_norm or "emergency" in c_norm):
                return True
            # 绝对路径落在门禁项目内
            try:
                ap = os.path.normcase(os.path.abspath(c))
            except Exception:
                ap = ""
            if ap.startswith(base_norm + os.sep):
                tail = os.path.normcase(ap[len(base_norm) + 1:])
                name = os.path.basename(tail)
                if name in GATE_PROTECTED_NAMES:
                    return False           # 状态文件:豁免不适用
                if (tail.split(os.sep)[0] in SELF_REPAIR_DIRS
                        or name in SELF_REPAIR_NAMES):
                    return True
    except Exception:
        return False
    return False


# ==================================================================


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
        # v2.31.0(R4):写失败必须留痕。旧版静默放弃 → 状态停在旧时刻,
        # 门禁却继续拦人(2026-09-21 事故:state mtime 停在 08:45,而钩子
        # 已跑过多轮,外部完全看不出异常)。连续失败达阈值 → 自动拉闸。
        health_log("write_fail", os.path.basename(path))
        if write_fail_streak() >= WRITE_FAIL_LIMIT:
            trip_switch("状态文件连续写入失败 %d 次: %s"
                        % (WRITE_FAIL_LIMIT, os.path.basename(path)))
    except Exception as e:
        health_log("write_error", "%s: %s" % (type(e).__name__, e))
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


def clear_violations_if_any(reason):
    """v2.31.0(用户钦定 2026-09-21「违规合规即清零」):任务合规即结清违规记录。

    旧版把"通过即清除"写在 Stop 分支最末尾,而前面有三处提前 sys.exit(0)
    → 清除代码永远走不到 → 2026-09-20 那条 count=3 挂了一整天,每轮重播。
    现在:结清动作提到**所有早返回之前**,并把结清痕迹写进 cleared_ts /
    cleared_task —— 计数归零但保留可审计历史,不销毁证据。
    """
    try:
        vio = load_violations()
        if vio.get("count", 0) > 0:
            save_violations({
                "count": 0,
                "last_ts": None,
                "last_reason": None,
                "task": None,
                "cleared_ts": now_ts(),
                "cleared_task": (vio.get("task") or "")[:200],
                "cleared_reason": reason,
            })
            health_log("violations_cleared", reason)
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


def is_continuation(text):
    """v2.22.0:追加式消息判定 —— 同一任务的延续,不应重置门禁状态

    v2.30.0 起不再作为任务边界判定(被"同对话+2小时窗口"取代),保留供回滚参考。
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
        # v2.31.0:精确判定 —— 只有"真正写向受保护文件"才算篡改。
        # 旧版"命令里提到文件名 + 命令里有任意写动作"即拦,会把
        # `printf ... >> .gitignore`(文本中提到状态文件名)这类正常命令误杀;
        # 实测 2026-09-21 当场误拦了一次正常的 git 提交流程。
        targets = bash_write_targets(cmd)
        if not targets:
            return False
        return any(any(n in t for n in GATE_PROTECTED_NAMES) for t in targets)
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


def _main_impl():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    # ---------- UserPromptSubmit ----------
    if EVENT == "UserPromptSubmit":
        prompt = payload.get("prompt", "") or ""
        if not prompt.strip():
            sys.exit(0)
        # v2.30.0(用户钦定 2026-09-20):任务边界 = 同一对话 + 距上次活动 2 小时内。
        # 旧版把"每条非追加式消息"都当新任务 → 状态重置 → 中途每个对话段落都三查
        # (用户抓包:"明明设计好好的,任务开始三查一次,中途不再三查")。
        # 改为:同任务不重置不重查;仅"必需分类完全不相交"时提示询问用户是否重新三查。
        data = load_state()
        sid = str(payload.get("session_id") or "")  # 拿得到就用;没有则退化为纯时间窗
        cutoff = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.localtime(time.time() - 2 * 3600))
        same_task = bool(
            data.get("reset_ts")
            and (data.get("last_seen_ts") or "") >= cutoff
            and (not sid or not data.get("session_id")
                 or data.get("session_id") == sid)
        )
        # 每条消息都刷新活动时间(2 小时窗口按"最近活动"计算)
        data["last_seen_ts"] = now_ts()
        if sid:
            data["session_id"] = sid
        if is_simple(prompt):
            save_state(data)
            with open(SIMPLE_FLAG, "w", encoding="utf-8") as f:
                f.write("simple")
            sys.exit(0)
        if same_task:
            # 同一任务:不重置、不重复要求三查(通行证/证据持续有效)。
            # 两条边界(用户钦定 2026-09-20):
            # ① 三查仅任务开始一次 —— 例外:本消息必需分类与当前任务完全不相交
            #    → 可能另起新类型任务,提示 Agent 询问用户是否重新三查;
            #    答复前按当前通行证放行(fail-open)。
            # ② 「有匹配必用」每轮都适用 —— 本消息有必需分类就提醒一行,
            #    相关技能必须调用;只一行,不重复三查全文(省 token)。
            save_state(data)
            try:
                cur = data.get("required_categories") or []
                new_cats = required_categories_via_pre_hook(prompt) or []
                if cur and new_cats and not (set(cur) & set(new_cats)):
                    print(
                        "【宪法·新任务确认】本消息可能是同对话里另起的新类型任务"
                        "(当前任务必需分类:{};本消息必需分类:{})。"
                        "请先询问用户:是否重新执行宪法三查?答复前按当前通行证继续放行."
                        .format("、".join(cur), "、".join(new_cats)),
                        file=sys.stdout,
                    )
                elif new_cats:
                    print(
                        "【宪法·有匹配必用】本消息必需分类:"
                        + "、".join(new_cats)
                        + "。相关技能必须用 Skill 工具调用,无匹配才走通用能力"
                          "(三查本任务已做过,无需重复)。",
                        file=sys.stdout,
                    )
            except Exception:
                pass
            sys.exit(0)
        # 新任务(>2 小时未活动 / 换了对话 / 无任务状态):
        # 清除豁免标记 + 重置门禁状态(含 reset_ts / last_task),要求新任务重新走三查
        try:
            if os.path.exists(SIMPLE_FLAG):
                os.remove(SIMPLE_FLAG)
        except Exception:
            pass
        data["steps"] = {}
        data.pop("skill_invoked", None)
        data.pop("required_categories", None)  # v2.27.5:新任务重置必需分类缓存
        data.pop("stop_checked_ts", None)      # v2.30.0:Stop 每任务只校验一次
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
        # v2.31.0:警告与任务时间窗解耦 —— 只对"未结清"的记录出警告。
        # 旧版:超 2h 判新任务 → 重新读违规文件 → 把几天前的旧账当新警告弹出来
        # (2026-09-21 实测:09-20 的"爬虫"旧账在 09-21 每轮重播,而本轮任务
        #  跟那条记录毫无关系)。任务合规时 Stop 会立即结清,不再重播。
        vio = load_violations()
        if vio.get("count", 0) > 0 and not vio.get("cleared_ts"):
            print(
                "【宪法违规警告】检测到**未结清**的违规记录"
                "(累计 {} 次;最近时间:{};涉及任务:{})."
                "本次任务必须:① 真正读取记忆;② 真正读取技能树并列出命中的技能名"
                "(禁止只写\"已读\");③ 有匹配必用. 若再次违规将累计记录."
                "(门禁若异常,拉闸:删除 {}/.constitution-off 对应的开关文件即可,"
                "或运行 scripts/emergency-off.sh)"
                .format(vio.get("count", 0), vio.get("last_ts", "?"),
                        (vio.get("task") or "?")[:60], BASE),
                file=sys.stdout,
            )
        sys.exit(0)

    # ---------- PreToolUse ----------
    if EVENT == "PreToolUse":
        tool = payload.get("tool_name", "") or ""
        tool_input = payload.get("tool_input", {})
        # v2.31.0(R2):payload 结构异常(无法可靠判定目标)→ 放行,绝不误拦。
        # 正常 Write/Edit 的 tool_input 一定是 dict;非 dict 只可能来自平台
        # 版本差异或探测流量,门禁无从判断,按"异常放行"处理。
        if tool_input is not None and not isinstance(tool_input, dict):
            health_log("payload_anomaly",
                       "tool=%s tool_input_type=%s" % (tool, type(tool_input).__name__))
            sys.exit(0)
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
        # v2.31.0(R3):自修复豁免 —— 门禁不得拦截对门禁自身的修复。
        # 事故复盘:门禁一旦开始误拦,连"修门禁"的写操作也被拦 → 自锁死,
        # 只能靠改 hooks.json 文件名逃生。状态文件仍永久禁写(上面已拦死)。
        if self_repair_targeted(tool, tool_input, tinput):
            health_log("self_repair_pass", "%s -> %s" % (tool, tinput[:120]))
            sys.exit(0)
        # 简单任务豁免
        if os.path.exists(SIMPLE_FLAG):
            sys.exit(0)
        # 核心:本任务内三查证据链完整即放行
        # (① step1 新鲜 PASS;② 注入+技能调用 —— v2.22.0)
        data = load_state()
        # v2.27.3:状态文件损坏/丢失 → 降级放行(提醒,不阻断)
        # v2.31.0(R2):去掉 "and injection_ready()" 条件 —— 状态不可读就是门禁
        # 自身故障,无论注入是否就绪都必须放行(旧版在注入也缺失时会 exit 2
        # 拦死写操作,正是 2026-09-21 事故里"误拦正常任务"的最后一环)。
        if state_broken(data):
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
        # v2.27.3:状态文件损坏/丢失 → 放行且不记违规(防"拿门禁自己的故障
        # 去惩罚用户")。v2.31.0(R2):去掉 injection 条件,状态不可读一律放行。
        if state_broken(data):
            sys.exit(0)
        # v2.30.0:收尾校验每任务只做一次(针对任务首轮回复)。
        # 旧版每轮 Stop 都校验 → 用户每个对话段落都被要求三查(用户钦定 2026-09-20:
        # "任务开始三查一次,中途不再三查")。
        if data.get("stop_checked_ts") and is_fresh(
                data["stop_checked_ts"], data.get("reset_ts", "")):
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
                # v2.31.0:早返回之前先结清 —— 本任务已合规,旧违规账目就地清零。
                # (旧版在这里直接 sys.exit(0),结清代码在函数末尾 → 永不清除)
                clear_violations_if_any("本任务证据链完整(强证据或无需三查)")
                data["stop_checked_ts"] = now_ts()
                save_state(data)
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
                timeout=10,   # v2.31.0(R5):预算内。旧值 30s 会顶穿平台 Stop 上限
            )
            out = (r.stdout or b"").decode("utf-8", errors="ignore").strip()
            vio = load_violations()
            if r.returncode == 0:
                # v2.31.0:通过 = 已合规 → 结清旧违规记录(合规即清零,用户钦定)
                clear_violations_if_any("Stop 收尾校验 PASS")
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
        # v2.30.0:无论通过与否,本任务收尾只校验这一次(下次任务开始时随重置清除)
        data["stop_checked_ts"] = now_ts()
        save_state(data)
        sys.exit(0)

    sys.exit(0)


def main():
    """v2.31.0 抗崩溃外壳(R1/R2/R5):拉闸优先、异常放行、耗时留痕。

    任何未预期异常 → 退出码 0(放行),绝不因为门禁自身故障拦住用户。
    只有 _main_impl 里显式 sys.exit(2)(任务内三查证据确实不足)才允许拦截。
    """
    t0 = time.time()
    sw = kill_switch_active()
    if sw:
        print("[constitution-gate] 宪法门禁已拉闸(%s),本次直接放行。"
              "恢复: 删除 %s 或运行 scripts/emergency-on.sh"
              % (sw, KILL_SWITCH), file=sys.stderr)
        sys.exit(0)
    try:
        _main_impl()
    except SystemExit:
        cost = int((time.time() - t0) * 1000)
        if cost > SLOW_MS:
            health_log("slow", "%s %dms" % (EVENT, cost))
            trip_switch("单次钩子耗时 %dms,已接近平台超时上限(15000ms),"
                        "为防止再次把用户消息拦死,自动拉闸" % cost)
        raise
    except BaseException as e:                     # noqa: BLE001
        health_log("crash", "%s %s: %s" % (EVENT, type(e).__name__, e))
        print("[constitution-gate] 门禁自身异常(%s: %s),按防灾规则 R2 放行本次操作。"
              % (type(e).__name__, e), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
