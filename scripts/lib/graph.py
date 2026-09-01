# -*- coding: utf-8 -*-
"""技能图谱(v2.23.0)—— 在技能树之上叠加确定性关系图

借鉴 GitNexus「预计算关系智能」:关系在索引期算好,运行时零推理。
与代码知识图谱的映射:
  GitNexus 的 CALLS/IMPORTS 边  → 本模块的 chains_to / co_anchor / alternative 边
  GitNexus 的社区检测(Leiden)   → 本模块的确定性标签传播聚类(零依赖,完全可复现)
  GitNexus 的 file:line 溯源    → 本模块每条边必带 evidence(为什么相关)

三种边(全部确定性抽取,零 LLM):
  chains_to    A 的 output_schema ∩ B 的 input_schema ≠ ∅(registry.json 已有数据,
               此前仅 step4 临时用,现固化进图谱)——有向
  co_anchor    共享实体锚点(同一领域词/工具名/文件名,正则抽取,不靠字面巧合)
  alternative  同分类 + 描述重叠度高(互为替代方案)

明确不借(与宪法零依赖原则同构):图数据库、LLM 参与建边、全量 AST、
每次调用重建图。图为 JSON 文件,随技能树重建而重建(秒级全量即可)。
"""
import json
import os
import re
import sys
from collections import Counter

try:
    from .text import overlap_score
except ImportError:
    try:
        from lib.text import overlap_score
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from text import overlap_score  # type: ignore

# 锚点抽取:ASCII token(≥3 字符)。锚点是"实体"而不是"虚词",
# 共享锚点 = 两个技能谈论同一实体(如都涉及 git / docx / mcp__rh-frontend)。
_ANCHOR_RE = re.compile(r"[a-z0-9][a-z0-9_\-\.]{2,}")

# 锚点停用词:任意技能描述里都会出现的高频虚词/套话动词,不构成"同一实体"证据。
# 实测教训:不滤掉这些词,全部技能会经 "supports+search"/"create+asks" 这类
# 套话词对连成一个巨簇(真实案例:268 节点巨簇)。
ANCHOR_STOPWORDS = {
    # 虚词
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "were", "been", "when", "what", "which", "who", "how", "why",
    "via", "into", "onto", "out", "can", "could", "will", "would",
    "not", "all", "any", "more", "most", "other", "some", "such",
    "only", "also", "just", "like", "than", "then", "them", "they",
    "you", "your", "its", "has", "have", "had", "does", "did", "done",
    # 套话动词(描述里"用于/支持/帮助"类)
    "use", "used", "uses", "using", "useful", "help", "helps", "helped",
    "support", "supports", "supported", "need", "needs", "needed",
    "want", "wants", "wanted", "ask", "asks", "asked", "let", "lets",
    "make", "makes", "making", "made", "get", "gets", "getting",
    "create", "creates", "created", "creating", "creation",
    "edit", "edits", "edited", "editing", "write", "writes", "writing",
    "written", "read", "reads", "reading", "build", "builds", "building",
    "built", "manage", "manages", "managed", "managing", "management",
    "process", "processes", "processed", "processing",
    "generate", "generates", "generated", "generating", "generation",
    "handle", "handles", "handled", "handling", "work", "works", "working",
    "convert", "converts", "converted", "converting", "conversion",
    "extract", "extracts", "extracted", "extracting", "extraction",
    "include", "includes", "included", "including", "provide", "provides",
    "provided", "providing", "enable", "enables", "enabled", "allow",
    "allows", "allowed", "ensure", "ensures", "apply", "applies", "applied",
    "run", "runs", "running", "set", "sets", "setup", "start", "starts",
    "stop", "add", "adds", "added", "adding", "find", "finds", "finding",
    "check", "checks", "checked", "checking", "try", "tries", "keep",
    "keeps", "take", "takes", "taken", "give", "gives", "given",
    # 泛化名词(不指代具体实体)
    "tool", "tools", "skill", "skills", "plugin", "plugins", "agent",
    "agents", "task", "tasks", "user", "users", "model", "models",
    "system", "systems", "service", "services", "app", "apps",
    "application", "applications", "feature", "features", "function",
    "functions", "way", "ways", "type", "types", "format", "formats",
    "content", "contents", "data", "information", "knowledge", "context",
    "conversation", "current", "project", "projects", "file", "files",
    "folder", "folders", "page", "pages", "example", "examples",
    "case", "cases", "result", "results", "output", "outputs",
    "input", "inputs", "value", "values", "key", "keys", "list",
    "level", "levels", "part", "parts", "step", "steps",
    "development", "guide", "guides", "tutorial", "design", "native",
    "advanced", "professional", "simple", "easy", "complex", "basic",
    "various", "multiple", "different", "specific", "related", "similar",
    "based", "base", "main", "common", "general", "custom", "standard",
    "automatically", "automatic", "efficient", "powerful", "complete",
    "directly", "quickly", "easily", "properly", "correctly", "fully",
    "one", "two", "new", "per", "non",
    # 活动词(排障/测试/部署等"做什么",不是"对什么实体做")
    "debug", "debugs", "debugging", "debugged", "diagnose", "diagnosing",
    "diagnosis", "diagnostic", "fix", "fixes", "fixed", "fixing",
    "problem", "problems", "error", "errors", "issue", "issues",
    "bug", "bugs", "troubleshoot", "troubleshooting",
    "configure", "configures", "configuration", "config",
    "install", "installs", "installed", "installation",
    "deploy", "deploys", "deployed", "deployment",
    "test", "tests", "tested", "testing", "review", "reviews",
    "optimize", "optimizes", "optimization", "improve", "improves",
    "monitor", "monitors", "monitoring", "analyze", "analyzes",
    "analysis", "workflow", "workflows", "pipeline", "pipelines",
    "integration", "template", "templates", "best", "practices",
    "weekly", "daily", "monthly", "hourly", "report", "reports",
    # 中文泛词
    "支持", "工具", "技能", "使用", "用于", "可以", "进行", "相关",
    "内容", "数据", "文件", "用户", "任务", "功能", "自动", "帮助",
}


