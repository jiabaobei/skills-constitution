# -*- coding: utf-8 -*-
"""文本提取与匹配工具(零依赖,Python 标准库)"""
import re
import sys


def read_input(path=None):
    """读取输入文本:优先文件,缺省读 stdin;'-' 表示显式 stdin(v2.14.0: 修复 Stop 钩子传 --input - 报 FileNotFoundError)"""
    if path and path != "-":
        with open(path, encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


def has(text, *keywords):
    """所有关键词都出现"""
    t = text or ""
    return all(k in t for k in keywords)


def has_any(text, *keywords):
    """任一关键词出现"""
    t = text or ""
    return any(k in t for k in keywords)


def github_links(text):
    """提取 github.com/owner/repo 链接"""
    return re.findall(r"github\.com/[\w\-\.]+/[\w\-\.]+", text or "")


def star_count(text):
    """提取 star 数标记:5k★ / 40K+★ / 12.5k stars / 21.1k 星"""
    t = text or ""
    return re.findall(r"\d[\d\.]*\s*[kK]?\s*(?:★|⭐|star|stars|星)", t)


def version_numbers(text):
    """提取版本号 v1.2.3 / 1.2.3"""
    return re.findall(r"v?\d+\.\d+(?:\.\d+)?", text or "")


# ---------------- v2.12.0 零依赖轻语义工具 ----------------
# 设计原则:确定性、零依赖(标准库)、任何平台可跑。
# 重依赖语义模型(sentence-transformers/cross-encoder)走可选脚本 semantic_index.py,
# 主链路永远可用这组轻量实现兜底。

_CJK_RE = re.compile(r"[一-鿿]")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-\.]*")


def is_ascii_keyword(kw):
    """关键词是否为纯 ASCII(英文关键词用词边界匹配,中文用子串)"""
    return all(ord(c) < 128 for c in kw)


def keyword_in(text, kw):
    """关键词命中判断(v2.12.0 修复子串误杀)

    - 英文关键词:词边界正则匹配 — "code" 不再误杀 "encode",
      "search" 不再误杀 "research"(v2.11.0 及以前的子串匹配缺陷)
    - 中文关键词:保持子串匹配(中文无词边界)
    """
    t = (text or "").lower()
    k = (kw or "").lower()
    if not k:
        return False
    if is_ascii_keyword(k):
        return re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) is not None
    return k in t


def tokenize(text):
    """零依赖分词:英文/数字按词切分(连字符词再拆子词),中文按单字+二元组切分

    用于轻量语义重叠度计算,不依赖任何第三方库。
    连字符拆分: "git-workflow-and-versioning" → 整词 + git/workflow/and/versioning,
    保证技能名中的子词也能参与匹配。
    """
    t = (text or "").lower()
    words = _WORD_RE.findall(t)
    tokens = set(words)
    for w in words:
        if "-" in w or "_" in w or "." in w:
            for part in re.split(r"[_\-\.]", w):
                if part:
                    tokens.add(part)
    cjk_chars = _CJK_RE.findall(t)
    # 中文单字 + 二元组,兼顾召回与精度
    tokens.update(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    return {tok for tok in tokens if tok.strip()}


def _token_intersection(a_tokens, b_tokens):
    """精确交集 + ASCII 子串近似(如 git ⊂ github 视为命中)"""
    inter = set(a_tokens & b_tokens)
    a_ascii = {t for t in a_tokens if t.isascii() and len(t) >= 3}
    b_ascii = {t for t in b_tokens if t.isascii() and len(t) >= 3}
    for x in a_ascii:
        for y in b_ascii:
            if x != y and (x in y or y in x):
                inter.add(x)
                break
    return inter


def overlap_score(text_a, text_b):
    """重叠系数 |A∩B| / min(|A|,|B|),取值 [0,1]

    比 Jaccard 更适合"短任务文本 vs 长技能描述"的场景:
    只要任务里的关键词大部分出现在技能描述中,得分就高。
    交集含 ASCII 子串近似(git/github),避免同族词误判为零相关。
    """
    a, b = tokenize(text_a), tokenize(text_b)
    if not a or not b:
        return 0.0
    return len(_token_intersection(a, b)) / max(1, min(len(a), len(b)))
