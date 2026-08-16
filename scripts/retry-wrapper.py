# -*- coding: utf-8 -*-
"""retry-wrapper —— 带重试循环的宪法门禁校验包装器

文章"三明治架构"核心: Post-hook 层必须实现自动重试。
当 Agent 输出不合规时，注入错误提示并重新执行，最多 max_retries 次。
超限则转人工处理。

用法:
  python retry-wrapper.py --input output.txt           # 单轮校验
  python retry-wrapper.py --input output.txt --max-retries 3  # 指定最大重试次数
  python retry-wrapper.py --input output.txt --strict  # 严格模式(FAIL阻断)
  python retry-wrapper.py --help                        # 帮助信息
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


MAX_RETRIES_DEFAULT = 3
MAX_RETRIES_HARD_LIMIT = 5  # 硬限制，防止无限循环


def run_checks(text, memory_path, tree_path, step_filter=None):
    """执行一轮完整校验，返回结果列表和总通过状态"""
    results = []
    all_passed = True

    for name, desc in STEPS:
        if step_filter and int(step_filter) != int(name[-1]):
            continue

        check_fn = load_check(name)
        # 根据 step 名称传递额外参数
        if name == "step1":
            passed, msg, level = check_fn(text, memory_path, tree_path)
        elif name in ("step2", "step3"):
            passed, msg, level = check_fn(text, tree_path)
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
    """生成错误报告文本，用于注入重试"""
    failures = [r for r in results if not r["passed"]]
    if not failures:
        return ""

    lines = ["\n\n【宪法门禁校验失败，请修正后重新输出】"]
    for r in failures:
        lines.append(f"- {r['step']}: {r['message']}")
    lines.append("\n请按宪法要求重新执行完整流程，确保：")
    lines.append("1. 汇报「宪法三查」时引用 MEMORY.md 和 skill_tree.json 的实际内容")
    lines.append("2. 声明命中技能时，必须真实调用该技能")
    lines.append("3. 任务完成后，推荐相关 GitHub 技能（含链接和 star 数）")
    return "\n".join(lines)


def run_with_retry(text, memory_path, tree_path, max_retries=MAX_RETRIES_DEFAULT,
                   strict=False, state_path=None):
    """带重试循环的主函数"""
    # 硬限制
    max_retries = min(max_retries, MAX_RETRIES_HARD_LIMIT)

    last_results = None
    retry_count = 0

    for attempt in range(max_retries + 1):
        # 执行校验
        results, all_passed = run_checks(text, memory_path, tree_path)
        last_results = results

        # 保存状态
        for r in results:
            S.set_step(r["step"], r["passed"], r["message"], r["level"], state_path)

        # 全部通过 → 结束
        if all_passed:
            return {"success": True, "attempts": attempt + 1, "results": results}

        # 未达到重试上限 → 生成错误报告并追加到文本
        if attempt < max_retries:
            error_report = generate_error_report(results)
            text += error_report
            retry_count += 1
            print(f"[RETRY {retry_count}/{max_retries}] 已注入错误提示，继续重试...",
                  file=sys.stderr)

    # 超限 → 转人工
    return {
        "success": False,
        "attempts": max_retries + 1,
        "results": last_results,
        "need_human": True,
        "error": f"Agent连续{max_retries + 1}次未通过宪法门禁，需人工介入"
    }


def main():
    ap = argparse.ArgumentParser(description="Skills 宪法门禁校验（带重试循环）")
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--memory", default=None,
                    help=f"MEMORY.md路径(默认:{os.path.expanduser('~/.workbuddy/MEMORY.md')})")
    ap.add_argument("--tree", default=None,
                    help="skill_tree.json路径(默认:scripts/../skill_tree.json)")
    ap.add_argument("--max-retries", type=int, default=MAX_RETRIES_DEFAULT,
                    help=f"最大重试次数(默认:{MAX_RETRIES_DEFAULT},硬上限:{MAX_RETRIES_HARD_LIMIT})")
    ap.add_argument("--strict", action="store_true", help="严格模式:FAIL即阻断")
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

    # 执行带重试的校验
    result = run_with_retry(
        text,
        a.memory,
        a.tree,
        max_retries=a.max_retries,
        strict=a.strict,
        state_path=a.state
    )

    # 输出结果
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"宪法门禁校验结果 (尝试 {result['attempts']} 次)")
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
            print("❌ 宪法门禁未通过，已达到最大重试次数")
            print(f"{'='*60}")
            if result.get("need_human"):
                print("⚠️  建议转人工处理")
            return 1 if a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
