#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recommend_skills — 宪法第五条"答复推荐"的本地快照推荐器 (v2.25.0 新增)

极度省 token 原则的落地:
  旧版: Agent 每次答复推荐都要去 GitHub 全盘搜索(WebSearch/WebFetch) →
        每次任务烧一堆 token。
  新版: 推荐环节只读本地排行榜快照 data/skill_rankings.json ——
        纯本地、零网络、~20KB 文件, 匹配+排序全部确定性规则, 不调用 LLM。

用法(推荐环节, Agent 或用户均可直接跑):
  python scripts/recommend_skills.py --task "帮我写 PPT 汇报"
  python scripts/recommend_skills.py --task "爬取网页数据" --skills-dir ~/.workbuddy/skills
  python scripts/recommend_skills.py --task "代码审查" --top 3

行为:
  1. 读本地快照(默认 data/skill_rankings.json, 可 --snapshot 指定)
  2. 任务文本分词(英文词 + 中文词), 与条目 keywords/name/desc 做子串匹配
  3. 排除本地已装技能(repo 名/技能名与本地技能目录同名则剔除)
  4. 按"命中数优先, 星数次之"排序, 取前 N(默认 3)
  5. 零命中 → 按星数取 Top N(仍排除已装), 保证任何任务都有推荐
  6. 快照过期(> stale_days 天) → 输出顶部提示刷新命令, 但不自动拉取网络

输出格式天然满足 step5 校验(GitHub 链接 + star 数 + 获取方式)。
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

DEFAULT_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "skill_rankings.json")
DEFAULT_SKILLS_DIR = os.path.expanduser("~/.workbuddy/skills")
DEFAULT_TOP = 3


def _load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _task_tokens(task):
    """任务文本分词: 英文词(≥3 字符) + 中文连续片段(≥2 字)。"""
    tokens = []
    for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9\-]{2,}|[\u4e00-\u9fff]{2,}", task.lower()):
        t = m.group(0).strip("-")
        if len(t) >= 3:
            tokens.append(t)
    # 去重保序
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _match_score(item, tokens):
    """命中得分: 每个 token 在 (keywords+name+desc) 拼接中命中 +1; 星数做次级排序。"""
    hay = " ".join(item.get("keywords", [])) + " " + item.get("name", "") + " " + item.get("desc", "")
    hay_l = hay.lower()
    hits = sum(1 for t in tokens if t in hay_l)
    return hits


def _is_installed(item, skills_dir):
    """判断该排行榜条目是否已被本地安装。

    与 step5 Layer E 口径一致:
      E1: 本地技能目录名(去 __xxx 后缀)与 repo/name 同名 → 已装
      E2: 本地存在 `_<name>-references` 标记目录 → 对应框架已装
    """
    if not skills_dir or not os.path.isdir(skills_dir):
        return False
    try:
        local_dirs = os.listdir(skills_dir)
    except OSError:
        return False
    repo_l = item.get("repo", "").lower()
    name_l = item.get("name", "").lower()

    installed_frameworks = set()
    for d in local_dirs:
        if d.startswith("_") and d.endswith("-references"):
            installed_frameworks.add(d[1:].replace("-references", "").lower())
        if d.startswith("_") or d.startswith("."):
            continue
        d_base = re.sub(r"__[a-z0-9_]+$", "", d).lower()
        if repo_l and repo_l == d_base:
            return True
        if name_l and name_l == d_base:
            return True
    # E2: _<name>-references 标记的框架(如 _agent-skills-references → agent-skills)
    if repo_l and repo_l in installed_frameworks:
        return True
    if name_l and name_l in installed_frameworks:
        return True
    return False


def _age_days(updated):
    """快照年龄(天); 解析失败返回 0(视为新鲜)。"""
    try:
        d = datetime.strptime(updated, "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 0


def recommend(task, snapshot=DEFAULT_SNAPSHOT, skills_dir=DEFAULT_SKILLS_DIR,
              top=DEFAULT_TOP, out_lines=False):
    """核心推荐逻辑。返回 (lines, snapshot) 供测试与 CLI 复用。"""
    if not os.path.isfile(snapshot):
        return (["[recommend_skills] 未找到排行榜快照, 请先运行: "
                 "python scripts/update_skill_rankings.py"],
                None)

    snap = _load_snapshot(snapshot)
    items = snap.get("items", [])
    tokens = _task_tokens(task)

    scored = []
    for it in items:
        if _is_installed(it, skills_dir):
            continue
        scored.append((_match_score(it, tokens), it.get("stars", 0), it))

    # 命中数优先, 星数次之(降序)
    scored.sort(key=lambda x: (-x[0], -x[1]))
    if scored and scored[0][0] == 0:
        # 零命中: 保持按星数排序(此时即全局 Top N, 排除已装)
        pass

    picked = [it for _, _, it in scored[:top]]

    src = snap.get("source", "?")
    updated = snap.get("updated", "?")
    stale_days = snap.get("stale_days", 30)
    lines = []
    age = _age_days(updated)
    if age > stale_days:
        lines.append(f"[recommend_skills] ⚠️ 排行榜快照已过期 {age} 天"
                     f"(> {stale_days} 天), 建议运行 python scripts/"
                     f"update_skill_rankings.py 刷新; 当前仍用旧快照推荐。")
    if not picked:
        lines.append("[recommend_skills] 快照中无可用条目(可能全部已装)。")
        return lines, snap

    lines.append(f"🔍 本次相关技能推荐(来源: 本地排行榜快照, {src}, 更新于 {updated}):")
    for i, it in enumerate(picked, 1):
        url = f"https://github.com/{it['owner']}/{it['repo']}"
        star_str = f"{it['stars'] // 1000}K★" if it["stars"] >= 1000 else f"{it['stars']}★"
        desc = (it.get("desc") or "")[:120]
        lines.append(f"- {it['name']} — {desc} ({url}, {star_str})")
        lines.append(f"  安装: git clone {url}")
    return lines, snap


def main():
    ap = argparse.ArgumentParser(description="宪法第五条: 本地排行榜快照推荐(v2.25.0)")
    ap.add_argument("--task", required=True, help="任务描述(用于匹配关键词)")
    ap.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, help="排行榜快照路径")
    ap.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR,
                    help=f"本地技能目录(默认 {DEFAULT_SKILLS_DIR})")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP, help="推荐条数(默认 3)")
    a = ap.parse_args()
    lines, _ = recommend(a.task, a.snapshot, a.skills_dir, a.top)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
