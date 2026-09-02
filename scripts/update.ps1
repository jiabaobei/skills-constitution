# ============================================================
# skills-constitution 一键更新 (v2.26.0 新增)
# ============================================================
# 死规矩: 更新前先去 GitHub 下载最新版, 更新完成后自动在本地安装最新版。
# 流程: 下载最新 main 包 -> 完整性校验(不毁旧装) -> 跑新版 install.ps1 -> 成功清理临时目录
#
# 用法: powershell -ExecutionPolicy Bypass -File scripts\update.ps1 [install.ps1 的参数]
# ============================================================
$ErrorActionPreference = "Stop"

$repo = "jiabaobei/skills-constitution"
$primary = "https://codeload.github.com/$repo/tar.gz/refs/heads/main"
$fallback = "https://api.github.com/repos/$repo/tarball/main"

$tmp = Join-Path $env:TEMP ("sc-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null

try {
    Write-Host "⬇️  更新前先从 GitHub 下载最新版..."
    $archive = Join-Path $tmp "latest.tar.gz"
    try {
        Invoke-WebRequest -Uri $primary -OutFile $archive -UseBasicParsing
    } catch {
        Invoke-WebRequest -Uri $fallback -OutFile $archive -UseBasicParsing
    }

    # 完整性校验: 必须可解压且含 SKILL.md —— 半残包绝不覆盖本地旧版
    tar -xzf $archive -C $tmp
    if ($LASTEXITCODE -ne 0) { throw "解压失败, 保持旧版不安装" }
    $newDir = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    if (-not (Test-Path (Join-Path $newDir "SKILL.md"))) {
        throw "包完整性校验失败(缺 SKILL.md), 保持旧版不安装"
    }

    $verLine = (Select-String -Path (Join-Path $newDir "SKILL.md") -Pattern '^version:' | Select-Object -First 1).Line
    $ver = ($verLine -replace '^version:\s*', '').Trim()
    Write-Host "✅ 已下载最新版: v$ver"

    Write-Host "📦 更新完成后自动在本地安装最新版..."
    & (Join-Path $newDir "install.ps1") @args
    if ($LASTEXITCODE -ne 0) { throw "安装脚本返回非零, 请检查上方输出" }
    Write-Host "✅ 已更新并安装 v$ver"
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
