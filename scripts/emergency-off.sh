#!/usr/bin/env bash
# =============================================================================
# 宪法门禁 · 紧急拉闸(v2.31.0)
#
# 用途:门禁一旦又在拦正常任务 / 又把用户消息卡死,用这一条命令当场断电。
# 纯 bash,不依赖 python —— 断电权必须比门禁本身更可靠。
#
# 用法:
#   bash scripts/emergency-off.sh                 # 拉闸(写开关文件,全部事件立即放行)
#   bash scripts/emergency-off.sh "原因说明"       # 带原因拉闸(会记进开关文件)
#
# 拉闸后门禁的唯一行为:对 UserPromptSubmit / PreToolUse / Stop / SessionStart
# 全部直接放行(见 constitution-gate.py 的 R1:拉闸优先)。
# 恢复:bash scripts/emergency-on.sh
# =============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"
OFF="$BASE/.constitution-off"
HEALTH="$BASE/.constitution-health.log"

REASON="${1:-用户手动拉闸}"

if [ -f "$OFF" ]; then
  echo "[已拉闸] 开关文件已存在: $OFF"
  echo "--- 内容 ---"
  cat "$OFF"
  echo "------------"
  echo "恢复命令: bash \"$HERE/emergency-on.sh\""
  exit 0
fi

{
  echo "手动拉闸 $(date '+%Y-%m-%d %H:%M:%S')"
  echo "原因: $REASON"
  echo "恢复: bash \"$HERE/emergency-on.sh\"   或删除本文件"
} > "$OFF" 2>/dev/null

if [ ! -f "$OFF" ]; then
  echo "[失败] 无法写入 $OFF —— 请手工创建这个空文件,效果相同。" >&2
  echo "        例:  > \"$OFF\"   (cmd)  或  touch \"$OFF\"   (bash)" >&2
  exit 1
fi

echo "[已拉闸] $OFF"
echo "        原因: $REASON"
{ echo "$(date '+%Y-%m-%d %H:%M:%S')	manual_off	$REASON"; } >> "$HEALTH" 2>/dev/null

echo
echo "现在门禁对任何事件都直接放行,不会再拦任务。"
echo "恢复: bash \"$HERE/emergency-on.sh\""
echo
echo "注意(WorkBuddy 平台):钩子配置是会话启动时加载的,改 settings.json 当轮不生效;"
echo "  而本开关是门禁进程每次运行都会读的文件 —— 所以拉闸立刻生效,不用重启。"