def _normalize_anchor(tok):
    """锚点归一化:英文复数折回单数(images→image),避免同实体算两个锚点

    保守规则:长度≥4、以单个 s 结尾(非 ss)才剥离。
    """
    if len(tok) >= 4 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok

# alternative 边参数(防图爆炸:全局只保留最强的 N 条)
ALT_MIN_SCORE = 0.35
ALT_MAX_EDGES = 200

# 参与聚簇的边类型(确定性纪律,同 GitNexus 只对结构边做社区检测):
# "互为替代"不代表"同一条任务线",alternative 边只供查询/注入,不合并簇
CLUSTER_EDGE_KINDS = {"chains_to", "co_anchor"}

# co_anchor 锚点文档频率上限:一个锚点出现在超过该比例的技能里,
# 说明它是"creating/wants"这类描述套话而不是实体,剔除(确定性 IDF 思想)
ANCHOR_DF_RATIO = 0.05
ANCHOR_DF_MIN_CAP = 8


def extract_anchors(name, description):
    """从一个技能的名称+描述中抽取实体锚点集合(确定性正则,零依赖)

    锚点 = 归一化后的 ASCII token(去停用词)。技能名本身按 -/_/. 拆子词,
    保证 `git-workflow-and-versioning` 的 git 也能成为锚点。
    """
    text = f"{name or ''} {name or ''} {description or ''}".lower()
    anchors = set()
    for tok in _ANCHOR_RE.findall(text):
        if tok in ANCHOR_STOPWORDS:
            continue
        anchors.add(_normalize_anchor(tok.rstrip("._")))
    return {a for a in anchors if len(a) >= 3 and a not in ANCHOR_STOPWORDS}


def load_registry(registry_path):
    """读 registry.json,返回 {技能名: 条目};缺失/损坏返回 {}"""
    try:
        with open(registry_path, encoding="utf-8") as f:
            reg = json.load(f)
        return {s["name"]: s for s in reg.get("skills", []) if s.get("name")}
    except Exception:
        return {}


