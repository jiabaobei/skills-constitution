#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_skill_rankings — 技能推荐排行榜快照生成器 (v2.25.0 新增)

目的(宪法第五条"答复推荐"极度省 token 改造):
  旧版要求 Agent 每次答复都"去 GitHub 全盘搜索"高星技能 —— 一个任务一次
  WebSearch/WebFetch,长期下来 token 消耗巨大。本脚本把"搜索"降频为
  "抓一次、存本地、读快照":

    ① 本脚本(低频, 建议每次发布会/每周手动跑一次):
       从权威排行榜仓库拉取 Top N 技能 → 生成本地 JSON 快照
       data/skill_rankings.json(仓库自带作者快照, 用户可自行刷新)
    ② recommend_skills.py(高频, 每次答复推荐时跑):
       纯本地读快照 → 任务关键词匹配 → 排除已装 → 星数排序 → 出 3 条
       零网络请求, token 成本 = 读一个 ~20KB 本地文件

数据源(默认, 可信度 + 可持续维护):
  quemsah/awesome-claude-plugins
    GitHub README "Awesome Claude Code Plugins: Top 100 Repositories"
    - raw.githubusercontent.com 直出 markdown, 无 API 限流
    - 索引 3.6 万+ 仓库, 表格人工/程序筛选, 更新频繁(实测 2026-08-31)
    - 字段: rank / repo / desc / stars / subs / plugins 全为数字, 解析确定性高
  备选(--source skilld): skilld.dev/skills/leaderboard(单技能级, HTML 解析较重)

用法:
  python scripts/update_skill_rankings.py                 # 默认 quemsah 源
  python scripts/update_skill_rankings.py --out data/skill_rankings.json
  python scripts/update_skill_rankings.py --input README.md   # 离线: 从本地文件解析
  python scripts/update_skill_rankings.py --source skilld    # 切换 skilld 源

失败安全: 网络失败/解析异常 → 退出码 1, 不覆盖已有快照(旧快照继续可用)。
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SOURCE_QUEMSAH = {
    "id": "quemsah/awesome-claude-plugins",
    "url": "https://raw.githubusercontent.com/quemsah/awesome-claude-plugins/main/README.md",
    "title": "Awesome Claude Code Plugins: Top 100 Repositories",
}
SOURCE_SKILLD = {
    "id": "skilld.dev",
    "url": "https://skilld.dev/skills/leaderboard",
    "title": "Top Skill Repositories on GitHub",
}
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "skill_rankings.json")
DEFAULT_STALE_DAYS = 30  # 快照超过此天数视为过期(仅提示, 不自动拉取)
TOP_N = 100

# keywords 提取停用词(极小集合, 只滤模板套话, 不滤实义词)
_STOP = {
    "a", "an", "the", "and", "or", "for", "with", "your", "that", "this",
    "from", "into", "when", "use", "uses", "using", "used", "you", "can",
    "any", "all", "its", "are", "was", "were", "not", "but", "has", "have",
    "skill", "skills", "agent", "agents", "ai", "make", "makes", "making",
    "work", "works", "working", "code", "claude", "openai", "github", "tool",
    "tools", "project", "projects", "file", "files", "via", "will", "well",
}


