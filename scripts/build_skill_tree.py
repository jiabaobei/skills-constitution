#!/usr/bin/env python3
"""
技能树构建器 — 扫描所有 SKILL.md，按 description 分类生成索引
通用适配：支持环境变量 SKILLS_DIR 指定技能目录
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from lib.text import keyword_in
except ImportError:
    def keyword_in(text, kw):  # 兜底:与 lib.text 同逻辑
        t, k = (text or "").lower(), (kw or "").lower()
        if not k:
            return False
        if all(ord(c) < 128 for c in k):
            return re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) is not None
        return k in t


# 分类规则（关键词 → 分支）
CATEGORY_RULES = {
    "meta": ["constitution", "rule", "规范", "元规则", "宪法"],
    "memory": ["memory", "memor", "recall", "remember", "记忆", "持久化"],
    "browser": ["browser", "bsk", "自动化", "网页", "爬虫", "搜索", "playwright", "agent-browser"],
    "code": ["code", "编程", "开发", "review", "git", "commit", "测试", "debug", "python", "javascript"],
    "doc": ["docx", "pdf", "xlsx", "pptx", "文档", "wps", "office", "word", "excel"],
    "image": ["image", "图生", "文生图", "图生图", "生成图片", "ai图片", "ai绘图", "picset", "image-gen", "image-generation", "photoshop"],
    "video": ["video", "视频", "视频生成", "视频制作", "agnes", "video-generator", "video-gen"],
    "finance": ["finance", "金融", "股票", "投资", "研报", "a-share", "wb-finance"],
    "email": ["email", "邮件", "mail", "qq-mail", "agent-mail"],
    "search": ["search", "anysearch", "firecrawl", "研究", "调研"],
    "data": ["data", "分析", "图表", "可视化", "chart", "plot"],
    "file": ["file", "文件", "目录", "整理", "清理", "归档"],
    "automation": ["automation", "自动化", "定时", "工作流"],
}


def classify_skill(skill_name: str, description: str) -> list[str]:
    """根据名称和描述匹配分类

    v2.12.0:英文关键词改用词边界匹配(lib.text.keyword_in),
    修复子串误杀 — "code" 不再命中 "encode"、"search" 不再命中 "research"。
    """
    text = f"{skill_name} {description}".lower()
    matches = []
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword_in(text, kw) for kw in keywords):
            matches.append(category)
    return matches if matches else ["general"]


def parse_frontmatter(content: str) -> dict:
    """解析 SKILL.md 的 frontmatter"""
    if not content.startswith("---"):
        return {}

    match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    fm_text = match.group(1)
    fm = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            fm[key] = value
    return fm


def read_constitution_version() -> str:
    """从仓库根 SKILL.md 的 frontmatter 读取宪法版本号，保持索引与技能版本同源"""
    try:
        root = Path(__file__).resolve().parent.parent
        content = (root / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"^version:\s*(\S+)", content, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


# binaries 下视为"运行时/辅助"的目录（不算独立库/工具）
LIB_EXCLUDE = {"python", "node", "envs", "node_modules", "tmp", "temp", "kroki"}


def scan_binary_libs(binaries_dir: str) -> list[dict]:
    """扫描 ~/.workbuddy/binaries 下带独立 venv 的 Python 库/工具，
    生成"已装库/工具"条目，供技能树查询。binaries 目录不存在时静默跳过（兼容 CI）。"""
    libs = []
    root = Path(binaries_dir)
    if not root.exists():
        return libs
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in LIB_EXCLUDE:
            continue
        venv_py = entry / "venv" / "Scripts" / "python.exe"
        if not venv_py.exists():
            venv_py = entry / ".venv" / "Scripts" / "python.exe"  # 兼容 .venv 命名
        if not venv_py.exists():
            # v2.19.0:补 POSIX venv 路径(旧版只查 Windows, Linux/macOS 永远扫不到,
            # 而 CI 恰好跑在 ubuntu 上)
            venv_py = entry / "venv" / "bin" / "python"
        if not venv_py.exists():
            venv_py = entry / ".venv" / "bin" / "python"
        if not venv_py.exists():
            continue
        description = "已装 Python 库/工具（独立 venv）"
        version = ""
        try:
            import subprocess
            r = subprocess.run(
                [str(venv_py), "-m", "pip", "show", entry.name],
                capture_output=True, text=True, timeout=20,
            )
            for line in r.stdout.splitlines():
                if line.startswith("Summary:"):
                    description = line.split(":", 1)[1].strip()[:200] or description
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
        except Exception:
            pass
        libs.append({
            "name": entry.name,
            "type": "python_lib",
            "description": description,
            "version": version or "unknown",
            "path": str(entry),
        })
    return libs


def build_skill_tree(skills_dir: str, binaries_dir: str = "") -> dict:
    """扫描所有技能，生成树形索引；可选扫描已装 Python 库/工具"""
    tree = {
        "categories": {},
        "total": 0,
        "version": read_constitution_version(),
        "generated_at": datetime.now().isoformat(),
        "skills_dir": skills_dir
    }

    skills_path = Path(skills_dir)
    if not skills_path.exists():
        print(f"警告：技能目录不存在 {skills_dir}", file=sys.stderr)
        return tree

    for skill_name in sorted(skills_path.iterdir()):
        if not skill_name.is_dir():
            continue

        skill_md = skill_name / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            print(f"读取 {skill_name.name} 失败: {e}", file=sys.stderr)
            continue

        # 解析 frontmatter
        fm = parse_frontmatter(content)
        description = fm.get("description", "") or fm.get("description_zh", "")
        version = fm.get("version", "0.0.0")

        # 分类
        categories = classify_skill(skill_name.name, description)

        skill_info = {
            "name": skill_name.name,
            "description": description[:200],  # 截断到 200 字符
            "version": version,
            "categories": categories
        }

        tree["total"] += 1

        # 添加到树
        for cat in categories:
            if cat not in tree["categories"]:
                tree["categories"][cat] = []
            tree["categories"][cat].append(skill_info)

    # 追加已装 Python 库/工具（binaries 扫描）
    if binaries_dir:
        libs = scan_binary_libs(binaries_dir)
        if libs:
            tree["categories"]["libs"] = libs
        tree["libs_count"] = len(libs)
        tree["total_entries"] = tree["total"] + len(libs)

    return tree


def generate_markdown(tree: dict) -> str:
    """生成人类可读的 Markdown 索引"""
    libs_count = tree.get("libs_count", 0)
    lines = [
        "# 技能树索引",
        "",
        f"**生成时间**: {tree['generated_at']}",
        f"**总技能数**: {tree['total']}",
        f"**已装库/工具数**: {libs_count}",
        f"**总条目数**: {tree.get('total_entries', tree['total'])}",
        f"**技能目录**: `{tree['skills_dir']}`",
        "",
        "---",
        "",
        "## 分类概览",
        ""
    ]

    # 分类标题映射
    category_names = {
        "meta": "📜 元规则类",
        "memory": "🧠 记忆管理类",
        "browser": "🌐 网页自动化类",
        "code": "💻 代码开发类",
        "doc": "📄 文档处理类",
        "image": "🖼️ 图像生成类",
        "video": "🎬 视频生成类",
        "finance": "💰 金融投资类",
        "email": "📧 邮件通信类",
        "search": "🔍 搜索研究类",
        "data": "📊 数据分析类",
        "file": "📁 文件管理类",
        "automation": "⚙️ 自动化工作流",
        "general": "🔧 通用工具类",
        "libs": "🧩 已装库/工具"
    }

    for cat, skills in sorted(tree["categories"].items()):
        icon = category_names.get(cat, f"📦 {cat}")
        lines.append(f"## {icon} ({len(skills)} 个)")
        lines.append("")
        for s in sorted(skills, key=lambda x: x["name"]):
            if cat == "libs":
                desc = s["description"][:60] + "..." if len(s["description"]) > 60 else s["description"]
                lines.append(f"- `{s['name']}` ({s.get('type','python_lib')} v{s.get('version','?')}): {desc} — `{s['path']}`")
            else:
                desc = s["description"][:80] + "..." if len(s["description"]) > 80 else s["description"]
                lines.append(f"- `{s['name']}` (v{s['version']}): {desc}")
        lines.append("")

    return "\n".join(lines)


def main():
    # 支持环境变量覆盖
    skills_dir = os.environ.get("SKILLS_DIR", os.path.expanduser("~/.workbuddy/skills"))
    binaries_dir = os.environ.get("BINARIES_DIR", os.path.expanduser("~/.workbuddy/binaries"))

    print(f"扫描技能目录: {skills_dir}")
    print(f"扫描库目录: {binaries_dir}")
    tree = build_skill_tree(skills_dir, binaries_dir)

    # 输出 JSON
    output_dir = Path(__file__).parent.parent
    json_path = output_dir / "skill_tree.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    print(f"✓ 生成索引: {json_path}")

    # 自检：技能分类条数和应 >= 技能 total（libs 分类是库，单独统计）
    cat_sum_skills = sum(len(v) for k, v in tree["categories"].items() if k != "libs")
    if cat_sum_skills < tree["total"]:
        print(
            f"✗ 自检失败: 技能分类条数和({cat_sum_skills}) < total({tree['total']})，索引数据不一致！",
            file=sys.stderr,
        )
        sys.exit(1)
    cat_sum = sum(len(v) for v in tree["categories"].values())
    print(f"✓ 自检通过: 技能分类 {cat_sum_skills} >= total {tree['total']}；含库共 {cat_sum} 条")

    # 输出 Markdown
    md_path = output_dir / "SKILL_TREE.md"
    md_content = generate_markdown(tree)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✓ 生成文档: {md_path}")

    # 打印统计
    print(f"\n统计:")
    print(f"  - 总技能数: {tree['total']}")
    print(f"  - 已装库/工具数: {tree.get('libs_count', 0)}")
    print(f"  - 分类数: {len(tree['categories'])}")
    for cat, skills in sorted(tree["categories"].items()):
        print(f"    - {cat}: {len(skills)} 个")


if __name__ == "__main__":
    main()
