# -*- coding: utf-8 -*-
"""Step1 校验:宪法三查是否真正执行(而非仅汇报)

文章"三明治架构"核心原则:不要把"是否查记忆"交给概率模型自选。
本 Step 分两层校验:
  Layer A(软):回复文本里有三查汇报 → 基础通过
  Layer B(硬):回复中引用了 MEMORY.md / skill_tree.json 的实质内容 → 强通过

Layer B 是文章说的"确定性代码包夹概率LLM"的具体实现:
  不是让 Agent 说"我查了记忆",而是让 Agent 把记忆内容复述出来,
  校验脚本验证这些内容是否真实存在。
"""
import argparse
import os
import sys

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
            # 独特关键词:技能数量、平台名、铁律标记
            unique_markers = ["389", "388", "385", "384", "386", "铁律", "MEMORY",
                              "skills-disabled", "skills-backup", "jiabaobei",
                              "xiaozhao-radar", "agnes-video", "Ju-You-Hui", "ju-you-hui"]
            found = [m for m in unique_markers if m.lower() in memory_content.lower()]
            if found and T.has_any(text, *found[:3]):
                has_memory_evidence = True
        except Exception:
            pass

    # 检查 skill_tree.json 内容证据
    if tree_path and os.path.exists(tree_path):
        try:
            import json
            with open(tree_path, encoding="utf-8") as f:
                tree = json.load(f)
            # 提取分类名
            categories = set()
            for item in tree.get("items", []):
                cat = item.get("category", "")
                if cat:
                    categories.add(cat)
            # 检查回复中是否出现了这些分类名
            if categories:
                cat_list = list(categories)[:5]  # 最多检查5个
                if T.has_any(text, *cat_list):
                    has_tree_evidence = True
        except Exception:
            pass

    return has_memory_evidence and has_tree_evidence, (
        f"memory={has_memory_evidence},tree={has_tree_evidence}"
    )


def check(text, memory_path=None, tree_path=None):
    """主校验函数:两层校验,LAYER_B优先"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验 — 文本里有汇报
    has_report = T.has_any(text, "宪法三查", "三查", "【宪法三查】")

    # Layer B:硬校验 — 真实引用了记忆和技能树内容
    hard_passed, hard_msg = layer_b_hard_check(text, memory_path, tree_path)

    # 决策逻辑:
    # - 硬校验通过 → 直接PASS(确定性证据)
    # - 硬校验未通过但软校验通过 → WARN(有汇报但无实质证据)
    # - 都没有 → FAIL
    if hard_passed:
        return True, f"硬校验通过({hard_msg}),三查已真实执行", "PASS"
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
    a = ap.parse_args()

    # 默认路径
    if not a.memory:
        a.memory = os.path.expanduser("~/.workbuddy/MEMORY.md")
    if not a.tree:
        a.tree = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "..", "skill_tree.json")

    text = T.read_input(a.input)
    passed, msg, level = check(text, a.memory, a.tree)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
