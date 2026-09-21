# -*- coding: utf-8 -*-
"""v2.31.0 抗崩溃验收套件 · gate_failsafe

背景(2026-09-21 事故,用户三次截图):
    钩子 UserPromptSubmit 超时 → 平台 block 整条用户消息
    ("operation blocked by hook: Hook timed out after 15000ms/20000ms"),
    用户发什么都进不来 = 感知为"系统崩溃"。事后复盘出五条死规则:

    R1 拉闸优先      拉闸开关存在 → 任何事件在任何逻辑之前直接放行
    R2 异常放行      门禁自身异常 → 退出码 0,永不因自身故障拦人
    R3 自修复豁免    门禁不得拦截对门禁自身的修复(破"自锁死")
    R4 写失败可见    状态写不进去要留痕;连续失败 → 自动拉闸
    R5 耗时预算      单次钩子耗时超预算 → 记 slow / 自动拉闸

本套件逐条断言"无论如何都不能把用户任务拦死"。
**发布前置门禁**:本套件不全绿 → 不允许发布(见 SKILL.md 发布流程)。

用法: python scripts/tests/gate_failsafe.py
"""
import json
import os
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(HERE, "scripts", "constitution-gate.py")
STATE = os.path.join(HERE, ".constitution-state.json")
VIO = os.path.join(HERE, ".constitution-violations.json")
SIMPLE = os.path.join(HERE, ".constitution-simple")
OFF = os.path.join(HERE, ".constitution-off")
HEALTH = os.path.join(HERE, ".constitution-health.log")
PY = sys.executable

# 平台给的上限(gate 15000ms / pre-hook 20000ms),断言时留 20% 余量
PLATFORM_LIMIT_MS = 15000
assert_under = int(PLATFORM_LIMIT_MS * 0.8)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def run_gate(event, payload=None, raw=None, env=None, timeout=60):
    """调用门禁。payload=dict 走 JSON;raw=str 原样喂;raw 为空串则喂空 stdin。"""
    if raw is None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        data = raw.encode("utf-8")
    e = dict(os.environ)
    if env:
        e.update(env)
    t0 = time.time()
    try:
        p = subprocess.run([PY, GATE, event], input=data, capture_output=True,
                           timeout=timeout, env=e)
        rc = p.returncode
        so = (p.stdout or b"").decode("utf-8", "replace")
        se = (p.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        rc, so, se = -999, "", "TimeoutExpired"
    return rc, so, se, int((time.time() - t0) * 1000)


def ts_now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json(path, d):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def write_raw(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def clean_env():
    """每次测试前把环境恢复到"干净起点"。"""
    for p in (OFF, SIMPLE):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    if os.path.exists(STATE):
        try:
            with open(STATE, "r+", encoding="utf-8") as f:
                f.truncate(0)
        except Exception:
            pass


def state_with_evidence(ts):
    """造一个"本任务已合规"的状态(强证据:step1 PASS)。"""
    return {
        "steps": {"step1": {"passed": True, "level": "PASS", "ts": ts}},
        "reset_ts": ts,
        "last_seen_ts": ts,
        "last_task": "帮我写一个python爬虫抓取天气数据",
        "injected": True,
        "required_categories": ["code"],
        "task_cleared": {"ts": ts, "reason": "step1"},
    }


def state_no_evidence(ts):
    """造一个"状态正常但毫无三查证据"的状态(用于验证拦截防线没被放宽)。"""
    return {
        "steps": {},
        "reset_ts": ts,
        "last_seen_ts": ts,
        "last_task": "帮我写一个python爬虫抓取天气数据",
        "injected": False,
        "required_categories": ["code"],
    }


print("=" * 74)
print("v2.31.0 抗崩溃验收 · gate_failsafe")
print("=" * 74)

# 记录初始状态,结束时恢复
_orig_state = read_json(STATE, {})
_orig_vio = read_json(VIO, {})
_orig_state_ro = False
try:
    _orig_state_ro = not (os.stat(STATE).st_mode & stat.S_IWRITE) and True
except Exception:
    pass

clean_env()

# ---------------- R1 拉闸优先 ----------------
write_json(STATE, state_no_evidence(ts_now()))
rc, _, _, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}})
check("R1a 无拉闸 + 无证据 → 仍拦(基线,证明测试有效)", rc == 2, "exit=%s" % rc)

write_raw(OFF, "手动拉闸 by gate_failsafe\n")
rc, so, _, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}})
check("R1b 文件拉闸开关存在 → 一律放行", rc == 0, "exit=%s" % rc)

