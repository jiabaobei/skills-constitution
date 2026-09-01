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
  python pre-hook.py --task "爬虫" --json            # JSON 输出(机器可读,含 sad_candidates)
  python pre-hook.py --check --input agent_opening.txt  # 校验开场是否已注入(宿主hook用)
  python pre-hook.py --check --input agent_opening.txt --strict  # 校验失败 exit 1

v2.12.0:
  - 任务同义词扩展(TASK_SYNONYM_MAP):"把代码传上去"等口语表达也能命中 git/push 必需分类
  - SAD 宽松语义检索(loose_retrieve_skills):零依赖 token 重叠打分,注入 top-K 候选技能

v2.21.0:
  - 双机制平台覆盖:技能树 = 独立技能 ∪ 插件技能(插件缓存扫描见 build_skill_tree.py);
    注入块与 SAD 候选展示插件技能的完整调用名(插件名:技能名,如 document-skills:docx),
    命中插件技能后按完整调用名调用 —— 在 ZCode 等双机制平台上裸技能名可能无法被 Skill 机制加载

v2.22.0:
  - 注入块 token 瘦身:SAD 候选 6→4 条、描述截断 60→40 字、每分类技能清单 12→8 个、
    记忆片段上限 1200→900 字、执行要求文案精简(单次注入约省 30% token)

返回码:
  --check 模式: 0=注入合规, 1=缺注入(宿主 hook 应阻断任务)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from lib.text import overlap_score, keyword_in
except ImportError:
    def keyword_in(text, kw):  # 兜底:与 lib.text 同逻辑(英文词边界,中文子串)
        t, k = (text or "").lower(), (kw or "").lower()
        if not k:
            return False
        if all(ord(c) < 128 for c in k):
            return re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) is not None
        return k in t

    def overlap_score(text_a, text_b):  # 兜底:与 lib.text 同逻辑(零依赖轻语义)
        word_re = re.compile(r"[a-z0-9][a-z0-9_\-\.]*")
        cjk_re = re.compile(r"[一-鿿]")
        def tok(text):
            t = (text or "").lower()
            words = word_re.findall(t)
            tokens = set(words)
            for w in words:
                if "-" in w or "_" in w or "." in w:
                    for part in re.split(r"[_\-\.]", w):
                        if part:
                            tokens.add(part)
            chars = cjk_re.findall(t)
            tokens.update(chars)
            for i in range(len(chars) - 1):
                tokens.add(chars[i] + chars[i + 1])
            return {x for x in tokens if x.strip()}
        a, b = tok(text_a), tok(text_b)
        if not a or not b:
            return 0.0
        inter = set(a & b)
        a_ascii = {t for t in a if t.isascii() and len(t) >= 3}
        b_ascii = {t for t in b if t.isascii() and len(t) >= 3}
        for x in a_ascii:
            for y in b_ascii:
                if x != y and (x in y or y in x):
                    inter.add(x)
                    break
        return len(inter) / max(1, min(len(a), len(b)))

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

# v2.11.0 新增:任务关键词 → 必需技能分类(确定性映射,用于硬校验)
# 当任务命中以下任一关键词时,Agent 输出必须引用对应分类下的实际技能名,
# 否则视为"查了技能树但没找到任务相关技能"——硬校验 FAIL。
# 关键词按优先级排列(越靠前越强),命中即映射到必需分类。
REQUIRED_CATEGORY_KEYWORDS = [
    # (任务关键词, 必需分类列表)
    ("git", ["code"]), ("github", ["code"]), ("push", ["code"]),
    ("commit", ["code"]), ("deploy", ["code"]), ("部署", ["code"]),
    ("代码", ["code"]), ("编码", ["code"]), ("编程", ["code"]),
    ("写一个", ["code"]), ("实现", ["code"]), ("开发", ["code"]),
    ("爬虫", ["browser", "data"]), ("抓取", ["browser", "data"]),
    ("网页", ["browser"]), ("网站", ["browser"]), ("前端", ["browser"]),
    ("浏览器", ["browser"]), ("自动化", ["browser", "automation"]),
    ("文档", ["doc"]), ("word", ["doc"]), ("excel", ["doc"]),
    ("ppt", ["doc"]), ("pdf", ["doc"]), ("表格", ["doc", "data"]),
    ("邮件", ["email"]), ("发送邮件", ["email"]),
    ("数据", ["data"]), ("分析", ["data"]), ("报表", ["data"]),
    ("图表", ["data"]), ("可视化", ["data"]),
    ("图片", ["image"]), ("图像", ["image"]), ("设计", ["image"]),
    ("视频", ["video"]), ("剪辑", ["video"]),
    ("搜索", ["search"]), ("查询", ["search"]),
    ("记忆", ["memory"]), ("知识库", ["memory"]),
    ("金融", ["finance"]), ("股票", ["finance"]), ("基金", ["finance"]),
    ("文件", ["file"]),
    # v2.12.1 宪法自举：安装/配置/元规则类任务必须查 meta 分类
    # 覆盖单复数：skill / skills / 技能
    ("skill", ["meta"]), ("skills", ["meta"]), ("技能", ["meta"]),
    ("安装", ["meta"]), ("install", ["meta"]), ("配置", ["meta"]),
    ("元规则", ["meta"]), ("元规则层", ["meta"]), ("宪法", ["meta"]),
]


