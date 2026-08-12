# -*- coding: utf-8 -*-
"""Step1 校验:宪法三查是否汇报(记忆 / 技能树 / 匹配)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step1"
DESC = "宪法三查汇报"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    if not T.has_any(text, "宪法三查", "三查"):
        return False, "未出现「宪法三查」汇报", "FAIL"
    checks = [
        ("记忆", T.has_any(text, "记忆", "MEMORY", "记忆库")),
        ("技能树", T.has_any(text, "技能树", "skill_tree", "SKILL_TREE")),
        ("匹配", T.has_any(text, "匹配", "命中")),
    ]
    missing = [name for name, ok in checks if not ok]
    if not missing:
        return True, "三查(记忆/技能树/匹配)均已汇报", "PASS"
    return False, f"三查字段缺失:{'/'.join(missing)}", "FAIL"


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
