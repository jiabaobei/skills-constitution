# ============================================================
# skills-constitution 一键安装脚本 — Windows PowerShell 版 (v2.21.0)
# ============================================================
# 用法(在 PowerShell 里,进入本脚本所在目录):
#   .\install.ps1                        # 自动探测 (WorkBuddy > ZCode > Claude Code)
#   .\install.ps1 -Platform claude
#   .\install.ps1 -Platform workbuddy
#   .\install.ps1 -Platform zcode
#   .\install.ps1 -SkillsDir D:\my-skills
#   .\install.ps1 -RegisterHooks         # 装完自动注册钩子
#
# 注意: 本脚本在 Windows 真机之外的环境无法实测,如有问题请提 Issue;
#       钩子的 SessionStart 注入依赖 bash,Windows 上装 Git Bash 后即可生效,
#       不装也不影响其余三个钩子。
# ============================================================
[CmdletBinding()]
param(
    [string]$Platform = "",
    [string]$SkillsDir = "",
    [switch]$RegisterHooks
)

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($msg)  { Write-Host $msg -ForegroundColor Green }
function Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Die($msg)  { Write-Host $msg -ForegroundColor Red; exit 1 }

# ---- 1. 定位 python ----
$Py = $null
foreach ($cand in @("python3", "python", "py")) {
    $found = Get-Command $cand -ErrorAction SilentlyContinue
    if ($found) { $Py = $found.Source; break }
}
if (-not $Py) { Die "未找到 python,请先安装 Python 3 并加入 PATH" }

# ---- 2. 定位技能目录 ----
if (-not $SkillsDir) {
    switch ($Platform) {
        "claude"    { $SkillsDir = Join-Path $HOME ".claude\skills" }
        "workbuddy" { $SkillsDir = Join-Path $HOME ".workbuddy\skills" }
        "zcode"     { $SkillsDir = Join-Path $HOME ".zcode\skills" }
        default {
            if (Test-Path (Join-Path $HOME ".workbuddy\skills")) {
                $SkillsDir = Join-Path $HOME ".workbuddy\skills"; $Platform = "workbuddy"
            } elseif (Test-Path (Join-Path $HOME ".zcode\skills")) {
                $SkillsDir = Join-Path $HOME ".zcode\skills"; $Platform = "zcode"
            } else {
                $SkillsDir = Join-Path $HOME ".claude\skills"; $Platform = "claude"
            }
        }
    }
}
elseif (-not $Platform) { $Platform = "claude" }
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
Say "[1/4] 平台: $Platform | 技能目录: $SkillsDir"

# ---- 3. 复制宪法 ----
$Dest = Join-Path $SkillsDir "skills-constitution"
if (Test-Path $Dest) {
    Warn "      检测到旧版安装,覆盖更新: $Dest"
    Remove-Item -Recurse -Force $Dest
}
Copy-Item -Recurse $RepoDir $Dest
foreach ($f in @(".constitution-state.json", ".constitution-simple", ".constitution-violations.json")) {
    Remove-Item -Force (Join-Path $Dest $f) -ErrorAction SilentlyContinue
}
Say "[2/4] 已安装到: $Dest"

# ---- 4. 重建技能树(最容易被漏掉的一步) ----
Say "[3/4] 重建技能树(扫描 $SkillsDir)..."
$env:SKILLS_DIR = $SkillsDir
& $Py (Join-Path $Dest "scripts\build_skill_tree.py")
if ($LASTEXITCODE -eq 0) { Say "      技能树重建成功" }
else { Warn "      技能树重建失败(不影响宪法本身,可稍后手工重跑)" }
$env:SKILLS_DIR = $null

# ---- 5. 自检 ----
Say "[4/4] 自检..."
$check = @'
import json, os, sys
tree_path, skills_dir = sys.argv[1], sys.argv[2]
if not os.path.exists(tree_path):
    print("  X skill_tree.json 不存在"); sys.exit(1)
tree = json.load(open(tree_path, encoding="utf-8"))
# v2.21.0: 双机制口径 = 独立技能 + 插件技能
total = tree.get("total", 0) + tree.get("plugin_skills_count", 0)
sd = tree.get("skills_dir", "")
if total <= 0:
    print(f"  X 技能树为空(扫描到 0 个技能)"); sys.exit(1)
if sd and os.path.normpath(sd) != os.path.normpath(skills_dir):
    print(f"  ! 技能树指向 {sd},与当前技能目录不一致"); sys.exit(1)
print(f"  OK 技能树正常: 独立 {tree.get('total', 0)} + 插件 {tree.get('plugin_skills_count', 0)} 个技能,{len(tree.get('categories', {}))} 个分类")
'@
$check | & $Py - (Join-Path $Dest "skill_tree.json") $SkillsDir
if ($LASTEXITCODE -eq 0) { Say "`n[OK] 安装完成!" } else { Warn "`n[!] 安装完成,但自检有问题" }

# ---- 6. 可选: 钩子注册 ----
if ($RegisterHooks) {
    Say "`n注册宿主钩子(强制拦截)..."
    & $Py (Join-Path $Dest "scripts\register_hooks.py") --platform $Platform --skills-dir $Dest
    if ($LASTEXITCODE -ne 0) { Warn "钩子注册未完成,可按 reference\installation.md 手工注册" }
}

# ---- 7. 下一步指引 ----
$MemHint = if ($Platform -eq "workbuddy") { "~\.workbuddy\MEMORY.md(默认,门禁直接认)" }
           elseif ($Platform -eq "zcode") { "AGENTS.md(用户级 ~\.zcode\AGENTS.md 或项目根);门禁校验时传 --memory <路径>" }
           else { "CLAUDE.md(用户级 ~\.claude\CLAUDE.md 或项目级);门禁校验时传 --memory <路径>" }
Write-Host @"

--------------------------------------------------------------
下一步(可选,按需):

1) 强制拦截(钩子注册):
   .\install.ps1 -Platform $Platform -RegisterHooks
   或手工注册: 见 reference\installation.md

2) 记忆层(宪法第零条要查的记忆):
   你的平台记忆文件: $MemHint

3) SessionStart 注入钩子需要 bash: 装 Git Bash 后自动生效(可选)

4) 以后新增/删除了技能,重跑一次即可刷新技能树:
   `$env:SKILLS_DIR="$SkillsDir"; & "$Py" "$Dest\scripts\build_skill_tree.py"
--------------------------------------------------------------
"@