# v2.12.0 新增:任务同义词扩展表(SAD 第一轮"用词对齐"的确定性实现)
# 痛点(v2.11.0 真实漏洞):用户说"我要把代码传上去",无 git/push 关键词 →
# Layer C 失效。口语/近义表达先映射到正式关键词,再走原有关键词映射,
# 不依赖 Agent 自觉联想,也不需要 LLM-in-loop。
TASK_SYNONYM_MAP = {
    # 代码/版本管理口语
    "传上去": ["git", "push", "推送"], "推上去": ["git", "push", "推送"],
    "上传代码": ["git", "push", "推送"], "同步代码": ["git", "push", "commit"],
    "提交代码": ["git", "commit"], "拉代码": ["git", "clone"],
    "签入": ["git", "commit"], "检出": ["git", "clone"],
    "上线": ["部署", "deploy"], "发布": ["部署", "deploy"],
    # 爬虫/数据口语
    "抓一下": ["抓取", "爬虫"], "爬一下": ["爬虫", "抓取"],
    "采集": ["抓取", "数据"], "抓点": ["抓取", "爬虫"],
    # 文档/办公口语
    "做幻灯片": ["ppt"], "做个表": ["excel", "表格"],
    "写个文档": ["word", "文档"], "画个图": ["图表", "图片"],
    # 通信口语
    "发个邮件": ["邮件", "发送邮件"], "发邮件": ["邮件", "发送邮件"],
    # 检索口语
    "查一下": ["查询", "搜索"], "搜一下": ["搜索", "查询"],
    # 文件口语
    "整理文件": ["文件"], "清理文件": ["文件"],
}


def expand_task_text(task):
    """v2.12.0:同义词扩展 — 把口语表达蕴含的正式关键词追加到任务文本后

    返回扩展后的文本,供关键词匹配使用(仅召回侧扩展,不改原任务)。
    """
    t = (task or "").lower()
    extra = []
    for phrase, implied in TASK_SYNONYM_MAP.items():
        if phrase.lower() in t:
            extra.extend(implied)
    if not extra:
        return task or ""
    return (task or "") + " " + " ".join(extra)


def required_categories_for_task(task):
    """v2.11.0:按任务关键词返回必需技能分类(确定性,非 Agent 自觉)
    v2.12.0:先经同义词扩展(TASK_SYNONYM_MAP)再匹配,口语表达不再漏判。
    v2.19.0:英文关键词改词边界匹配 —— 修复 "rapid" 误命中 "api"、
    "research" 误命中 "search" 等子串碰撞导致的误强制。

    返回 list[str],如 ["code"] / ["browser","data"] / [] (无强相关)
    这是硬校验的依据:任务含"代码/git/部署"关键词 → 输出必须命中 code 分类技能。
    """
    if not task:
        return []
    task_lower = expand_task_text(task).lower()
    matched = []
    for kw, cats in REQUIRED_CATEGORY_KEYWORDS:
        if keyword_in(task_lower, kw):
            for c in cats:
                if c not in matched:
                    matched.append(c)
    return matched