def build_graph(skills, registry_path):
    """从技能清单 + registry 构建技能图谱(确定性,零依赖)

    skills: [{name, description, categories, qualified_name?}, ...]
            (直接取 build_skill_tree 的树内条目即可)
    返回 {node_count, edge_count, edges, clusters}
    """
    registry = load_registry(registry_path)
    names = []
    seen = set()
    for s in skills:
        n = s.get("name") or ""
        if n and n not in seen and n != "libs":
            seen.add(n)
            names.append(n)
    by_name = {s["name"]: s for s in skills if s.get("name")}

    edges = []
    edge_keys = set()

    def add_edge(a, b, kind, evidence):
        if a == b:
            return
        key = (kind, a, b)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({"source": a, "target": b, "kind": kind, "evidence": evidence})

    # 1) chains_to: registry 的 output ∩ input(schema 数据已有,固化进图)
    for a in names:
        sa = registry.get(a)
        if not sa or not sa.get("output_schema"):
            continue
        out_a = set(sa["output_schema"])
        for b in names:
            if a == b:
                continue
            sb = registry.get(b)
            if not sb or not sb.get("input_schema"):
                continue
            shared = sorted(out_a & set(sb["input_schema"]))
            if shared:
                add_edge(a, b, "chains_to", "输出→输入: " + "/".join(shared[:4]))

    # 2) co_anchor: 共享实体锚点
    # 先做文档频率过滤:出现在过多技能里的锚点是描述套话(如 creating),
    # 不构成"同一实体"证据 —— 否则所有技能经套话连成一个巨簇。
    anchor_map_raw = {n: extract_anchors(n, by_name[n].get("description", ""))
                      for n in names}
    df = Counter()
    for anchors in anchor_map_raw.values():
        for a in anchors:
            df[a] += 1
    df_cap = max(ANCHOR_DF_MIN_CAP, int(len(names) * ANCHOR_DF_RATIO))
    anchor_map = {n: {a for a in anchors if df[a] <= df_cap}
                  for n, anchors in anchor_map_raw.items()}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = anchor_map[a] & anchor_map[b]
            # 至少 2 个过滤后仍共享的锚点才连边(单锚点误连率高)
            if len(shared) >= 2:
                ev = ", ".join(sorted(shared, key=lambda x: (-len(x), x))[:3])
                add_edge(*sorted((a, b)), "co_anchor", "共享锚点: " + ev)

    # 3) alternative: 同分类 + 描述高重叠(保留全局最强的一批,防图爆炸)
    alt_candidates = []
    cats = {}
    for n in names:
        for c in by_name[n].get("categories", []):
            cats.setdefault(c, []).append(n)
    pair_seen = set()
    for members in cats.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pair = tuple(sorted((a, b)))
                if pair in pair_seen:
                    continue
                pair_seen.add(pair)
                sc = overlap_score(by_name[a].get("description", ""),
                                   by_name[b].get("description", ""))
                if sc >= ALT_MIN_SCORE:
                    alt_candidates.append((sc, pair))
    alt_candidates.sort(key=lambda x: (-x[0], x[1]))
    for sc, (a, b) in alt_candidates[:ALT_MAX_EDGES]:
        add_edge(a, b, "alternative", f"同分类替代方案(描述重叠 {sc:.2f})")

    # 4) 聚类:确定性标签传播(零依赖社区检测,借鉴 GitNexus 的聚类思想)
    # 不用连通分量:跨域桥接技能(同时提 github 和 excel)会把两个域并成巨簇。
    # 标签传播让稠密连通区域各自收敛到自己的标签,桥接技能归多数派一侧,
    # 弱连接的区域即使图论连通也保持分离。
    adj_s = {}
    for e in edges:
        if e["kind"] not in CLUSTER_EDGE_KINDS:
            continue
        adj_s.setdefault(e["source"], []).append(e["target"])
        adj_s.setdefault(e["target"], []).append(e["source"])
    labels = {n: n for n in names}
    for _ in range(20):  # 固定轮数上限,保证终止
        changed = False
        for n in names:  # 排序遍历 + 平票取字典序最小 → 完全确定性
            nbr_labels = [labels[m] for m in adj_s.get(n, [])]
            if not nbr_labels:
                continue
            cnt = Counter(nbr_labels)
            top = max(cnt.values())
            best = min(l for l, c in cnt.items() if c == top)
            if best != labels[n]:
                labels[n] = best
                changed = True
        if not changed:
            break
    groups = {}
    for n in names:
        groups.setdefault(labels[n], []).append(n)

    clusters = {}
    used_labels = set()
    for root, members in sorted(groups.items()):
        if len(members) < 2:
            continue  # 孤立节点不入簇
        # 簇标签:成员经文档频率过滤后的锚点里最高频的(套话已被滤掉)
        tokens = Counter()
        for m in members:
            for tok in anchor_map.get(m, set()):
                if len(tok) >= 4:
                    tokens[tok] += 1
        label = tokens.most_common(1)[0][0] if tokens else root
        base_label = label
        k = 2
        while label in used_labels:
            label = f"{base_label}-{k}"
            k += 1
        used_labels.add(label)
        clusters[label] = {"members": sorted(members), "size": len(members)}

    return {
        "node_count": len(names),
        "edge_count": len(edges),
        "edges": edges,
        "clusters": clusters,
    }