os.remove(OFF)
rc, so, _, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}},
    env={"CONSTITUTION_OFF": "1"})
check("R1c 环境变量 CONSTITUTION_OFF=1 → 一律放行", rc == 0, "exit=%s" % rc)

# ---------------- R2 异常放行 ----------------
rc, so, se, _ = run_gate("UserPromptSubmit", raw="{这不是合法 JSON")
check("R2a stdin 非法 JSON → 放行且不抛栈", rc == 0 and "Traceback" not in se,
      "exit=%s traceback=%s" % (rc, "Traceback" in se))

rc, so, se, _ = run_gate("UserPromptSubmit", raw="")
check("R2b stdin 为空 → 放行且不抛栈", rc == 0 and "Traceback" not in se, "exit=%s" % rc)

rc, so, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": "oops-不是dict"})
check("R2c payload 结构异常(tool_input 非 dict) → 放行且不抛栈",
      rc == 0 and "Traceback" not in se, "exit=%s traceback=%s" % (rc, "Traceback" in se))

rc, so, se, _ = run_gate("PreToolUse", {"tool_name": None, "tool_input": None})
check("R2d payload 字段为 None → 放行且不抛栈", rc == 0 and "Traceback" not in se, "exit=%s" % rc)

# 状态损坏 + 注入缺失:旧版会 exit 2 拦死,新版必须放行
write_raw(STATE, '{"steps": ')
rc, so, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}})
check("R2e 状态文件损坏 → 放行(不得因门禁自身故障拦人)", rc == 0, "exit=%s" % rc)
write_raw(STATE, "")
rc, so, se, _ = run_gate("Stop", {"last_assistant_message": "收尾回复"})
check("R2f 状态文件为空 + Stop → 放行且不记违规", rc == 0, "exit=%s" % rc)

# ---------------- R3 自修复豁免 ----------------
write_json(STATE, state_no_evidence(ts_now()))
rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": GATE, "content": "# 修门禁自己"}})
check("R3a 无证据但目标是门禁自身源码 → 放行(破自锁死)", rc == 0, "exit=%s" % rc)

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scripts", "emergency-off.sh"), "content": "#!/bin/sh"}})
check("R3b 写 emergency-off.sh → 放行", rc == 0, "exit=%s" % rc)

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "touch \"%s\"" % OFF.replace("\\", "/")}})
check("R3c 拉闸动作(touch .constitution-off)→ 放行", rc == 0, "exit=%s" % rc)

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}})
check("R3d 豁免不越界:写普通文件仍拦(防线未被放宽)", rc == 2, "exit=%s" % rc)

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Write", "tool_input": {
    "file_path": STATE, "content": "{}"}})
check("R3e 状态文件仍永久禁写(防伪造通行证)", rc == 2, "exit=%s" % rc)

# ---------------- 误拦修复:只认"真实写入目标"(2026-09-21 当场误拦复盘) ----------------
# 实测事故:提交代码时命令里"提到"了 .constitution-state.json(写 .gitignore、
# grep 统计),旧版判定 = 提到名字 + 命令含任意写动作 → 判成"篡改门禁文件"拦死。
# 门禁自己把用户的正常任务拦了 —— 正是本次要消灭的事故形态。
FORGE_MSG = "禁止直接修改门禁状态文件"
write_json(STATE, state_no_evidence(ts_now()))
_st = STATE.replace("\\", "/")

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "printf '.constitution-state.json\\n' >> .gitignore"}})
check("误拦F1 提到状态文件名但写的是别的文件 → 不得判为篡改", FORGE_MSG not in se, se[:120])

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "grep -c .constitution-state.json .gitignore && cat .constitution-state.json"}})
check("误拦F2 只读/统计状态文件名 → 不得判为篡改", FORGE_MSG not in se, se[:120])

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "echo '{}' > \"%s\"" % _st}})
check("误拦F3 真重定向写状态文件 → 必须判为篡改并拦截",
      rc == 2 and FORGE_MSG in se, "exit=%s %s" % (rc, se[:100]))

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "rm -f \"%s\"" % _st}})
check("误拦F4 真删除状态文件 → 必须判为篡改并拦截",
      rc == 2 and FORGE_MSG in se, "exit=%s %s" % (rc, se[:100]))

rc, _, se, _ = run_gate("PreToolUse", {"tool_name": "Bash", "tool_input": {
    "command": "tee \"%s\" <<<'{}'" % _st}})
