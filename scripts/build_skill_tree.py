#!/usr/bin/env python3
"""
技能树构建器 — 扫描所有 SKILL.md，按 description 分类生成索引
通用适配：支持环境变量 SKILLS_DIR 指定技能目录

v2.21.0：双机制平台覆盖 —— 能力注册表 = 独立技能 ∪ 插件技能。
在扫描独立技能目录之外，自动扫描插件缓存里的插件技能
（ZCode / Claude Code 已知路径自动发现；其他双机制平台如 DeepSeek Harness
用 PLUGIN_CACHE_DIRS 环境变量或仓库根 plugin_roots.json 接入，无需改代码）。
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


# ============================================================
# v2.21.0: 插件技能扫描 —— 双机制平台（技能 + 插件两条平行机制）全覆盖
# ============================================================
# ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的"能力"来自两条平行通道:
#   ① 独立技能: 平台技能目录下的 SKILL.md(~/.zcode/skills 等)
#   ② 插件内置技能: 插件包缓存里的 SKILL.md(调用名通常为 `插件名:技能名`)
# 宪法"查技能库"两条通道同权重,本扫描器把 ② 也编入技能树。
#
# 布局无关设计(不锁定任何一家的目录规范,新 agent 免改代码接入):
#   - KNOWN_PLUGIN_CACHE_LAYOUTS: 已核实的平台缓存路径(存在才扫,缺谁跳谁)
#   - 环境变量 PLUGIN_CACHE_DIRS(os.pathsep 分隔): 任何新 agent 的插件缓存目录
#     (DeepSeek Harness v0.1 插件路径未定型,推荐用此方式接入)
#   - 仓库根 plugin_roots.json: {"cache_dirs": ["..."]} 持久化自定义目录
#   - 环境变量 PLUGIN_SCAN=0: 整体关闭插件扫描
# 扫描只依赖一个共同形态: 插件包内含 skills/ 或 bundled-skills/ 技能目录;
# 路径任一段以 .DISABLED 结尾(停用的市场/插件)整棵子树跳过。
KNOWN_PLUGIN_CACHE_LAYOUTS = {
    "zcode": {
        "cache": ["~/.zcode/cli/plugins/cache"],
        # ZCode 插件启用表: config.json plugins.enabledPlugins 中值为 false 的插件不入树
        "enabled_map": ("~/.zcode/cli/config.json", "plugins.enabledPlugins"),
    },
    "claude": {"cache": ["~/.claude/plugins/cache"]},
}
# 注: DeepSeek Harness "一切皆插件"(Cordis 架构),技能随插件(Bundle)分发,
#     其"技能 = 目录 + 装载器"形态与本扫描器假设兼容;插件目录规范在 v0.1
#     预览期尚未定型,路径稳定后加入本表,当前用 PLUGIN_CACHE_DIRS 接入。
SKILL_DIR_MARKERS = {"skills", "bundled-skills"}  # 插件包内技能目录惯用名
# 插件包内常见的非插件名中间目录(payload 打包层/marketplace 元数据层等)
_GENERIC_SEGMENTS = {"plugins", "skills", "bundled-skills", "marketplace", "cache",
                     "repos", "payload", "bundle", "bundles", "dist", "build"}
_VERSION_SEG_RE = re.compile(r"[vV]?\d+(\.\d+){1,3}")


def _is_version_segment(seg: str) -> bool:
    """目录段是否形如版本号(0.2.0 / v1.0 / 1.15.0-beta)"""
    return bool(_VERSION_SEG_RE.fullmatch(seg or ""))


def _version_key(v) -> tuple:
    m = re.search(r"\d+(\.\d+)*", str(v or ""))
    return tuple(int(x) for x in m.group(0).split(".")) if m else (0,)


def _load_enabled_map(spec) -> dict | None:
    """读取平台插件启用表;读不到/格式不符 → None(全部视为启用,降级不误杀)"""
    try:
        path, dotted = spec
        p = Path(path).expanduser()
        if not p.exists():
            return None
        node = json.loads(p.read_text(encoding="utf-8"))
        for part in dotted.split("."):
            node = node[part]
        return node if isinstance(node, dict) else None
    except Exception:
        return None


def resolve_plugin_cache_dirs() -> list[tuple[str, Path]]:
    """汇总插件缓存目录: 已知平台表 + PLUGIN_CACHE_DIRS + plugin_roots.json

    返回 [(来源标记, 目录)];目录不存在直接丢弃,重复路径去重。
    """
    items: list[tuple[str, str]] = []
    for agent, spec in KNOWN_PLUGIN_CACHE_LAYOUTS.items():
        for cache in spec.get("cache", []):
            items.append((agent, cache))
    env_val = os.environ.get("PLUGIN_CACHE_DIRS", "")
    for cache in env_val.split(os.pathsep):
        if cache.strip():
            items.append(("custom", cache.strip()))
    cfg = Path(__file__).resolve().parent.parent / "plugin_roots.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for cache in (data.get("cache_dirs") or []):
                items.append(("custom", str(cache)))
        except Exception as e:
            print(f"警告: plugin_roots.json 解析失败(忽略): {e}", file=sys.stderr)
    seen, out = set(), []
    for agent, cache in items:
        p = Path(cache).expanduser()
        if not p.exists():
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append((agent, p))
    return out


def scan_plugin_skills(cache_root, agent: str = "", enabled_map: dict | None = None) -> list[dict]:
    """扫描一个插件缓存根目录，返回插件技能条目（布局无关）

    形态假设(各双机制平台通用): .../插件缓存/<...>/<skills|bundled-skills>/<技能名>/SKILL.md
    - 插件名 = skills 段之前、跳过版本号段的最近目录名(无版本段则取相邻目录名)
    - enabled_map={"插件@市场": bool}(可选): 值为 False 的插件跳过;未提供 → 全算启用
    - 同一插件同名技能多版本共存 → 保留插件版本号最高的那份
    """
    found: dict[tuple[str, str], tuple[tuple, dict]] = {}
    root = Path(cache_root).expanduser()
    for dirpath, dirnames, filenames in os.walk(root):
        # 剪枝: 隐藏目录 / node_modules / .DISABLED 停用子树
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "node_modules"
                       and not d.upper().endswith(".DISABLED")]
        if "SKILL.md" not in filenames:
            continue
        skill_md = Path(dirpath) / "SKILL.md"
        parts = skill_md.parent.relative_to(root).parts
        if len(parts) < 2 or parts[-2].lower() not in SKILL_DIR_MARKERS:
            continue  # 不在技能目录形态下的 SKILL.md 不认(避免把插件说明文档当技能)
        skill_name = parts[-1]
        marker_idx = len(parts) - 2
        marketplace = parts[0] if len(parts) >= 3 else ""
        # 插件名推导: 优先取市场段后第一个"非版本号、非通用中间目录"的段
        # (真实案例 v2.21.0: mimosa/1.0.3/payload/skills/... 的打包层 payload
        #  曾被误当插件名,导致停用插件 mimosa 的技能漏过启用表过滤)
        plugin = None
        if marker_idx >= 2 and not _is_version_segment(parts[1]) \
                and parts[1].lower() not in _GENERIC_SEGMENTS:
            plugin = parts[1]
        else:
            for seg in reversed(parts[:marker_idx]):
                if not _is_version_segment(seg) and seg.lower() not in _GENERIC_SEGMENTS:
                    plugin = seg
                    break
        plugin = plugin or (parts[0] if marker_idx >= 1 else skill_name)
        plugin_version = parts[marker_idx - 1] if marker_idx >= 1 and _is_version_segment(parts[marker_idx - 1]) else ""
        if enabled_map is not None:
            # 停用检查覆盖路径上所有插件名候选段(防打包层导致漏匹配)
            if any(enabled_map.get(f"{seg}@{marketplace}") is False
                   for seg in parts[1:marker_idx]):
                continue
            if enabled_map.get(f"{plugin}@{marketplace}", enabled_map.get(plugin, True)) is False:
                continue
        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            print(f"读取插件技能 {skill_md} 失败: {e}", file=sys.stderr)
            continue
        fm = parse_frontmatter(content)
        description = fm.get("description", "") or fm.get("description_zh", "")
        entry = {
            "name": skill_name,
            "description": description[:200],  # 截断到 200 字符,与独立技能一致
            "version": fm.get("version", "0.0.0"),
            "categories": classify_skill(skill_name, description),
            "source": "plugin",
            "plugin": plugin,
            "plugin_version": plugin_version,
            "qualified_name": f"{plugin}:{skill_name}",  # 完整调用名(双机制平台 Skill 机制认它)
            "marketplace": marketplace,
            "agent": agent,
            "path": str(skill_md),
        }
        key = (plugin, skill_name)
        rank = _version_key(plugin_version)
        if key not in found or rank > found[key][0]:
            found[key] = (rank, entry)
    return [e for _, e in found.values()]


def build_skill_tree(skills_dir: str, binaries_dir: str = "",
                     plugin_cache_dirs: list[tuple[str, Path]] | None = None) -> dict:
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

    # v2.21.0: 追加插件技能（双机制平台；PLUGIN_SCAN=0 可关闭）
    # 独立技能与插件技能同权重进分类,插件条目额外带 source/plugin/qualified_name
    plugin_count = 0
    if os.environ.get("PLUGIN_SCAN", "1") != "0":
        if plugin_cache_dirs is None:
            plugin_cache_dirs = resolve_plugin_cache_dirs()
        seen_qualified = set()
        for agent, cache_dir in plugin_cache_dirs:
            spec = KNOWN_PLUGIN_CACHE_LAYOUTS.get(agent, {})
            emap = _load_enabled_map(spec["enabled_map"]) if spec.get("enabled_map") else None
            for entry in scan_plugin_skills(cache_dir, agent=agent, enabled_map=emap):
                if entry["qualified_name"] in seen_qualified:
                    continue  # 多缓存根重复插件,只入树一次
                seen_qualified.add(entry["qualified_name"])
                plugin_count += 1
                for cat in entry["categories"]:
                    tree["categories"].setdefault(cat, []).append(entry)
    tree["plugin_skills_count"] = plugin_count
    if plugin_cache_dirs is not None:
        tree["plugin_cache_dirs"] = [str(p) for _, p in plugin_cache_dirs]

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
    plugin_count = tree.get("plugin_skills_count", 0)
    lines = [
        "# 技能树索引",
        "",
        f"**生成时间**: {tree['generated_at']}",
        f"**独立技能数**: {tree['total']}" + (f"（+ 插件技能 {plugin_count} = 技能总数 {tree['total'] + plugin_count}）" if plugin_count else ""),
        f"**插件技能数**: {plugin_count}" + ("（v2.21.0 双机制覆盖：插件技能以完整调用名 `插件名:技能名` 调用）" if plugin_count else ""),
        f"**已装库/工具数**: {libs_count}",
        f"**总条目数**: {tree.get('total_entries', tree['total'] + plugin_count)}",
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
            elif s.get("source") == "plugin":
                desc = s["description"][:80] + "..." if len(s["description"]) > 80 else s["description"]
                lines.append(f"- `{s.get('qualified_name', s['name'])}`（插件 v{s.get('plugin_version', '?')}，技能 v{s['version']}）: {desc}")
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

    # 自检：技能分类条数和应 >= 独立技能 total + 插件技能数（libs 分类是库，单独统计）
    cat_sum_skills = sum(len(v) for k, v in tree["categories"].items() if k != "libs")
    total_all = tree["total"] + tree.get("plugin_skills_count", 0)
    if cat_sum_skills < total_all:
        print(
            f"✗ 自检失败: 技能分类条数和({cat_sum_skills}) < 独立+插件总数({total_all})，索引数据不一致！",
            file=sys.stderr,
        )
        sys.exit(1)
    cat_sum = sum(len(v) for v in tree["categories"].values())
    plugin_note = f"；插件技能 {tree.get('plugin_skills_count', 0)}" if tree.get("plugin_skills_count") else ""
    print(f"✓ 自检通过: 技能分类 {cat_sum_skills} >= 独立+插件 {total_all}；含库共 {cat_sum} 条{plugin_note}")

    # 输出 Markdown
    md_path = output_dir / "SKILL_TREE.md"
    md_content = generate_markdown(tree)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✓ 生成文档: {md_path}")

    # v2.23.0: 顺带重建技能图谱(技能树之上的确定性关系图;SKILL_GRAPH=0 可关闭)
    if os.environ.get("SKILL_GRAPH", "1") != "0":
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from build_skill_graph import build_graph_payload
            graph = build_graph_payload(tree, str(output_dir / "registry.json"))
            graph_path = output_dir / "skill_graph.json"
            with open(graph_path, "w", encoding="utf-8") as f:
                json.dump(graph, f, ensure_ascii=False, indent=2)
            print(f"✓ 生成技能图谱: {graph_path}"
                  f"(节点 {graph['node_count']} | 边 {graph['edge_count']}"
                  f" | 簇 {len(graph['clusters'])})")
        except Exception as e:
            print(f"⚠ 技能图谱生成失败(不影响技能树): {e}", file=sys.stderr)

    # 打印统计
    print(f"\n统计:")
    print(f"  - 独立技能数: {tree['total']}")
    print(f"  - 插件技能数: {tree.get('plugin_skills_count', 0)}")
    print(f"  - 已装库/工具数: {tree.get('libs_count', 0)}")
    print(f"  - 分类数: {len(tree['categories'])}")
    for cat, skills in sorted(tree["categories"].items()):
        print(f"    - {cat}: {len(skills)} 个")


if __name__ == "__main__":
    main()
