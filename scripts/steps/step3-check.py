# -*- coding: utf-8 -*-
"""Step3 校验:匹配技能必用(命中→有调用痕迹;无匹配→已声明)

文章"三明治架构"核心:确定性代码必须验证实际执行,而非信任声明。
本 Step 增加硬校验:检查回复中是否引用了实际调用的技能名。
v2.11.0 增加 Layer C:任务含代码/git/部署关键词时,必须引用对应分类技能名。
v2.12.0 增加 Layer D:引用的技能必须与任务语义相关(零依赖 token 重叠),
防"引用真实存在但与任务无关的技能"蒙混过关。
v2.23.0 增加 Layer F:技能图谱证据校验(借鉴 GitNexus 预计算关系智能)——
引用的技能必须与任务锚点技能图谱连通(同簇/一跳),带图证据溯源。
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
    """Layer B:硬校验 — 检查是否真实引用了技能内容

    v2.19.0:词边界匹配 + 证据白名单过滤 —— 名为 github/code 的单短词技能
    不再被误判为"调用过技能"(推荐链接里出现 github 即命中的漏洞);
    技能树缺失时降级放行。
    """
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    if not tree_path or not os.path.exists(tree_path):
        return True, "skill_tree.json 不存在,技能校验降级放行", "PASS"

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

        # v2.19.0:词边界 + 白名单过滤(单短词技能名不构成证据)
        found_skills = [
            s for s, _ in skills
            if T.is_meaningful_evidence_name(s) and T.keyword_in(text, s)
        ]
        if found_skills:
            return True, f"硬校验通过:引用了技能名={found_skills[:3]}", "PASS"
        return False, "硬校验未通过:未引用实际技能名", "FAIL"
    except Exception as e:
        return True, f"读取技能树失败(降级放行):{e}", "PASS"


def layer_c_task_hard_check(text, tree_path, task):
    """Layer C(v2.11.0):任务相关技能调用硬校验(与 step1/2 共用逻辑)

    v2.19.0:词边界匹配 + 废除分类名兜底(只认实际技能名);树缺失降级放行。
    """
    if not task or not task.strip():
        return True, "无任务描述,跳过任务相关校验", "PASS"
    if not tree_path or not os.path.exists(tree_path):
        return True, "skill_tree.json 不存在,任务相关校验降级放行", "PASS"

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
        # Agent 输出中引用的真实技能(v2.19.0:词边界 + 白名单过滤)
        claimed = [
            (n, d) for n, d in skills.items()
            if T.is_meaningful_evidence_name(n) and T.keyword_in(text, n)
        ]
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


def layer_f_graph_check(text, tree_path, task, graph_path=None):
    """Layer F(v2.23.0):技能图谱证据校验 —— 引用技能须与任务锚点图谱连通

    借鉴 GitNexus「预计算关系智能」:技能间关系已在索引期固化进
    skill_graph.json(chains_to/co_anchor/alternative 边 + 连通分量簇),
    校验时零推理直接用 —— 比 Layer D 的描述重叠打分更硬:
    引用的技能必须是任务锚点技能(必需分类技能)本身,或与其同簇/一跳可达。

    保守设计(防误杀):图缺失/无任务/无引用/引用不在图中(图陈旧) → 放行或跳过。
    只在"引用确实在图中、但与任务锚点零连通"时 FAIL,并附簇归属证据(溯源)。
    """
    if not task or not str(task).strip():
        return True, "无任务描述,跳过图谱校验", "PASS"
    if not graph_path and tree_path:
        graph_path = os.path.join(os.path.dirname(tree_path), "skill_graph.json")
    try:
        from lib import graph as G
    except ImportError:
        return True, "图谱模块不可用,跳过", "SKIP"
    graph = G.load_graph(graph_path) if graph_path else {}
    if not graph:
        return True, "skill_graph.json 不存在,图谱校验降级放行", "PASS"

    try:
        # 任务锚点:必需分类技能(与 Layer C 同源确定性映射)
        pre_hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pre-hook.py")
        spec = importlib.util.spec_from_file_location("pre_hook_mod_step3_f", pre_hook_path)
        ph = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ph)
        required_cats, required_skills = ph.required_skills_for_task(
            ph.load_tree(tree_path), task)
    except Exception as e:
        return True, f"锚点解析失败({e}),放行", "SKIP"
    if not required_skills:
        return True, "任务无必需分类,图谱校验不适用", "PASS"

    # v2.23.0 锚点排名:必需分类可能有噪声(分类器不完美),复用 pre-hook 的
    # SAD 排名(名称加成+分类加成+描述重叠)取任务最相关的必需技能当锚点,
    # 孤立于图谱的锚点自动被排除 —— 锚点越准,连通判断越硬
    try:
        ranked = ph.rank_anchors_for_task(tree_path, task, required_skills, top_k=8)
    except Exception:
        ranked = sorted(required_skills)[:8]

    # 输出中引用的技能名(只认有意义的名字,与 Layer B 同口径)
    nodes = G.node_set(graph)
    try:
        with open(tree_path, encoding="utf-8") as f:
            tree = json.load(f)
        all_names = set()
        for items in tree.get("categories", {}).values():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("name"):
                    all_names.add(item["name"])
                elif isinstance(item, str):
                    all_names.add(item)
    except Exception:
        return True, "技能树读取失败,图谱校验放行", "SKIP"
    claimed = [n for n in all_names
               if T.is_meaningful_evidence_name(n) and T.keyword_in(text, n)]
    if not claimed:
        return True, "未引用具体技能名,图谱校验不适用", "SKIP"

    anchors = [s for s in ranked if s in nodes]
    if not anchors:
        return True, "锚点技能不在图谱中(图可能陈旧),降级放行", "PASS"

    relevant = G.graph_relevant_set(graph, anchors)
    hit = [c for c in claimed if c in relevant]
    if hit:
        return True, f"图谱证据通过: 引用技能 {hit[:3]} 在任务锚点 {anchors[:2]} 图谱上", "PASS"

    in_graph = [c for c in claimed if c in nodes]
    if not in_graph:
        return True, "引用技能不在图谱中,无法证伪,放行", "SKIP"
    c0, a0 = in_graph[0], anchors[0]
    c_cluster = G.cluster_of(graph, c0) or "孤立节点"
    a_cluster = G.cluster_of(graph, a0) or "孤立节点"
    return False, (
        f"引用技能 {in_graph[:3]} 与任务锚点技能 {a0} 图谱零连通"
        f"(引用侧簇={c_cluster}, 锚点侧簇={a_cluster}),疑似乱引用"
    ), "FAIL"


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
                # Layer F(v2.23.0):图谱连通性证据(比描述重叠更硬,带溯源)
                f_ok, f_msg, f_level = layer_f_graph_check(text, tree_path, task)
                if f_level == "FAIL":
                    return False, f"LayerF FAIL: {f_msg}", "FAIL"
                f_note = "" if f_level == "PASS" else f"; 图谱校验跳过({f_msg})"
                return True, f"软+硬校验均通过:{hard_msg}; {task_msg}; {d_msg}{f_note}", "PASS"
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
