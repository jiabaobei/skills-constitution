#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pre-hook —— 任务开始前强制注入记忆 + 技能树上下文

文章"三明治架构"核心: 不要依赖 Agent 自觉去查记忆/技能树，
而是**在任务开始前由代码强制读取并注入**，让 Agent 一睁眼就"被迫"拥有上下文。

本脚本做两件事:
1. 生成注入块: 读取 MEMORY.md + skill_tree.json，按任务类型过滤出相关技能，
   产出可直接粘贴进 System Prompt / 任务开头的 Markdown 块
2. 校验注入痕迹: 检查某个文本(如 Agent 的开场汇报)是否已包含注入块元素，
   用于宿主 hook 在"开始跑"之前拦截

用法:
  python pre-hook.py --task "推送github"             # 生成注入块(按任务过滤技能树)
  python pre-hook.py --task "写文章" --output inj.md # 输出到文件
  python pre-hook.py --task "爬虫" --json            # JSON 输出(机器可读)
  python pre-hook.py --check --input agent_opening.txt  # 校验开场是否已注入(宿主hook用)
  python pre-hook.py --check --input agent_opening.txt --strict  # 校验失败 exit 1

返回码:
  --check 模式: 0=注入合规, 1=缺注入(宿主 hook 应阻断任务)
