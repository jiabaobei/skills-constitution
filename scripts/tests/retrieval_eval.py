#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retrieval_eval — 技能检索质量评测(配对 A/B + 留出集,零网络、零依赖、纯 CPU)

为什么要有这个文件(v2.28.0 新增):
借鉴 zg(zvec-grep) 的评测纪律 —— 检索层的改动不能只靠"我觉得更准了",要拿
配对 A/B 的数字说话:同一个任务集,旧打分与新融合各跑一遍,对比命中率与
上下文体积(注入候选数)。

为什么还要**留出集**(holdout):
只用一套用例反复迭代 = 把用例本身背下来。本版实测:在 dev 集(20 条)上把
hit@4 调到 100% 后,拿 12 条开发期从未用过的留出集一量,只剩 66.7% ——
过拟合被当场抓出。所以本文件默认同时报告两套集:

  dev      = data/retrieval_eval_cases.json       (可据其迭代调参)
  holdout  = data/retrieval_eval_holdout.json     (只用于验收,禁止据其调参)

对照双方:
  legacy = v2.27.6 及以前的单一加权打分(词重叠 + 分类加成 + 技能名加成)
  hybrid = v2.28.0 双路证据召回 + RRF 融合(pre-hook.hybrid_retrieve_skills)

指标:
  hit@1 / hit@4     —— 期望技能是否落在候选前 1 / 前 4 位
  平均候选数        —— 上下文体积的代理指标(越少越省 token,前提是命中率不掉)
  平均 Top1 注入字符 —— 只取首条候选渲染后的字符数

用法:
  python scripts/tests/retrieval_eval.py            # dev + holdout 对照报告
  python scripts/tests/retrieval_eval.py --holdout   # 只看留出集(验收用)
  python scripts/tests/retrieval_eval.py --json      # 机器可读(供 run_tests 门禁)
  python scripts/tests/retrieval_eval.py --strict    # hybrid 任一套 hit@4 低于 legacy 则 exit 1
  python scripts/tests/retrieval_eval.py --gate      # 加绝对下限门禁(CI 用,见 GATE)
  python scripts/tests/retrieval_eval.py -v          # 逐条打印候选
  python scripts/tests/retrieval_eval.py --cases X.json   # 指定用例文件

