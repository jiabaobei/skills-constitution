#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_doctor —— 隐形技能诊断与修复（Skills 宪法 v2.24.0）
============================================================
解决两类真实痛点（2026-09-01 用户实测提出）：

痛点 A：技能"装了却隐形"
    典型如 ponytail 全套——目录在、SKILL.md 在、内容完整，但索引里
    description 只剩一个 ">" 字符（YAML 块标量解析缺陷），导致按关键词
    检索永远命中不到，等于没装。这类技能用户以为有、实际从未被调用。

痛点 B：技能库膨胀与 token 成本的矛盾
    全库 764+ 目录 / 1250+ 技能，完整索引 600KB+，每次注入都读全量很贵；
    但砍掉冷门技能又会重演"装了用不上"。需要既能省 token，又保证冷门
    技能"该发挥作用时能发挥作用"。

设计取舍（本工具的核心结论）：
    · 冷门 ≠ 无用，**一律保留检索入口**，只是把"完整描述"换成"短摘要"
      （mini 索引），命中候选后再回查完整索引 —— 省下的是常驻 token，
      不是可用性。
    · 损坏技能（无 SKILL.md / 空文件 / frontmatter 不可解析）**从索引排除**
      并可选隔离 —— 它们既检索不到又白占 token，留着是纯浪费。

检测项（severity: broken=损坏 / invisible=隐形 / warn=告警）：
    missing_skill_md      broken     目录无 SKILL.md
    empty_skill_md        broken     SKILL.md 为空或极短(<20 字符)
    no_frontmatter        broken     无 --- frontmatter 块
    missing_name          broken     frontmatter 缺 name
    missing_desc          invisible  缺 description 或过短(<12 字符)
    block_scalar_residue  invisible  description 只剩 > / | 等块标量符号
                                     （块标量未被解析，重建索引即可修复）
    name_mismatch         warn       目录名与 frontmatter name 不一致
    empty_dir             broken     空目录

用法：
    python skill_doctor.py                    # 扫描并输出人读报告
    python skill_doctor.py --json             # 机器可读
    python skill_doctor.py --fix              # 自动修复可修项（重建索引等）
    python skill_doctor.py --quarantine       # 把损坏技能移入 .broken/
    python skill_doctor.py --emit-min-index   # 生成轻量索引（省 token）
    python skill_doctor.py --query "关键词"    # 用 mini 索引检索（验证）

环境变量 SKILLS_DIR 可指定技能目录（默认 ~/.workbuddy/skills）。
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_skill_tree import parse_frontmatter, classify_skill  # 复用官方解析器
except Exception:  # pragma: no cover - 独立运行兜底
    parse_frontmatter = None
    classify_skill = None

DEFAULT_SKILLS = os.path.expanduser("~/.workbuddy/skills")
CONSTITUTION = Path(__file__).resolve().parent.parent
TREE_JSON = CONSTITUTION / "skill_tree.json"
MIN_INDEX = CONSTITUTION / "skill_index_min.json"
BROKEN_DIR_NAME = ".broken"
MINI_DESC_LEN = 48          # mini 索引摘要长度（够检索，不铺张）
SHORT_DESC_THRESHOLD = 12   # 短于此视为描述失效

# v2.24.0:摘要截断会丢掉长尾关键词(实测 ponytail 的 "yagni" 位于描述
# 第 200+ 字符,截断后检索不到 —— 冷门技能等于还是隐形)。
# 对策:只对"被截断的尾部"提取关键词单独留存,未截断的技能不增体积。
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "when", "when",
    "use", "used", "using", "not", "but", "are", "you", "your", "its",
    "can", "will", "all", "any", "has", "have", "was", "were", "what",
    "how", "why", "who", "out", "get", "set", "add", "new", "one", "two",
    "more", "most", "than", "then", "them", "they", "their", "there",
    "here", "into", "only", "also", "such", "some", "like", "just",
    "over", "before", "after", "other", "each", "per", "via", "instead",
    "does", "done", "should", "would", "could", "must", "need", "needs",
    "task", "tasks", "skill", "skills", "code", "file", "files",
}


