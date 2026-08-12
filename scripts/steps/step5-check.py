# -*- coding: utf-8 -*-
"""Step5 校验:推荐板块(须含 GitHub 链接 + star 数;宪法第五条)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step5"
DESC = "推荐板块(GitHub 高星)"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    # 是否有推荐板块
    if not T.has_any(text, "本次相关技能推荐", "相关技能推荐", "顺手搜了一圈", "🔍", "技能推荐"):
        return False, "未输出「本次相关技能推荐」板块", "FAIL"
    links = T.github_links(text)
    if not links:
        return False, "推荐板块缺 GitHub 链接(github.com/owner/repo)", "FAIL"
    if not T.star_count(text):
        return False, "推荐板块缺 star 数标记(如 20K★/45k stars)", "FAIL"
    # 获取方式:含链接或命令/安装词
    if not T.has_any(text, "github.com", "install", "安装", "获取", "下载", "git clone", "npm"):
        return False, "推荐板块缺获取方式", "FAIL"
    return True, f"推荐板块合格(链接 {len(links)} 个,含 star 数)", "PASS"


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
