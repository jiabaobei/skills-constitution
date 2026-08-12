# -*- coding: utf-8 -*-
"""Step2 校验:技能树已读(或声明"技能树无匹配")"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step2"
DESC = "技能树已读/无匹配声明"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    if T.has_any(text, "skill_tree.json", "SKILL_TREE.md", "SKILL_TREE", "技能树已读", "已读技能树", "读了技能树", "技能树 ✅", "技能树已查", "技能树已看"):
        return True, "技能树已读", "PASS"
    if T.has(text, "技能树", "无匹配"):
        return True, "已读技能树并声明无匹配", "PASS"
    return False, "未出现技能树读取痕迹(skill_tree.json/已读声明)", "FAIL"


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
