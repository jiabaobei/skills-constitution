# -*- coding: utf-8 -*-
"""状态文件:记录每个 step 的 PASS/FAIL,支持链式依赖(零依赖)"""
import json
import os
import time

DEFAULT_STATE = ".constitution-state.json"

_ORDER = ["step1", "step2", "step3", "step4", "step5"]


def resolve_path(state=None):
    """状态文件路径:默认放项目根目录(scripts/lib/state.py -> 项目根)"""
    if state:
        return state
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, DEFAULT_STATE)


def load(state=None):
    p = resolve_path(state)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"steps": {}, "updated": None}
    return {"steps": {}, "updated": None}


def save(data, state=None):
    p = resolve_path(state)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_step(name, passed, message, level="PASS", state=None):
    data = load(state)
    data["steps"][name] = {
        "passed": bool(passed),
        "level": level,
        "message": message,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save(data, state)
    return data


def get_step(name, state=None):
    return load(state)["steps"].get(name)


def previous_passed(name, state=None):
    """检查前置 step 是否已 PASS(链式依赖)。step1 无前置。返回 (ok, prev_name)"""
    if name not in _ORDER or name == "step1":
        return True, None
    prev = _ORDER[_ORDER.index(name) - 1]
    rec = get_step(prev, state)
    if rec is None:
        return False, prev
    return bool(rec.get("passed")), prev


def reset(state=None):
    save({"steps": {}, "updated": None}, state)
