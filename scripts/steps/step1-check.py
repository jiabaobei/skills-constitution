# -*- coding: utf-8 -*-
"""Step1 校验:宪法三查是否真正执行(而非仅汇报)

文章"三明治架构"核心原则:不要把"是否查记忆"交给概率模型自选。
本 Step 分两层校验:
  Layer A(软):回复文本里有三查汇报 → 基础通过
  Layer B(硬):回复中引用了 MEMORY.md / skill_tree.json 的实质内容 → 强通过
  Layer C(v2.11.0):任务含"代码/git/部署"等关键词时,回复必须引用对应分类下的实际技能名
     → 防止 Agent 用"查了 skills-constitution 就算查了技能"糊弄

Layer B/C 是文章说的"确定性代码包夹概率LLM"的具体实现:
  不是让 Agent 说"我查了记忆",而是让 Agent 把记忆内容复述出来,
  校验脚本验证这些内容是否真实存在。
"""
import argparse
import json
import os
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step1"
DESC = "宪法三查汇报(软+硬两层校验)"


def layer_b_hard_check(text, memory_path, tree_path):
    """Layer B:硬校验 — 检查是否真实引用了记忆和技能树内容

    文章核心:确定性代码不信任概率模型的自觉。
    这里用文件存在性 + 内容特征作为硬证据:
    - 如果回复中出现了 MEMORY.md 里的独特关键词(如技能数量、平台名等)
    - 如果回复中出现了 skill_tree.json 里的分类(如 browser/code/data 等)
    则视为真正执行了查记忆和查技能树的动作,而非仅汇报。
    """
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    has_memory_evidence = False
    has_tree_evidence = False

    # 检查 MEMORY.md 内容证据
    if memory_path and os.path.exists(memory_path):
        try:
            with open(memory_path, encoding="utf-8") as f:
                memory_content = f.read()
            # 独特关键词:语义标记优先(Agent 实际会引用铁律/仓库名/目录名),
            # 数字标记兜底(技能数量等)。v2.11.0 修正顺序,避免只匹配到数字。
            unique_markers = ["铁律", "MEMORY", "jiabaobei", "skills-disabled",
                              "skills-backup", "xiaozhao-radar", "agnes-video",
                              "389", "388", "385", "384", "386",
                              "Ju-You-Hui", "ju-you-hui"]
            found = [m for m in unique_markers if m.lower() in memory_content.lower()]
            if found and T.has_any(text, *found[:3]):
                has_memory_evidence = True
        except Exception:
            pass

    # 检查 skill_tree.json 内容证据
    if tree_path and os.path.exists(tree_path):
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

            # 检查回复中是否出现了分类名或技能名
            # v2.11.0:全量匹配(不用 [:5]/[:10] 切片——set 无序导致切片不稳定)
            has_cat_match = any(T.has_any(text, c) for c in categories)
            has_skill_match = any(T.has_any(text, s) for s in skill_names)

            if has_cat_match or has_skill_match:
                has_tree_evidence = True
        except Exception:
            pass

    return has_memory_evidence and has_tree_evidence, (
        f"memory={has_memory_evidence},tree={has_tree_evidence}"
    )


def layer_c_task_hard_check(text, tree_path, task):
    """Layer C(v2.11.0):任务相关技能命中硬校验

    关键改动:当任务含"代码/git/部署/编程/开发"等关键词时,
    回复必须引用 skill_tree.json 对应分类下的**实际技能名**(如 git-workflow-and-versioning),
    否则判定 FAIL —— 防止 Agent 用"查了 skills-constitution 就算查了技能"糊弄。

    返回 (passed, msg, level)
    """
    if not task or not task.strip():
        return True, "无任务描述,跳过任务相关校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return False, f"skill_tree.json 不存在:{tree_path}", "FAIL"

    try:
        # 复用 pre-hook 的确定性映射
        pre_hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-hook.py")
        spec = importlib.util.spec_from_file_location("pre_hook_mod_step1", pre_hook_path)
        ph = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ph)

        required_cats, required_skills = ph.required_skills_for_task(
            ph.load_tree(tree_path), task)
        if not required_skills:
            return True, f"任务无强相关分类(必需分类:{required_cats or '无'})", "PASS"

        # 输出中必须出现至少一个必需技能名或分类名
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


def check(text, memory_path=None, tree_path=None, task=None):
    """主校验函数:三层校验,LAYER_B优先,LAYER_C叠加"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验 — 文本里有汇报
    has_report = T.has_any(text, "宪法三查", "三查", "【宪法三查】")

    # Layer B:硬校验 — 真实引用了记忆和技能树内容
    hard_passed, hard_msg = layer_b_hard_check(text, memory_path, tree_path)

    # Layer C:任务相关技能命中硬校验(v2.11.0)
    task_passed, task_msg, task_level = layer_c_task_hard_check(text, tree_path, task)
    task_ok = (task_level == "PASS")

    # 决策逻辑:
    # - 硬校验通过 + 任务校验通过 → 直接PASS(确定性证据)
    # - 任务校验 FAIL(无论软校验如何)→ FAIL(这是v2.11.0的关键拦截点)
    # - 硬校验未通过但软校验通过 → WARN(有汇报但无实质证据)
    # - 都没有 → FAIL
    if task_level == "FAIL":
        return False, f"LayerC FAIL: {task_msg}", "FAIL"
    if task_level == "SKIP":
        return False, f"LayerC 异常: {task_msg}", "FAIL"
    if hard_passed and task_ok:
        return True, f"硬校验通过({hard_msg}; {task_msg}),三查已真实执行", "PASS"
    elif hard_passed:
        return False, f"硬校验通过但任务校验未过({task_msg})", "FAIL"
    elif has_report:
        return False, f"仅有文本汇报,硬校验未通过({hard_msg})。文章原则:确定性代码不信任自觉。", "FAIL"
    else:
        return False, "无三查汇报,无硬校验证据", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--memory", default=None,
                    help=f"MEMORY.md路径(默认:{os.path.expanduser('~/.workbuddy/MEMORY.md')})")
    ap.add_argument("--tree", default=None,
                    help=f"skill_tree.json路径(默认:scripts/../skill_tree.json)")
    ap.add_argument("--task", default=None,
                    help="任务描述(v2.11.0:含代码/git/部署关键词时,输出必须引用对应分类技能)")
    a = ap.parse_args()

    # 默认路径
    if not a.memory:
        a.memory = os.path.expanduser("~/.workbuddy/MEMORY.md")
    if not a.tree:
        # skill_tree.json 在 skills-constitution/ 目录（scripts 的父目录）
        # 使用绝对路径确保跨平台兼容
        script_dir = os.path.dirname(os.path.abspath(__file__))
        constitution_dir = os.path.dirname(script_dir)
        a.tree = os.path.join(constitution_dir, "skill_tree.json")

    text = T.read_input(a.input)
    passed, msg, level = check(text, a.memory, a.tree, a.task)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
