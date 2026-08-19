#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semantic_index — 可选语义向量索引(SkillWeaver 启发一的完整实现,重依赖可选层)

设计定位:
  主链路(pre-hook / constitution-check)永远零依赖、确定性;
  本脚本是**可选增强层** —— 装了 sentence-transformers 就把"关键词检索"
  升级为"语义向量检索",不装不影响主链路任何功能。

功能:
  build  读取 skill_tree.json 全量技能描述,生成 embedding 索引(skill_vectors.npz)
  query  给定任务文本,语义检索 top-K 相关技能

依赖(按需安装,约 100MB 模型 + torch):
  pip install sentence-transformers numpy
  # 可选:pip install faiss-cpu  (不装则用 numpy 余弦相似度,功能等价、小规模无差)

用法:
  python semantic_index.py build                          # 建索引
  python semantic_index.py query "我要把代码传上去" -k 5    # 语义检索 top-5

返回码: 0=成功, 2=缺依赖(打印安装指引), 1=运行错误
"""
import argparse
import json
import os
import sys

MODEL_NAME = "all-MiniLM-L6-v2"  # 开源免费,本地运行,90MB
DEFAULT_TREE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skill_tree.json")
DEFAULT_INDEX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skill_vectors.npz")

EXCLUDED_SKILLS = {"skills-constitution", "constitution-check"}


def _check_deps():
    """检查可选依赖,缺失时打印安装指引并退出(这不是兜底,是功能开关)"""
    missing = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        missing.append("sentence-transformers")
    if missing:
        print("✗ 语义索引为可选增强层,缺少依赖: " + ", ".join(missing), file=sys.stderr)
        print("  安装: pip install sentence-transformers numpy", file=sys.stderr)
        print("  (可选加速: pip install faiss-cpu)", file=sys.stderr)
        print("  不安装不影响宪法主链路 —— pre-hook 的零依赖轻量检索照常可用。", file=sys.stderr)
        sys.exit(2)


def load_skills(tree_path=DEFAULT_TREE):
    """从 skill_tree.json 读取全量技能(名称+描述,跨分类去重)"""
    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)
    skills = {}
    for cat, items in tree.get("categories", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                name = item["name"]
                if name in EXCLUDED_SKILLS:
                    continue
                e = skills.setdefault(name, {"name": name, "description": "", "categories": []})
                if item.get("description") and not e["description"]:
                    e["description"] = item["description"]
                if cat not in e["categories"]:
                    e["categories"].append(cat)
    return list(skills.values())


def build(tree_path=DEFAULT_TREE, index_path=DEFAULT_INDEX):
    _check_deps()
    import numpy as np
    from sentence_transformers import SentenceTransformer

    skills = load_skills(tree_path)
    if not skills:
        print(f"✗ 技能树为空或不存在: {tree_path}", file=sys.stderr)
        return 1
    print(f"加载模型 {MODEL_NAME} (首次运行需下载 ~90MB)...")
    model = SentenceTransformer(MODEL_NAME)
    texts = [f"{s['name']} {s['description']}" for s in skills]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    meta = [{"name": s["name"], "description": s["description"],
             "categories": s["categories"]} for s in skills]
    np.savez_compressed(index_path,
                        embeddings=np.asarray(embeddings, dtype="float32"),
                        meta=json.dumps(meta, ensure_ascii=False))
    print(f"✓ 语义索引已生成: {index_path} ({len(skills)} 个技能, dim={embeddings.shape[1]})")
    print("  提示: pre-hook 的零依赖轻量检索仍为主链路;本索引供 query/外部集成使用。")
    return 0


def query(task, top_k=5, index_path=DEFAULT_INDEX):
    _check_deps()
    import numpy as np
    from sentence_transformers import SentenceTransformer

    if not os.path.exists(index_path):
        print(f"✗ 索引不存在: {index_path} — 先运行: python semantic_index.py build",
              file=sys.stderr)
        return 1
    data = np.load(index_path, allow_pickle=False)
    embeddings = data["embeddings"]
    meta = json.loads(str(data["meta"]))
    model = SentenceTransformer(MODEL_NAME)
    q = model.encode([task], normalize_embeddings=True)

    # 优先 FAISS,缺省 numpy 余弦(向量已归一化,点积即余弦)
    try:
        import faiss
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        scores, indices = index.search(np.asarray(q, dtype="float32"), top_k)
        results = [(float(scores[0][i]), meta[int(indices[0][i])]) for i in range(top_k)]
        backend = "faiss"
    except ImportError:
        sims = embeddings @ np.asarray(q[0], dtype="float32")
        top = sims.argsort()[::-1][:top_k]
        results = [(float(sims[i]), meta[int(i)]) for i in top]
        backend = "numpy"

    print(json.dumps({
        "task": task, "backend": backend, "top_k": top_k,
        "candidates": [
            {"name": m["name"], "score": round(sc, 4), "categories": m["categories"]}
            for sc, m in results
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="可选语义向量索引(增强层,非主链路)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="构建语义索引")
    p_build.add_argument("--tree", default=DEFAULT_TREE)
    p_build.add_argument("--index", default=DEFAULT_INDEX)
    p_query = sub.add_parser("query", help="语义检索 top-K 技能")
    p_query.add_argument("task")
    p_query.add_argument("-k", "--top-k", type=int, default=5)
    p_query.add_argument("--index", default=DEFAULT_INDEX)
    a = ap.parse_args()

    if a.cmd == "build":
        return build(a.tree, a.index)
    return query(a.task, a.top_k, a.index)


if __name__ == "__main__":
    sys.exit(main())
