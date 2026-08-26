#!/usr/bin/env bash
# ============================================================
# skills-constitution 一键安装脚本 (v2.20.0)
# ============================================================
# 平台机制不一样,安装方式也不一样 —— 本脚本按平台形态分流:
#
#   技能目录型(完整体验: 技能树+门禁可注册)
#     workbuddy / claude     → 复制到技能目录 + 自动重建技能树 + 自检
#   规则文件型(建议级: 宪法作为项目规则,无技能树/无钩子)
#     cursor / windsurf / cline → 宪法正文写入对应规则文件
#   纯注入型(建议级: 复制模板到系统提示词)
#     prompt                  → 打印【快速注入模板】供手工粘贴
#
# 用法:
#   bash install.sh                              # 自动探测 (WorkBuddy > Claude Code)
#   bash install.sh --platform claude            # 指定技能目录型平台
#   bash install.sh --platform cursor --target-dir /path/to/project
#   bash install.sh --platform prompt
#   bash install.sh --skills-dir <目录>           # 显式指定技能目录
#   bash install.sh --register-hooks             # 技能目录型平台: 装完自动注册钩子
#
# Windows 用户: 用 install.ps1(或在 Git Bash 里跑本脚本)
# ============================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR=""
PLATFORM=""
TARGET_DIR=""
REGISTER_HOOKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skills-dir)      SKILLS_DIR="$2"; shift 2 ;;
    --platform)        PLATFORM="$2"; shift 2 ;;
    --target-dir)      TARGET_DIR="$2"; shift 2 ;;
    --register-hooks)  REGISTER_HOOKS=1; shift ;;
    -h|--help)         grep '^#' "$0" | sed 's/^# \{0,1\}//' ; exit 0 ;;
    *) echo "未知参数: $1(用 --help 查看用法)" >&2; exit 1 ;;
  esac
done

say()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

# ============================================================
# 分支 1: 规则文件型平台(建议级,无技能树/无钩子)
# ============================================================
install_as_rules() {
  local target="${TARGET_DIR:-$PWD}"
  [[ -d "$target" ]] || die "目标项目目录不存在: $target"
  local header="<!-- skills-constitution v2.20.0 (advisory level: 规则文件型平台无钩子机制,
#  技能树/门禁不可用, 宪法以行为建议生效) -->
"
  case "$PLATFORM" in
    cursor)
      mkdir -p "$target/.cursor/rules"
      { echo "$header"; cat "$REPO_DIR/SKILL.md"; } > "$target/.cursor/rules/skills-constitution.md"
      say "✅ 已安装: $target/.cursor/rules/skills-constitution.md" ;;
    windsurf)
      _append_marker_block "$target/.windsurfrules"
      say "✅ 已安装: $target/.windsurfrules" ;;
    cline)
      _append_marker_block "$target/.clinerules"
      say "✅ 已安装: $target/.clinerules" ;;
  esac
  warn "ℹ️  $PLATFORM 无钩子/技能树机制, 宪法以建议级生效(见 reference/platform-mapping.md)"
}

# windsurf/cline 的规则文件是单文件共享,用标记块追加(幂等:先删旧块)
_append_marker_block() {
  local file="$1"
  local begin="<!-- BEGIN skills-constitution -->"
  local end="<!-- END skills-constitution -->"
  if [[ -f "$file" ]] && grep -qF "$begin" "$file"; then
    # 删除旧块再重写(幂等更新)
    local tmp; tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" '$0==b{skip=1} !skip{print} $0==e{skip=0}' "$file" > "$tmp"
    mv "$tmp" "$file"
    warn "      检测到旧宪法块,已替换"
  fi
  {
    [[ -s "$file" ]] && echo ""
    echo "$begin"
    cat "$REPO_DIR/SKILL.md"
    echo "$end"
  } >> "$file"
}

