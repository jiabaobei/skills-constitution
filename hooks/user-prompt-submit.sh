#!/usr/bin/env bash
# UserPromptSubmit hook: 宪法分类器 + 注入上下文保活
# 简单任务 → 通道A跳过 | 专业任务 → 通道B(上下文保活,不拦)
#
# v2.27.0 重写(钩子单进程化):
#   旧版整个钩子要起 9 次进程(解释器探针 3 + stdin解析 1 + sed 2 + 分类器 1
#   + 结果解析 1 + 状态检查 1),在慢机器(每进程约2s)上实测 33~39s,
#   远超宿主 20s 上限 → 任务被超时拦截。现改为:
#     ① 解释器缓存 .py-interp(首次探测后落盘,热路径 0 次进程启动)
#     ② stdin 用 read builtin 限时读取(零进程启动)
#     ③ 路径转换用 bash 内建(替代 sed)
#     ④ exec 单次 python pre-hook.py --hook-mode 完成分类+上下文保活
#   热路径总进程启动:1 次(首次 3~4 次)。全程 fail-open。
set -uo pipefail

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
if [[ ! -f "${PRE_HOOK}" ]]; then
  exit 0
fi
HOOK_DIR="${PLUGIN_ROOT}/hooks"

# ---- 路径转换(Git Bash /c/... → Windows C:/...),bash 内建实现,零进程启动 ----
to_win() {
  case "$1" in
    /[a-zA-Z]/*) printf '%s\n' "${1:1:1}:${1:2}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}
PRE_HOOK_WIN="$(to_win "${PRE_HOOK}")"

# ---- 解释器检测:v2.25.1 存活探针 + v2.27.0 结果缓存 ----
# Windows 上 python 可能是 Microsoft Store 占位别名(启动即挂起),必须真跑一次;
# 探针通过后把绝对路径写入缓存,后续每次钩子 0 次探针进程。
PY_CMD=""
PY_CACHE="${HOOK_DIR}/.py-interp"
if [[ -r "${PY_CACHE}" ]]; then
  _cached=""
  { read -r _cached; } < "${PY_CACHE}" 2>/dev/null || _cached=""
  if [[ -n "${_cached}" && -x "${_cached}" ]]; then
    PY_CMD="${_cached}"
  fi
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
if [[ -z "${PY_CMD}" ]]; then
  exit 0  # 无可用解释器:降级放行(fail-open,不卡任务)
fi

# ---- 读取任务描述:$1 优先,其次 stdin JSON(builtin 限时读取) ----
# 任务文本经管道喂给 python(写方是本钩子自己,写完即 EOF,python 不会挂起)
if [[ -n "${1:-}" ]]; then
  exec "${PY_CMD}" "${PRE_HOOK_WIN}" --hook-mode --task "${1}"
else
  _payload=""
  read -r -t 2 _payload || true
  if [[ -z "${_payload}" ]]; then
    exit 0  # 无任务描述:放行
  fi
  printf '%s' "${_payload}" | "${PY_CMD}" "${PRE_HOOK_WIN}" --hook-mode
fi
exit 0
