# -*- coding: utf-8 -*-
"""Step3 校验:匹配技能必用(命中→有调用痕迹;无匹配→已声明)

文章"三明治架构"核心:确定性代码必须验证实际执行,而非信任声明。
本 Step 增加硬校验:检查回复中是否引用了实际调用的技能名。
v2.11.0 增加 Layer C:任务含代码/git/部署关键词时,必须引用对应分类技能名。
v2.12.0 增加 Layer D:引用的技能必须与任务语义相关(零依赖 token 重叠),
防"引用真实存在但与任务无关的技能"蒙混过关。
"""
import argparse
import json
import os
import sys
import importlib.util

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


def layer_c_task_hard_check(text, tree_path, task):
    """Layer C(v2.11.0):任务相关技能调用硬校验(与 step1/2 共用逻辑)"""
    if not task or not task.strip():
        return True, "无任务描述,跳过任务相关校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return False, f"skill_tree.json 不存在:{tree_path}", "FAIL"

    try:
        pre_hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-hook.py")
        spec = importlib.util.spec_from_file_location("pre_hook_mod_step3", pre_hook_path)
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


def layer_d_relevance_check(text, tree_path, task):
    """Layer D(v2.12.0):轻量语义相关性校验(零依赖,token 重叠打分)

    防的漏洞:Agent 引用一个**真实存在但与任务无关**的技能名蒙混过关
    (Layer B 只验证"技能名在树中",不验证"技能与任务相关")。
    规则:输出引用的技能中,至少一个与任务文本 overlap_score >= 0.10(保守阈值防误杀)。
    无任务描述/无技能树/未引用技能 → 不适用,放行。
    """
    if not task or not str(task).strip():
        return True, "无任务描述,跳过语义相关性校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return True, "无技能树,跳过语义相关性校验", "SKIP"
    try:
        with open(tree_path, encoding="utf-8") as f:
            tree = json.load(f)
        skills = {}
        for cat, items in tree.get("categories", {}).items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("name"):
                        skills.setdefault(item["name"], item.get("description", ""))
                    elif isinstance(item, str):
                        skills.setdefault(item, "")
        # 任务文本先经同义词扩展(与 pre-hook 同源,防"口语任务"误判零相关)
        expanded_task = task
        try:
            pre_hook_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-hook.py")
            spec = importlib.util.spec_from_file_location("pre_hook_mod_step3_d", pre_hook_path)
            ph = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ph)
            expanded_task = ph.expand_task_text(task)
        except Exception:
            pass
        # Agent 输出中引用的真实技能
        claimed = [(n, d) for n, d in skills.items() if T.has_any(text, n)]
        if not claimed:
            return True, "未引用具体技能名,相关性校验不适用", "SKIP"
        # 相关判定(满足其一即相关):
        #  ① 任务与技能名有较强重叠(≥0.10) —— 技能名是最强标识,
        #     口语长任务(如"我要把代码传上去")也不会因 token 分母膨胀而误杀
        #  ② 任务与技能名+描述整体重叠 ≥0.10
        relevant = [
            n for n, d in claimed
            if T.overlap_score(expanded_task, n) >= 0.10
            or T.overlap_score(expanded_task, f"{n} {d}") >= 0.10
        ]
        if relevant:
            return True, f"语义相关性通过:相关技能={relevant[:3]}", "PASS"
        return False, (
            f"引用了 {len(claimed)} 个技能但均与任务'{task}'语义无关"
            f"(如:{[n for n, _ in claimed][:3]}),疑似乱引用/空头汇报"
        ), "FAIL"
    except Exception as e:
        return True, f"相关性校验异常(放行):{e}", "SKIP"


def check(text, tree_path=None, task=None):
    """主校验函数:两层校验 + v2.11.0 任务相关校验"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验
    no_match_keywords = ["技能树无匹配", "无匹配", "未命中", "无命中", "没有匹配"]
    has_no_match = T.has_any(text, *no_match_keywords)

    hit_keywords = ["命中", "匹配"]
    has_hit = T.has_any(text, *hit_keywords)

    # Layer C 先行:任务含代码/git/部署关键词时必须命中对应技能(v2.11.0)
    task_passed, task_msg, task_level = layer_c_task_hard_check(text, tree_path, task)
    if task_level == "FAIL":
        return False, f"LayerC FAIL: {task_msg}", "FAIL"
    if task_level == "SKIP":
        return False, f"LayerC 异常: {task_msg}", "FAIL"

    if has_no_match:
        return True, f"技能树无匹配,已声明({task_msg})", "PASS"

    if has_hit:
        call_keywords = ["已调用", "已加载", "加载了", "调用", "执行了", "使用", "已按"]
        has_call = T.has_any(text, *call_keywords)
        if has_call:
            # 软校验通过,再检查硬校验
            hard_result, hard_msg, hard_level = layer_b_hard_check(text, tree_path)
            hard_passed = (hard_level == "PASS")
            if hard_passed:
                # Layer D(v2.12.0):引用技能必须与任务语义相关
                d_ok, d_msg, d_level = layer_d_relevance_check(text, tree_path, task)
                if d_level == "FAIL":
                    return False, f"LayerD FAIL: {d_msg}", "FAIL"
                return True, f"软+硬校验均通过:{hard_msg}; {task_msg}; {d_msg}", "PASS"
            return False, f"软校验通过但硬校验未通过。{hard_msg}", "FAIL"
        return False, "声明命中但未见调用痕迹(软校验失败)", "FAIL"

    return False, "未声明命中或无匹配(需二选一)", "FAIL"


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
