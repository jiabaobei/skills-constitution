#!/usr/bin/env bash
# SessionStart hook: 注入宪法上下文到会话
# 产出 injected-context.json，并把「完整注入块」输出到 stdout（平台会注入 Agent 上下文）
#
# v2.13.2 修复（2026-08-21）:
#   1. 解释器检测: python3/python/py 逐个尝试，不再硬编码 python3（平台 hook 环境 PATH 无 python3 → tree=0）
#   2. 关键: 把 pre-hook.py 生成的完整注入块（宪法三查+记忆+技能树+SAD候选）输出到 stdout，
#      而不是只输出一行统计（此前 Agent 上下文只有 "memory=1237字 tree=0分类"，无任何可执行内容）
#   3. 无 python 环境: bash 兜底注入宪法核心条款 + 记忆原文 + 技能树路径，保证最小可执行
set -uo pipefail

PLUGIN_ROOT="${CODEBUDDY_PLUGIN_ROOT:-/c/Users/HUAWEI/.workbuddy/skills/skills-constitution}"
HOOK_DIR="${PLUGIN_ROOT}/hooks"
OUTPUT="${HOOK_DIR}/injected-context.json"
mkdir -p "${HOOK_DIR}"

# 路径转换: Git Bash /c/... → Windows C:/...（python 在 Windows 下不认 /c/）
to_win() { echo "$1" | sed 's|^/\([a-zA-Z]\)|\1:|'; }

MEMORY_FILE="${HOME}/.workbuddy/MEMORY.md"
TREE_FILE="${PLUGIN_ROOT}/skill_tree.json"
MEMORY_FILE_WIN="$(to_win "${MEMORY_FILE}")"
TREE_FILE_WIN="$(to_win "${TREE_FILE}")"

memory_len=0
tree_categories=0
injected_cats=""
sad_candidates=""
INJECTION=""

# ---- 解释器检测（关键修复1）----
PY_CMD=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then PY_CMD="$c"; break; fi
done

if [[ -f "${MEMORY_FILE}" ]]; then
  memory_len=$(wc -c < "${MEMORY_FILE}" 2>/dev/null || echo 0)
fi

# ---- 有 python: 用 pre-hook.py 生成完整注入块 ----
if [[ -n "${PY_CMD}" && -f "${TREE_FILE}" ]]; then
  tree_categories=$("${PY_CMD}" -c "import json; d=json.load(open(r'${TREE_FILE_WIN}')); print(len(d.get('categories', d) if isinstance(d, dict) else 0))" 2>/dev/null || echo 0)

  PRE_HOOK="${PLUGIN_ROOT}/scripts/pre-hook.py"
  PRE_HOOK_WIN="$(to_win "${PRE_HOOK}")"
  if [[ -f "${PRE_HOOK}" ]]; then
    TASK_DESC="${CODEBUDDY_TASK_DESC:-默认任务}"
    result=$("${PY_CMD}" "${PRE_HOOK_WIN}" --task "${TASK_DESC}" --json --memory "${MEMORY_FILE_WIN}" --tree "${TREE_FILE_WIN}" 2>/dev/null || echo '{}')
    if [[ "${result}" != '{}' && "${result}" != '' ]]; then
      INJECTION=$(echo "${result}" | "${PY_CMD}" -c "import sys,json; print(json.load(sys.stdin).get('injection',''))" 2>/dev/null || echo "")
      injected_cats=$(echo "${result}" | "${PY_CMD}" -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('injected_categories',[])))" 2>/dev/null || echo "")
      sad_candidates=$(echo "${result}" | "${PY_CMD}" -c "import sys,json; d=json.load(sys.stdin); c=d.get('sad_candidates',[]); print(';'.join([x['name'] for x in c[:3]]))" 2>/dev/null || echo "")
    fi
  fi
fi

# ---- bash 兜底注入块（无 python 也要让 Agent 看到宪法核心，关键修复）----
if [[ -z "${INJECTION}" ]]; then
  # 分类计数兜底（categories 为数组结构 "doc": [；技能对象内嵌的 "categories": [ 需排除）
  if [[ -f "${TREE_FILE}" ]]; then
    tree_categories=$(grep -o '"[a-z][a-z0-9_-]*": \[' "${TREE_FILE}" | grep -v '"categories":' | wc -l 2>/dev/null | tr -d '\r\n' || echo 0)
  fi
  INJECTION="## ⚡ 宪法 Pre-hook 注入（bash 兜底版，无 python 环境）

> 本会话 Skills 宪法（v2.13）已启用。**任何专业任务开始前必须执行【宪法三查】并显式汇报**：
> ① 查记忆：已读用户级 MEMORY.md 与项目记忆
> ② 查技能树：已读技能索引，**必须列出命中的技能名清单**（名称+依据），禁止只写\"已读技能树\"
> ③ 匹配必用：有匹配 → 无条件优先加载该技能执行；无匹配 → 说明\"技能树无匹配\"再走通用能力
>
> 违规判定：跳过三查直接干 / 有匹配但不用 / 查了但不列技能名（空头汇报）均视为违规。

### 📜 记忆层（MEMORY.md，必须遵循）
\`\`\`
$(cat "${MEMORY_FILE}" 2>/dev/null | head -80)
\`\`\`

### 🗂️ 技能树
- 路径: ${TREE_FILE_WIN}
- 分类数: ${tree_categories}（bash 兜底计数）
- ⚠️ 当前环境无 python，请 Agent 用 Read 工具直接读取技能树文件后按分类定位技能（doc/code/browser/email/memory 等）。"
fi

# ---- 写注入上下文文件（供 UserPromptSubmit hook 校验）----
cat > "${OUTPUT}" << EOF
{
  "status": "ready",
  "hook": "SessionStart",
  "memory_file": "${MEMORY_FILE_WIN}",
  "memory_len": ${memory_len},
  "tree_file": "${TREE_FILE_WIN}",
  "tree_categories": ${tree_categories:-0},
  "injected_categories": "${injected_cats}",
  "sad_candidates": "${sad_candidates}",
  "python": "${PY_CMD:-none}",
  "injection_len": ${#INJECTION},
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

# ---- 关键修复2: 完整注入块输出到 stdout（平台注入 Agent 上下文）----
echo "${INJECTION}"
echo "【宪法】注入完成: memory=${memory_len}字 tree=${tree_categories}分类 python=${PY_CMD:-无}"
exit 0
