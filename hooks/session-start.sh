#!/usr/bin/env bash
# SessionStart hook: 注入宪法上下文到会话
# 产出 injected-context.json，并把「完整注入块」输出到 stdout（平台会注入 Agent 上下文）
#
# v2.27.0 单进程化 + 省 token:
#   ① python 分支从约 6 次进程启动(生成1+JSON解析3+写上下文1)合并为 1 次
#     (pre-hook.py --context-out: 原子写入 injected-context.json + stdout 直出注入块)
#   ② 解释器检测结果缓存 .py-interp(与 user-prompt-submit.sh 共用),热路径 0 次探针
#   ③ 路径转换改 bash 内建(替代 sed 子进程)
#   ④ bash 兜底注入块不再引导 Agent「整读技能树文件」——技能树可达数十万字符,
#     极度费 token;改为引导运行 pre-hook 按任务过滤(约 3 千字符)
# v2.25.1: 解释器存活探针(3s 限时,Windows Store 占位 python 不再挂起)
# v2.13.3: stderr 捕获 / 兜底文案动态化
set -uo pipefail

if [[ -n "${CODEBUDDY_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="${CODEBUDDY_PLUGIN_ROOT}"
else
  _SK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLUGIN_ROOT="$(dirname "${_SK_SCRIPT_DIR}")"
fi
if [[ ! -f "${PLUGIN_ROOT}/SKILL.md" ]]; then
  echo "【宪法钩子·错误】PLUGIN_ROOT 定位失败（${PLUGIN_ROOT} 下无 SKILL.md）。请设置环境变量 CODEBUDDY_PLUGIN_ROOT 指向 skills-constitution 目录。" >&2
  exit 1
fi
HOOK_DIR="${PLUGIN_ROOT}/hooks"
OUTPUT="${HOOK_DIR}/injected-context.json"
mkdir -p "${HOOK_DIR}"

# 路径转换: Git Bash /c/... → Windows C:/...（bash 内建实现,零进程启动）
to_win() {
  case "$1" in
    /[a-zA-Z]/*) printf '%s\n' "${1:1:1}:${1:2}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

MEMORY_FILE="${HOME}/.workbuddy/MEMORY.md"
TREE_FILE="${PLUGIN_ROOT}/skill_tree.json"
MEMORY_FILE_WIN="$(to_win "${MEMORY_FILE}")"
TREE_FILE_WIN="$(to_win "${TREE_FILE}")"

memory_len=0
tree_categories=0
INJECTION=""
FALLBACK_REASON=""
python_branch_ok="no"

# ---- 解释器检测: 存活探针(v2.25.1) + 结果缓存(v2.27.0) ----
PY_CMD=""
PY_CACHE="${HOOK_DIR}/.py-interp"
if [[ -r "${PY_CACHE}" ]]; then
  _cached=""
  { read -r _cached; } < "${PY_CACHE}" 2>/dev/null || _cached=""
  [[ -n "${_cached}" && -x "${_cached}" ]] && PY_CMD="${_cached}"
fi
if [[ -z "${PY_CMD}" ]]; then
  _HAVE_TIMEOUT=""
  command -v timeout >/dev/null 2>&1 && _HAVE_TIMEOUT=1
  for c in python3 python py; do
    command -v "$c" >/dev/null 2>&1 || continue
    _cand="$(command -v "$c")"
    # v2.27.0: 垫片真身解析——同目录优先取原生 .exe(少一层 bash 垫片进程;
    # 慢机器每进程约 2-3s,直接决定钩子能否压进宿主超时)
    _cdir="${_cand%/*}"
    _real=""
    for _alt in python.exe python3.exe; do
      if [[ -x "${_cdir}/${_alt}" ]]; then _real="${_cdir}/${_alt}"; break; fi
    done
    [[ -z "${_real}" ]] && _real="${_cand}"
    if [[ -n "${_HAVE_TIMEOUT}" ]] && ! timeout 3 "${_real}" -c "pass" 2>/dev/null; then continue; fi
    PY_CMD="${_real}"
    printf '%s\n' "${PY_CMD}" > "${PY_CACHE}" 2>/dev/null || true
    break
  done
fi

# ---- 有 python: 单次调用生成注入块 + 原子写入上下文(v2.27.0) ----
PRE_HOOK="${PLUGIN_ROOT}/scripts/pre-hook.py"
if [[ -n "${PY_CMD}" && -f "${TREE_FILE}" && -f "${PRE_HOOK}" ]]; then
  PRE_HOOK_WIN="$(to_win "${PRE_HOOK}")"
  OUTPUT_WIN="$(to_win "${OUTPUT}")"
  TASK_DESC="${CODEBUDDY_TASK_DESC:-默认任务}"
  INJECTION=$("${PY_CMD}" "${PRE_HOOK_WIN}" --task "${TASK_DESC}" --context-out "${OUTPUT_WIN}" 2>"${HOOK_DIR}/pre-hook.err" || true)
  [[ -n "${INJECTION}" ]] && python_branch_ok="yes"
fi

# ---- bash 兜底注入块(无 python / python 分支失败时) ----
if [[ -z "${INJECTION}" ]]; then
  if [[ -f "${MEMORY_FILE}" ]]; then
    memory_len=$(wc -c < "${MEMORY_FILE}" 2>/dev/null || echo 0)
  fi
  if [[ -f "${TREE_FILE}" ]]; then
    tree_categories=$(grep -o '"[a-z][a-z0-9_-]*": \[' "${TREE_FILE}" 2>/dev/null | grep -v '"categories":' | wc -l 2>/dev/null | tr -d '\r\n ' || echo 0)
  fi
  if [[ -z "${PY_CMD}" ]]; then
    FALLBACK_REASON="no_python"
    FALLBACK_TAG="bash 兜底版，无 python 环境"
  else
    FALLBACK_REASON="python_branch_failed"
    FALLBACK_TAG="bash 兜底版（python 分支失败，已降级）"
  fi
  INJECTION="## ⚡ 宪法 Pre-hook 注入（${FALLBACK_TAG}）

> 本会话 Skills 宪法已启用。**任何专业任务开始前必须执行【宪法三查】并显式汇报**：
> ① 查记忆：已读用户级 MEMORY.md 与项目记忆
> ② 查技能树：已读技能索引，**必须列出命中的技能名清单**（名称+依据），禁止只写\"已读技能树\"
> ③ 匹配必用：有匹配 → 无条件优先加载该技能执行；无匹配 → 说明\"技能树无匹配\"再走通用能力
>
> 违规判定：跳过三查直接干 / 有匹配但不用 / 查了但不列技能名（空头汇报）均视为违规。
>
> ⚠️ 省 token 死规则：**禁止整读技能树文件**（可达数十万字符）。需要技能详情时运行:
> \`\`\`
> python \"${PLUGIN_ROOT}/scripts/pre-hook.py\" --task \"当前任务\"
> \`\`\`
> 只输出按任务过滤的轻量注入块（约 3 千字符）。"

  # 兜底也要产出上下文文件(UserPromptSubmit 校验依赖 status=ready)
  if [[ -z "${PY_CMD}" ]]; then
    cat > "${OUTPUT}" << EOF
{
  "status": "ready",
  "hook": "SessionStart",
  "memory_file": "${MEMORY_FILE_WIN}",
  "memory_len": ${memory_len},
  "tree_file": "${TREE_FILE_WIN}",
  "tree_categories": ${tree_categories:-0},
  "injected_categories": "",
  "sad_candidates": "",
  "python": "none",
  "python_branch_ok": "no",
  "fallback_reason": "${FALLBACK_REASON}",
  "injection_len": ${#INJECTION},
  "debug": {"pre_hook_stderr": "bash fallback"},
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
  else
    # python 在但 pre-hook 分支失败: 复用 refresh_injection 原子写上下文
    "${PY_CMD}" -c "
import sys
sys.path.insert(0, r'$(to_win "${PLUGIN_ROOT}/scripts")')
import importlib.util as ilu
spec = ilu.spec_from_file_location('ph_refresh', r'$(to_win "${PRE_HOOK}")')
m = ilu.module_from_spec(spec)
spec.loader.exec_module(m)
m.refresh_injection('默认任务', r'$(to_win "${OUTPUT}")')
" 2>>"${HOOK_DIR}/pre-hook.err" || true
  fi
fi

# ---- 完整注入块输出到 stdout（平台注入 Agent 上下文）----
printf '%s\n' "${INJECTION}"
exit 0
