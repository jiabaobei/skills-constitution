# -*- coding: utf-8 -*-
"""Step3 校验:匹配技能必用(命中→有调用痕迹;无匹配→已声明)

文章"三明治架构"核心:确定性代码必须验证实际执行,而非信任声明。
本 Step 增加硬校验:检查回复中是否引用了实际调用的技能名。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step3"
DESC = "匹配技能调用(软+硬两层校验)"


def layer_b_hard_check(text, tree_path):
    """Layer B:硬校验 — 检查是否真实引用了技能内容"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    if not tree_path or not os.path.exists(tree_path):
        return False, f"skill_tree.json 不存在:{tree_path}", "FAIL"

    try:
        with open(tree_path, encoding="utf-8") as f:
            tree = json.load(f)
        # 提取技能名和技能描述
        skills = []
        if "categories" in tree:
            for cat, items in tree["categories"].items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("name"):
                            skills.append((item["name"], item.get("description", "")))
                        elif isinstance(item, str):
                            skills.append((item, ""))
        elif "items" in tree:
            for item in tree.get("items", []):
                name = item.get("name", "")
                desc = item.get("description", "")
                if name:
                    skills.append((name, desc))

        # 检查回复中是否出现了技能名
        found_skills = [s for s, _ in skills if T.has_any(text, s)]
        if found_skills:
            return True, f"硬校验通过:引用了技能名={found_skills[:3]}", "PASS"
        return False, "硬校验未通过:未引用实际技能名", "FAIL"
    except Exception as e:
        return False, f"读取技能树失败:{e}", "SKIP"


def check(text, tree_path=None):
    """主校验函数:两层校验"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验
    no_match_keywords = ["技能树无匹配", "无匹配", "未命中", "无命中", "没有匹配"]
    has_no_match = T.has_any(text, *no_match_keywords)

    hit_keywords = ["命中", "匹配"]
    has_hit = T.has_any(text, *hit_keywords)

    if has_no_match:
        return True, "技能树无匹配,已声明", "PASS"

    if has_hit:
        call_keywords = ["已调用", "已加载", "加载了", "调用", "执行了", "使用", "已按"]
        has_call = T.has_any(text, *call_keywords)
        if has_call:
            # 软校验通过,再检查硬校验
            hard_passed, hard_msg = layer_b_hard_check(text, tree_path)
            if hard_passed:
                return True, f"软+硬校验均通过:{hard_msg}", "PASS"
            return False, f"软校验通过但硬校验未通过。{hard_msg}", "FAIL"
        return False, "声明命中但未见调用痕迹(软校验失败)", "FAIL"

    return False, "未声明命中或无匹配(需二选一)", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--tree", default=None,
                    help="skill_tree.json路径(默认:scripts/../skill_tree.json)")
    a = ap.parse_args()

    if not a.tree:
        # skill_tree.json 在 skills-constitution/ 目录（scripts 的父目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        constitution_dir = os.path.dirname(script_dir)
        a.tree = os.path.join(constitution_dir, "skill_tree.json")

    text = T.read_input(a.input)
    passed, msg, level = check(text, a.tree)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
