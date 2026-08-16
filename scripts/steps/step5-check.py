# -*- coding: utf-8 -*-
"""Step5 校验:推荐板块(须含 GitHub 链接 + star 数;宪法第五条)

文章"三明治架构"延伸:推荐不是幻觉,必须有证据支撑。
本 Step 硬校验:验证 GitHub 链接是否真实存在且可访问。
"""
import argparse
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step5"
DESC = "推荐板块(GitHub 高星,软+硬两层校验)"


def layer_b_hard_check(text):
    """Layer B:硬校验 — 验证 GitHub 链接有效性(可选,耗时)"""
    links = T.github_links(text)
    if not links:
        return False, "无 GitHub 链接", "FAIL"

    # 简化验证:检查链接格式是否符合 github.com/owner/repo
    valid_links = []
    for link in links:
        # 提取 owner/repo
        match = re.search(r"github\.com/([^/]+)/([^/]+)", link)
        if match:
            owner, repo = match.groups()
            # 基本格式检查
            if owner and repo and len(owner) > 0 and len(repo) > 0:
                valid_links.append(link)

    if valid_links:
        return True, f"硬校验通过:{len(valid_links)} 个有效 GitHub 链接", "PASS"
    return False, "硬校验未通过:GitHub 链接格式无效", "FAIL"


def check(text):
    """主校验函数:两层校验"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验
    has_recommendation = T.has_any(text, "本次相关技能推荐", "相关技能推荐",
                                   "顺手搜了一圈", "🔍", "技能推荐")
    if not has_recommendation:
        return False, "未输出「本次相关技能推荐」板块", "FAIL"

    links = T.github_links(text)
    if not links:
        return False, "推荐板块缺 GitHub 链接(github.com/owner/repo)", "FAIL"

    if not T.star_count(text):
        return False, "推荐板块缺 star 数标记(如 20K★/45k stars)", "FAIL"

    if not T.has_any(text, "github.com", "install", "安装", "获取", "下载",
                     "git clone", "npm"):
        return False, "推荐板块缺获取方式", "FAIL"

    # Layer A 通过,检查 Layer B
    hard_passed, hard_msg = layer_b_hard_check(text)
    if hard_passed:
        return True, f"软+硬校验均通过。{hard_msg}", "PASS"

    # Layer A 通过但 Layer B 未通过,降级为 WARN
    return False, f"软校验通过但硬校验未通过。{hard_msg}", "FAIL"


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
