# -*- coding: utf-8 -*-
"""Step3 校验:匹配技能必用(命中→有调用痕迹;无匹配→已声明)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step3"
DESC = "匹配技能调用"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    # 无匹配声明 → 通过(宪法第三条路径)
    if T.has_any(text, "技能树无匹配", "无匹配", "未命中", "无命中", "没有匹配"):
        return True, "技能树无匹配,已声明", "PASS"
    # 命中 → 必须有调用痕迹
    if T.has_any(text, "命中", "匹配"):
        if T.has_any(text, "已调用", "已加载", "加载了", "调用", "执行了", "使用", "已按"):
            return True, "命中技能且有调用痕迹", "PASS"
        return False, "声明命中但未见调用痕迹", "FAIL"
    return False, "未声明命中或无匹配(需二选一)", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    a = ap.parse_args()
    text = T.read_input(a.input)
    passed, msg, level = check(text)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
