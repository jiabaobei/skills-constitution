#!/usr/bin/env bash
# ============================================================
# skills-constitution 一键更新 (v2.26.0 新增)
# ============================================================
# 死规矩: 更新前先去 GitHub 下载最新版, 更新完成后自动在本地安装最新版。
# 流程: 下载最新 main 包 → 完整性校验(不毁旧装) → 跑新版 install.sh(参数透传) → 成功清理临时目录
#
# 用法:
#   bash scripts/update.sh                          # 自动探测平台安装
#   bash scripts/update.sh --platform workbuddy --register-hooks
#   bash scripts/update.sh --skills-dir /path       # 显式指定技能目录(测试/自定义)
# Windows: 用 scripts/update.ps1(或在 Git Bash 里跑本脚本)
# ============================================================
set -euo pipefail

REPO="jiabaobei/skills-constitution"
PRIMARY_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/main"
FALLBACK_URL="https://api.github.com/repos/${REPO}/tarball/main"

say()  { printf '\033[1;32m%s\0m\n' "$*"; }
die()  { printf '\033[1;31m%s\0m\n' "$*" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "⬇️  更新前先从 GitHub 下载最新版..."
if ! curl -fsSL --retry 2 --retry-delay 2 -o "$TMP/latest.tar.gz" "$PRIMARY_URL" 2>/dev/null; then
  curl -fsSL --retry 2 --retry-delay 2 -o "$TMP/latest.tar.gz" "$FALLBACK_URL" \
    || die "下载失败: $PRIMARY_URL 与 $FALLBACK_URL 都不通, 保持旧版不安装"
fi

# 完整性校验: 必须可解压且含 SKILL.md —— 半残包绝不覆盖本地旧版
# (注意: 不能用 grep -q 提前退出, SIGPIPE+pipefail 会把 tar 的退出码拖成失败)
LIST="$(tar -tzf "$TMP/latest.tar.gz" 2>/dev/null)" || die "包读取失败, 保持旧版不安装"
echo "$LIST" | grep "SKILL.md" >/dev/null || die "包完整性校验失败(缺 SKILL.md), 保持旧版不安装"
tar -xzf "$TMP/latest.tar.gz" -C "$TMP" || die "解压失败, 保持旧版不安装"
NEW_DIR="$(cd "$TMP"/*/ && pwd)"

NEW_VER="$(grep -m1 '^version:' "$NEW_DIR/SKILL.md" | awk '{print $2}')"
say "✅ 已下载最新版: v${NEW_VER}"

say "📦 更新完成后自动在本地安装最新版..."
bash "$NEW_DIR/install.sh" "$@"
say "✅ 已更新并安装 v${NEW_VER}"
