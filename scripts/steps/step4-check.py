# -*- coding: utf-8 -*-
"""Step4 校验:交付自检(版本/文件核查;非版本类任务自动跳过)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step4"
DESC = "交付自检"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    # 非版本交付类任务(无版本/文件核查关键词)→ SKIP,视为通过(不强制)
    versionish = T.has_any(text, "CHANGELOG", "README", "版本", "v2.", "v1.", "核查", "全文件", "frontmatter", "徽章", "一致")
    if not versionish:
        return True, "非版本交付类任务,跳过自检", "SKIP"
    # 版本类任务:需含版本号 + 核查痕迹
    if T.has_any(text, "CHANGELOG", "核查", "全文件", "一致", "同步"):
        if T.version_numbers(text):
            return True, "版本交付已含版本号与核查痕迹", "PASS"
        return False, "版本类任务缺版本号", "FAIL"
    return False, "版本类任务缺 CHANGELOG/核查痕迹", "FAIL"


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