def required_skills_for_task(tree, task):
    """v2.11.0:从技能树中提取任务必需分类下的实际技能名

    返回 (required_cats, skill_names):
      required_cats: 必需分类列表
      skill_names:   这些分类下所有技能名(去重)
    注意:排除 skills-constitution 自身——它是元规则,不是任务技能,
    写"已查 skills-constitution"不算命中 code 分类(用户反馈的真实漏洞)。
    """
    EXCLUDED_SKILLS = {"skills-constitution", "constitution-check"}
    required_cats = required_categories_for_task(task)
    if not required_cats or not tree:
        return required_cats, []
    skill_names = []
    for cat in required_cats:
        for item in tree.get(cat, []):
            if isinstance(item, dict):
                if item.get("name") and item["name"] not in EXCLUDED_SKILLS:
                    skill_names.append(item["name"])
            elif isinstance(item, str) and item not in EXCLUDED_SKILLS:
                skill_names.append(item)
    # 去重
    seen = set()
    result = []
    for s in skill_names:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return required_cats, result

# 零号条款：简单任务关键词（命中任一 → 判定简单，走通道A，不拦截）
# v2.19.0:匹配改词边界(英文) + 专业词优先(见 classify_task),
# 修复 "hi"⊂"this"、"explain"⊂"explain this bug and fix" 等碰撞导致的整体豁免逃逸。
SIMPLE_TASK_MARKERS = [
    "翻译", "润色", "改写", "解释", "解释一下", "概念", "是什么意思",
    "知识问答", "科普", "闲聊", "你好", "谢谢", "再见", "打招呼",
    "简单说明", "一句话", "概括", "总结一下这篇文章", "介绍一下",
    "translate", "paraphrase", "explain", "meaning", "greeting",
    "thank", "hi", "hello", "what is", "what's",
]