def extract_tail_keywords(tail, trig_limit=14, word_limit=6):
    """从被截断的描述尾部提取长尾关键词（保证冷门技能仍能被检索命中）

    分级保留（实测教训：ponytail 的 "yagni" 位于描述第 400+ 字符，
    若按出现顺序一刀切取前 N 个，会被 "senior"/"dev" 这类普通实词挤掉，
    冷门技能依旧检索不到 —— 省了 token 却丢了可用性）：
      ① 引号内短语 —— 作者显式设计的触发条件，优先级最高
      ② 全大写专有词 —— YAGNI / TDD / MCP 这类高信号缩写
      ③ 英文实词 + 中文词组 —— 兜底，限额最小
    """
    # 摘要是按字符硬切的，尾部首词可能是被腰斩的残片，先丢弃
    if tail and not tail[0].isspace():
        sp = tail.find(" ")
        tail = tail[sp:] if sp > 0 else ""
    if not tail:
        return []

    triggers, words, seen = [], [], set()

    def _seen(x):
        low = (x or "").strip().lower()
        if not low or low in seen or low in STOPWORDS:
            return None
        seen.add(low)
        return low

    # ① 引号内短语（触发词）
    for m in re.findall(r'"([^"]{2,32})"', tail):
        v = _seen(m.strip())
        if v:
            triggers.append(v)
    # ② 全大写专有词
    for m in re.findall(r"\b[A-Z][A-Z0-9_]{1,11}\b", tail):
        v = _seen(m)
        if v:
            triggers.append(v)
    triggers = triggers[:trig_limit]
    # ③ 英文实词 + 中文词组（兜底，限额小）
    for m in re.findall(r"\b[A-Za-z][A-Za-z0-9_.\-]{2,24}\b", tail):
        low = m.lower()
        if low in STOPWORDS or len(low) < 3:
            continue
        v = _seen(low)
        if v:
            words.append(v)
    for m in re.findall(r"[\u4e00-\u9fff]{2,8}", tail):
        v = _seen(m)
        if v:
            words.append(v)
    return triggers + words[:word_limit]
BLOCK_SCALAR = {">", "|", ">-", "|-", ">+", "|+", "> ", "| "}


# ---------------------------------------------------------------- 工具函数
def now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_text(path, limit=None):
    try:
        t = path.read_text(encoding="utf-8", errors="ignore")
        return t[:limit] if limit else t
    except Exception:
        return None


def fallback_parse(content):
    """build_skill_tree 导入失败时的兜底解析（支持块标量）"""
    fm = {}
    if not content or not content.startswith("---"):
        return fm
    m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return fm
    lines = m.group(1).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if re.match(r"^[|>][+-]?[0-9]*$", v):
                block, i = [], i + 1
                while i < len(lines):
                    nx = lines[i]
                    if nx.strip() and not nx.startswith((" ", "\t")):
                        break
                    block.append(nx.strip())
                    i += 1
                fm[k] = (" " if v.startswith(">") else "\n").join(
                    x for x in block if x).strip()
                continue
            fm[k] = v
        i += 1
    return fm


def get_frontmatter(content):
    if parse_frontmatter is not None:
        try:
            return parse_frontmatter(content) or {}
        except Exception:
            pass
    return fallback_parse(content)


# ---------------------------------------------------------------- 扫描诊断
def scan(skills_dir):
    """扫描技能目录，返回 (findings, ok_list)

    findings: [{name, path, issue, severity, detail}]
    ok_list:  [{name, fm, content, categories}]
    """
    root = Path(skills_dir)
    findings, ok = [], []
    if not root.exists():
        return findings, ok

    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        # 跳过隔离区与本仓库自身之外的非技能目录（无 SKILL.md 且无子技能）
        skill_md = entry / "SKILL.md"
        if not skill_md.exists():
            # 命名空间式布局：目录下还有子目录且各自带 SKILL.md → 逐个体检
            subs = [p for p in entry.iterdir()
                    if p.is_dir() and (p / "SKILL.md").exists()]
            if subs:
                for s in subs:
                    issue, info = _check_one(s, s.name)
                    if issue:
                        findings.append(issue)
                    if info:
                        ok.append(info)
                continue
            try:
                has_any = any(entry.iterdir())
            except Exception:
                has_any = False
            findings.append({
                "name": entry.name, "path": str(entry),
                "issue": "empty_dir" if not has_any else "missing_skill_md",
                "severity": "broken",
                "detail": "空目录" if not has_any else "目录下无 SKILL.md",
            })
            continue
        issue, info = _check_one(entry, entry.name)
        if issue:
            findings.append(issue)
        else:
            ok.append(info)
    return findings, ok