返回码: 0=正常(或门禁通过), 1=--strict/--gate 检出检索质量退化
"""
import argparse
import importlib.util
import json
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
TREE_PATH = os.path.join(ROOT_DIR, "skill_tree.json")
CASES_PATH = os.path.join(ROOT_DIR, "data", "retrieval_eval_cases.json")
HOLDOUT_PATH = os.path.join(ROOT_DIR, "data", "retrieval_eval_holdout.json")

# --gate 的绝对下限:比当前实测值低一档留余量,用于拦住"以后再改检索时悄悄掉档"。
#   当前实测 dev 100% / holdout 100%(hit@4),dev 50% / holdout 66.7%(hit@1)。
GATE = {"dev": {"hit@4": 0.85, "hit@1": 0.35},
        "holdout": {"hit@4": 0.75, "hit@1": 0.25}}

sys.path.insert(0, SCRIPTS_DIR)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ph = load_module("ph_eval", os.path.join(SCRIPTS_DIR, "pre-hook.py"))


def legacy_retrieve(skills, task, top_k=4, min_score=0.08,
                    category_boost=0.25, name_boost=0.15):
    """v2.27.6 的原始打分(逐行复刻,用作 A/B 对照的基线)。

    刻意保持"老代码"的写法,不重构 —— 基线一旦被改动就不再是基线。
    """
    if not task or not skills:
        return []
    has_install_intent = any(k in ph.expand_task_text(task).lower()
                             for k in ["安装", "install", "配置", "configure"])
    EXCLUDED = set() if has_install_intent else {"skills-constitution", "constitution-check"}
    required_cats = set(ph.required_categories_for_task(task))
    expanded = ph.expand_task_text(task)
    scored = []
    for s in skills:
        if s.get("name") in EXCLUDED:
            continue
        hay = "%s %s" % (s.get("name", ""), s.get("description", ""))
        score = ph.overlap_score(expanded, hay)
        if required_cats and (set(s.get("categories", [])) & required_cats):
            score += category_boost
        if s.get("name") and ph.overlap_score(expanded, s["name"]) > 0:
            score += name_boost
        if score >= min_score:
            scored.append((round(score, 3), s))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return scored[:top_k]


def render_chars(entry):
    """一条候选在注入块里的近似渲染字符数(与 build_injection 同构)。"""
    _, s = entry
    desc = (s.get("description") or "")[:40]
    cats = "/".join(s.get("categories", [])[:3])
    return len(f"- `{s['name']}` ({cats}, 相关度 1.0): {desc}")


def run(which, skills, cases, verbose=False):
    hit1 = hit4 = n = 0
    chars = 0
    rows = []
    for case in cases:
        task, expect = case["task"], set(case.get("expect") or [])
        res = (ph.hybrid_retrieve_skills(skills, task) if which == "hybrid"
               else legacy_retrieve(skills, task))
        names = [s.get("name") for _, s in res]
        ok1 = bool(names) and names[0] in expect
        ok4 = bool(expect & set(names))
        hit1 += ok1
        hit4 += ok4
        n += len(res)
        chars += render_chars(res[0]) if res else 0
        rows.append((task, names, ok4, ok1, sorted(expect)))
        if verbose:
            print("  %s%s %s\n      top: %s"
                  % ("OK  " if ok4 else "MISS", " H1" if ok1 else "   ", task, names))
    total = max(1, len(cases))
    return {
        "cases": len(cases),
        "hit@1": hit1 / total, "hit@4": hit4 / total,
        "avg_candidates": n / total, "avg_top1_chars": chars / total,
        "rows": rows,
    }


def load_cases(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [c for c in data.get("cases", []) if c.get("task")]


def report(label, legacy, hybrid, verbose=False):
    print("【%s】%d 条任务，技能池 %d 个" % (label, hybrid["cases"], len(SKILLS)))
    print("%-8s %8s %8s %14s %16s"
          % ("通道", "hit@1", "hit@4", "平均候选数", "平均Top1字符"))
    for name, m in (("legacy", legacy), ("hybrid", hybrid)):
        print("%-8s %7.1f%% %7.1f%% %14.2f %16.1f"
              % (name, m["hit@1"] * 100, m["hit@4"] * 100,
                 m["avg_candidates"], m["avg_top1_chars"]))
    print("差值      hit@1 %+.1fpt   hit@4 %+.1fpt"
          % ((hybrid["hit@1"] - legacy["hit@1"]) * 100,
             (hybrid["hit@4"] - legacy["hit@4"]) * 100))
    miss = [r[0] for r in hybrid["rows"] if not r[2]]
    if miss:
        print("hybrid 未命中: %d 条 —— %s" % (len(miss), "; ".join(miss[:5])))
    if verbose:
        for task, names, ok4, ok1, expect in legacy["rows"]:
            if not ok4:
                print("  [legacy MISS] %s\n      top: %s\n      expect: %s"
                      % (task, names, expect))
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--strict", action="store_true",
                    help="hybrid hit@4 低于同集 legacy 则 exit 1")
    ap.add_argument("--gate", action="store_true",
                    help="叠加绝对下限门禁(CI 用)")
    ap.add_argument("--holdout", action="store_true", help="只跑留出集(验收用)")
    ap.add_argument("--cases", help="指定用例 JSON(替代 dev 集)")
    ap.add_argument("-v", "--verbose", action="store_true", help="逐条打印候选/漏检")
    args = ap.parse_args()

    global SKILLS
    if not os.path.exists(TREE_PATH):
        print("找不到 skill_tree.json: %s\n先跑 scripts/build_skill_tree.py" % TREE_PATH)
        return 1
    SKILLS = ph.load_tree_full(TREE_PATH)

    sets = []
    if args.cases:
        cases = load_cases(args.cases)
        if not cases:
            print("用例为空或不存在: %s" % args.cases)
            return 1
        sets.append((os.path.basename(args.cases), cases))
    elif args.holdout:
        cases = load_cases(HOLDOUT_PATH)
        if not cases:
            print("找不到留出集: %s" % HOLDOUT_PATH)
            return 1
        sets.append(("留出集 holdout", cases))
    else:
        sets.append(("开发集 dev", load_cases(CASES_PATH)))
        ho = load_cases(HOLDOUT_PATH)
        if ho:
            sets.append(("留出集 holdout", ho))

    out, verdicts, exit_code = {}, [], 0
    for label, cases in sets:
        if not cases:
            continue
        legacy = run("legacy", SKILLS, cases, args.verbose)
        hybrid = run("hybrid", SKILLS, cases, args.verbose)
        key = "holdout" if "holdout" in label else "dev"
        out[key] = {
            "label": label, "cases": hybrid["cases"],
            "legacy": {k: v for k, v in legacy.items() if k != "rows"},
            "hybrid": {k: v for k, v in hybrid.items() if k != "rows"},
        }
        if not args.json:
            report(label, legacy, hybrid, args.verbose)

        if args.strict and hybrid["hit@4"] < legacy["hit@4"]:
            verdicts.append("%s: 融合 hit@4(%.1f%%) 低于旧基线(%.1f%%) → 退化"
                            % (label, hybrid["hit@4"] * 100, legacy["hit@4"] * 100))
            exit_code = 1
        floor = GATE.get(key, {})
        for metric, low in floor.items():
            if hybrid[metric] < low:
                verdicts.append("%s: hybrid %s = %.1f%% 低于门禁下限 %.0f%%"
                                % (label, metric, hybrid[metric] * 100, low * 100))
                exit_code = 1

    if args.json:
        payload = {"sets": out}
        if verdicts:
            payload["verdicts"] = verdicts
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif verdicts:
        print("门禁未通过:")
        for v in verdicts:
            print("  - %s" % v)
    elif args.strict or args.gate:
        print("门禁通过: 融合检索 hit@4 不低于旧基线,且在绝对下限之上。")

    return exit_code if (args.strict or args.gate) else 0


if __name__ == "__main__":
    sys.exit(main())