def load_graph(graph_path):
    """读 skill_graph.json;缺失/损坏返回 {}(fail-open,图缺失不阻断任何链路)"""
    try:
        with open(graph_path, encoding="utf-8") as f:
            g = json.load(f)
        if isinstance(g, dict) and g.get("edges") is not None:
            return g
        return {}
    except Exception:
        return {}


def adjacency(graph, kinds=None):
    """从边表构建邻接表 {技能: [(邻居, kind, evidence), ...]}(双向)

    kinds: 只保留指定边类型(缺省全部)。门禁连通性判断只应使用结构边
    (CLUSTER_EDGE_KINDS)——"互为替代"不构成任务线连通的凭证。
    """
    adj = {}
    for e in graph.get("edges", []):
        if kinds is not None and e.get("kind", "") not in kinds:
            continue
        a, b = e.get("source", ""), e.get("target", "")
        adj.setdefault(a, []).append((b, e.get("kind", ""), e.get("evidence", "")))
        adj.setdefault(b, []).append((a, e.get("kind", ""), e.get("evidence", "")))
    return adj


def cluster_of(graph, skill_name):
    """技能所在簇标签;不在任何簇返回 None"""
    for label, c in graph.get("clusters", {}).items():
        if skill_name in c.get("members", []):
            return label
    return None


def graph_expand(graph, anchor_skills, max_neighbors=8):
    """从锚点技能(按相关度排序)扩展出图谱相关技能:同簇成员 + 一跳邻居

    轮转填充:每轮每个锚点最多贡献 2 个候选,再放宽 —— 防止排名靠前的
    锚点所在大簇吃光整个 token 预算,保证候选跨锚点多样化。
    返回 [{name, via(锚点名), kind, evidence, cluster}],去重、排除锚点自身。
    """
    if not graph or not anchor_skills:
        return []
    adj = adjacency(graph)
    anchors = [a for a in dict.fromkeys(anchor_skills) if a]

    # 预生成每个锚点的候选序列(先同簇——整条任务线,后一跳邻居)
    seqs = []
    for a in anchors:
        seq = []
        label = cluster_of(graph, a)
        if label:
            for m in graph["clusters"][label].get("members", []):
                if m != a:
                    seq.append((m, "cluster", f"与 {a} 同簇({label})", label))
        for nb, kind, ev in adj.get(a, []):
            seq.append((nb, kind, ev, cluster_of(graph, nb)))
        if seq:
            seqs.append((a, seq))

    out, seen = [], set(anchors)
    idx = [0] * len(seqs)
    per_round = 2
    while len(out) < max_neighbors:
        progressed = False
        for i, (a, seq) in enumerate(seqs):
            taken = 0
            while idx[i] < len(seq) and taken < per_round and len(out) < max_neighbors:
                m, kind, ev, cl = seq[idx[i]]
                idx[i] += 1
                if m in seen:
                    continue
                seen.add(m)
                taken += 1
                progressed = True
                out.append({"name": m, "via": a, "kind": kind,
                            "evidence": ev or kind, "cluster": cl})
        if not progressed:
            break
        per_round = max_neighbors  # 第二轮起不限每锚点额度,填满为止
    return out[:max_neighbors]


def node_set(graph):
    """出现在边或簇中的节点集合(孤立节点不在其中)"""
    nodes = set()
    for e in graph.get("edges", []):
        nodes.add(e.get("source", ""))
        nodes.add(e.get("target", ""))
    for c in graph.get("clusters", {}).values():
        nodes.update(c.get("members", []))
    nodes.discard("")
    return nodes


def graph_relevant_set(graph, anchor_skills):
    """锚点技能的图谱相关集合(锚点自身 + 同簇 + 结构边一跳),供门禁图证据校验

    注意:只用结构边(chains_to/co_anchor)判断连通 —— 与聚簇纪律一致,
    alternative 边不做放行凭证。
    """
    relevant = set(a for a in anchor_skills if a)
    if not graph:
        return relevant
    adj = adjacency(graph, kinds=CLUSTER_EDGE_KINDS)
    for a in list(relevant):
        label = cluster_of(graph, a)
        if label:
            relevant.update(graph["clusters"][label].get("members", []))
        for nb, _kind, _ev in adj.get(a, []):
            relevant.add(nb)
    return relevant