def _check_one(dirpath, name):
    """检查单个技能目录 → (issue_dict|None, info_dict|None)"""
    p = Path(dirpath)
    skill_md = p / "SKILL.md"
    content = read_text(skill_md)
    if content is None:
        return ({"name": name, "path": str(p), "issue": "missing_skill_md",
                 "severity": "broken", "detail": "SKILL.md 读取失败"}, None)
    if len(content.strip()) < 20:
        return ({"name": name, "path": str(p), "issue": "empty_skill_md",
                 "severity": "broken",
                 "detail": f"SKILL.md 仅 {len(content.strip())} 字符"}, None)
    if not content.startswith("---"):
        return ({"name": name, "path": str(p), "issue": "no_frontmatter",
                 "severity": "broken", "detail": "缺少 --- frontmatter 块"}, None)
    fm = get_frontmatter(content)
    if not fm:
        return ({"name": name, "path": str(p), "issue": "no_frontmatter",
                 "severity": "broken", "detail": "frontmatter 解析为空"}, None)
    fname = (fm.get("name") or "").strip()
    desc = (fm.get("description") or "").strip()
    if not fname:
        return ({"name": name, "path": str(p), "issue": "missing_name",
                 "severity": "broken", "detail": "frontmatter 缺 name 字段"}, None)
    if not desc:
        return ({"name": name, "path": str(p), "issue": "missing_desc",
                 "severity": "invisible", "detail": "frontmatter 缺 description"}, None)
    # 区分两类"描述失效":
    #   desc 本身就是块标量符号 → 解析/索引侧问题,重建索引即可修复
    #   desc 有内容但过短(如"腾讯云 COS")→ 源文件侧问题,需人工补全描述
    if desc in BLOCK_SCALAR:
        return ({"name": name, "path": str(p), "issue": "block_scalar_residue",
                 "severity": "invisible",
                 "detail": f"description 解析为 {desc!r}（块标量未展开，"
                           f"重建索引可修复）"}, None)
    if len(desc) < SHORT_DESC_THRESHOLD:
        return ({"name": name, "path": str(p), "issue": "missing_desc",
                 "severity": "invisible",
                 "detail": f"description 过短({len(desc)} 字符): {desc!r} "
                           f"—— 源文件侧问题，需人工补全"}, None)
    issue = None
    # v2.24.0:`__skillhub` 等安装后缀是平台加的，不算命名不一致
    # （否则 110+ 条噪声会淹没真实问题）
    norm = re.sub(r"__\w+$", "", name)
    if fname != name and fname != norm and norm != re.sub(r"__\w+$", "", fname):
        issue = {"name": name, "path": str(p), "issue": "name_mismatch",
                 "severity": "warn",
                 "detail": f"目录名 {name!r} ≠ frontmatter name {fname!r}"}
    info = {"name": name, "path": str(p), "fm": fm,
            "content": content, "categories": None}
    if classify_skill is not None:
        try:
            info["categories"] = classify_skill(name, desc)
        except Exception:
            info["categories"] = None
    return (issue, info)


def index_health(tree_path):
    """检查已生成索引里有多少条描述失效（索引侧隐形）"""
    try:
        data = json.load(open(tree_path, encoding="utf-8"))
    except Exception:
        return None
    cats = data.get("categories", {}) or {}
    bad, total = [], 0
    for c, items in cats.items():
        for s in items:
            total += 1
            d = (s.get("description") or "").strip()
            if d in BLOCK_SCALAR or len(d) < SHORT_DESC_THRESHOLD:
                bad.append({"name": s.get("name", "?"), "category": c,
                            "description": d})
    return {"total": total, "bad": bad, "bad_count": len(bad)}


# ---------------------------------------------------------------- 修复
def fix_missing_name(dirpath, dirname):
    """给缺 name 字段的 SKILL.md 补上 name（平台可能因缺 name 而识别不到）

    只增不删：仅在 frontmatter 开头插入 name 行，已有 name 则不动。
    """
    p = Path(dirpath) / "SKILL.md"
    content = read_text(p)
    if content is None:
        return False, "读取失败"
    m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return False, "无 frontmatter"
    fm_text = m.group(1)
    if re.search(r"^name\s*:", fm_text, re.M):
        return False, "已有 name 字段"
    clean = re.sub(r"__\w+$", "", dirname)
    new_content = (content[:m.start(1)] + f"name: {clean}\n" + fm_text
                   + content[m.end(1):])
    try:
        p.write_text(new_content, encoding="utf-8")
        return True, f"已补 name: {clean}"
    except Exception as e:
        return False, str(e)[:80]


def rebuild_index():
    """用官方脚本重建索引（修复块标量解析导致的索引侧隐形）"""
    script = CONSTITUTION / "scripts" / "build_skill_tree.py"
    import subprocess
    r = subprocess.run([sys.executable, str(script)],
                       capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout or "")[-400:], (r.stderr or "")[-300:]