def _fetch(url, timeout=20):
    """抓取远程文本(UTF-8 优先, 失败抛异常由调用方处理)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "skills-constitution/2.26.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_keywords(name, desc, limit=20):
    """从技能名+描述提取匹配用关键词(英文小写词, 去停用词, 保序去重)。"""
    text = f"{name} {desc}".lower()
    words = re.findall(r"[a-z][a-z0-9\-]{2,}", text)
    seen, out = set(), []
    for w in words:
        w2 = w.strip("-")
        if len(w2) < 3 or w2 in _STOP or w2 in seen:
            continue
        seen.add(w2)
        out.append(w2)
        if len(out) >= limit:
            break
    return out


def parse_quemsah(md_text):
    """解析 quemsah README 的 Top100 表格。

    表格行格式:
      | 1 | [superpowers](https://github.com/obra/superpowers) | desc | 279372 | 1026 | 1 |
    返回: (items, meta)  items=[{rank,name,owner,repo,stars,subs,plugins,desc,keywords}]
    """
    items = []
    meta = {"total_indexed": 0, "last_updated": ""}
    # 元信息: "Last updated: 16.08.2026 with 33702 total repositories indexed."
    m = re.search(r"Last updated:\s*([\d.]+)", md_text)
    if m:
        meta["last_updated"] = m.group(1)
    m2 = re.search(r"(\d[\d,]*)\s+total repositories indexed", md_text)
    if m2:
        meta["total_indexed"] = int(m2.group(1).replace(",", ""))
    for line in md_text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # 跳过表头/分隔行
        if len(cells) < 6:
            continue
        if not cells[0].strip().isdigit():
            continue
        rank = int(cells[0])
        rm = re.match(r"\[([^\]]+)\]\(https://github\.com/([^/]+)/([^/]+)\)", cells[1])
        if not rm:
            continue
        name, owner, repo = rm.group(1), rm.group(2), rm.group(3)
        desc = cells[2]
        try:
            stars = int(cells[3].replace(",", ""))
            subs = int(cells[4].replace(",", ""))
            plugins = int(cells[5].replace(",", ""))
        except ValueError:
            continue
        items.append({
            "rank": rank, "name": name, "owner": owner, "repo": repo,
            "stars": stars, "subs": subs, "plugins": plugins,
            "desc": desc, "keywords": extract_keywords(name, desc),
        })
    return items, meta


def parse_skilld(html_text):
    """解析 skilld.dev 排行榜(单技能级)。

    HTML 结构复杂且可能变化, 此源为备选: 只尽力解析出
    (skill_name, owner/repo, stars) 三元组; 解析不到则抛异常。
    """
    items = []
    # 形如: 01 brainstormingobra/superpowers272,360★ ...
    pattern = re.compile(
        r"(\d{2})\s+([a-z0-9\-]+)\s*([a-zA-Z0-9\-]+)/([a-zA-Z0-9\-]+)\s*([\d,]+)\s*★",
        re.IGNORECASE)
    for m in pattern.finditer(html_text):
        rank = int(m.group(1))
        name, owner, repo = m.group(2), m.group(3), m.group(4)
        stars = int(m.group(5).replace(",", ""))
        items.append({
            "rank": rank, "name": name, "owner": owner, "repo": repo,
            "stars": stars, "subs": 0, "plugins": 0,
            "desc": "", "keywords": extract_keywords(name, ""),
        })
    if not items:
        raise ValueError("skilld 源解析不到任何条目(页面结构可能已变)")
    return items, {"last_updated": "", "total_indexed": 0}


def build_snapshot(items, source, meta, updated, stale_days=DEFAULT_STALE_DAYS):
    """组装快照 JSON 结构。"""
    return {
        "format": 1,
        "source": source["id"],
        "source_url": source["url"],
        "title": source["title"],
        "updated": updated,              # 快照生成日期 YYYY-MM-DD
        "stale_days": stale_days,        # 过期阈值(仅提示用)
        "count": len(items),
        "meta": meta,
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser(description="生成技能推荐排行榜快照(v2.25.0)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="快照输出路径")
    ap.add_argument("--input", help="从本地文件解析(离线, 跳过网络)")
    ap.add_argument("--source", choices=["quemsah", "skilld"], default="quemsah",
                    help="数据源(默认 quemsah)")
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                    help="快照过期阈值天数")
    a = ap.parse_args()

    source = SOURCE_QUEMSAH if a.source == "quemsah" else SOURCE_SKILLD
    if a.input:
        try:
            with open(a.input, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            print(f"[update_skill_rankings] 读取本地文件失败: {e}", file=sys.stderr)
            return 1
        print(f"[update_skill_rankings] 从本地文件解析: {a.input}")
    else:
        try:
            print(f"[update_skill_rankings] 抓取 {source['url']} ...")
            raw = _fetch(source["url"])
        except Exception as e:  # noqa: BLE001 — 网络失败不覆盖旧快照
            print(f"[update_skill_rankings] 抓取失败: {e}", file=sys.stderr)
            print("  已有快照未被覆盖, 仍可使用。可稍后重试或用 --input 离线解析。",
                  file=sys.stderr)
            return 1

    try:
        if a.source == "skilld":
            items, meta = parse_skilld(raw)
        else:
            items, meta = parse_quemsah(raw)
    except Exception as e:  # noqa: BLE001
        print(f"[update_skill_rankings] 解析失败: {e}", file=sys.stderr)
        return 1

    if not items:
        print("[update_skill_rankings] 未解析到任何条目, 放弃写入", file=sys.stderr)
        return 1

    items = items[:TOP_N]
    today = date.today().isoformat()
    snap = build_snapshot(items, source, meta, today, a.stale_days)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    os.replace(tmp, a.out)  # 原子替换, 失败不损坏旧快照
    print(f"[update_skill_rankings] 已生成快照: {a.out}")
    print(f"  条目数: {len(items)} | 来源: {source['id']} | 日期: {today}")
    top3 = ", ".join(f"{i['name']}({i['stars']})" for i in items[:3])
    print(f"  Top3: {top3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