check("误拦F5 真用 tee 写状态文件 → 必须判为篡改并拦截",
      rc == 2 and FORGE_MSG in se, "exit=%s %s" % (rc, se[:100]))

# ---------------- 违规合规即清零(用户钦定 2026-09-21) ----------------
ts = ts_now()
write_json(STATE, state_with_evidence(ts))
write_json(VIO, {"count": 3, "last_ts": "2026-09-20 23:12:30",
                 "last_reason": "LayerC FAIL ...", "task": "帮我写一个python爬虫抓取天气数据"})
rc, so, se, _ = run_gate("Stop", {"last_assistant_message": "本轮正常回复"})
_v = read_json(VIO, {})
check("清1 合规任务收尾 → 违规计数清零", _v.get("count", -1) == 0,
      "count=%s" % _v.get("count"))
check("清2 清零留痕(cleared_ts / cleared_task 可审计)",
      bool(_v.get("cleared_ts")) and bool(_v.get("cleared_task")),
      "cleared_ts=%s" % _v.get("cleared_ts"))

# 下一轮新任务:结清的旧账不得再弹警告
write_json(VIO, {"count": 0, "cleared_ts": ts, "cleared_task": "旧任务"})
rc, so, se, _ = run_gate("UserPromptSubmit", {"prompt": "帮我修复技能项目的 bug",
                                             "session_id": "fs-clean"})
check("清3 已结清记录不再重播警告", "宪法违规警告" not in so, "stdout含警告=%s" % ("宪法违规警告" in so))

# ---------------- R4 写失败可见 + 自动拉闸 ----------------
clean_env()
if os.path.exists(HEALTH):
    os.remove(HEALTH)
write_json(STATE, state_no_evidence(ts_now()))
try:
    os.chmod(STATE, stat.S_IREAD)      # 置只读 → 状态写入必失败
    for _ in range(3):
        run_gate("UserPromptSubmit", {"prompt": "帮我写一个python爬虫抓取天气数据",
                                      "session_id": "fs-ro"})
    _tripped = os.path.exists(OFF)
    _health = ""
    try:
        with open(HEALTH, encoding="utf-8") as f:
            _health = f.read()
    except Exception:
        pass
    check("R4a 状态写失败被留痕(health log 记 write_fail)",
          "write_fail" in _health, "health=%d 字节" % len(_health))
    check("R4b 连续写失败 → 自动拉闸(不用人工介入)", _tripped,
          "OFF存在=%s" % _tripped)
finally:
    try:
        os.chmod(STATE, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass

# ---------------- R5 耗时预算 ----------------
clean_env()
write_json(STATE, state_with_evidence(ts_now()))
costs = []
for ev, pl in (("UserPromptSubmit", {"prompt": "帮我修复技能项目的 bug", "session_id": "fs-t"}),
               ("PreToolUse", {"tool_name": "Write", "tool_input": {
                   "file_path": os.path.join(HERE, "scratch_normal.txt"), "content": "x"}}),
               ("Stop", {"last_assistant_message": "收尾"})):
    rc, so, se, ms = run_gate(ev, pl)
    costs.append((ev, ms))
_worst = max(c[1] for c in costs)
check("R5a 单次钩子耗时 < 平台上限 80%%(实测最慢 %dms,上限 %dms)"
      % (_worst, PLATFORM_LIMIT_MS), _worst < assert_under,
      " ".join("%s=%dms" % c for c in costs))
check("R5b 超预算有留痕通道(health log 支持 slow 记录)",
      "SLOW_MS" in open(GATE, encoding="utf-8").read(), "")

# ---------------- 收尾:恢复现场 ----------------
clean_env()
write_json(STATE, _orig_state if _orig_state else {})
if _orig_vio:
    write_json(VIO, _orig_vio)
for _p in (os.path.join(HERE, "scratch_normal.txt"), OFF, SIMPLE):
    if os.path.exists(_p):
        try:
            os.remove(_p)
        except Exception:
            pass

print()
passed = 0
for name, ok, detail in results:
    print("  %s %s%s" % ("PASS" if ok else "FAIL", name,
                         ("   [%s]" % detail) if (detail and not ok) else ""))
    passed += 1 if ok else 0
print()
print("-" * 74)
print("  结果: %d/%d 通过" % (passed, len(results)))
print("-" * 74)
sys.exit(0 if passed == len(results) else 1)
