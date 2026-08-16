# -*- coding: utf-8 -*-
"""Step2 校验:技能树已读(或声明"技能树无匹配")

文章"三明治架构"原则:确定性代码必须验证实际操作,而非信任声明。
本 Step 增加硬校验:检查回复中是否引用了 skill_tree.json 的实际内容。
v2.11.0 增加 Layer C:任务含代码/git/部署关键词时,必须引用对应分类技能名。
"""
import argparse
import json
import os
import sys
import importlib.util

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
        # 提取分类名和技能名
        categories = set()
        skill_names = set()
        if "categories" in tree:
            for cat, items in tree["categories"].items():
                categories.add(cat)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("name"):
                            skill_names.add(item["name"])
                        elif isinstance(item, str):
                            skill_names.add(item)
        elif "items" in tree:
            for item in tree.get("items", []):
                cat = item.get("category", "")
                name = item.get("name", "")
                if cat:
                    categories.add(cat)
                if name:
                    skill_names.add(name)

        # 检查回复中是否出现了分类名或技能名(v2.11.0:全量匹配,不用切片)
        cat_match = any(T.has_any(text, c) for c in categories)
        skill_match = any(T.has_any(text, s) for s in skill_names)

        if cat_match or skill_match:
            return True, f"硬校验通过:引用了技能树内容(分类={cat_match},技能={skill_match})", "PASS"
        return False, "硬校验未通过:未引用技能树实际内容", "FAIL"
    except Exception as e:
        return False, f"读取技能树失败:{e}", "SKIP"


def layer_c_task_hard_check(text, tree_path, task):
    """Layer C(v2.11.0):任务相关技能命中硬校验(与 step1 共用逻辑)"""
    if not task or not task.strip():
        return True, "无任务描述,跳过任务相关校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return False, f"skill_tree.json 不存在:{tree_path}", "FAIL"

    try:
        pre_hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-hook.py")
        spec = importlib.util.spec_from_file_location("pre_hook_mod_step2", pre_hook_path)
        ph = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ph)

        required_cats, required_skills = ph.required_skills_for_task(
            ph.load_tree(tree_path), task)
        if not required_skills:
            return True, f"任务无强相关分类(必需分类:{required_cats or '无'})", "PASS"

        text_lower = (text or "").lower()
        found_skills = [s for s in required_skills if s.lower() in text_lower]
        found_cats = [c for c in required_cats if c.lower() in text_lower]
        if not found_skills and not found_cats:
            return False, (
                f"任务含'{task}'相关关键词,但输出未引用对应分类技能"
                f"(必需分类:{required_cats}, 候选技能如:{required_skills[:5]})"
            ), "FAIL"
        return True, (
            f"任务相关技能命中: 分类={found_cats or required_cats}, "
            f"技能={found_skills[:3] or required_skills[:3]}"
        ), "PASS"
    except Exception as e:
        return False, f"任务相关校验异常:{e}", "SKIP"


def check(text, tree_path=None, task=None):
    """主校验函数:两层校验 + v2.11.0 任务相关校验"""
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
    hard_result, hard_msg, hard_level = layer_b_hard_check(text, tree_path)
    hard_passed = (hard_level == "PASS")

    # Layer C:任务相关校验(v2.11.0)
    task_passed, task_msg, task_level = layer_c_task_hard_check(text, tree_path, task)
    task_ok = (task_level == "PASS")

    # 决策逻辑
    if task_level == "FAIL":
        return False, f"LayerC FAIL: {task_msg}", "FAIL"
    if task_level == "SKIP":
        return False, f"LayerC 异常: {task_msg}", "FAIL"
    if hard_passed and task_ok:
        return True, f"{hard_msg}; {task_msg}", "PASS"
    elif hard_passed:
        return False, f"硬校验通过但任务校验未过({task_msg})", "FAIL"
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
    ap.add_argument("--task", default=None,
                    help="任务描述(v2.11.0:含代码/git/部署关键词时,输出必须引用对应分类技能)")
    a = ap.parse_args()

    if not a.tree:
        # skill_tree.json 在 skills-constitution/ 目录（scripts 的父目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        constitution_dir = os.path.dirname(script_dir)
        a.tree = os.path.join(constitution_dir, "skill_tree.json")

    text = T.read_input(a.input)
    passed, msg, level = check(text, a.tree, a.task)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