def emit_min_index(skills_dir=None, exclude_broken=True, out_path=None):
    """生成轻量索引 skill_index_min.json（省 token 的检索入口）

    保留**全部**健康技能（含冷门），只把完整描述换成短摘要；
    损坏技能排除（检索不到又白占 token）。
    """
    out_path = Path(out_path or MIN_INDEX)
    src = TREE_JSON
    skills = []
    excluded = 0
    if src.exists():
        try:
            data = json.load(open(src, encoding="utf-8"))
            cats = data.get("categories", {}) or {}
            seen = set()
            for c, items in cats.items():
                for s in items:
                    nm = s.get("name", "")
                    if not nm or nm in seen:
                        continue
                    seen.add(nm)
                    d = (s.get("description") or "").strip()
                    if exclude_broken and (d in BLOCK_SCALAR
                                           or len(d) < SHORT_DESC_THRESHOLD):
                        excluded += 1
                        continue
                    item = {"n": nm, "c": [c], "d": d[:MINI_DESC_LEN]}
                    # v2.24.0:截断补偿 —— 把被截掉部分的长尾关键词存进 k,
                    # 冷门技能才不会因省 token 而重新隐形
                    if len(d) > MINI_DESC_LEN:
                        kws = extract_tail_keywords(d[MINI_DESC_LEN:])
                        if kws:
                            item["k"] = kws
                    skills.append(item)
        except Exception:
            skills = []
    payload = {
        "v": "2.24.0",
        "generated": now_ts(),
        "source": str(src.name),
        "total": len(skills),
        "broken_excluded": excluded,
        "desc_len": MINI_DESC_LEN,
        "skills": skills,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return payload, out_path


def query_min_index(q, top=8, min_path=None):
    """用轻量索引检索（冷门技能依然可被命中）"""
    p = Path(min_path or MIN_INDEX)
    if not p.exists():
        return None
    data = json.load(open(p, encoding="utf-8"))
    ql = (q or "").lower().strip()
    toks = [t for t in re.split(r"[\s,，、]+", ql) if t]
    scored = []
    for s in data.get("skills", []):
        name = (s.get("n") or "").lower()
        desc = (s.get("d") or "").lower()
        # v2.24.0:关键词字段权重低于名字/摘要，命中即加分（截断补偿入口）
        kws = " ".join(s.get("k") or []).lower()
        score = 0
        # 短语整体命中优先：否则 "lazy mode" 会被拆成 lazy / mode
        # 各自命中，把无关技能顶到前面
        if ql and (ql in name or ql in desc or ql in kws):
            score += 10
        for t in toks:
            if t in name:
                score += 3
            if t in desc:
                score += 2
            if t in kws:
                score += 1
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [{"name": s["n"], "categories": s.get("c", []),
             "desc": s.get("d", ""), "score": sc} for sc, s in scored[:top]]


# ---------------------------------------------------------------- 报告
def report(findings, health, skills_dir, as_json=False):
    sev_order = {"broken": 0, "invisible": 1, "warn": 2}
    findings = sorted(findings, key=lambda x: (sev_order.get(x["severity"], 9),
                                               x["issue"], x["name"]))
    by_sev = {}
    by_issue = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_issue[f["issue"]] = by_issue.get(f["issue"], 0) + 1

    if as_json:
        print(json.dumps({"skills_dir": str(skills_dir),
                          "total_findings": len(findings),
                          "by_severity": by_sev, "by_issue": by_issue,
                          "index_health": health, "findings": findings},
                         ensure_ascii=False, indent=2))
        return findings

    print("=" * 64)
    print("隐形技能诊断报告  技能目录: " + str(skills_dir))
    print("生成时间: " + now_ts())
    print("=" * 64)
    if health:
        flag = "⚠️" if health["bad_count"] else "✓"
        print(f"索引健康度(skill_tree.json): {flag} 共 {health['total']} 条，"
              f"描述失效 {health['bad_count']} 条"
              f"（{health['bad_count'] * 100 // max(health['total'], 1)}%）")
        if health["bad_count"]:
            print("  → 这些技能在检索中完全命不中（装了等于隐形），"
                  "运行 --fix 重建索引即可修复")
    print(f"\n目录级问题: {len(findings)} 项"
          f"  [损坏 {by_sev.get('broken', 0)} / 隐形 "
          f"{by_sev.get('invisible', 0)} / 告警 {by_sev.get('warn', 0)}]")
    for k, v in sorted(by_issue.items(), key=lambda x: -x[1]):
        print(f"  · {k}: {v}")
    if findings:
        print("\n--- 明细（按严重度）---")
        for f in findings:
            print(f"  [{f['severity']:<9}] {f['name']:<42} {f['issue']}")
            print(f"             {f['detail']}")
    print()
    return findings


def main():
    ap = argparse.ArgumentParser(description="隐形技能诊断与修复")
    ap.add_argument("--skills", default=os.environ.get("SKILLS_DIR", DEFAULT_SKILLS),
                    help="技能目录（默认 ~/.workbuddy/skills）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--fix", action="store_true",
                    help="自动修复可修项（重建索引以修复块标量导致的索引侧隐形）")
    ap.add_argument("--quarantine", action="store_true",
                    help="把损坏技能目录移入 .broken/ 隔离（不再占索引与 token）")
    ap.add_argument("--emit-min-index", action="store_true",
                    help="生成轻量索引 skill_index_min.json（省 token 的检索入口）")
    ap.add_argument("--query", metavar="关键词", help="用轻量索引检索验证")
    ap.add_argument("--min-index", help="指定轻量索引路径")
    a = ap.parse_args()

    if a.query:
        res = query_min_index(a.query, min_path=a.min_index)
        if res is None:
            print("轻量索引不存在，请先运行 --emit-min-index", file=sys.stderr)
            return 1
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"轻量索引检索: {a.query}")
            for r in res:
                print(f"  {r['score']:>2}  {r['name']}  [{','.join(r['categories'])}]")
                print(f"      {r['desc']}")
            if not res:
                print("  （无命中）")
        return 0

    if a.emit_min_index:
        payload, out = emit_min_index(a.skills, out_path=a.min_index)
        full = TREE_JSON.stat().st_size if TREE_JSON.exists() else 0
        mini = out.stat().st_size
        pct = (mini * 100 // full) if full else 0
        if a.json:
            print(json.dumps({"out": str(out), "total": payload["total"],
                              "broken_excluded": payload["broken_excluded"],
                              "mini_bytes": mini, "full_bytes": full,
                              "ratio_pct": pct}, ensure_ascii=False, indent=2))
        else:
            print(f"✓ 轻量索引已生成: {out}")
            print(f"  健康技能 {payload['total']} 个，排除损坏 "
                  f"{payload['broken_excluded']} 个")
            print(f"  体积 {mini // 1024}KB / 完整索引 {full // 1024}KB "
                  f"≈ 完整的 {pct}%（省 {100 - pct}%）")
        return 0

    findings, ok = scan(a.skills)
    health = index_health(TREE_JSON)
    report(findings, health, a.skills, as_json=a.json)

    if a.fix or a.quarantine:
        fixed = []
        if a.fix:
            # ① 补缺失的 name 字段（缺 name 平台可能压根识别不到，典型隐形）
            for f in list(findings):
                if f["issue"] != "missing_name":
                    continue
                okfix, msg = fix_missing_name(f["path"], f["name"])
                fixed.append((("✓ 补 name " if okfix else "✗ 补 name ")
                              + f["name"] + " → " + msg))
            # ② 重建索引修复块标量解析导致的索引侧隐形
            if health and health.get("bad_count"):
                rc, out, err = rebuild_index()
                if rc == 0:
                    fixed.append(f"重建索引，修复 {health['bad_count']} 条失效描述")
                    # 重建后重新体检，向用户如实回报告结果
                    h2 = index_health(TREE_JSON)
                    if h2:
                        fixed.append(f"复检：失效描述 {health['bad_count']} → "
                                     f"{h2['bad_count']}")
                else:
                    fixed.append(f"重建索引失败(rc={rc}): {(err or out)[:200]}")
        if a.quarantine:
            bdir = Path(a.skills) / BROKEN_DIR_NAME
            moved = 0
            for f in findings:
                if f["severity"] != "broken":
                    continue
                src = Path(f["path"])
                if not src.exists():
                    continue
                bdir.mkdir(exist_ok=True)
                dst = bdir / src.name
                try:
                    if dst.exists():
                        dst = bdir / (src.name + "_" + str(int(time.time())))
                    shutil.move(str(src), str(dst))
                    moved += 1
                except Exception as e:
                    fixed.append(f"隔离失败 {src.name}: {str(e)[:80]}")
            if moved:
                fixed.append(f"已隔离损坏技能 {moved} 个到 {bdir}")
        if not a.json:
            print("--- 修复动作 ---")
            for line in (fixed or ["无可自动修复项"]):
                print("  · " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
