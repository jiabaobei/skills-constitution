#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests — Skills Constitution 零依赖回归测试(v2.12.0 新增)

把 CHANGELOG 里各版本的"验证测试"表格固化为可重复执行的代码,
不再靠手工跑一遍 —— 用项目自己的理念 dogfooding:
"不靠自觉,靠确定性代码"。

覆盖:
  1. 同义词扩展(口语任务命中必需分类 / 任务分类器)
  2. 词边界匹配修复子串误杀(code≠encode, search≠research)
  3. SAD 宽松语义检索(top-K 候选非空且按相关度排序)
  4. Layer D 语义相关性校验(无关技能 FAIL / 相关技能 PASS)
  5. 多技能编排兼容性检查(不兼容链 FAIL / 兼容链 PASS)
  6. 可选语义索引缺依赖行为(exit 2 + 安装指引;已装依赖则跳过)

用法: python scripts/tests/run_tests.py
返回码: 0=全部通过, 1=有失败
"""
import importlib.util
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
TREE_PATH = os.path.join(ROOT_DIR, "skill_tree.json")
REGISTRY_PATH = os.path.join(ROOT_DIR, "registry.json")

sys.path.insert(0, SCRIPTS_DIR)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ph = load_module("pre_hook_under_test", os.path.join(SCRIPTS_DIR, "pre-hook.py"))
bst = load_module("build_skill_tree_under_test", os.path.join(SCRIPTS_DIR, "build_skill_tree.py"))
step3 = load_module("step3_under_test", os.path.join(SCRIPTS_DIR, "steps", "step3-check.py"))
step4 = load_module("step4_under_test", os.path.join(SCRIPTS_DIR, "steps", "step4-check.py"))
from lib import text as T  # noqa: E402

RESULTS = []


def check(case, actual, expect=True):
    ok = (actual == expect) if isinstance(expect, bool) else bool(actual)
    RESULTS.append((case, ok, actual))
    print(f"[{'PASS' if ok else 'FAIL'}] {case}" + ("" if ok else f"  (actual={actual!r})"))
    return ok


def main():
    print("=" * 60)
    print("Skills Constitution 回归测试 (v2.12.0)")
    print("=" * 60)

    # ---- 1. 同义词扩展:口语任务命中必需分类 ----
    print("\n[1] 同义词扩展(TASK_SYNONYM_MAP)")
    check("口语'我要把代码传上去'命中 code 必需分类",
          "code" in ph.required_categories_for_task("我要把代码传上去"))
    check("口语'帮我抓一下网页数据'命中 browser+data",
          set(ph.required_categories_for_task("帮我抓一下网页数据")) >= {"browser", "data"})
    check("口语任务分类器判 professional",
          ph.classify_task("我要把代码传上去") == "professional")
    check("简单任务仍判 simple(不受扩展影响)",
          ph.classify_task("帮我翻译这段话") == "simple")

    # ---- 2. 词边界匹配修复子串误杀 ----
    print("\n[2] 词边界匹配(code≠encode, search≠research)")
    check("keyword_in: 'encode video' 不命中 'code'",
          T.keyword_in("encode video files", "code") is False)
    check("keyword_in: 'research tool' 不命中 'search'",
          T.keyword_in("deep research tool", "search") is False)
    check("keyword_in: 'code review' 命中 'code'",
          T.keyword_in("code review tool", "code") is True)
    check("keyword_in: 中文子串保持命中",
          T.keyword_in("抓取网页数据", "抓取") is True)
    check("classify_skill: encoder 技能不误入 code 分类",
          "code" not in bst.classify_skill("video-encoder", "encode video files tool"))
    check("classify_skill: 代码审查技能正入 code 分类",
          "code" in bst.classify_skill("code-reviewer", "代码审查工具 code review"))

    # ---- 3. SAD 宽松语义检索 ----
    print("\n[3] SAD 宽松语义检索(loose_retrieve_skills)")
    skills = ph.load_tree_full(TREE_PATH)
    check("load_tree_full 读到技能", len(skills) > 0)
    results = ph.loose_retrieve_skills(skills, "推送github代码")
    check("SAD 检索返回非空候选", len(results) > 0)
    check("SAD 候选按相关度降序",
          all(results[i][0] >= results[i + 1][0] for i in range(len(results) - 1)))
    if results:
        top_names = [s["name"] for _, s in results]
        print(f"       top 候选: {top_names}")
        check("SAD top-K 含 git 相关技能",
              any("git" in n for n in top_names))
    check("SAD 空任务返回空", ph.loose_retrieve_skills(skills, "") == [])

    # ---- 4. Layer D 语义相关性校验 ----
    print("\n[4] Layer D 语义相关性校验(step3)")
    ok4a, msg4a, lv4a = step3.layer_d_relevance_check(
        "已调用 agnes-video-generator 完成任务", TREE_PATH, "推送github代码")
    check("引用与任务无关的真实技能 → FAIL", lv4a == "FAIL")
    if lv4a != "FAIL":
        print(f"       (got {lv4a}: {msg4a})")
    ok4b, msg4b, lv4b = step3.layer_d_relevance_check(
        "已调用 git-workflow-and-versioning 完成推送", TREE_PATH, "推送github代码")
    check("引用相关技能 → PASS", lv4b == "PASS")
    if lv4b != "PASS":
        print(f"       (got {lv4b}: {msg4b})")
    ok4c, _, lv4c = step3.layer_d_relevance_check(
        "随便一段输出", TREE_PATH, "")
    check("无任务描述 → 跳过(不误伤)", lv4c in ("PASS", "SKIP"))

    # ---- 5. 多技能编排兼容性检查 ----
    print("\n[5] 多技能编排兼容性(step4 + registry schema)")
    chain = step4.extract_skill_chain("先 `docx` → `git-workflow-and-versioning` 两步走")
    check("技能链提取", chain == ["docx", "git-workflow-and-versioning"])
    _, _, lv5a = step4.check_chain_compatibility(
        ["docx", "git-workflow-and-versioning"], REGISTRY_PATH)
    check("不兼容链(docx→git) → FAIL", lv5a == "FAIL")
    _, _, lv5b = step4.check_chain_compatibility(
        ["spec-driven-development", "test-driven-development"], REGISTRY_PATH)
    check("兼容链(spec→tdd) → PASS", lv5b == "PASS")
    _, _, lv5c = step4.check_chain_compatibility(
        ["docx", "不存在的技能xyz"], REGISTRY_PATH)
    check("无 schema 覆盖 → 跳过不误杀", lv5c in ("PASS", "SKIP"))

    # ---- 6. 可选语义索引缺依赖行为 ----
    print("\n[6] 可选语义索引(semantic_index.py)")
    try:
        import sentence_transformers  # noqa: F401
        has_st = True
    except ImportError:
        has_st = False
    if has_st:
        print("[SKIP] 本环境已装 sentence-transformers,缺依赖用例不适用")
    else:
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "semantic_index.py"), "query", "测试"],
            capture_output=True, text=True)
        check("缺依赖 exit 2", r.returncode == 2)
        check("缺依赖提示安装指引", "pip install" in (r.stderr or ""))

    # ---- 汇总 ----
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"结果: {passed}/{total} 通过")
    print("=" * 60)
    failed = [c for c, ok, _ in RESULTS if not ok]
    if failed:
        print("失败用例:")
        for c in failed:
            print(f"  - {c}")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
