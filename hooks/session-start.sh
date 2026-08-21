#!/usr/bin/env bash
# SessionStart hook: 注入宪法上下文到会话
# 产出 injected-context.json，供 UserPromptSubmit hook 校验
set -uo pipefail

PLUGIN_ROOT="${CODEBUDDY_PLUGIN_ROOT:-/c/Users/HUAWEI/.workbuddy/skills/skills-constitution}"
HOOK_DIR="${PLUGIN_ROOT}/hooks"
OUTPUT="${HOOK_DIR}/injected-context.json"

# 确保 hook 目录存在
mkdir -p "${HOOK_DIR}"

# 检查 pre-hook.py 是否存在
PRE_HOOK="${PLUGIN_ROOT}/scripts/pre-hook.py"
if [[ ! -f "${PRE_HOOK}" ]]; then
  echo '{"status":"error","message":"pre-hook.py not found"}' > "${OUTPUT}"
  exit 0
fi

# 路径转换: Git Bash /c/... → Windows C:/...（python3 在 Windows 下不认 /c/）
to_win() { echo "$1" | sed 's|^/\([a-zA-Z]\)|\1:|'; }

MEMORY_FILE="${HOME}/.workbuddy/MEMORY.md"
TREE_FILE="${PLUGIN_ROOT}/skill_tree.json"
MEMORY_FILE_WIN="$(to_win "${MEMORY_FILE}")"
TREE_FILE_WIN="$(to_win "${TREE_FILE}")"
PRE_HOOK_WIN="$(to_win "${PRE_HOOK}")"

memory_len=0
tree_categories=0
injected_cats=""
sad_candidates=""

if [[ -f "${MEMORY_FILE}" ]]; then
  memory_len=$(wc -c < "${MEMORY_FILE}" 2>/dev/null || echo 0)
fi

if [[ -f "${TREE_FILE}" ]]; then
  tree_categories=$(python3 -c "import json; d=json.load(open(r'${TREE_FILE_WIN}')); print(len(d.get('categories', d) if isinstance(d, dict) else 0))" 2>/dev/null || echo 0)
fi

# 调用 pre-hook.py 生成注入块
TASK_DESC="${CODEBUDDY_TASK_DESC:-默认任务}"
result=$(python3 "${PRE_HOOK_WIN}" --task "${TASK_DESC}" --json --memory "${MEMORY_FILE_WIN}" --tree "${TREE_FILE_WIN}" 2>/dev/null || echo '{}')

# 解析结果
if [[ "${result}" != '{}' && "${result}" != '' ]]; then
  injected_cats=$(echo "${result}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('injected_categories',[])))" 2>/dev/null || echo "")
  sad_candidates=$(echo "${result}" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('sad_candidates',[]); print(';'.join([x['name'] for x in c[:3]]))" 2>/dev/null || echo "")
fi

# 生成注入上下文文件
cat > "${OUTPUT}" << EOF
{
  "status": "ready",
  "hook": "SessionStart",
  "memory_file": "${MEMORY_FILE_WIN}",
  "memory_len": ${memory_len},
  "tree_file": "${TREE_FILE_WIN}",
  "tree_categories": ${tree_categories},
  "injected_categories": "${injected_cats}",
  "sad_candidates": "${sad_candidates}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "宪法上下文已注入: memory=${memory_len}字 tree=${tree_categories}分类"
exit 0