# ============================================================
# 分支 2: 纯注入型平台(打印模板)
# ============================================================
install_as_prompt() {
  local out=""
  if [[ -n "$TARGET_DIR" ]]; then
    mkdir -p "$TARGET_DIR"
    out="$TARGET_DIR/constitution-injection-template.md"
  fi
  say "提取【快速注入模板】..."
  local tpl
  tpl="$(awk '/^````markdown$/{f=1;next} /^````$/{if(f){exit}} f{print}' "$REPO_DIR/README.md")"
  [[ -n "$tpl" ]] || die "未能从 README.md 提取注入模板"
  if [[ -n "$out" ]]; then
    echo "$tpl" > "$out"
    say "✅ 模板已写入: $out"
  else
    echo ""
    echo "$tpl"
    echo ""
  fi
  cat <<'EOF'
──────────────────────────────────────────────────────────────
请把上面的模板粘贴到:
  ChatGPT  → Custom Instructions 或 GPT 的 System Prompt
  Gemini   → Gem 的 Instructions
  扣子/文心/通义等 → 系统提示词 / 记忆层
注意: 这类平台无文件系统与钩子, 宪法仅以建议级生效;
     门禁/技能树/推荐校验等机制不可用(见 reference/platform-mapping.md)。
──────────────────────────────────────────────────────────────
EOF
}

# ============================================================
# 分支 3: 技能目录型平台(完整体验)
# ============================================================
install_as_skill() {
  # ---- 定位技能目录 ----
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
      *) die "未知平台: $PLATFORM(支持 workbuddy/claude/cursor/windsurf/cline/prompt)" ;;
    esac
  else
    PLATFORM="${PLATFORM:-claude}"
  fi
  mkdir -p "$SKILLS_DIR"
  say "[1/4] 平台: $PLATFORM | 技能目录: $SKILLS_DIR"

  # ---- 复制宪法 ----
  DEST="$SKILLS_DIR/skills-constitution"
  if [[ -d "$DEST" ]]; then
    warn "      检测到旧版安装,覆盖更新: $DEST"
    rm -rf "$DEST"
  fi
  cp -r "$REPO_DIR" "$DEST"
  rm -f "$DEST/.constitution-state.json" "$DEST/.constitution-simple" \
        "$DEST/.constitution-violations.json" 2>/dev/null || true
  say "[2/4] 已安装到: $DEST"

  # ---- 重建技能树(最容易被漏掉的一步,现在由脚本代劳) ----
  PY="$(command -v python3 || command -v python || true)"
  [[ -n "$PY" ]] || die "未找到 python3,请先安装 Python 3"
  say "[3/4] 重建技能树(扫描 $SKILLS_DIR)..."
  if SKILLS_DIR="$SKILLS_DIR" "$PY" "$DEST/scripts/build_skill_tree.py"; then
    say "      技能树重建成功"
  else
    warn "      技能树重建失败(不影响宪法本身,可稍后手工重跑)"
  fi

  # ---- 自检 ----
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

  # ---- 可选: 钩子自动注册 ----
  if [[ "$REGISTER_HOOKS" == "1" ]]; then
    say ""
    say "注册宿主钩子(强制拦截)..."
    "$PY" "$DEST/scripts/register_hooks.py" --platform "$PLATFORM" --skills-dir "$DEST" || \
      warn "钩子注册未完成,可按 reference/installation.md 手工注册"
  fi

  # ---- 下一步指引(含记忆层平台对照) ----
  local mem_hint
  case "$PLATFORM" in
    workbuddy) mem_hint="~/.workbuddy/MEMORY.md(默认,门禁直接认)" ;;
    claude)    mem_hint="CLAUDE.md(用户级 ~/.claude/CLAUDE.md 或项目级);门禁校验时传 --memory <路径> 指向它" ;;
    *)         mem_hint="按平台记忆层约定放置,门禁校验时传 --memory <路径>" ;;
  esac
  cat <<EOF

──────────────────────────────────────────────────────────────
下一步(可选,按需):

1) 强制拦截(钩子注册):
   bash install.sh --platform $PLATFORM --register-hooks
   或手工注册: 见 reference/installation.md 的 settings.json 示例。

2) 记忆层(宪法第零条要查的记忆):
   你的平台记忆文件: $mem_hint

3) 宪法正文: $DEST/SKILL.md
   平台适配说明: $DEST/reference/platform-mapping.md
   技能树使用指南: $DEST/reference/skill-tree-guide.md

4) 以后新增/删除了技能,重跑一次即可刷新技能树:
   SKILLS_DIR="$SKILLS_DIR" python3 "$DEST/scripts/build_skill_tree.py"
──────────────────────────────────────────────────────────────
EOF
}

# ============================================================
# 分流
# ============================================================
case "${PLATFORM:-}" in
  cursor|windsurf|cline) install_as_rules ;;
  prompt)                install_as_prompt ;;
  *)                     install_as_skill ;;
esac
