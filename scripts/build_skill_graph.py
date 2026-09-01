#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_skill_graph —— 从已有技能树 + registry 重建技能图谱（v2.23.0）

与 build_skill_tree.py 的分工：
  - build_skill_tree.py 扫描技能目录生成树时会**顺带**重建图谱（推荐路径）
  - 本脚本不需要技能目录：直接从仓库里的 skill_tree.json（作者快照或你
    已生成的树）+ registry.json 重建图谱 —— 用于快照维护、CI 校验、
    以及"树没变只想刷新图"的场景

用法:
  python scripts/build_skill_graph.py                     # 默认读仓库内两文件
  python scripts/build_skill_graph.py --tree 路径 --registry 路径 --out 路径
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import graph as G  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def skills_from_tree(tree):
    """把技能树摊平成去重技能清单(保留 name/description/categories/qualified_name)"""
    skills, seen = [], set()
    for items in tree.get("categories", {}).values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                if item["name"] in seen:
                    continue
                seen.add(item["name"])
                skills.append(item)
    return skills


def build_graph_payload(tree, registry_path):
    """生成完整的 skill_graph.json 内容(含版本与来源信息)"""
    g = G.build_graph(skills_from_tree(tree), registry_path)
    version = tree.get("version", "")
    if not version:
        # 与 build_skill_tree 同源:从 SKILL.md frontmatter 读
        try:
            import re as _re
            with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as f:
                m = _re.search(r"^version:\s*(\S+)", f.read(), _re.MULTILINE)
                version = m.group(1) if m else "unknown"
        except Exception:
            version = "unknown"
    return {
        "version": version,
        "generated_at": datetime.now().isoformat(),
        "source": {"tree": "skill_tree.json", "registry": "registry.json"},
        **g,
    }


def main():
    ap = argparse.ArgumentParser(description="重建技能图谱(技能树 + registry → skill_graph.json)")
    ap.add_argument("--tree", default=os.path.join(ROOT, "skill_tree.json"))
    ap.add_argument("--registry", default=os.path.join(ROOT, "registry.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "skill_graph.json"))
    a = ap.parse_args()

    if not os.path.exists(a.tree):
        print(f"错误:技能树不存在 {a.tree}(先运行 build_skill_tree.py)", file=sys.stderr)
        return 1
    with open(a.tree, encoding="utf-8") as f:
        tree = json.load(f)

    payload = build_graph_payload(tree, a.registry)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    kinds = {}
    for e in payload["edges"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"✓ 技能图谱已生成: {a.out}")
    print(f"  节点 {payload['node_count']} | 边 {payload['edge_count']}"
          f"({', '.join(f'{k}×{v}' for k, v in sorted(kinds.items()))})"
          f" | 簇 {len(payload['clusters'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
