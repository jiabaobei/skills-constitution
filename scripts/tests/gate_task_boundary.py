# -*- coding: utf-8 -*-
"""v2.30.0 门禁任务边界改动 · 端到端流程测试(repo 本地跑,状态写在 repo 内)

覆盖用户钦定设计(2026-09-20):
  同一对话 + 2 小时内 = 同一个任务,三查只做一次;
  同对话另起新类型任务 → 提示询问用户是否重新三查。
"""
import json
import os
import subprocess
import sys
import time

# 本文件在 <repo>/scripts/tests/ 下,往上三级才是 repo 根(曾因少算一级,
# GATE 指到不存在的 scripts/scripts/,门禁调用全部静默空转 —— 2026-09-20 教训)
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(HERE, "scripts", "constitution-gate.py")
STATE = os.path.join(HERE, ".constitution-state.json")
PY = sys.executable

# 开局清状态:保证测试可重复运行(不受上次运行遗留的同任务窗口影响)
if os.path.exists(STATE):
    os.remove(STATE)


def run_gate(event, payload):
    p = subprocess.run([PY, GATE, event], input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, timeout=60)
    return (p.stdout or b"").decode("utf-8", "replace"), (p.stderr or b"").decode("utf-8", "replace")


def read_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(d):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# ---- T1 任务开始:新任务应重置并缓存必需分类 ----
out1, _ = run_gate("UserPromptSubmit", {"prompt": "帮我写一个python爬虫抓取天气数据", "session_id": "s1"})
s = read_state()
t1_reset = s.get("reset_ts", "")
check("T1 新任务重置(reset_ts 写入)", bool(t1_reset), "reset_ts=" + t1_reset)
check("T1 必需分类已缓存", bool(s.get("required_categories")), str(s.get("required_categories")))

# ---- T2 同任务追问(2 小时内,同会话):不得重置 ----
time.sleep(1)
out2, _ = run_gate("UserPromptSubmit", {"prompt": "继续把爬虫加上重试和日志", "session_id": "s1"})
s2 = read_state()
check("T2 同任务追问不重置", s2.get("reset_ts") == t1_reset,
      "reset_ts {} -> {}".format(t1_reset, s2.get("reset_ts")))
check("T2 同任务不弹询问框", "新任务确认" not in out2, out2[:120])

# ---- T3 同对话另起类型:应弹询问提示,且不重置 ----
cur = s2.get("required_categories") or []
# 选一个与当前任务必需分类不相交的提示词
cand_prompts = ["帮我写一份周报文档并排版", "帮我搜索今天的新闻热点", "帮我把这个excel表按月汇总统计"]
chosen, new_cats = None, None
for cp in cand_prompts:
    out3, _ = run_gate("UserPromptSubmit", {"prompt": cp, "session_id": "s1"})
    s3 = read_state()
    if s3.get("reset_ts") != t1_reset:
        continue  # 意外重置了,不算
    # 从 stdout 判断是否弹框
    if "新任务确认" in out3:
        chosen = cp
        break
check("T3 新类型任务弹询问框", chosen is not None, "cur={} out3={}".format(cur, out3[:160]))
check("T3 弹框后状态仍未重置", read_state().get("reset_ts") == t1_reset, "")

# ---- T4 超过 2 小时:新任务,应重置 ----
s4 = read_state()
old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3 * 3600))
s4["last_seen_ts"] = old
write_state(s4)
out4, _ = run_gate("UserPromptSubmit", {"prompt": "再帮我部署这个网站", "session_id": "s1"})
s4b = read_state()
check("T4 超2小时视为新任务并重置", s4b.get("reset_ts") != t1_reset and s4b.get("reset_ts", "") > t1_reset,
      "reset_ts=" + s4b.get("reset_ts", ""))

# ---- T5 换对话(session_id 变化):2 小时内也算新任务 ----
out5, _ = run_gate("UserPromptSubmit", {"prompt": "帮我写一个python爬虫抓取天气数据", "session_id": "s1"})
s5 = read_state()
t5_reset = s5.get("reset_ts", "")
out5b, _ = run_gate("UserPromptSubmit", {"prompt": "帮我写一个数据分析脚本", "session_id": "s2"})
s5b = read_state()
check("T5 换对话视为新任务并重置", s5b.get("reset_ts") != t5_reset,
      "reset_ts {} -> {}".format(t5_reset, s5b.get("reset_ts")))

# ---- T6 Stop 每任务只校验一次 ----
# 让任务处于弱通行证状态(有必需分类,无强证据)
run_gate("UserPromptSubmit", {"prompt": "帮我写一个python爬虫抓取天气数据", "session_id": "s3"})
s6 = read_state()
s6.pop("task_cleared", None)
s6.pop("skill_invoked", None)
s6["required_categories"] = ["code"]
write_state(s6)
outA, errA = run_gate("Stop", {"last_assistant_message": "随便聊聊,没有三查内容"})
sA = read_state()
check("T6 首轮 Stop 校验后写 stop_checked_ts", bool(sA.get("stop_checked_ts")),
      "stop_checked_ts=" + str(sA.get("stop_checked_ts")) + " vio_count=" + str((sA.get("_vio") or "")))
outB, errB = run_gate("Stop", {"last_assistant_message": "还是没有三查内容"})
sB = read_state()
check("T6 第二轮 Stop 不再校验(时间戳不变)", sB.get("stop_checked_ts") == sA.get("stop_checked_ts"),
      "{} vs {}".format(sA.get("stop_checked_ts"), sB.get("stop_checked_ts")))

# ---- T7 同任务每轮「有匹配必用」提醒(一行,不重复三查) ----
# 前置:确保处于同任务窗口内且必需分类已缓存
run_gate("UserPromptSubmit", {"prompt": "帮我写一个python爬虫抓取天气数据", "session_id": "s7"})
out7a, _ = run_gate("UserPromptSubmit", {"prompt": "继续把爬虫加上重试和日志", "session_id": "s7"})
check("T7a 同任务相关消息有必用提醒", "有匹配必用" in out7a, out7a[:150])
check("T7b 提醒不要求重复三查", "三查" not in out7a.split("有匹配必用")[-1][:60] or "无需重复" in out7a,
      out7a[:150])
out7c, _ = run_gate("UserPromptSubmit", {"prompt": "这个 coffee 不错", "session_id": "s7"})
check("T7c 无必需分类的消息不打扰", "有匹配必用" not in out7c, out7c[:150])

# ---- 汇总 ----
print("\n===== 测试结果 =====")
fails = 0
for name, ok, detail in results:
    print("[{}] {} {}".format("PASS" if ok else "FAIL", name, detail if not ok else ""))
    if not ok:
        fails += 1
print("共 {} 项,失败 {} 项".format(len(results), fails))
sys.exit(1 if fails else 0)
