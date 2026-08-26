# -*- coding: utf-8 -*-
"""retry-wrapper —— 宪法门禁校验 + 结构化错误报告（Post-hook 层）

v2.19.0 语义修正（重要）：
  旧版把"错误报告"拼进被校验文本后再跑同一套关键词校验——而错误报告本身
  自带校验关键词（宪法三查/skill_tree.json/GitHub/star），等于系统把自己的
  提示词喂给了自己的检查器，"重试"结果与 Agent 是否改正无关。
  新版改为单次真实校验：
    - 全部通过 → exit 0（或 --strict 下同样 0）
    - 未通过   → 生成结构化错误报告（注入给宿主/Agent 修正用），
                 "重试"由宿主在收到报告后重新执行 Agent 完成，
                 包装器自身不再伪造重试循环
  同时修复：旧版 run_checks 不传 task，导致 retry 链路里 Layer C 永远被跳过。

用法:
  python retry-wrapper.py --input output.txt                     # 单次全量校验
  python retry-wrapper.py --input output.txt --task "推送github代码"  # 带任务相关校验
  python retry-wrapper.py --input output.txt --strict            # 未通过即 exit 1
  python retry-wrapper.py --input output.txt --json              # JSON 输出
"""
import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import state as S
from lib import text as T

STEPS = [
    ("step1", "三查汇报"),
    ("step2", "技能树已读/无匹配声明"),
    ("step3", "匹配技能调用"),
    ("step4", "交付自检"),
    ("step5", "推荐板块(GitHub 高星)"),
]


def load_check(name):
    """动态加载步骤校验模块"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "steps", f"{name}-check.py")
    spec = importlib.util.spec_from_file_location(f"step_mod_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check


def run_checks(text, memory_path, tree_path, task=None, step_filter=None):
    """执行一轮完整校验，返回结果列表和总通过状态

    v2.19.0:step1/2/3 传入 task（Layer C 任务相关校验不再被静默跳过）。
    """
    results = []
    all_passed = True

    for name, desc in STEPS:
        if step_filter and int(step_filter) != int(name[-1]):
            continue

        check_fn = load_check(name)
        # 根据 step 名称传递额外参数
        if name == "step1":
            passed, msg, level = check_fn(text, memory_path, tree_path, task)
        elif name in ("step2", "step3"):
            passed, msg, level = check_fn(text, tree_path, task)
        else:
            passed, msg, level = check_fn(text)

        results.append({
            "step": name,
            "desc": desc,
            "level": level,
            "message": msg,
            "passed": passed,
        })

        if not passed:
            all_passed = False

    return results, all_passed


def generate_error_report(results):
    """生成结构化错误报告（宿主收到后应驱动 Agent 修正并重新提交）

    v2.19.0:报告只面向宿主/Agent 阅读，不再被拼回输入二次校验。
    """
    failures = [r for r in results if not r["passed"]]
    if not failures:
        return ""

    lines = ["【宪法门禁校验失败，请修正后重新输出】"]
    for r in failures:
        lines.append(f"- {r['step']}: {r['message']}")
    lines.append("")
    lines.append("请按宪法要求重新执行完整流程，确保：")
    lines.append("1. 汇报「宪法三查」时引用 MEMORY.md 和 skill_tree.json 的实际内容")
    lines.append("2. 声明命中技能时，必须真实调用该技能")
    lines.append("3. 任务完成后，推荐相关 GitHub 技能（含链接和 star 数）")
    return "\n".join(lines)


def run_once(text, memory_path, tree_path, task=None, state_path=None):
    """v2.19.0:单次真实校验（替代旧版语义无效的"自我重试"循环）"""
    results, all_passed = run_checks(text, memory_path, tree_path, task)

    for r in results:
        S.set_step(r["step"], r["passed"], r["message"], r["level"], state_path)

    if all_passed:
        return {"success": True, "attempts": 1, "results": results}

    return {
        "success": False,
        "attempts": 1,
        "results": results,
        "need_human": False,
        "error_report": generate_error_report(results),
        "error": "宪法门禁未通过,错误报告已生成;请由宿主驱动 Agent 修正后重新提交校验",
    }


def main():
    ap = argparse.ArgumentParser(description="Skills 宪法门禁校验（单次校验+错误报告）")
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--memory", default=None,
                    help=f"MEMORY.md路径(默认:{os.path.expanduser('~/.workbuddy/MEMORY.md')})")
    ap.add_argument("--tree", default=None,
                    help=f"skill_tree.json路径(默认:scripts/../skill_tree.json)")
    ap.add_argument("--task", default=None,
                    help="任务描述(传入后启用 Layer C 任务相关校验;v2.19.0 前此参数缺失导致 Layer C 被跳过)")
    ap.add_argument("--max-retries", type=int, default=3,
                    help="[兼容保留,不再生效] 重试由宿主驱动,包装器只做单次真实校验")
    ap.add_argument("--strict", action="store_true", help="严格模式:未通过即 exit 1")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    a = ap.parse_args()

    # 设置默认路径
    if not a.memory:
        a.memory = os.path.expanduser("~/.workbuddy/MEMORY.md")
    if not a.tree:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        constitution_dir = os.path.dirname(script_dir)
        a.tree = os.path.join(constitution_dir, "skill_tree.json")

    # 读取输入
    text = T.read_input(a.input)
    if not text.strip():
        print("错误:无输入文本,请用 --input <file> 或管道输入", file=sys.stderr)
        return 2

    result = run_once(text, a.memory, a.tree, task=a.task, state_path=a.state)

    # 输出结果
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print("宪法门禁校验结果")
        print(f"{'='*60}")

        for r in result["results"]:
            icon = "✅" if r["passed"] else "❌"
            print(f"{icon} [{r['step']}] {r['desc']}: {r['message']}")

        if result["success"]:
            print(f"\n{'='*60}")
            print("✅ 宪法门禁全部通过!")
            print(f"{'='*60}")
            return 0
        else:
            print(f"\n{'='*60}")
            print("❌ 宪法门禁未通过")
            print(f"{'='*60}")
            if result.get("error_report"):
                print("\n--- 错误报告(注入给 Agent 修正用) ---")
                print(result["error_report"])
            return 1 if a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
