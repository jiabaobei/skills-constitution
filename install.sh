#!/usr/bin/env bash
# ============================================================
# skills-constitution 一键安装脚本 (v2.19.0+)
# ============================================================
# 解决的头号痛点:手工安装最容易漏掉"重建技能树"这一步 ——
# 漏掉后用户拿着作者的快照查自己的环境,查树永远"无匹配",
# 核心机制静默失效且用户不知道自己装错了。
#
# 本脚本自动完成: 复制到技能目录 → 重建你自己的技能树 → 自检 → 输出下一步
#
# 用法:
#   bash install.sh                        # 自动探测平台 (WorkBuddy > Claude Code)
#   bash install.sh --skills-dir <目录>    # 显式指定技能目录
#   bash install.sh --platform claude      # 强制按 Claude Code 安装
#   bash install.sh --platform workbuddy   # 强制按 WorkBuddy 安装
# ============================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR=""
PLATFORM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skills-dir) SKILLS_DIR="$2"; shift 2 ;;
    --platform)   PLATFORM="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' ; exit 0 ;;
    *) echo "未知参数: $1(用 --help 查看用法)" >&2; exit 1 ;;
  esac
done

say()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

# ---- 1. 定位技能目录 ----
if [[ -z "$SKILLS_DIR" ]]; then
  case "$PLATFORM" in
    claude)    SKILLS_DIR="$HOME/.claude/skills" ;;
    workbuddy) SKILLS_DIR="$HOME/.workbuddy/skills" ;;
    "")
      if [[ -d "$HOME/.workbuddy/skills" ]]; then
        SKILLS_DIR="$HOME/.workbuddy/skills"; PLATFORM="workbuddy"
      else
        SKILLS_DIR="$HOME/.claude/skills"; PLATFORM="claude"
      fi ;;
    *) die "未知平台: $PLATFORM(支持 claude / workbuddy)" ;;
  esac
fi
mkdir -p "$SKILLS_DIR"
say "[1/4] 技能目录: $SKILLS_DIR"

# ---- 2. 复制宪法 ----
DEST="$SKILLS_DIR/skills-constitution"
if [[ -d "$DEST" ]]; then
  warn "      检测到旧版安装,覆盖更新: $DEST"
  rm -rf "$DEST"
fi
cp -r "$REPO_DIR" "$DEST"
# 清掉运行时状态文件(如有)
rm -f "$DEST/.constitution-state.json" "$DEST/.constitution-simple" \
      "$DEST/.constitution-violations.json" 2>/dev/null || true
say "[2/4] 已安装到: $DEST"

# ---- 3. 重建你自己的技能树(最容易被漏掉的一步,现在由脚本代劳) ----
PY="$(command -v python3 || command -v python || true)"
[[ -n "$PY" ]] || die "未找到 python3,请先安装 Python 3"
say "[3/4] 重建技能树(扫描 $SKILLS_DIR)..."
if SKILLS_DIR="$SKILLS_DIR" "$PY" "$DEST/scripts/build_skill_tree.py"; then
  say "      技能树重建成功"
else
  warn "      技能树重建失败(不影响宪法本身,可稍后手工重跑)"
fi

# ---- 4. 自检 ----
say "[4/4] 自检..."
if "$PY" - "$DEST/skill_tree.json" "$SKILLS_DIR" <<'PYEOF'
import json, os, sys
tree_path, skills_dir = sys.argv[1], sys.argv[2]
if not os.path.exists(tree_path):
    print("  ✗ skill_tree.json 不存在"); sys.exit(1)
tree = json.load(open(tree_path, encoding="utf-8"))
total = tree.get("total", 0)
sd = tree.get("skills_dir", "")
if total <= 0:
    print(f"  ✗ 技能树为空(扫描到 0 个技能) —— 请确认 {skills_dir} 下有带 SKILL.md 的技能目录")
    sys.exit(1)
if sd and os.path.normpath(sd) != os.path.normpath(skills_dir):
    print(f"  ⚠ 技能树指向 {sd},与当前技能目录不一致(可能未重建成功)")
    sys.exit(1)
print(f"  ✓ 技能树正常: {total} 个技能,{len(tree.get('categories', {}))} 个分类,指向本机目录")
PYEOF
then
  say ""
  say "✅ 安装完成!"
else
  warn ""
  warn "⚠ 安装完成,但自检发现问题,请按上面的提示处理。"
fi

# ---- 下一步指引 ----
cat <<EOF

──────────────────────────────────────────────────────────────
下一步(可选,按需):

1) 想让门禁"强制拦截"而不只是"行为建议"?
   注册宿主 hooks(PreToolUse/Stop/UserPromptSubmit):
   见 reference/gate-details.md 与 SKILL.md 的【门禁自检】章节。

2) 宪法正文(快速上手): $DEST/SKILL.md
   平台适配说明:          $DEST/reference/platform-mapping.md
   技能树使用指南:        $DEST/reference/skill-tree-guide.md

3) 以后新增/删除了技能,重跑一次即可刷新技能树:
   SKILLS_DIR="$SKILLS_DIR" python3 "$DEST/scripts/build_skill_tree.py"
──────────────────────────────────────────────────────────────
EOF