# 零号条款：专业任务关键词（命中任一 → 判定专业，走通道B，强制拦截）
# 注意:专业词保持子串匹配(宽松) —— 专业词的误报只会"多查一次",符合零号条款
# "模糊任务宁可不放过"的精神;危险方向是简单词误报导致豁免逃逸,那边用词边界收紧。
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

    v2.19.0 两处修复:
    1. 简单词用词边界匹配 —— "hi" 不再命中 "this/shift"、"explain" 不再
       豁免 "explain this bug and fix the code" 这类混合任务中的专业部分。
    2. 专业词优先 —— 同时命中简单词和专业词时判 professional
       ("帮我解释这个报错然后修复代码并部署" 不再被整体豁免)。
       专业词保持子串匹配:误报只会多查一次,符合"宁可不放过"。
    """
    if not text:
        return "ambiguous"
    text_lower = expand_task_text(text).lower()  # v2.12.0:同义词扩展后分类
    has_simple = any(keyword_in(text_lower, m) for m in SIMPLE_TASK_MARKERS)
    has_pro = any(m.lower() in text_lower for m in PROFESSIONAL_TASK_MARKERS)
    if has_pro:
        return "professional"
    if has_simple:
        return "simple"
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


def load_tree_full(tree_path=DEFAULT_TREE):
    """v2.12.0:读取 skill_tree.json 完整条目(含描述),供宽松语义检索使用

    返回 [{name, description, categories}],按技能名去重、跨分类合并。
    v2.21.0:插件技能条目额外携带 qualified_name(完整调用名 插件名:技能名)。
    """
    if not os.path.exists(tree_path):
        return []
    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)
    skills = {}
    for cat, items in tree.get("categories", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                e = skills.setdefault(item["name"], {
                    "name": item["name"], "description": "", "categories": []})
                if item.get("description") and not e["description"]:
                    e["description"] = item["description"]
                if item.get("qualified_name") and "qualified_name" not in e:
                    e["qualified_name"] = item["qualified_name"]
                if cat not in e["categories"]:
                    e["categories"].append(cat)
            elif isinstance(item, str):
                e = skills.setdefault(item, {"name": item, "description": "", "categories": []})
                if cat not in e["categories"]:
                    e["categories"].append(cat)
    return list(skills.values())


def load_skill_aliases(tree_path=DEFAULT_TREE):
    """v2.21.0:插件技能调用名映射 {技能名: 完整调用名}

    双机制平台(ZCode 等)上,插件技能要用完整调用名(插件名:技能名)才能被
    Skill 机制加载 —— 独立技能与插件技能可能同名,命中后必须按完整名调用。
    树中没有插件技能时返回 {}。
    """
    if not os.path.exists(tree_path):
        return {}
    with open(tree_path, encoding="utf-8") as f:
        tree = json.load(f)
    aliases = {}
    for items in tree.get("categories", {}).values():
        if not isinstance(items, list):
            continue
        for item in items:
            if (isinstance(item, dict) and item.get("name")
                    and item.get("qualified_name")):
                aliases.setdefault(item["name"], item["qualified_name"])
    return aliases


def loose_retrieve_skills(skills, task, top_k=4, min_score=0.08,
                          category_boost=0.25, name_boost=0.15):
    """v2.12.0 SAD 第一轮:宽松语义检索(零依赖 token 重叠打分)

    SkillWeaver SAD 反馈循环的确定性实现:
    原方案需要 LLM 草拟→检索→喂回→重写;本实现把"粗检索"环节代码化 ——
    pre-hook 先按任务与技能描述的 token 重叠度检索 top-K 候选注入上下文,
    Agent 起草方案时天然带着候选技能"重写对齐"(第二轮由 Agent 完成)。

    打分 = token 重叠度 + 必需分类加成(category_boost) + 技能名命中加成(name_boost):
    - 技能的分类命中任务必需分类(REQUIRED_CATEGORY_KEYWORDS 映射结果)时加分,
      让确定性路由信号(Layer C 同源)参与排序;
    - 任务与**技能名**有 token 交集时再加 name_boost —— 技能名是最强标识,
      避免 git-workflow 这类描述简短的技能被描述冗长的泛相关技能挤掉。

    返回 [(score, skill)],按相关度降序;排除元规则自身。
    """
    if not task or not skills:
        return []
    # v2.12.1: 只有非安装类任务才排除自身
    # 若任务含"安装/配置"等关键词，说明宪法本身就是目标，不应排除
    has_install_intent = any(k in expand_task_text(task).lower()
                             for k in ["安装", "install", "配置", "configure"])
    EXCLUDED = set() if has_install_intent else {"skills-constitution", "constitution-check"}
    required_cats = set(required_categories_for_task(task))
    expanded = expand_task_text(task)
    scored = []
    for s in skills:
        if s.get("name") in EXCLUDED:
            continue
        hay = f"{s.get('name','')} {s.get('description','')}"
        score = overlap_score(expanded, hay)
        if required_cats and (set(s.get("categories", [])) & required_cats):
            score += category_boost
        if s.get("name") and overlap_score(expanded, s["name"]) > 0:
            score += name_boost
        if score >= min_score:
            scored.append((round(score, 3), s))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return scored[:top_k]


def filter_tree_by_task(tree, task):
    """按任务关键词过滤技能树分类，返回相关分类名列表
    v2.12.0:先经同义词扩展再匹配,口语表达也能定位分类。"""
    if not task:
        return list(tree.keys())
    task_lower = expand_task_text(task).lower()
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


def extract_memory_relevant(memory_text, task, max_total=900):
    """v2.17.0 注入块记忆瘦身：只注入任务相关片段 + 关键铁律

    背景:旧逻辑按固定 marker 取前 4 个 section(各 500 字)或兜底 memory_text[:800],
    内容与任务相关性低,把技能树省下的 token 又吃回去。
    新策略:
      1. 按 '## ' 切分 MEMORY.md 为 sections
      2. 铁律优先: 标题含 死规则/铁律/宪法/偏好 → 总是注入(最多2个,各300字)
      3. 任务相关: 其余 section 按任务扩展文本重叠打分,取 top2(各400字)
      4. 兜底: 无 section 或任务无匹配 → 取前 400 字
    返回注入用文本块(不含代码围栏),总长 ≤ max_total。
    """
    if not memory_text:
        return "_（MEMORY.md 未找到）_"
    import re as _re
    sections = _re.split(r"(?m)^## ", memory_text)
    parts = []
    budget = 0
    rule_keywords = ["死规则", "铁律", "宪法", "偏好"]
    task_lower = expand_task_text(task).lower() if task else ""

    # 1) 铁律/偏好类 section 总是注入(最多 2 个,各 300 字)
    rules = []
    for s in sections[1:]:
        title = s.splitlines()[0][:40] if s.splitlines() else ""
        if any(k in title for k in rule_keywords):
            rules.append(s.strip()[:300])
    for r in rules[:2]:
        parts.append(r)
        budget += len(r)

    # 2) 任务相关 section top2(各 400 字)
    scored = []
    for s in sections[1:]:
        title = s.splitlines()[0][:40] if s.splitlines() else ""
        if any(k in title for k in rule_keywords):
            continue
        hay = (title + " " + s[:200]).lower()
        sc = overlap_score(task_lower, hay)
        if sc > 0:
            scored.append((sc, s.strip()))
    scored.sort(key=lambda x: -x[0])
    for _sc, s in scored[:2]:
        if budget < max_total:
            seg = s[:400]
            parts.append(seg)
            budget += len(seg)

    # 3) 兜底
    if not parts:
        return memory_text[:400]
    return "\n\n".join(parts)[:max_total]


def build_injection(memory_text, tree, matched_cats, task, sad_candidates=None, aliases=None):
    """生成注入块 Markdown
    v2.12.0:新增 sad_candidates(SAD 宽松语义检索 top-K 候选)渲染段落。
    v2.17.0:记忆层改用 extract_memory_relevant(任务相关+铁律,瘦身)。
    v2.21.0:新增 aliases(插件技能调用名映射)—— 双机制平台上插件技能
    以完整调用名(插件名:技能名)渲染,命中后按完整名调用。"""
    aliases = aliases or {}

    def disp(name):
        q = aliases.get(name)
        return f"{name}(调用名 `{q}`)" if q else name

    lines = []
    lines.append("## ⚡ 宪法 Pre-hook 注入（任务开始前强制注入，禁止跳过）")
    lines.append("")
    lines.append(f"> 任务: {task or '(未指定)'} — 以下内容由代码强制注入，Agent 无需自行检索。")
    lines.append("")

    # 记忆层注入（v2.17.0: 只注入任务相关片段+铁律,避免记忆吃掉技能树省下的 token）
    lines.append("### 📜 记忆层（MEMORY.md 关键规则，必须遵循）")
    mem_block = extract_memory_relevant(memory_text, task)
    lines.append("```")
    lines.append(mem_block)
    lines.append("```")
    lines.append("")

    # 技能树注入
    lines.append("### 🗂️ 技能树（相关分类，Agent 应先查此处再动手）")
    if aliases:
        example = next(iter(aliases.values()))
        lines.append(f"> 双机制平台（v2.21.0）：技能树含 {len(aliases)} 个插件技能，"
                     f"命中插件技能时按完整调用名调用（如 `{example}`）。")
    for cat in matched_cats:
        skills = tree.get(cat, [])
        if skills:
            lines.append(f"- **{cat}** ({len(skills)}): {', '.join(disp(n) for n in skills[:8])}{'...' if len(skills) > 8 else ''}")
    lines.append("")

    # v2.11.0 必需技能清单注入（硬校验依据）
    required_cats, required_skills = required_skills_for_task(tree, task)
    if required_skills:
        lines.append("### 🎯 任务必需技能（v2.11.0 硬校验：输出必须引用其一，否则判定 FAIL）")
        for cat in required_cats:
            cat_skills = [s for s in required_skills if s in tree.get(cat, [])]
            if cat_skills:
                lines.append(f"- **{cat}** 分类命中候选: {', '.join(cat_skills[:10])}")
        lines.append("")

    # v2.12.0 SAD 候选技能注入（宽松语义检索 top-K，起草方案时对齐用词）
    # v2.21.0:插件技能以完整调用名渲染(双机制平台按完整名调用)
    if sad_candidates:
        lines.append("### 🧠 SAD 候选技能（v2.12.0 宽松语义检索 top-K，按相关度排序）")
        for score, s in sad_candidates:
            desc = (s.get("description") or "")[:40]
            cats = "/".join(s.get("categories", [])[:3])
            qname = s.get("qualified_name")
            label = f"`{qname}`（插件）" if qname else f"`{s['name']}`"
            lines.append(f"- {label} ({cats}, 相关度 {score}): {desc}")
        lines.append("")
        lines.append("> **SAD 流程**：先草拟执行方案 → 对照以上候选技能修订用词与粒度 → 再输出【宪法三查】。"
                     "候选均不相关时才允许声明\"技能树无匹配\"。")
        lines.append("")

    lines.append("**执行要求：**")
    lines.append("1. 首句输出【宪法三查】,②技能树必须列出命中技能名清单(禁止只写'已读技能树')")
    lines.append("2. 命中技能必调用;无命中声明'技能树无匹配'再走通用能力")
    lines.append("3. 完成后输出【本次相关技能推荐】:本地技能不够用时去 GitHub 搜高 Star 技能推荐(链接+star+获取方式),排除已装")
    lines.append("")
    return "\n".join(lines)


def check_injection(text, memory_path=DEFAULT_MEMORY, tree_path=DEFAULT_TREE, task=None):
    """校验文本是否包含注入块元素（宿主 hook 用）

    v2.11.0 增强:传入 task 后,若任务含"代码/git/部署"等关键词,
    输出文本必须引用对应分类下的实际技能名(从 skill_tree.json 读取),
    否则视为"查了技能树但未命中任务相关技能" → FAIL。

    v2.19.0 修复:
    - tree 未初始化导致 UnboundLocalError(skill_tree.json 缺失且传 --task 时崩溃)
    - 全部匹配改词边界;废除"分类名出现即算命中"兜底 —— 必需技能校验只认实际技能名
    """
    if not text:
        return False, "无输入文本"
    # 必须包含三查汇报
    if not re.search(r"【宪法三查】|宪法三查|三查", text):
        return False, "缺【宪法三查】汇报"
    # 必须包含记忆标记
    memory_text = load_memory(memory_path)
    if memory_text:
        memory_markers = ["铁律", "MEMORY", "技能", "宪法", "GitHub", "仓库"]
        found_mem = [m for m in memory_markers if keyword_in(text, m)]
        if len(found_mem) < 2:
            return False, f"记忆引用不足(仅命中:{found_mem})"
    # 必须包含技能树标记(树缺失时跳过该项,不再因缺文件崩溃/误拦)
    tree = load_tree(tree_path)
    if tree:
        all_cats = list(tree.keys())
        found_cat = [c for c in all_cats[:10] if keyword_in(text, c)]
        if not found_cat:
            return False, "缺技能树分类引用"

    # v2.11.0:任务必需技能硬校验 — 任务含代码/git/部署关键词时,必须命中对应分类技能名
    if task:
        required_cats, required_skills = required_skills_for_task(tree, task)
        if required_skills:
            # v2.19.0:只认实际技能名(词边界);分类名出现不再算证据
            found_skills = [s for s in required_skills if keyword_in(text, s)]
            if not found_skills:
                return False, (
                    f"任务含必需关键词但输出未引用任务相关技能"
                    f"(必需分类:{required_cats}, 候选技能示例:{required_skills[:5]})"
                )
    return True, "注入合规(三查+记忆+技能树均已覆盖)"


def main():
    ap = argparse.ArgumentParser(description="宪法 Pre-hook: 任务前强制注入记忆+技能树")
    ap.add_argument("--task", help="任务描述(用于过滤技能树分类;check模式用于任务必需技能硬校验)")
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
        if a.task:
            task_text = a.task
        elif a.input:
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
        ok, msg = check_injection(text, a.memory, a.tree, a.task)
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
    # v2.12.0:SAD 宽松语义检索候选(top-K)
    sad_candidates = loose_retrieve_skills(load_tree_full(a.tree), a.task) if a.task else []
    # v2.21.0:插件技能调用名映射(双机制平台按完整名调用)
    aliases = load_skill_aliases(a.tree)
    injection = build_injection(memory_text, tree, matched_cats, a.task, sad_candidates, aliases)

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
            "sad_candidates": [
                {"name": s["name"], "score": sc, "categories": s.get("categories", []),
                 "qualified_name": s.get("qualified_name", "")}
                for sc, s in sad_candidates
            ],
            "plugin_skills": len(aliases),
            "injection": injection,
        }, ensure_ascii=False, indent=2))
    else:
        print(injection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