"""
import argparse
import json
import os
import re
import sys

DEFAULT_MEMORY = os.path.expanduser("~/.workbuddy/MEMORY.md")
DEFAULT_TREE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skill_tree.json"
)

# 任务类型 → 技能树分类关键词映射（用于过滤注入哪些技能）
TASK_CATEGORY_MAP = {
    "编码/开发": ["code", "coding", "编程", "代码", "开发"],
    "网页/前端": ["browser", "web", "frontend", "网页", "前端"],
    "文档/办公": ["doc", "document", "word", "excel", "ppt", "文档"],
    "数据/分析": ["data", "analysis", "数据", "分析"],
    "文件操作": ["file", "文件"],
    "邮件": ["email", "邮件"],
    "图像/设计": ["image", "design", "图像", "设计"],
    "金融/投资": ["finance", "stock", "金融", "股票"],
    "通用": ["general", "通用"],
}

# 零号条款：简单任务关键词（命中任一 → 判定简单，走通道A，不拦截）
SIMPLE_TASK_MARKERS = [
    "翻译", "润色", "改写", "解释", "解释一下", "概念", "是什么意思",
    "知识问答", "科普", "闲聊", "你好", "谢谢", "再见", "打招呼",
    "简单说明", "一句话", "概括", "总结一下这篇文章",
    "translate", "paraphrase", "explain", "meaning", "greeting",
    "thank", "hi", "hello", "what is", "what's",
]

# 零号条款：专业任务关键词（命中任一 → 判定专业，走通道B，强制拦截）
PROFESSIONAL_TASK_MARKERS = [
    "编码", "代码", "编程", "开发", "写一个", "实现", "部署", "推送",
    "文件", "脚本", "爬虫", "抓取", "API", "接口", "数据库", "查询",
    "分析", "数据处理", "生成", "创建", "修改", "编辑", "删除",
    "git", "github", "push", "commit", "deploy", "运行", "测试",
    "安装", "配置", "启动", "打包", "编译", "调优", "排错", "修复",
    "网页", "网站", "前端", "后端", "服务器", "docker", "npm", "python",
    "excel", "word", "pdf", "ppt", "报表", "图表", "可视化",
    "金融", "股票", "行情", "基金", "邮件", "发送邮件",
]


def classify_task(text):
    """零号条款任务分类器（确定性代码，不依赖 Agent 自觉）

    返回: "simple" | "professional" | "ambiguous"
    - simple: 命中简单关键词 → 通道A（跳过门禁，直接通用能力）
    - professional: 命中专业关键词 → 通道B（强制 pre-hook + 五步校验）
    - ambiguous: 无命中 → 宁可不放过，按专业处理（宪法:模糊任务 ✅ 查一下）
    """
    if not text:
        return "ambiguous"
    text_lower = text.lower()
    for marker in SIMPLE_TASK_MARKERS:
        if marker.lower() in text_lower:
            return "simple"
    for marker in PROFESSIONAL_TASK_MARKERS:
        if marker.lower() in text_lower:
            return "professional"
    return "ambiguous"


def load_memory(memory_path=DEFAULT_MEMORY):
    """读取 MEMORY.md，返回文本"""
    if not os.path.exists(memory_path):
        return ""
    with open(memory_path, encoding="utf-8") as f:
        return f.read()


def load_tree(tree_path=DEFAULT_TREE):
    """读取 skill_tree.json，返回 {分类: [技能...] }"""
    if not os.path.exists(tree_path):
        return {}
    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)
    categories = tree.get("categories", {})
    result = {}
    for cat, items in categories.items():
        names = []
        for item in items:
            if isinstance(item, dict):
                names.append(item.get("name", ""))
            elif isinstance(item, str):
                names.append(item)
        result[cat] = [n for n in names if n]
    return result


def filter_tree_by_task(tree, task):
    """按任务关键词过滤技能树分类，返回相关分类名列表"""
    if not task:
        return list(tree.keys())
    task_lower = task.lower()
    matched = []
    for cat, keywords in TASK_CATEGORY_MAP.items():
        for kw in keywords:
            if kw.lower() in task_lower:
                # 找到该分类在树中对应的 key（模糊匹配分类名）
                for tree_cat in tree.keys():
                    if cat.lower() in tree_cat.lower() or tree_cat.lower() in cat.lower():
                        matched.append(tree_cat)
                        break
                break
    # 去重，保留顺序
    seen = set()
    result = []
    for c in matched:
        if c not in seen:
            seen.add(c)
            result.append(c)
    if not result:
        return list(tree.keys())[:5]  # 未匹配 → 取前5个分类兜底
    return result


def build_injection(memory_text, tree, matched_cats, task):
    """生成注入块 Markdown"""
    lines = []
    lines.append("## ⚡ 宪法 Pre-hook 注入（任务开始前强制注入，禁止跳过）")
    lines.append("")
    lines.append(f"> 任务: {task or '(未指定)'} — 以下内容由代码强制注入，Agent 无需自行检索。")
    lines.append("")

    # 记忆层注入
    lines.append("### 📜 记忆层（MEMORY.md 关键规则，必须遵循）")
    if memory_text:
        # 提取关键部分：铁律、宪法、GitHub 仓库等
        key_sections = []
        for marker in ["## ⚠️ 铁律", "## ⚠️ 铁律（宪法级）", "## skills-constitution",
                       "## 用户的 GitHub 仓库", "## 已装技能记录"]:
            idx = memory_text.find(marker)
            if idx >= 0:
                end = memory_text.find("\n## ", idx + 5)
                key_sections.append(memory_text[idx: end if end > 0 else None].strip()[:600])
        if key_sections:
            for section in key_sections[:4]:
                lines.append("```")
                lines.append(section[:500])
                lines.append("```")
        else:
            lines.append("```")
            lines.append(memory_text[:800])
            lines.append("```")
    else:
        lines.append("_（MEMORY.md 未找到）_")
    lines.append("")

    # 技能树注入
    lines.append("### 🗂️ 技能树（相关分类，Agent 应先查此处再动手）")
    for cat in matched_cats:
        skills = tree.get(cat, [])
        if skills:
            lines.append(f"- **{cat}** ({len(skills)}): {', '.join(skills[:12])}{'...' if len(skills) > 12 else ''}")
    lines.append("")
    lines.append("**执行要求：**")
    lines.append("1. 第一句话必须输出【宪法三查】汇报（记忆✅ / 技能树✅ / 匹配✅或无匹配）")
    lines.append("2. 命中技能 → 必须调用；无命中 → 声明'技能树无匹配'再走通用能力")
    lines.append("3. 任务完成后输出【本次相关技能推荐】")
    lines.append("")
    return "\n".join(lines)


def check_injection(text, memory_path=DEFAULT_MEMORY, tree_path=DEFAULT_TREE):
    """校验文本是否包含注入块元素（宿主 hook 用）"""
    if not text:
        return False, "无输入文本"
    # 必须包含三查汇报
    if not re.search(r"【宪法三查】|宪法三查|三查", text):
        return False, "缺【宪法三查】汇报"
    # 必须包含记忆标记
    memory_text = load_memory(memory_path)
    if memory_text:
        memory_markers = ["铁律", "MEMORY", "技能", "宪法", "GitHub", "仓库"]
        found_mem = [m for m in memory_markers if m in text]
        if len(found_mem) < 2:
            return False, f"记忆引用不足(仅命中:{found_mem})"
    # 必须包含技能树标记
    if os.path.exists(tree_path):
        tree = load_tree(tree_path)
        all_cats = list(tree.keys())
        found_cat = [c for c in all_cats[:10] if c.lower() in text.lower()]
        if not found_cat:
            return False, "缺技能树分类引用"
    return True, "注入合规(三查+记忆+技能树均已覆盖)"


def main():
    ap = argparse.ArgumentParser(description="宪法 Pre-hook: 任务前强制注入记忆+技能树")
    ap.add_argument("--task", help="任务描述(用于过滤技能树分类)")
    ap.add_argument("--memory", default=DEFAULT_MEMORY, help=f"MEMORY.md路径(默认:{DEFAULT_MEMORY})")
    ap.add_argument("--tree", default=DEFAULT_TREE, help=f"skill_tree.json路径(默认:{DEFAULT_TREE})")
    ap.add_argument("--output", help="注入块输出到文件(缺省打印到 stdout)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--check", action="store_true", help="校验模式:检查文本是否已注入")
    ap.add_argument("--input", help="校验模式:待检查的文本文件")
    ap.add_argument("--strict", action="store_true", help="校验失败 exit 1(宿主 hook 阻断)")
    ap.add_argument("--classify", action="store_true",
                    help="任务分类模式:按零号条款判定简单/专业/模糊(不注入不校验)")
    a = ap.parse_args()

    # ---- 任务分类模式（零号条款双通道分流） ----
    if a.classify:
        task_text = ""
        if a.input:
            with open(a.input, encoding="utf-8") as f:
                task_text = f.read()
        else:
            task_text = sys.stdin.read()
        task_type = classify_task(task_text)
        if a.json:
            print(json.dumps({
                "task_type": task_type,
                "channel": "A-简单(通用能力)" if task_type == "simple"
                           else "B-专业(强制门禁)" if task_type == "professional"
                           else "B-模糊(按专业处理)",
                "rule": "零号条款:简单问答跳过;专业任务必查;模糊任务查一下(宁可不放过)"
            }, ensure_ascii=False, indent=2))
        else:
            if task_type == "simple":
                print("[通道A] 简单任务 → 跳过门禁，直接通用能力（零号条款豁免）")
            elif task_type == "professional":
                print("[通道B] 专业任务 → 强制 pre-hook 注入 + 五步门禁校验")
            else:
                print("[通道B] 模糊任务 → 宁可不放过，按专业任务强制门禁")
        return 0

    # ---- 校验模式 ----
    if a.check:
        text = ""
        if a.input:
            with open(a.input, encoding="utf-8") as f:
                text = f.read()
        ok, msg = check_injection(text, a.memory, a.tree)
        if a.json:
            print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"[{'PASS' if ok else 'FAIL'}] {msg}")
        if a.strict and not ok:
            return 1
        return 0

    # ---- 注入模式 ----
    memory_text = load_memory(a.memory)
    tree = load_tree(a.tree)
    matched_cats = filter_tree_by_task(tree, a.task)
    injection = build_injection(memory_text, tree, matched_cats, a.task)

    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(injection)
        print(f"✓ 注入块已写入: {a.output}")
        print(f"  记忆: {len(memory_text)} 字符 | 技能树分类: {len(tree)} | 注入分类: {len(matched_cats)}")
        return 0

    if a.json:
        print(json.dumps({
            "task": a.task,
            "memory_len": len(memory_text),
            "tree_categories": len(tree),
            "injected_categories": matched_cats,
            "injection": injection,
        }, ensure_ascii=False, indent=2))
    else:
        print(injection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
