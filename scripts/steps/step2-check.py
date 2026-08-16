# -*- coding: utf-8 -*-
"""Step2 校验:技能树已读(或声明"技能树无匹配")

文章"三明治架构"原则:确定性代码必须验证实际操作,而非信任声明。
本 Step 增加硬校验:检查回复中是否引用了 skill_tree.json 的实际内容。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step2"
DESC = "技能树已读/无匹配声明(软+硬两层校验)"


def layer_b_hard_check(text, tree_path):
    """Layer B:硬校验 — 检查是否真实引用了技能树内容"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    if not tree_path or not os.path.exists(tree_path):
        return False, f"skill_tree.json 不存在:{tree_path}", "FAIL"

    try:
        with open(tree_path, encoding="utf-8") as f:
            tree = json.load(f)
        # 提取所有分类名和技能名
        categories = set()
        skill_names = set()
        for item in tree.get("items", []):
            cat = item.get("category", "")
            name = item.get("name", "")
            if cat:
                categories.add(cat)
            if name:
                skill_names.add(name)

        # 检查回复中是否出现了分类名或技能名
        cat_match = any(T.has_any(text, c) for c in list(categories)[:5])
        skill_match = any(T.has_any(text, s) for s in list(skill_names)[:10])

        if cat_match or skill_match:
            return True, f"硬校验通过:引用了技能树内容(分类={cat_match},技能={skill_match})", "PASS"
        return False, "硬校验未通过:未引用技能树实际内容", "FAIL"
    except Exception as e:
        return False, f"读取技能树失败:{e}", "SKIP"


def check(text, tree_path=None):
    """主校验函数:两层校验"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验 — 文本里有声明
    soft_keywords = [
        "skill_tree.json", "SKILL_TREE.md", "SKILL_TREE", "技能树已读",
        "已读技能树", "读了技能树", "技能树 ✅", "技能树已查", "技能树已看"
    ]
    has_soft = T.has_any(text, *soft_keywords)

    # 无匹配声明
    no_match_keywords = ["技能树无匹配", "无匹配", "未命中", "无命中", "没有匹配"]
    has_no_match = T.has_any(text, *no_match_keywords)

    # Layer B:硬校验
    hard_passed, hard_msg = layer_b_hard_check(text, tree_path)

    # 决策逻辑
    if hard_passed:
        return True, hard_msg, "PASS"
    elif has_soft or has_no_match:
        return False, f"仅有文本声明,硬校验未通过。{hard_msg}", "FAIL"
    else:
        return False, "无技能树读取痕迹(软+硬均未通过)", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--tree", default=None,
                    help="skill_tree.json路径(默认:scripts/../skill_tree.json)")
    a = ap.parse_args()

    if not a.tree:
        a.tree = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "..", "skill_tree.json")

    text = T.read_input(a.input)
    passed, msg, level = check(text, a.tree)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
