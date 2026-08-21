#!/usr/bin/env bash
# UserPromptSubmit hook: 宪法分类器 + 注入校验
# 简单任务 → 通道A跳过 | 专业任务 → 通道B强制校验
set -uo pipefail

PLUGIN_ROOT="${CODEBUDDY_PLUGIN_ROOT:-/c/Users/HUAWEI/.workbuddy/skills/skills-constitution}"
PRE_HOOK="${PLUGIN_ROOT}/scripts/pre-hook.py"
CONTEXT_FILE="${PLUGIN_ROOT}/hooks/injected-context.json"
TASK_DESC="${1:-}"

if [[ -z "${TASK_DESC}" ]]; then
  exit 0
fi

# 检查 pre-hook.py
if [[ ! -f "${PRE_HOOK}" ]]; then
  exit 0
fi

# 路径转换: Git Bash /c/... → Windows C:/...
to_win() { echo "$1" | sed 's|^/\([a-zA-Z]\)|\1:|'; }
PRE_HOOK_WIN="$(to_win "${PRE_HOOK}")"
CONTEXT_FILE_WIN="$(to_win "${CONTEXT_FILE}")"

# 调用分类器判断任务类型（使用 --task 参数，不是 stdin）
result=$(python3 "${PRE_HOOK_WIN}" --classify --task "${TASK_DESC}" --json 2>/dev/null || echo '{"task_type":"ambiguous"}')

# 提取任务类型
task_type=$(echo "${result}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_type','ambiguous'))" 2>/dev/null || echo "ambiguous")

case "${task_type}" in
  "simple")
    # 简单任务：跳过门禁，直接通用能力
    exit 0
    ;;
  "professional"|"ambiguous")
    # 专业/模糊任务：检查注入上下文
    if [[ -f "${CONTEXT_FILE}" ]]; then
      status=$(python3 -c "import json; d=json.load(open(r'${CONTEXT_FILE_WIN}')); print(d.get('status',''))" 2>/dev/null || echo "")
      if [[ "${status}" == "ready" ]]; then
        exit 0
      fi
    fi
    # 无注入上下文或状态不对：阻断并提示
    echo "【宪法拦截】专业任务需要先注入记忆+技能树上下文，请确保宪法钩子已生效"
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
