# SessionStart hook (Windows): 注入宪法上下文
$PluginRoot = $env:CODEBUDDY_PLUGIN_ROOT
if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
  $PluginRoot = Split-Path -Parent $PSScriptRoot
}

$HookDir = Join-Path $PluginRoot "hooks"
$Output = Join-Path $HookDir "injected-context.json"
$PreHook = Join-Path $PluginRoot "scripts\pre-hook.py"
$MemoryFile = Join-Path $env:USERPROFILE ".workbuddy\MEMORY.md"
$TreeFile = Join-Path $PluginRoot "skill_tree.json"

# 确保目录存在
New-Item -ItemType Directory -Force -Path $HookDir | Out-Null

# 检查 pre-hook.py
if (-not (Test-Path -LiteralPath $PreHook -PathType Leaf)) {
  @{status="error"; message="pre-hook.py not found"} | ConvertTo-Json -Compress | Set-Content -Path $Output
  exit 0
}

$memoryLen = 0
$treeCats = 0

if (Test-Path -LiteralPath $MemoryFile) {
  $memoryLen = (Get-Item $MemoryFile).Length
}

if (Test-Path -LiteralPath $TreeFile) {
  try {
    $tree = Get-Content $TreeFile -Raw | ConvertFrom-Json
    $treeCats = $tree.categories.Count
  } catch {}
}

# 调用 pre-hook.py
$taskDesc = $env:CODEBUDDY_TASK_DESC
if ([string]::IsNullOrWhiteSpace($taskDesc)) { $taskDesc = "默认任务" }

$pyResult = & python $PreHook --task $taskDesc --json --memory $MemoryFile --tree $TreeFile 2>$null
if (-not $pyResult) { $pyResult = "{}" }

try {
  $result = $pyResult | ConvertFrom-Json
  $injectedCats = ($result.injected_categories -join ",")
  $sadCandidates = ($result.sad_candidates | Select-Object -First 3 | ForEach-Object { $_.name }) -join ";"
} catch {
  $injectedCats = ""
  $sadCandidates = ""
}

$context = @{
  status = "ready"
  hook = "SessionStart"
  memory_file = $MemoryFile
  memory_len = $memoryLen
  tree_file = $TreeFile
  tree_categories = $treeCats
  injected_categories = $injectedCats
  sad_candidates = $sadCandidates
  timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$context | ConvertTo-Json -Compress | Set-Content -Path $Output
Write-Host "宪法上下文已注入: memory=${memoryLen}字 tree=${treeCats}分类"
exit 0
