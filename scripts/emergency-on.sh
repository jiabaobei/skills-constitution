#!/usr/bin/env bash
# =============================================================================
# 宪法门禁 · 恢复合闸(v2.31.0)
#
# 用法:
#   bash scripts/emergency-on.sh            # 合闸 + 体检
#   bash scripts/emergency-on.sh --quiet    # 只合闸,不做体检
#
# 合闸后建议先跑一次体检,确认门禁健康再放它继续上班:
#   python scripts/constitution-doctor.py --fix
# =============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"
OFF="$BASE/.constitution-off"
QUIET="${1:-}"

if [ -f "$OFF" ]; then
  echo "--- 拉闸期间的原因记录 ---"
  cat "$OFF"
  echo "--------------------------"
  rm -f "$OFF" 2>/dev/null
  if [ -f "$OFF" ]; then
    echo "[失败] 无法删除 $OFF —— 请手工删除后再合闸。" >&2
    exit 1
  fi
  echo "[已合闸] 门禁恢复工作。"
else
  echo "[无需操作] 当前未拉闸。"
fi

if [ "$QUIET" = "--quiet" ]; then
  exit 0
fi

echo
echo "建议紧接着做一次体检(会实测钩子耗时、检查状态文件与违规记录):"
echo "  python \"$HERE/constitution-doctor.py\" --fix"
