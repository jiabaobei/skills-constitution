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
import re
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step1"
DESC = "宪法三查汇报(软+硬两层校验)"


def extract_memory_markers(memory_content, limit=8):
    """v2.19.0:从 MEMORY.md 实际内容动态提取独特标记(替代硬编码作者私货)

    旧实现硬编码 ["铁律","jiabaobei","xiaozhao-radar","389"...] 等作者个人标记,
    其他用户的记忆文件几乎永远不命中 → 硬校验对其他用户恒 FAIL(新用户死锁)。
    新实现:取记忆内容里高频、有辨识度的 ASCII 词(≥4 字符,去停用词)与
    中文规则类固定词(铁律/宪法/死规则),作为该用户自己的记忆指纹。
    """
    from collections import Counter
    stop = {"this", "that", "with", "from", "have", "will", "must", "should",
            "your", "the", "and", "for", "not", "are", "all", "can", "but",
            "how", "use", "using", "when", "what", "which", "into", "about",
            "more", "other", "some", "them", "then", "also", "only", "very"}
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{3,}", memory_content or "")
    cnt = Counter(w.lower() for w in words if w.lower() not in stop)
    markers = [w for w, _ in cnt.most_common(limit)]
    for fixed in ("铁律", "宪法", "死规则"):
        if fixed in (memory_content or "") and fixed not in markers:
            markers.append(fixed)
    return markers


def layer_b_hard_check(text, memory_path, tree_path):
    """Layer B:硬校验 — 检查是否真实引用了记忆和技能树内容

    文章核心:确定性代码不信任概率模型的自觉。
    这里用文件存在性 + 内容特征作为硬证据:
    - 如果回复中出现了 MEMORY.md 里的独特关键词(技能数量、平台名等)
    - 如果回复中出现了 skill_tree.json 里的分类(如 browser/code/data 等)
    则视为真正执行了查记忆和查技能树的动作,而非仅汇报。

    v2.19.0 修复:
    - 记忆标记改从 MEMORY.md 实际内容动态提取(不再硬编码作者私货)
    - 匹配改词边界;"encoded" 不再误命中 "code" 等单短词
    - 文件缺失/无标记时降级放行(记 WARN)——修复新装用户恒 FAIL 死锁
    """
    if not text or not text.strip():
        return False, "无输入文本"

    has_memory_evidence = False
    has_tree_evidence = False
    notes = []

    # 检查 MEMORY.md 内容证据
    if memory_path and os.path.exists(memory_path):
        try:
            with open(memory_path, encoding="utf-8") as f:
                memory_content = f.read()
            markers = extract_memory_markers(memory_content)
            if markers:
                found = [m for m in markers if T.keyword_in(text, m)]
                if found:
                    has_memory_evidence = True
            else:
                # 记忆文件存在但提取不到任何标记 → 无法证伪,降级放行
                has_memory_evidence = True
                notes.append("记忆无可用标记,降级放行")
        except Exception:
            has_memory_evidence = True
            notes.append("记忆读取失败,降级放行")
    else:
        # MEMORY.md 不存在(新装用户)→ 无记忆可查,降级放行而非恒 FAIL
        has_memory_evidence = True
        notes.append("MEMORY.md 不存在,记忆校验降级放行")

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

            # v2.19.0:词边界匹配 + 证据白名单过滤(单短词分类/技能名不算证据)
            has_cat_match = any(
                T.is_meaningful_evidence_name(c) and T.keyword_in(text, c)
                for c in categories)
            has_skill_match = any(
                T.is_meaningful_evidence_name(s) and T.keyword_in(text, s)
                for s in skill_names)

            if has_cat_match or has_skill_match:
                has_tree_evidence = True
        except Exception:
            has_tree_evidence = True
            notes.append("技能树读取失败,降级放行")
    else:
        # skill_tree.json 不存在(未重建技能树的新装用户)→ 降级放行
        has_tree_evidence = True
        notes.append("skill_tree.json 不存在,技能树校验降级放行")

    return has_memory_evidence and has_tree_evidence, (
        f"memory={has_memory_evidence},tree={has_tree_evidence}"
        + (f"({';'.join(notes)})" if notes else "")
    )


def layer_c_task_hard_check(text, tree_path, task):
    """Layer C(v2.11.0):任务相关技能命中硬校验

    关键改动:当任务含"代码/git/部署/编程/开发"等关键词时,
    回复必须引用 skill_tree.json 对应分类下的**实际技能名**(如 git-workflow-and-versioning),
    否则判定 FAIL —— 防止 Agent 用"查了 skills-constitution 就算查了技能"糊弄。

    v2.19.0 修复:
    - 技能名匹配改词边界 —— "encoded" 不再误命中分类名 "code" 打穿校验
    - 废除"分类名出现即算命中"兜底 —— 分类名是常见英文单词,出现在任意
      技术文本里的概率极高,不构成证据;只认实际技能名
    - 技能树缺失时降级放行(记 WARN),不再恒 FAIL 阻断新装用户

    返回 (passed, msg, level)
    """
    if not task or not task.strip():
        return True, "无任务描述,跳过任务相关校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return True, "skill_tree.json 不存在,任务相关校验降级放行", "PASS"

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

        # v2.19.0:只认实际技能名(词边界匹配),分类名不再算证据
        found_skills = [s for s in required_skills if T.keyword_in(text, s)]
        if not found_skills:
            return False, (
                f"任务含'{task}'相关关键词,但输出未引用对应分类的实际技能名"
                f"(必需分类:{required_cats}, 候选技能如:{required_skills[:5]})"
            ), "FAIL"
        return True, (
            f"任务相关技能命中: 分类={required_cats}, 技能={found_skills[:3]}"
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
