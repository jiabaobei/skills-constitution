# -*- coding: utf-8 -*-
"""Step4 校验:交付自检(版本/文件核查;非版本类任务自动跳过)
v2.12.0 新增:多技能编排兼容性检查 — 输出含技能链(A→B→C)时,
按 registry.json 的 input/output schema 校验相邻技能输出→输入是否兼容。"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import state as S
from lib import text as T

NAME = "step4"
DESC = "交付自检"


def _default_registry():
    """registry.json 在 skills-constitution/ 目录(scripts 的父目录)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    constitution_dir = os.path.dirname(script_dir)
    return os.path.join(constitution_dir, "registry.json")


def extract_skill_chain(text):
    """提取输出中的技能链:`skill-a` → `skill-b` → `skill-c`

    识别 `反引号技能名` 之间由 →/->/⇒/然后/接着/再 连接的序列;
    只有 >=2 个技能才视为编排链。返回技能名列表(保序)。
    """
    if not text:
        return []
    chain = []
    pattern = re.compile(
        r"`([\w\-\.]+)`\s*(?:→|->|⇒|然后|接着|→再|然后再|再交给|再给)\s*`([\w\-\.]+)`")
    for m in pattern.finditer(text):
        a, b = m.group(1), m.group(2)
        if not chain:
            chain.append(a)
        elif chain[-1] != a:
            # 链断开了,重新开始(保守处理)
            chain.append(a)
        chain.append(b)
    # 去重保序的相邻对即可,这里返回完整序列
    return chain


def check_chain_compatibility(chain, registry_path=None):
    """按 registry schema 校验相邻技能 output→input 兼容性

    规则(保守,防误杀):
    - 技能不在 registry / 无 schema → 该相邻对跳过(unknown,不判负)
    - 相邻对 schema 齐全且 output ∩ input = ∅ → 不兼容,FAIL
    """
    registry_path = registry_path or _default_registry()
    if not chain or len(chain) < 2 or not os.path.exists(registry_path):
        return True, "无技能链或无 registry,跳过编排兼容性检查", "SKIP"
    try:
        with open(registry_path, encoding="utf-8") as f:
            reg = json.load(f)
    except Exception as e:
        return True, f"registry 读取失败(放行):{e}", "SKIP"
    schemas = {s["name"]: s for s in reg.get("skills", [])}
    problems = []
    checked = 0
    for a, b in zip(chain, chain[1:]):
        sa, sb = schemas.get(a), schemas.get(b)
        if not sa or not sb:
            continue
        out_a = set(sa.get("output_schema") or [])
        in_b = set(sb.get("input_schema") or [])
        if not out_a or not in_b:
            continue
        checked += 1
        if not (out_a & in_b):
            problems.append(f"`{a}` 输出 {sorted(out_a)} ≠ `{b}` 输入 {sorted(in_b)}")
    if problems:
        return False, "技能编排不兼容: " + "; ".join(problems), "FAIL"
    if checked:
        return True, f"编排兼容性通过({checked} 对相邻技能已校验)", "PASS"
    return True, "链中技能无 schema 覆盖,跳过兼容性判断", "SKIP"


def check(text):
    if not text or not text.strip():
        return False, "无输入文本", "FAIL"
    # v2.12.0:多技能编排兼容性检查(优先于版本自检,任何任务类型都可能含技能链)
    chain = extract_skill_chain(text)
    if len(chain) >= 2:
        ok, msg, level = check_chain_compatibility(chain)
        if level == "FAIL":
            return False, f"LayerDAG FAIL: {msg}", "FAIL"
    # 非版本交付类任务(无版本/文件核查关键词)→ SKIP,视为通过(不强制)
    versionish = T.has_any(text, "CHANGELOG", "README", "版本", "v2.", "v1.", "核查", "全文件", "frontmatter", "徽章", "一致")
    if not versionish:
        return True, "非版本交付类任务,跳过自检", "SKIP"
    # 版本类任务:需含版本号 + 核查痕迹
    if T.has_any(text, "CHANGELOG", "核查", "全文件", "一致", "同步"):
        if T.version_numbers(text):
            return True, "版本交付已含版本号与核查痕迹", "PASS"
        return False, "版本类任务缺版本号", "FAIL"
    return False, "版本类任务缺 CHANGELOG/核查痕迹", "FAIL"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--input", help="输入文本文件")
    ap.add_argument("--state", help="状态文件路径")
    a = ap.parse_args()
    text = T.read_input(a.input)
    passed, msg, level = check(text)
    S.set_step(NAME, passed, msg, level, a.state)
    print(f"[{level}] {NAME} - {DESC}: {msg}")
    sys.exit(0 if passed else 1)
