#!/usr/bin/env bash
# UserPromptSubmit hook: 宪法分类器 + 注入校验
# 简单任务 → 通道A跳过 | 专业任务 → 通道B强制校验
# 输入支持两种方式:
#   1. WorkBuddy hook: stdin JSON payload {"prompt": "..."}
#   2. 直接调用: bash user-prompt-submit.sh "任务描述"
set -uo pipefail

# v2.14.0: 去掉 HUAWEI 硬编码——环境变量优先，缺失时按脚本位置自定位；定位失败静默放行（fail-open，不卡任务）
if [[ -n "${CODEBUDDY_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="${CODEBUDDY_PLUGIN_ROOT}"
else
  _SK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLUGIN_ROOT="$(dirname "${_SK_SCRIPT_DIR}")"
fi
if [[ ! -f "${PLUGIN_ROOT}/SKILL.md" ]]; then
  exit 0
fi
PRE_HOOK="${PLUGIN_ROOT}/scripts/pre-hook.py"
CONTEXT_FILE="${PLUGIN_ROOT}/hooks/injected-context.json"
TASK_DESC=""

# 解释器检测（v2.13.2: 兼容 hook 环境无 python3 的情况，找不到则降级放行）
PY_CMD=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then PY_CMD="$c"; break; fi
done
if [[ -z "${PY_CMD}" ]]; then
  exit 0
fi

# ---- 读取任务描述: 优先 stdin JSON(prompt 字段), 其次 $1 ----
if [[ -n "${1:-}" ]]; then
  TASK_DESC="${1}"
else
  # 读取 stdin JSON payload
  read -r stdin_payload
  if [[ -n "${stdin_payload}" ]]; then
    TASK_DESC=$(echo "${stdin_payload}" | "${PY_CMD}" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('prompt', d.get('task', d.get('input', ''))).strip())
except Exception:
    print('')
" 2>/dev/null)
  fi
fi

# 无任务描述则放行
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
result=$("${PY_CMD}" "${PRE_HOOK_WIN}" --classify --task "${TASK_DESC}" --json 2>/dev/null || echo '{"task_type":"ambiguous"}')

# 提取任务类型
task_type=$(echo "${result}" | "${PY_CMD}" -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_type','ambiguous'))" 2>/dev/null || echo "ambiguous")

case "${task_type}" in
  "simple")
    # 简单任务：跳过门禁，直接通用能力
    exit 0
    ;;
  "professional"|"ambiguous")
    # 专业/模糊任务：检查注入上下文
    if [[ -f "${CONTEXT_FILE}" ]]; then
      status=$("${PY_CMD}" -c "import json; d=json.load(open(r'${CONTEXT_FILE_WIN}')); print(d.get('status',''))" 2>/dev/null || echo "")
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
