# -*- coding: utf-8 -*-
"""Step5 校验:推荐板块(须含 GitHub 链接 + star 数;宪法第五条)

文章"三明治架构"延伸:推荐不是幻觉,必须有证据支撑。
本 Step 硬校验:验证 GitHub 链接格式符合 github.com/owner/repo。
(v2.19.0 文档修正:旧版注释声称"验证链接是否真实存在且可访问",
实际从未发起网络请求,只做格式校验 —— 现注释与实现保持一致。
真实存在性校验见 reference/gate-details.md 的可选增强说明。)
v2.15.0: 新增 Layer E 本地已装排除校验(推荐候选不得是本地已装技能)。
v2.25.0: 新增推荐来源标注软校验 —— 标注"本地排行榜快照"(data/skill_rankings.json)
  为省 token 最佳实践(配合 scripts/recommend_skills.py), 标注"GitHub 搜索"给出
  改用快照的提示; 未标注不判 FAIL(兼容旧 Agent)。
"""
import argparse
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step5"
DESC = "推荐板块(GitHub 高星,软+硬两层校验)"
DEFAULT_SKILLS_DIR = os.path.expanduser("~/.workbuddy/skills")


def layer_b_hard_check(text):
    """Layer B:硬校验 — 验证 GitHub 链接有效性(可选,耗时)"""
    links = T.github_links(text)
    if not links:
        return False, "无 GitHub 链接", "FAIL"

    # 简化验证:检查链接格式是否符合 github.com/owner/repo
    valid_links = []
    for link in links:
        # 提取 owner/repo
        match = re.search(r"github\.com/([^/]+)/([^/]+)", link)
        if match:
            owner, repo = match.groups()
            # 基本格式检查
            if owner and repo and len(owner) > 0 and len(repo) > 0:
                valid_links.append(link)

    if valid_links:
        return True, f"硬校验通过:{len(valid_links)} 个有效 GitHub 链接", "PASS"
    return False, "硬校验未通过:GitHub 链接格式无效", "FAIL"


def layer_e_installed_check(text, skills_dir=None):
    """Layer E(v2.15.0):本地已装排除校验 — 推荐候选不得是本地已装技能

    防的漏洞:搜索结果恰好命中本地已装仓库仍被推荐
      (如 addyosmani/agent-skills 已装 24 技能, 旧版仍会把它列为推荐)。
    E1: 推荐仓库 repo 名 与 本地技能目录名(去 __xxx 后缀)完全匹配 → FAIL
    E2: 本地存在 `_<name>-references` 已装框架标记目录, 且推荐 repo 名与该框架名
        匹配(如本地 `_agent-skills-references` 存在, 推荐 agent-skills) → FAIL
    """
    if not skills_dir:
        skills_dir = DEFAULT_SKILLS_DIR
    if not os.path.isdir(skills_dir):
        return True, "无本地技能目录,跳过排除校验", "PASS"

    links = T.github_links(text)
    if not links:
        return True, "无 GitHub 链接,跳过排除校验", "PASS"

    try:
        local_dirs = [d for d in os.listdir(skills_dir)]
    except OSError:
        return True, "无法读取本地技能目录,跳过排除校验", "PASS"

    # E1: 本地技能目录名集合(去 __skillhub 等后缀)
    local_base = set()
    for d in local_dirs:
        if d.startswith("_"):
            continue
        local_base.add(re.sub(r"__[a-z0-9_]+$", "", d).lower())

    # E2: 已装框架标记目录(_<name>-references → 框架名 <name>)
    installed_frameworks = set()
    for d in local_dirs:
        if d.startswith("_") and d.endswith("-references"):
            installed_frameworks.add(d[1:].replace("-references", "").lower())

    for link in links:
        m = re.search(r"github\.com/([^/]+)/([^/]+)", link)
        if not m:
            continue
        owner, repo = m.groups()
        repo_l = repo.lower()
        # E1: 仓库名与本地技能目录名匹配
        if repo_l in local_base:
            return False, (
                f"LayerE FAIL: 推荐仓库 {owner}/{repo} 与本地已装技能同名"
                f"(目录 {repo}),宪法第五条禁止推荐已装项"
            ), "FAIL"
        # E2: 仓库名与本地已装框架标记匹配
        if repo_l in installed_frameworks:
            return False, (
                f"LayerE FAIL: 推荐仓库 {owner}/{repo} 对应技能框架已装"
                f"(本地 {repo_l}-references 标记存在),宪法第五条禁止推荐已装项"
            ), "FAIL"
    return True, "LayerE 通过: 推荐候选均非本地已装", "PASS"


def check(text, skills_dir=None):
    """主校验函数:两层校验 + v2.15.0 Layer E 已装排除"""
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"

    # Layer A:软校验
    has_recommendation = T.has_any(text, "本次相关技能推荐", "相关技能推荐",
                                   "顺手搜了一圈", "🔍", "技能推荐")
    if not has_recommendation:
        return False, "未输出「本次相关技能推荐」板块", "FAIL"

    links = T.github_links(text)
    if not links:
        return False, "推荐板块缺 GitHub 链接(github.com/owner/repo)", "FAIL"

    if not T.star_count(text):
        return False, "推荐板块缺 star 数标记(如 20K★/45k stars)", "FAIL"

    if not T.has_any(text, "github.com", "install", "安装", "获取", "下载",
                     "git clone", "npm"):
        return False, "推荐板块缺获取方式", "FAIL"

    # v2.15.0 Layer E:本地已装排除校验(硬伤,FAIL 即整体 FAIL)
    e_passed, e_msg, e_level = layer_e_installed_check(text, skills_dir)
    if not e_passed:
        return False, e_msg, "FAIL"

    # v2.25.0 推荐来源标注(软校验,不参与 PASS/FAIL):
    # 标注"本地排行榜快照"为省 token 最佳实践, 未标注不判 FAIL(兼容旧 Agent)。
    if T.has_any(text, "排行榜快照", "skill_rankings", "本地快照"):
        src_note = "推荐来源: 本地排行榜快照(data/skill_rankings.json) ✓ 省 token 最佳实践"
    elif T.has_any(text, "GitHub 搜索", "github 搜索", "去 GitHub 搜"):
        src_note = "推荐来源: GitHub 搜索(⚠️ 每次全盘搜索费 token, 建议改用本地排行榜快照)"
    else:
        src_note = "推荐来源未标注(建议标注: 本地排行榜快照 data/skill_rankings.json)"

    # Layer A 通过,检查 Layer B
    hard_passed, hard_msg, hard_level = layer_b_hard_check(text)
    if hard_passed:
        return True, f"软+硬校验均通过; {e_msg}; {src_note}", "PASS"

    # Layer A 通过但 Layer B 未通过,降级为 WARN
    return False, f"软校验通过但硬校验未通过。{hard_msg}; {src_note}", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR,
                    help=f"本地技能目录(默认 {DEFAULT_SKILLS_DIR})")
    a = ap.parse_args()
    text = T.read_input(a.input)
    passed, msg, level = check(text, a.skills_dir)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
