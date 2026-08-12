# -*- coding: utf-8 -*-
"""文本提取与匹配工具(零依赖,Python 标准库)"""
import re
import sys


def read_input(path=None):
    """读取输入文本:优先文件,缺省读 stdin"""
    if path:
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
