# -*- coding: utf-8 -*-
"""宪法门禁 · 体检工具(v2.31.0)

2026-09-21 事故后新增。事故形态:钩子 UserPromptSubmit 超时 → 平台
"operation blocked by hook: Hook timed out after 15000ms/20000ms"
→ 用户整条消息被拦死 = 感知为"系统崩溃"。

本工具回答一个问题:**现在放它继续上班,会不会又出事?**
逐项体检:

  1 拉闸开关状态
  2 状态文件:可读?可写(原子写实测)?是否损坏?
  3 注入缓存:新鲜度 / 是否触发每轮重建
  4 违规记录:是否存在"卡死清不掉"的旧账
  5 钩子注册:settings.json 里注册的命令指向的文件是否存在;超时值多大
  6 耗时实测:实跑一轮各事件,与平台上限比对(这是事故的根因指标)
  7 健康日志:尾部是否出现 crash / write_fail / slow / auto_trip

用法:
  python scripts/constitution-doctor.py            # 只体检
  python scripts/constitution-doctor.py --fix      # 体检 + 修可自动修的
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
GATE = os.path.join(HERE, "constitution-gate.py")
STATE = os.path.join(BASE, ".constitution-state.json")
VIO = os.path.join(BASE, ".constitution-violations.json")
OFF = os.path.join(BASE, ".constitution-off")
HEALTH = os.path.join(BASE, ".constitution-health.log")
INJECTED = os.path.join(BASE, "hooks", "injected-context.json")
SETTINGS = os.path.expanduser("~/.workbuddy/settings.json")
PY = sys.executable
FIX = "--fix" in sys.argv          # python scripts/constitution-doctor.py --fix

# 平台给的上限(ms):gate UserPromptSubmit 15000 / pre-hook 20000 / Stop 30000
PLATFORM_LIMITS = {"UserPromptSubmit": 15000, "PreToolUse": 10000, "Stop": 30000}

ok_n = warn_n = bad_n = 0
FIXES = []


def say(tag, msg, detail=""):
    global ok_n, warn_n, bad_n
    if tag == "OK":
        ok_n += 1
    elif tag == "WARN":
        warn_n += 1
    else:
        bad_n += 1
    mark = {"OK": "[ OK ]", "WARN": "[WARN]", "BAD": "[BAD ]", "INFO": "[INFO]"}[tag]
    print("%s %s%s" % (mark, msg, ("  -> " + detail) if detail else ""))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


print("=" * 74)
print("宪法门禁体检 v2.31.0   BASE=%s" % BASE)
print("=" * 74)

# ---- 1 拉闸状态 ----
print("\n【1】拉闸开关")
if os.path.exists(OFF):
    say("WARN", "门禁处于拉闸状态(不会拦任何任务)", OFF)
    try:
        with open(OFF, encoding="utf-8") as f:
            print("      原因: " + f.read().strip().replace("\n", " / "))
    except Exception:
        pass
else:
    say("OK", "未拉闸,门禁在岗")

# ---- 2 状态文件 ----
print("\n【2】状态文件")
data = read_json(STATE)
if data is None:
    say("BAD", "状态文件缺失或不是合法 JSON", STATE)
    if FIX:
        try:
            os.remove(STATE)
        except Exception:
            pass
        FIXES.append("已删除损坏的状态文件(下次任务会重建)")
else:
    say("OK", "状态文件可读", "keys=%s" % ",".join(list(data.keys())[:6]))
    if not data.get("reset_ts"):
        say("WARN", "状态里没有 reset_ts(可能是新装/刚被清空,下次任务会重建)")
    else:
        say("OK", "本任务时间戳正常", "reset_ts=%s" % data.get("reset_ts"))
# 原子写实测
probe = os.path.join(BASE, ".constitution-state.json")
try:
    tmp = "%s.doctor.%d.tmp" % (probe, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("{}")
    os.replace(tmp, os.path.join(BASE, ".doctor-write-probe"))
    os.remove(os.path.join(BASE, ".doctor-write-probe"))
    say("OK", "状态目录可写(os.replace 实测通过)")
except Exception as e:
    say("BAD", "状态目录写入失败:门禁会静默失去证据链", "%s: %s" % (type(e).__name__, e))

# ---- 3 注入缓存 ----
print("\n【3】注入缓存(记忆+技能树)")
if os.path.exists(INJECTED):
    age = time.time() - os.path.getmtime(INJECTED)
    h = age / 3600.0
    if h < 24:
        say("OK", "缓存新鲜(%.1f 小时前)" % h, "热路径不会触发重建")
    else:
        say("WARN", "缓存已过期(%.1f 小时),下一轮会进程内重建" % h,
            "建议在 SessionStart 预热,别留到热路径")
else:
    say("WARN", "注入缓存不存在", "下一轮会重建;若重建很慢会顶穿平台超时")

# ---- 4 违规记录 ----
print("\n【4】违规记录")
vio = read_json(VIO)
if not vio or vio.get("count", 0) == 0:
    say("OK", "无未结清违规", "cleared_ts=%s" % (vio or {}).get("cleared_ts"))
else:
    if vio.get("cleared_ts"):
        say("OK", "计数>0 但已标结清(不会再弹警告)", "count=%s" % vio.get("count"))
    else:
        say("BAD", "存在未结清违规,会被每轮重播",
            "count=%s last_ts=%s task=%s" % (vio.get("count"), vio.get("last_ts"),
                                             (vio.get("task") or "")[:40]))
        if FIX:
            with open(VIO, "w", encoding="utf-8") as f:
                json.dump({"count": 0, "last_ts": None, "last_reason": None,
                           "task": None, "cleared_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "cleared_task": (vio.get("task") or "")[:200],
                           "cleared_reason": "doctor --fix 结清旧账"}, f,
                          ensure_ascii=False, indent=2)
            FIXES.append("已结清卡死的违规记录")

# ---- 5 钩子注册 ----
print("\n【5】钩子注册(settings.json)")
st = read_json(SETTINGS)
if st is None:
    say("WARN", "读不到 %s(可能没用 WorkBuddy 钩子注册)" % SETTINGS)
else:
    hooks = st.get("hooks") or {}
    if not hooks:
        say("WARN", "settings.json 里没有任何钩子(门禁未注册)",
            "若你正在用门禁,说明钩子被旁路了")
    for phase, groups in hooks.items():
        for g in groups or []:
            for h in (g.get("hooks") or []):
                cmd = h.get("command", "")
                if "constitution" not in cmd:
                    continue
                to = h.get("timeout")
                # 从命令串里抠出 .py/.sh 路径检查存在性
                missing = []
                for tok in cmd.replace('"', " ").split():
                    if tok.lower().endswith((".py", ".sh", ".cjs")):
                        if not os.path.exists(tok):
                            missing.append(tok)
                if missing:
                    say("BAD", "%s 钩子指向的文件不存在" % phase, "；".join(missing))
                else:
                    lim = PLATFORM_LIMITS.get(phase, 15) * 1000
                    if to and to * 1000 <= lim:
                        say("WARN", "%s 超时值 %ss 偏紧(=平台上限)" % (phase, to),
                            "建议 >= 60s,让门禁自己控预算")
                    else:
                        say("OK", "%s 超时值 %ss 有余量" % (phase, to or "?"))

# ---- 6 耗时实测(事故根因指标) ----
print("\n【6】耗时实测(事故根因指标)")
# v2.31.0:探针不得污染违规档案 —— Stop 探针的文本天然不含三查汇报,
# 会被门禁记成一条真违规(实测 2026-09-21 19:46:26 造出假 count=1)。
# 故体检前快照、体检后原样恢复。
_vio_snapshot = None
try:
    if os.path.exists(VIO):
        with open(VIO, encoding="utf-8") as f:
            _vio_snapshot = f.read()
except Exception:
    pass
payloads = {
    "UserPromptSubmit": {"prompt": "帮我修复技能项目的 bug", "session_id": "doctor"},
    "PreToolUse": {"tool_name": "Write", "tool_input": {
        "file_path": os.path.join(BASE, ".doctor-probe.txt"), "content": "x"}},
    "Stop": {"last_assistant_message": "体检探针:本轮无三查内容,仅测耗时"},
}
worst = 0
for ev, pl in payloads.items():
    t0 = time.time()
    try:
        subprocess.run([PY, GATE, ev], input=json.dumps(pl, ensure_ascii=False).encode(),
                       capture_output=True, timeout=60)
        ms = int((time.time() - t0) * 1000)
    except Exception as e:
        say("BAD", "%s 调用异常" % ev, str(e))
        continue
    worst = max(worst, ms)
    lim = PLATFORM_LIMITS.get(ev, 15000)
    if ms > lim * 0.8:
        say("BAD", "%s 耗时 %dms,已超平台上限 %dms 的 80%%" % (ev, ms, lim), "必然超时")
    elif ms > lim * 0.5:
        say("WARN", "%s 耗时 %dms,接近上限 %dms" % (ev, ms, lim), "机器一忙就会超")
    else:
        say("OK", "%s 耗时 %dms(上限 %dms)" % (ev, ms, lim))
# 解释器启动基线(本机实测 python 启动本身要 2.2s,是根本原因)
t0 = time.time()
subprocess.run([PY, "-c", "pass"], capture_output=True)
base_ms = int((time.time() - t0) * 1000)
if base_ms > 800:
    say("WARN", "python 解释器启动就要 %dms(正常机器 ~100ms)" % base_ms,
        "每轮跑 N 个 python 钩子 = N×这个数;建议给 python 目录加杀软排除项")
else:
    say("OK", "python 解释器启动 %dms" % base_ms)
probe = os.path.join(BASE, ".doctor-probe.txt")
if os.path.exists(probe):
    try:
        os.remove(probe)
    except Exception:
        pass
# 还原违规档案(体检探针产生的一切记录都不算数)
try:
    if _vio_snapshot is not None:
        with open(VIO, "w", encoding="utf-8") as f:
            f.write(_vio_snapshot)
    elif os.path.exists(VIO):
        os.remove(VIO)
except Exception:
    pass

# ---- 7 健康日志 ----
print("\n【7】健康日志")
if os.path.exists(HEALTH):
    try:
        with open(HEALTH, encoding="utf-8", errors="ignore") as f:
            lines = [x for x in f.read().splitlines() if x.strip()]
        tail = lines[-200:]
        bad = [x for x in tail if ("\tcrash\t" in x or "\twrite_fail\t" in x
                                   or "\tauto_trip\t" in x or "\tslow\t" in x)]
        if bad:
            say("WARN", "近 %d 条里有 %d 条异常记录" % (len(tail), len(bad)), bad[-1][:120])
        else:
            say("OK", "近 %d 条无 crash/write_fail/auto_trip/slow" % len(tail))
    except Exception as e:
        say("WARN", "健康日志读取失败", str(e))
else:
    say("INFO", "还没有健康日志(新装或尚未运行)")

# ---- 结论 ----
print("\n" + "=" * 74)
print("体检结论: OK %d / WARN %d / BAD %d    最慢单次钩子 %dms" % (ok_n, warn_n, bad_n, worst))
if FIXES:
    print("已修复: " + "；".join(FIXES))
print("=" * 74)
if bad_n:
    print("有 BAD 项 —— 建议先拉闸(scripts/emergency-off.sh),修好再合闸。")
    sys.exit(2)
sys.exit(0)
