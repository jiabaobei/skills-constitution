# Changelog

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [2.27.6] - 2026-09-04

### 修复："查了技能树"却看不见技能 —— 注入名录截断 + 分类兜底退化

事故（2026-09-04，用户抓包）：任务"把我本机改好的最新版 skills 宪法推送到 github 和 gitee"，
`github-gitee-publish` **就在技能树里且分类正确**（`code/doc/file/automation`），
Agent 却报"技能树无匹配"。技能树本身是新的（2026-09-01 生成，764 条目），锅在注入器。

- **分类路由兜底退化（主因）**：`filter_tree_by_task` 的关键词表没覆盖"推送/github/gitee"，
  未命中时 `return list(tree.keys())[:5]` —— 直接返回**字母序前 5 个分类**
  `general/browser/search/file/data`，与任务毫无关系，真正相关的 `code`/`automation`
  根本没进必需清单。改为复用确定性路由 `required_categories_for_task(task)`
  （同一句话实测正确返回 `code`+`meta`），仍为空才退回前 5 个。
- **注入名录硬截断（兜底失效）**：`build_injection` 两处按字母序截取 ——
  分类名录 `skills[:8]`、必需技能候选 `cat_skills[:10]`。该技能在 `code` 类排**第 38 位**，
  永远显示不出来。新增 `pick_display_skills()`，复用现成的 `loose_retrieve_skills`
  按任务相关度排序取前 N（无任务文本/无人过线时退回字母序，行为不变），
  行尾标注"未列全；判定'无匹配'前须 grep 完整索引"。
- **新增死规则「第一条补充 A」**：注入名录是**预览不是清单**；行尾标"未列全"时，
  判定"技能树无匹配"前**必须**检索全量索引（`grep SKILL_TREE.md` 或查 `skill_tree.json`）。
- 实测：同一句话注入的分类由 `general/browser/search/file/data` 变为 `code`+`meta`，
  `github-gitee-publish` 出现在 code 类第 7 位。

## [2.27.5] - 2026-09-03

### Stop 追责拧紧：堵"弱通行证零追责"漏洞 + GBK 输出崩溃根治

- **Stop 收尾免检条件收紧（本版核心）**：原逻辑任务开始注入就绪即签发通行证，Stop 见到任何通行证一律免检——agent 无视注入提示、全程不汇报三查、不调用命中技能，收尾零追责。现区分强/弱证据：step1 真实 PASS 或本任务内真调用过技能（PreToolUse 自动记录）才免检；仅"注入即签"的弱通行证且本任务存在必需技能分类时，收尾回复仍须通过三查文本校验，不过即记违规、下轮任务开头红牌警告。"本任务无必需分类"（注入即查已足额）不受影响，不误记。
- **必需分类缓存**：UserPromptSubmit 时将 `required_categories` 缓存进门禁状态，Stop 判定零开销复用（不重复加载技能树）。
- **GBK 输出崩溃根治（从安装副本收编）**：`pre-hook.py`/`constitution-gate.py` 入口强制 stdout/stderr UTF-8（`errors="replace"`），根治 Windows 控制台打印 ⚡ 等字符时 `UnicodeEncodeError` 导致注入块从未送达的事故（2026-09-03 实锤：安装副本 `pre-hook.err` 抓到现行）。
- 新任务重置时同步清除 `required_categories` 缓存，防上一任务分类泄漏到下一任务。

## [2.27.4] - 2026-09-03

### 钩子注册补全：注入保活钩子入册 + 全链路直调 python（防"改好了、一用又不行"复发）

- **注册脚本漏注册注入保活钩子（本版核心修复）**：`register_hooks.py` 只注册门禁三钩子（UserPromptSubmit/PreToolUse/Stop）+ SessionStart 注入，UserPromptSubmit 的 `pre-hook.py --hook-mode` 未入册——注入只在会话启动做一次，长会话上下文过期（>24h）后 Agent 拿不到记忆+技能树注入，"该调用技能时一定调用技能"的防线随之失效。现补注册为 UserPromptSubmit 第二条钩子。
- **全链路直调 python，绕开 bash 层**：实测定位宿主 20s 超时元凶——bash.exe（MSYS）单次启动 2.5~12.9s 且随负载剧烈波动（Defender 扫描），而 pre-hook.py 本身仅 0.19s。注册脚本全面改为直调 python：热路径实测门禁 1.7~1.9s + 注入 1.5s ≈ **3.5s**，距宿主 20s 上限余量 5 倍+。20s 红线本身是宿主保险丝（防钩子挂死锁死会话），正确方向是把钩子做快而非放宽容忍度。
- **MARKERS 收编 `pre-hook.py`**：幂等替换/卸载可识别并接管此前手工添加的注入钩子条目，重跑注册不再产生重复或残留。
- **回归 +3 条（13.6 注册完整性）**：断言注入保活钩子已入册、全部直调 python（不再注册 bash user-prompt-submit.sh）、MARKERS 含 pre-hook.py。
- 实测：`--dry-run` 输出 UserPromptSubmit 双钩子（门禁+注入保活）正确，幂等替换逻辑确认。

## [2.27.3] - 2026-09-03

### 门禁状态文件并发截断根治 + 损坏兜底纠偏（修复"宪法不起作用"真因）

**起因**：用户反映"改版那么多次宪法却不起作用"。实测 `.constitution-state.json` 停在 `"last_task": ` 后半截被写残 → v2.27.0 遇损坏即静默放行（exit 0）→ 写文件拦截**永久短路**，门禁形同虚设。真因是 v2.27.0 的"原子写"在两处 Windows 并发场景下仍会截断主文件。

#### 修复

- **① 并发 tmp 重名**：三个钩子进程（UserPromptSubmit/PreToolUse/Stop）并发写状态，共用固定名 `state.json.tmp` → 互相 `open(w)` 截断 → 后写者把半成品 `os.replace` 换回主文件。改为 tmp 名带 pid（`state.<pid>.tmp`），各进程写各自文件。
- **② `os.replace` 失败兜底是截断元凶**：Windows 上目标文件被其他进程持读句柄时 `os.replace` 抛 PermissionError → v2.27.0 兜底 `open(path,"w")` 直接写 → 这一步才真正截断主文件。改为短重试（0.05s×10），仍失败则放弃本次写入保留旧文件——状态陈旧最多导致"多拦一次/漏签一次"，远好过写残文件致门禁失效。附陈旧 tmp 清理（强杀残留不堆积）。
- **③ 兜底语义纠偏（防极端宽松）**：v2.27.0 损坏即放行 = 门禁永久失效。改为**降级放行**：状态损坏时 exit 0 放行本次（agent 不卡死、任务不崩），但打印一行提示给 agent、**不签通行证**；下次任务开始 UserPromptSubmit 重置状态，门禁自动恢复三查。
- **④ 回归用例补齐**：新增 5 条——并发写 4 进程 3961 次读取 0 损坏、无破坏性直写兜底、tmp 带 pid、损坏判定走降级放行而非永久放行。

#### 实测

- 并发压测（6 进程 × 40 次写）：此前版本真损坏多次（读到半截 JSON），修复后 **真损坏 0 次**，8389 次有效读取全部完整。
- 端到端五场景：简单任务豁免放行 / 专业任务注入就绪签通行证中途不拦 / 状态损坏降级放行不阻断 / 无注入无证据 exit 2 真拦截 / 空 payload 不挂起——全部符合"简单放行、复杂拦一次、fail-open 防死锁"设计初衷。
- 全量回归 **131/131 通过**。

## [2.27.2] - 2026-09-03

### 测试修正：两例过时断言对齐 v2.27.0 钩子单进程架构（零功能变更）

**起因**：v2.27.1 本地安装后全量回归 123/125，两例失败均为 v2.25.1 时代的测试断言未跟上 v2.27.0 钩子单进程化重构，非功能回归（钩子热路径实测均值 7.4s，低于宿主 20s 上限）。

#### 修正

- **13.0c 断言过时**：原断言钩子源码含 `timeout 10`（bash 层嵌套自愈限时）。v2.27.0 自愈已改为 `pre-hook.py` 进程内 `refresh_injection()`（1.5s 级），嵌套自愈整体删除。现改为两条：钩子单进程委托（`--hook-mode` 在位）+ 嵌套自愈已删除（不再重跑 session-start.sh）。
- **13.3 阈值过紧**：原阈值 <10s。慢机器（每进程 2-3s）+ Defender 文件首扫/负载尖峰下实测 6~18s 波动（热路径均值 ~7s），10s 阈值误报。放宽到 <18s——仍低于宿主 20s 上限，且足以捕获真挂起（30s 级）。
- **测试套件健壮性**：13.1/13.3 的 `subprocess.run(timeout=25)` 超时会抛 `TimeoutExpired` 让整个套件崩溃退出（无汇总输出）。现捕获后记为失败用例继续跑，套件永远给出完整汇总。

#### 实测

- 本机（8GB + Defender）：bash 启动 1.6~12.9s 随负载大幅波动；钩子热路径 5.7~9.6s（均值 7.4s）、冷路径（解释器探针 + 首扫）17.9s，均 <20s 不触发宿主超时。

#### CHANGELOG 补齐（同日）

- 回填 **v2.13.1**（安装到 WorkBuddy：settings.json 注册钩子 + stdin JSON 兼容）与 **v2.12.1**（宪法自举：技能关键词映射 meta + SAD 条件排除）两版此前漏写的改版说明。

## [2.27.1] - 2026-09-02

### 技能图谱补全与降噪（省 token）

#### 修复

- **自愈路径漏传图谱候选**：v2.27.0 新增的 `refresh_injection()`（hook-mode 自愈）构建注入块时 graph_items 传 `[]`，导致自愈刷新产出的注入块缺少「🕸️ 技能图谱」段，与主链路（SessionStart / `--context-out`）不一致。现接入 `graph_candidates_for_task()`，两链路对齐。

#### 变更

- **cluster 候选降噪**：`graph_candidates_for_task()` 改为先超采样 3 倍，再过滤——同簇（cluster）候选必须与任务有词面交集（技能名或描述，`overlap_score > 0`）才收录；结构边（chains_to/co_anchor）与 alternative（建边时已要求同分类+描述重叠）语义足够强，不过滤。词面工具缺失时退化为不过滤（fail-open）。实测："写爬虫"任务候选 8→1（adobe-* 无关同簇成员全灭）、注入块 4199→3458 字符、无关任务宁缺毋滥（0 候选）。

## [2.27.0] - 2026-09-02

### 钩子单进程化 + 门禁「任务开始拦一次、中途不再拦」真实生效

#### 修复

- **门禁状态文件并发写截断（用户钦定 bug）**：UserPromptSubmit / PreToolUse / Stop 三个钩子进程并发 `open(w)+json.dump` 同一 `.constitution-state.json`，互相截断 → `load_state` 读到损坏 JSON 返回空 → 任务级通行证（task_cleared）与 injected 标记丢失 → PreToolUse 把任务中途的每次写文件都当「三查不足」拦截。现改为**原子写入**（temp + os.replace），读方永远看到完整文件。
- **注入上下文过期导致通行证不签发**：injected-context.json 超过 24h 时 `injection_ready()` 恒为 False → 任务开始时通行证根本没签发 → 中途被迫补证据。现改为 UserPromptSubmit 时**进程内自动刷新**（复用 `pre-hook.refresh_injection()`，零额外进程、秒级完成），刷新成功即签发通行证。
- **状态损坏兜底放行**：状态文件为空/损坏但注入证据就绪时，PreToolUse / Stop 兜底放行（不再误拦任务、不再误记违规）。
- **user-prompt-submit.sh 钩子单进程化**：解释器检测缓存（`.py-interp`，热路径 0 次探针）+ stdin builtin 限时读取 + 路径转换 bash 内建（替代 sed）+ exec 单次 `pre-hook.py --hook-mode`；进程启动 9 次→热路径 1 次，慢机器（每进程约 2s）实测 33~39s → 预期 <8s，不再触发宿主 20s 超时拦截。
- **session-start.sh 单进程化**：python 分支约 6 次进程启动→1 次（`--context-out` 原子写上下文 + stdout 直出注入块）。
- **bash 兜底 token 炸弹修复**：兜底注入块不再引导 Agent「整读技能树文件」（可达数十万字符、极度费 token），改为引导运行 `pre-hook.py --task "当前任务"` 获取按任务过滤的轻量注入块（约 3 千字符）。

#### 新增

- `pre-hook.py --hook-mode`：钩子单进程模式（任务分类 + 注入上下文保活一次完成；全程 fail-open，绝不拦任务）
- `pre-hook.py --context-out <path>`：注入块与 injected-context.json 一次调用同时产出（原子写入）
- `pre-hook.py refresh_injection()`：进程内刷新注入上下文（自愈，替代旧版嵌套重跑 session-start.sh —— 旧自愈在慢机器上 10s 限时内永远跑不完，导致注入永远不 ready）

## [2.26.0] - 2026-09-02

### 一键更新脚本：「更新前先下载最新版、更新后自动安装」固化为死规矩

#### 新增

- **`scripts/update.sh`（bash）/ `scripts/update.ps1`（Windows PowerShell）**：更新流程脚本化——
  ① 更新前先从 GitHub 下载最新 main 包（`codeload.github.com` 主、`api.github.com` tarball 备，双保险）；
  ② 完整性校验：必须可解压且含 `SKILL.md`，半残包**保持旧版不安装**（不毁旧装）；
  ③ 更新完成后自动在本地安装最新版——透传全部参数跑**新版**安装器（`install.sh` / `install.ps1`，`--platform` / `--skills-dir` / `--register-hooks` 等原样透传）；
  ④ 成功自动清理临时目录（`trap` / `finally` 保证失败也清理）。

#### 修复（脚本自身）

- `update.sh` 完整性校验初版用 `tar -tzf | grep -q`，`grep -q` 提前退出触发 SIGPIPE，在 `set -o pipefail` 下把 tar 退出码拖成失败、误判半残包；改为先取完整列表再 grep（全量读完，无 SIGPIPE）。

#### 实测

- `bash scripts/update.sh --platform claude --skills-dir <临时目录>`：下载 v2.25.1 → 校验通过 → 新版安装器自动安装、产物齐全 → 报「已更新并安装 v2.25.1」。

## [2.25.1] - 2026-09-02

### 钩子挂起修复：WorkBuddy 20s 强杀不再卡死任务（Windows）

#### 起因

Windows 平台上 `python`/`python3` 可能指向 Microsoft Store 占位别名（启动即挂起）。钩子的解释器检测只用 `command -v` 查存在、不真跑，导致钩子里每次 python 调用都挂起；叠加数次调用超过宿主 20000ms 超时，WorkBuddy 强杀钩子并报 `UserPromptSubmit operation blocked by hook: Hook timed out after 20000ms`，任务卡死。

#### 修复

- **解释器存活探针**：`hooks/user-prompt-submit.sh` 与 `hooks/session-start.sh` 探测 python3/python/py 时真跑 `timeout 3 <py> -c "pass"`；超时视为不可用并降级（无 python → 放行 / bash 兜底），不再使用挂起的解释器。
- **stdin 读取限时**：`read -r stdin_payload` 改为 `read -r -t 2` —— 宿主开着输入通道却不发内容、也不关闭时，不再无限阻塞。
- **自愈限时**：`user-prompt-submit.sh` 中注入缺失时重跑 SessionStart 的自愈加 `timeout 10` 上限，嵌套钩子挂起不会把整个 UserPromptSubmit 拖过宿主超时。

#### 纪律与实测

- fail-open 设计哲学不变：全链路不可用时降级放行，钩子永不卡任务。
- 实测最坏情况（三个解释器全部启动挂起）：9s 降级放行（低于宿主 20s 上限）；正常环境 0.2s。

#### 测试

- 新增第 13 组回归（8 用例）：三道保护静态断言 + 解释器全挂 fail-open/20s 内完成 + stdin 悬空不阻塞 + 正常环境秒级完成。全量 125/125 通过（含既有 117 用例零回归）。

## [2.25.0] - 2026-09-01

### 第五条「答复推荐」极度省 token 改造：本地排行榜快照（不再每次全盘搜 GitHub）

起因（用户需求）："推荐环节是不是每次都要全盘扫 github？太浪费 token。能不能找一个可信度高的现成 github 排行榜，以后推荐只读排行榜，找任务相关 + 星数高的 3 个 skill 推荐。一切原则是极度省 token。"

#### 新增

- **`data/skill_rankings.json` 排行榜快照（作者快照随仓库发布）**：从权威排行榜仓库 `quemsah/awesome-claude-plugins`（GitHub raw README "Awesome Claude Code Plugins: Top 100 Repositories"，索引 3.6 万+ 仓库，实测 2026-08-31 更新）抓取 Top100 技能生成。字段精简（rank/name/owner/repo/stars/subs/plugins/desc/keywords），约 20KB，纯本地可读。
- **`scripts/recommend_skills.py` 本地推荐器（推荐环节主入口）**：读快照 → 任务文本分词（英文词 + 中文连续片段）→ 条目 keywords/name/desc 子串匹配 → **排除本地已装**（E1 目录同名 + E2 `_<name>-references` 框架标记，与 step5 Layer E 口径一致）→ 命中数优先、星数次之排序 → 出 3 条（GitHub 链接 + star 数 + 获取方式，天然满足 step5 校验）。零命中 → 按星数回退 Top3，任何任务都有推荐。**零网络请求。**
- **`scripts/update_skill_rankings.py` 快照刷新器（低频）**：网络抓取或 `--input README.md` 离线解析，生成快照（原子替换，网络/解析失败不覆盖旧快照）；`--source skilld` 可切备选源（skilld.dev 单技能级排行）；`--stale-days` 配过期阈值。
- **快照过期策略**：超过 `stale_days`（默认 30 天）时，`recommend_skills.py` 输出顶部提示运行刷新命令 —— **只提示不自动拉取**，绝不在推荐环节发起网络请求。

#### 修改

- **宪法第五条重写（SKILL.md / README.md）**：推荐来源优先级改为 ① 本地排行榜快照（第一优先，零网络）→ ② GitHub 搜索（仅快照零相关时兜底，须标注来源）→ ③ 快照过期提示刷新。删除"每次答复必须去 GitHub 搜索"的旧要求；省 token 铁律：推荐环节默认零网络。
- **step5-check.py 新增推荐来源标注软校验**：标注"本地排行榜快照"（data/skill_rankings.json）= 省 token 最佳实践 ✓；标注"GitHub 搜索"给出改用快照提示；未标注不判 FAIL（兼容旧 Agent 输出）。Layer A/B/E 逻辑不变。
- **README 改版说明补 v2.24.0 摘要**（上次发布漏加，本次一并补齐）。

#### 测试

- 新增第 12 组回归（11 用例）：排行榜表格解析 / keywords 提取 / 推荐匹配排序 / E1+E2 已装排除 / 中文零命中回退 / 快照过期提示 / 快照缺失提示 / step5 来源标注。
- 全量 117/117 通过（含既有 106 用例零回归）。

## [2.24.0] - 2026-09-01

### 隐形技能治理 + 门禁「一次三查全程放行」+ 轻量索引

起因（用户实测两连问）：① 「我装过的 ponytail（马尾辫，GitHub 116k★）怎么从没见调用？」② 「任务开始时明明执行了三查，任务中途又被门禁拦了，必须改。」

#### 新增

- **`scripts/skill_doctor.py` 隐形技能诊断与修复**：8 类检查（missing_skill_md / empty_skill_md / no_frontmatter / missing_name / missing_desc / block_scalar_residue / name_mismatch / empty_dir），分 severity（broken=损坏 / invisible=隐形 / warn=告警）；`--fix` 自动修复（补缺失 name、重建索引）、`--quarantine` 隔离损坏技能、`--emit-min-index` 生成轻量索引、`--query` 轻量检索验证。实测本库：121 项目录级问题（损坏 7 / 隐形 4 / 告警 110），已自动补齐 4 个缺失 name（agnes-video-generator / caozhao-radar / desktop-control / grill-me-ytang）。
- **`skill_index_min.json` 轻量索引**：约为完整索引 20% 体积（160KB / 777KB）。检索入口先用它，命中后再回查完整索引 —— 冷门技能不删除、不丢检索入口，省的是常驻 token 不是可用性。摘要截断部分提取长尾触发词（引号短语 + 全大写缩写优先，普通实词限额兜底）单独存 `k` 字段；实测 yagni / lazy mode / do less / be lazy / shortest path 五个触发词全部命中 ponytail。
- **门禁任务级通行证（constitution-gate.py）**：任务开始时（UserPromptSubmit）平台注入成功即签发 `task_cleared`（注入即查）；step1 PASS 亦补发。持证任务内所有写操作一路绿灯，拦截前移为任务开始时的一次性「必需分类提醒」。追加式消息仍不重置；新任务重置重发。防伪造不变：状态文件仍在 GATE_PROTECTED 保护内，注入失败（bash 兜底）时回到 step1/Skill 调用证据路径。

#### 修复

- **`parse_frontmatter` 支持 YAML 块标量**（`>` / `|` 及 `>-` `|+` `|-` 变体）：旧版逐行 `key: value` 解析只取到 `>` 符号本身，实测 137 个技能描述失效（ponytail 全套、frontend-dev、fullstack-dev、api-gateway、ios-application-dev 等），分类按 description 匹配故被误塞 general。修复后 ponytail 描述从 1 字符恢复 825 字符，code 分类 132→164、general 699→640。
- **pre-hook.py 注入块序列化加固**：`json.dumps` 加 `default` 兜底 + 整段 try 降级 —— 任一字段含不可序列化对象时旧版整段失败 → session-start 判 python 分支失败 → 降级 bash 兜底 → 门禁 injected 证据缺失（实测 2026-09-01 18:37 会话即发生），「注入即查」失效、每个任务都被迫重跑三查。
- **索引描述截断 200→2000**（build_skill_tree.py `DESC_LIMIT`）：实测 ponytail 的触发词位于第 400~700+ 字符，截断 200 / 600 均丢失 —— 检索数据源必须完整，token 成本由轻量索引承担。
- **图谱巨簇回归**：描述放宽后 co_anchor 锚点暴增，实测产生 752 节点巨簇（纪律 ≤80）。修复：① 锚点抽取固定用描述前 200 字符（与 v2.23.0 快照口径一致，图结构与存储职责分离）；② 停用词三批扩容（模板套话 guidance/routing/reference/expert 等 + 销售/CRM 通用词 account/company/contact 等 + 技术通用桥接词 sdk/auth/webhook/video 等）；③ ANCHOR_DF_RATIO 0.05→0.035。最大簇 752→123→116→104→95→≤80，回归测试 106/106。
- **run_tests.py 清理容错**：Windows 沙箱回收站不可用时 os.remove 被 safe-delete 拦截抛错，临时文件残留不应让测试套件崩溃。

#### 测试

- 新增第 11 组回归（7 用例）：块标量折叠/字面解析、块标量后普通字段、DESC_LIMIT≥2000、截断补偿提取触发词、腰斩残片丢弃、短语整体命中优先（不按空格拆分误配）。
- 全量 106/106 通过。

## [2.23.0] - 2026-09-01

### 技能图谱：技能树之上的确定性关系图（GitNexus 启发）
**背景**：研究 GitNexus（零服务器代码知识图谱引擎）后确认其核心主张「图谱的价值在关系确定 / 预计算关系智能」可平移到技能域——宪法此前只有"树"（人为分类），缺少"关系"（技能之间怎么衔接、哪些技能天然成簇）。技能树解决"技能在哪个抽屉"，技能图谱解决"技能之间怎么连"。

#### 新增：技能图谱（`skill_graph.json`）
- **`scripts/lib/graph.py`**（核心模块，零依赖）：
  - **三种边**（全部确定性抽取，零 LLM）：
    - `chains_to`：A 的 output_schema ∩ B 的 input_schema ≠ ∅（registry.json 已有数据固化成图；此前仅 step4 临时用）——有向
    - `co_anchor`：共享实体锚点（正则抽取，不靠字面巧合）。**两道过滤**是质量关键：① 套话停用词表（约 200 词，滤掉 creating/wants/supports/diagnose 等"活动词"——实测不滤会经套话词对连出 268 节点巨簇）；② 文档频率过滤（锚点出现在 >5% 技能里即视为套话剔除，确定性 IDF 思想）；英文复数归一（images→image）
    - `alternative`：同分类 + 描述重叠 ≥0.35（全局只保留最强的 200 条防图爆炸）
  - **确定性标签传播聚类**（GitNexus 社区检测的零依赖简化形）：排序遍历 + 平票取字典序最小 + 20 轮上限，完全可复现。**纪律**：只有结构边（chains_to/co_anchor）参与聚簇——"互为替代"不代表"同一条任务线"；连通分量被弃用（跨域桥接技能会把两个域并成巨簇，实测 216 节点）
  - **溯源**：每条边必带 evidence（为什么相关）；门禁 FAIL 带簇归属证据
- **`scripts/build_skill_graph.py`**：从现有技能树 + registry 单独重建图谱（快照维护 / CI / "树没变只想刷新图"场景）；`build_skill_tree.py` 重建技能树时顺带自动重建（`SKILL_GRAPH=0` 可关）
- **明确不借**（与宪法零依赖原则同构）：图数据库（JSON 文件足够）、LLM 参与建边、全量 AST、每次调用重建图

#### 落地一：注入按任务线收窄（省 token）
- `pre-hook.py` 新增「🕸️ 技能图谱」注入段：任务锚点技能（必需技能按 SAD 排名精选，`rank_anchors_for_task()`）的同簇成员 + 一跳邻居（`graph_expand()`），每条带边证据
- **轮转填充**：每锚点每轮最多贡献 2 个候选——防排名靠前锚点的大簇吃光整个预算（实测教训：单簇一次注入 8 条 memory 簇成员）
- 图缺失时行为与旧版完全一致（只加不删）

#### 落地二：门禁 Layer F 图证据校验（step3）
- 任务含必需关键词时，引用的技能必须与任务锚点**图谱连通**（同簇 / 结构边一跳）；引用的技能在图中但与锚点零连通 → **FAIL 并附簇归属证据**（引用侧簇 vs 锚点侧簇，溯源）
- 比 Layer D（描述重叠打分）更硬：关系在索引期已算好，校验时零推理
- **保守防误杀**：图缺失 / 无引用 / 引用不在图中（图陈旧）→ 降级放行；锚点按 SAD 排名取前 8（必需分类可能有噪声，精选后再判连通）
- **纪律**：alternative 边不做放行凭证（`graph_relevant_set()` 只走结构边）

#### 作者快照
- `skill_graph.json`：独立 457 节点 / 737 边（alternative×200, chains_to×9, co_anchor×528）/ 25 簇（最大簇 46：memory；其余如 code×21 / browser×20 / word×41 / email×14 / html 部署线×8）

#### 文档
- SKILL.md：frontmatter/模板版本升 2.23.0；技能树章节新增「技能图谱」段
- README / README_EN：badge、改版说明、项目结构、门禁 Step 表（step3 加 Layer F）
- docs/release-notes-v2.23.0.md

#### 测试
- run_tests.py 新增第 10 组「技能图谱」（22 条）：锚点抽取（停用词/复数归一）、三种边构造、聚类纪律（替代边不并簇）、确定性复现（两次建图一致）、快照冒烟（无巨簇）、门禁图证据（密封 fixture：同簇放行/零连通 FAIL 带簇证据/缺图降级）、替代边不做放行凭证、注入集成（候选非空/带证据/预算约束）
- 全量 99 条零回归

#### 验证（本机实测）
- [x] 全量回归 99/99 通过
- [x] 聚类质量迭代实证：连通分量 268 节点巨簇 → 停用词过滤 256 → 结构边聚簇纪律 216 → 标签传播 25 簇（最大 46），每步有诊断数据支撑
- [x] 注入实测：「推送代码到github」任务注入 code/browser 任务线候选（带"与 X 同簇"证据）；「帮我写代码」fixture 下 LayerF 对 doc 簇技能引用判 FAIL 且带簇证据
- [x] 版本号全文件核查对齐 2.23.0

## [2.22.0] - 2026-09-01

### 门禁双向修正：防绕过 + 防干扰 + 省 token
**背景**（真实使用反馈三问题）：① Agent 仍能骗过门禁直接跑任务，绕过查记忆/查技能/调用技能；② 项目越改越费 token，违背"尽量省 token"的设计初衷；③ 门禁干扰任务运行——任务开始时 Agent 已查记忆/查技能/调用技能，任务中途门禁又拦截、误记违规。

#### 防绕过（门禁被骗）
- **门禁自身文件保护**（`constitution-gate.py` 新增 `gate_file_targeted()`）：`.constitution-state.json`（三查记录）/ `.constitution-simple`（豁免旗标）/ `.constitution-violations.json`（违规记录）/ `hooks/injected-context.json`（注入上下文）禁止被 Agent 经 Write/Edit/MultiEdit/NotebookEdit 或 Bash（重定向/tee/heredoc/rm/mv/cp/sed -i）篡改——**旧版 Agent 写一个 `.constitution-simple` 文件即可全局豁免、直接改 state 即可伪造 PASS**；只读门禁文件不拦（不误伤）
- **Bash 写文件检测补 `sed -i`**：就地改写文件也是写文件，旧正则漏判
- **step1 PASS 有效性加固**：PreToolUse 只认 `level=PASS` 的状态条目（constitution-check 真实判定结果），手写/降级条目不产生通行证

#### 防干扰（门禁误拦）
- **三查证据链**（核心机制）：「三查已完成」认两种证据，满足其一即放行写操作、收尾不重复校验：
  ① **手动路径**：本任务内 `constitution-check --step 1` 真实校验通过（新鲜度 + `level=PASS`）；
  ② **注入路径（新增）**：平台注入上下文就绪（`injected-context.json` status=ready，24h 内）= 记忆+技能树已由平台强制注入视为已查，叠加本任务内实际调用过技能即证据链完整——**PreToolUse 观察到 `Skill` 工具调用自动记录进 state**，Agent 无需再手动跑校验命令；注入就绪但任务无必需分类（未映射到任何技能分类）时直接放行
- **追加式消息不重置**（`is_continuation()`）：超短消息（≤8 字符）或以追加标记开头（继续/好的/下一步/ok/continue…，只认开头防子串误判）视为同一任务延续，保留既有证据——修复"任务中途每条追加消息都被要求重新三查"
- **Stop 防误记**：本任务内已有证据链时跳过最终回复的重复文本校验——修复"任务开头已查过、收尾回复没复述三查就被误记违规、下任务开头被误注入警告"
- **注入自愈**（`hooks/user-prompt-submit.sh`）：注入上下文缺失/过期时现场重跑 SessionStart 注入（幂等），不再直接【宪法拦截】挡任务；自愈仍失败才拦截

#### 省 token
- **注入块默认瘦身约 30%**（`pre-hook.py`）：SAD 候选 6→4 条、描述截断 60→40 字、每分类技能清单 12→8 个、记忆片段上限 1200→900 字、执行要求文案精简
- **`hooks/hooks.json` matcher 精简**：UserPromptSubmit 约 8KB 关键词列表改为 `.*`（任务分类在 hook 脚本内做，简单任务秒级 exit 0，巨型 matcher 纯属冗余）
- **SKILL.md 顶部版本史压缩**：多版本摘要块收成一行，详情移入 CHANGELOG（每次加载 SKILL.md 省约 1K token）；阻断提示文案精简约一半

#### 文档
- SKILL.md：frontmatter/快速注入模板版本升 2.22.0；技术边界说明新增「门禁证据链」章节
- README / README_EN：badge、注入模板、门禁自检章节加「三查证据链」、改版说明新增 v2.22.0 摘要
- reference/gate-details.md：新增 v2.22.0 章节（证据链定义/防绕过加固/防干扰修正/瘦身清单）
- docs/release-notes-v2.22.0.md

#### 测试
- run_tests.py 新增第 9 组「门禁证据链」（19 条）：门禁文件保护（写/删/读三态）、`sed -i` 写检测、追加式消息判定（含子串不误判）、证据链放行四种状态、瘦身默认参数断言、hooks.json matcher 断言
- 全量 77 条零回归

#### 验证（本机实测）
- [x] 全量回归 77/77 通过
- [x] 端到端冒烟：无证据写文件被拦（exit 2）/ 篡改豁免旗标被拦 / 平台注入+调用技能后写文件放行 / 追加消息不重置（后续写文件仍放行）/ Stop 有证据链不误记违规（无违规记录产生）
- [x] 版本号全文件核查对齐 2.22.0（SKILL.md frontmatter 与模板、README/README_EN badge 与模板、install.sh/ps1 头与规则文件标记、hooks.json 描述、skill_tree.json 快照、run_tests、reference 文档；build_skill_tree.py 从 SKILL.md frontmatter 动态读版本，重建即同源）

## [2.21.0] - 2026-08-30

### 双机制平台覆盖：能力注册表 = 独立技能 ∪ 插件技能
**背景**：ZCode / Claude Code / DeepSeek Harness(dsh) 等平台的能力来自两条平行机制——技能目录下的独立技能与插件包内置的插件技能（ZCode 实测：插件缓存含 2286 个 SKILL.md，其中大量位于已停用市场目录下）。宪法原"查技能库"只覆盖独立技能，会漏掉 document-skills / computer-use 等插件通道的能力；且双机制平台上插件技能需按完整调用名（`插件名:技能名`）调用，裸技能名可能无法被 Skill 机制加载。

#### 新增
- **`build_skill_tree.py` 布局无关插件技能扫描**（核心能力）：
  - 已知平台路径自动发现（`KNOWN_PLUGIN_CACHE_LAYOUTS`：ZCode / Claude Code），存在才扫、缺谁跳谁
  - 任意新 agent 免改代码接入：`PLUGIN_CACHE_DIRS` 环境变量（系统路径分隔符分隔）或仓库根 `plugin_roots.json`（`{"cache_dirs": [...]}`）；`PLUGIN_SCAN=0` 整体关闭
  - 插件条目带 `source="plugin"` / `plugin` / `plugin_version` / `qualified_name`（完整调用名）/ `marketplace` / `agent` 字段；同插件多版本共存去重取最高
  - ZCode 侧自动读取其 config 的插件启用表（`plugins.enabledPlugins`）：停用插件不入树；`.DISABLED` 停用市场整棵子树跳过
- **`pre-hook.py` 完整调用名注入**：新增 `load_skill_aliases()`（`{技能名: 插件名:技能名}` 映射）；注入块分类清单与 SAD 候选渲染完整调用名并标注（插件），`--json` 输出含 `plugin_skills` 数与候选 `qualified_name`
- **install.sh / install.ps1 技能目录型新增 `zcode` 平台**：自动探测顺序 WorkBuddy > ZCode > Claude Code；zcode 记忆层提示 AGENTS.md；自检口径改"独立 + 插件"双机制计数

#### 修复（真实案例驱动）
- **插件名推导被打包层干扰**：`mimosa/1.0.3/payload/skills/...` 的打包层 `payload` 曾被误当插件名，导致停用插件 mimosa 的技能漏过 ZCode 启用表过滤——改为优先取市场段后第一个非版本目录（`_GENERIC_SEGMENTS` 排除 payload/bundle/dist 等通用打包层），且停用检查覆盖路径上全部插件名候选段

#### 宪法正文（SKILL.md）
- 新增**第一条补充：双机制平台覆盖**四条款：插件技能与独立技能同权重（禁止以"它是插件"为由绕过）/ 命中按完整调用名调用 / 技能树自动编入 / 插件附带命令与 MCP 工具同规则
- 快速注入模板同步（版本标注 v2.21.0；违规判定新增"命中插件技能却绕过"）；技术边界说明新增插件扫描章节

#### 文档
- README / README_EN：平台分流表加 ZCode、双机制覆盖说明、改版说明、项目结构、支持框架加"双机制平台"行
- reference/platform-mapping.md：加 ZCode / DeepSeek Harness(dsh) 平台行，完全支持级加 ZCode，新增"双机制平台"说明块
- reference/skill-tree-guide.md：SKILLS_DIR 表加 ZCode；新增"插件技能扫描"章节（四种接入方式对照表）+ FAQ Q6
- docs/release-notes-v2.21.0.md

#### 测试
- run_tests.py 新增第 8 组"插件技能扫描"（19 条）：布局无关扫描 / qualified_name / source 标记 / 多版本去重 / `.DISABLED` 跳过 / 启用表过滤 / 打包层不漏过停用过滤 / 入树集成 / 别名提取 / 注入渲染 / `PLUGIN_CACHE_DIRS` 接入
- "SAD top-K 含 git 相关技能"断言改为机器无关的确定性信号（top-K 含任务必需分类技能）——技能树内容随机器与插件而异，绑定具体技能名的断言不再成立
- 全量 58 条零回归

#### 验证（本机实测）
- [x] 真机 ZCode 插件缓存扫描：启用插件技能 15 个全部入树（`document-skills:docx` / `computer-use:computer-use` / `zcode-guide:diagnosing-*` 等），停用插件（mimosa / cloudbase-skills 等）零残留，`.DISABLED` 市场整棵跳过
- [x] 技能树重建：独立 447 + 插件 15，自检通过（注：旧快照 757 为作者另一台机器 `C:/Users/user` 的产物，本次快照如实反映当前机器）
- [x] `install.sh --platform zcode` 沙箱全流程（探测 → 复制 → 重建含插件技能 → 自检）通过
- [x] 58/58 测试通过；版本号全文件核查对齐 2.21.0

## [2.20.0] - 2026-08-26

### 安装全平台分流 + 钩子自动注册 + Windows 支持
**背景**：外部测评指出安装脚本只覆盖"两个有技能目录的主力平台"，而文档宣称支持 17 个平台——规则文件型（Cursor/Windsurf/Cline）装不上、注入型平台没入口、钩子注册仍是 50 行手工配置、Windows 没有原生脚本、记忆层平台差异无提示。本版本把 5 个缺口一次补齐。

#### 新增
- **install.sh 按平台机制三分支**：
  - 技能目录型（workbuddy/claude）：复制 + 自动重建技能树 + 自检（原有流程）
  - 规则文件型（cursor/windsurf/cline）：宪法正文写入对应规则文件（`.cursor/rules/`；windsurf/cline 单文件用 BEGIN/END 标记块追加，幂等替换旧块），并如实声明"建议级，无钩子/技能树"
  - 纯注入型（`--platform prompt`）：自动从 README 提取【快速注入模板】输出/落盘，附各平台粘贴位置指引
- **`scripts/register_hooks.py` 钩子自动注册**（WorkBuddy + Claude Code 双平台同源格式，依据 reference/installation.md 官方样例）：
  - 注册四事件：UserPromptSubmit / PreToolUse / Stop（python 跨平台）+ SessionStart（检测到 bash 才装）
  - PreToolUse matcher 含 Bash（配合 v2.19.0 的 Bash 写文件检测）
  - 安全设计：写前带时间戳备份 / 原 JSON 损坏拒写不动用户配置 / 写后重载校验失败自动回滚 / 幂等（重复执行只替换宪法自己的条目）/ `--uninstall` 干净移除 / `--dry-run` 预览
- **`install.ps1` Windows PowerShell 版**：与 bash 版技能目录型流程对齐（探测→复制→重建→自检→可选 `-RegisterHooks`→记忆层指引）；如实标注本环境无 Windows 未实测，首次真机运行需用户回看结果
- **记忆层平台对照**：安装收尾输出各平台记忆文件位置与 `--memory` 指向方式（零号条款查记忆不再找错文件）
- `install.sh` 新增 `--target-dir`（规则文件型装入目标项目）与 `--register-hooks`（装完联动注册）

#### 修复
- install.sh `--register-hooks` 自定义技能目录时的路径传递（旧逻辑按平台默认目录找宪法导致注册失败）

#### 文档
- README / README_EN 快速开始改为平台分流表；reference/installation.md 钩子章节改"推荐自动注册"，手工格式降级为等价参考
- 英文 README 目录结构补 install.ps1 / register_hooks.py

#### 验证（本机实测）
- [x] cursor / windsurf（首次+幂等）/ prompt / 技能目录型四种安装模式全过；windsurf 已有规则内容保留
- [x] register_hooks 六场景全过：全新安装 / 用户钩子合并保留 / 幂等 / 损坏 JSON 拒写 / 卸载零残留 / 备份生成
- [x] `install.sh --register-hooks` 沙箱联动通过；修复路径传递后复测通过
- [ ] install.ps1 无 Windows 环境未实测（已如实标注，待真机首验）
- [x] 原 39 条测试无回归；版本全文件核查 2.20.0

## [2.19.0] - 2026-08-26

### 校验层防伪造升级 + 一键安装 + 对抗性测试进 CI + 英文 README
**背景**：外部深度测评（含实测复现）发现项目核心矛盾——"防糊弄"的校验器本身最容易被糊弄：一个 `"encoded"` 子串打穿 Layer C、一段含假链接的套话五步 `--strict` 全过、推荐链接里的 `github` 被当成"调用过技能"、新装用户无 MEMORY.md 时 step1 恒 FAIL 死锁、`check_injection` 缺树即崩溃、retry-wrapper 的"重试"是把错误报告喂给自己的检查器。本版本全部修复并把糊弄向量固化为自动化对抗测试。

#### 修复（校验层防伪造，P0）
- **词边界匹配全面替代裸子串**：Layer B/C 与分类器全部改用 `lib.text.keyword_in`——`"encoded"` 不再误命中 `"code"`、`"hi"` 不再命中 `"this"`、`"rapid"` 不再误命中 `"api"`
- **废除 Layer C "分类名出现即算命中"兜底**（step1/2/3 + check_injection）：`code`/`doc` 等常见短词不构成证据，必需技能校验只认**实际技能名**
- **证据白名单**（`lib/text.py` `GENERIC_EVIDENCE_BLOCKLIST` + `is_meaningful_evidence_name`）：名为 github/code/data 的单短词技能不再被误判为"调用过技能"（修复推荐链接即命中的漏洞）
- **记忆证据动态化**：Layer B 记忆标记改从 MEMORY.md 实际内容提取指纹（`extract_memory_markers`），废除硬编码作者私货（旧实现对其他用户恒 FAIL）
- **分类器双修**（零号条款）：简单词词边界 + **专业词优先**——"帮我解释这个报错然后修复代码并部署"不再被"解释"整体豁免；专业词保持宽松子串（误报只多查一次，符合"宁可不放过"）
- **统一执法口径**：gate 的 `is_simple` 委托 `pre-hook.classify_task`（单一词表），修复两套词表不同步（如"介绍一下"）
- **崩溃与死锁**：修 `check_injection` UnboundLocalError（树缺失+`--task` 时）；MEMORY.md / skill_tree.json 缺失时各硬校验**降级放行记 WARN**（新装用户不再恒 FAIL）
- **gate 拦 Bash 写文件**：重定向/tee/heredoc/cp/mv/touch/mkdir 视同 Write/Edit 进门禁（`>/dev/null` 不误报），堵住最大绕行通道
- **retry-wrapper 重做**：废除"把错误报告拼进输入再校验"的无效自我重试，改单次真实校验+结构化错误报告；补传 `--task`（旧版 Layer C 被静默跳过）

#### 新增（P1）
- **第 7 组对抗性防伪造测试**（15 条）：实测过的糊弄向量全部固化为"必须失败"；`ci.yml` 新增测试步骤（此前套件从未在 CI 执行）；移除从未 import 的 pyyaml 死依赖
- **`install.sh` 一键安装**：探测平台 → 复制 → 自动重建本机技能树（最易漏的一步）→ 自检 → 下一步指引
- **`README_EN.md` 英文 README**：面向英语社区（Claude Code 主用户群）；中文 README 顶部加入口 + 一键安装小节
- **`docs/release-notes-v2.19.0.md`**：首个正式 Release 的说明文案
- `build_skill_tree.py` venv 探测补 POSIX 路径（旧版只查 Windows，Linux/macOS 永远扫不到）

#### 验证（本机实测）
- [x] 原 24 条回归用例全过 + 15 条新对抗用例全过（**39/39**）
- [x] 伪造向量实测：`"encoded"` 打穿向量 → FAIL；全套伪造套话 → step1 FAIL；假链接冒充调用 → FAIL；混合任务豁免逃逸 → professional
- [x] `bash install.sh` 全流程实测（安装+重建+自检）；Bash 写文件检测 8 组边界用例全过
- [x] 版本全文件核查 2.19.0（SKILL.md frontmatter / skill_tree.json / README badge / 注入模板）

## [2.18.0] - 2026-08-24

### 新增：使用者建技能树指南（skill-tree-guide.md）+ 重建命令统一
**背景**：复盘"别人用 skills 宪法时怎么建技能树"——文档 7 处提到 build_skill_tree.py 但命令分散、裸命令无 SKILLS_DIR、缺"必须重建"警告、缺自检/FAQ。使用者照 README 跑会扫默认目录，技能不在树里 → 查树即"无匹配"（与作者快照问题同源）。

#### 新增/修复
- **新增 `reference/skill-tree-guide.md`**：为什么必须重建（作者快照 vs 你的技能）→ 完整命令（SKILLS_DIR/BINARIES_DIR + WorkBuddy/Claude Code/Cursor/Windows 四平台示例）→ 3 步自检确认（自检输出/total 对比/skills_dir 字段）→ 5 条 FAQ（total 不变/general 分类/Windows 路径/自动重建/改技能后重建）
- **SKILL.md**：技能树章节改"使用者安装后必须重建"+ Load 指向指南；参考文档列表新增第 4 项
- **README / reference/installation.md**：重建命令统一带 `SKILLS_DIR="$HOME/.workbuddy/skills"`（原裸命令会扫默认目录），并指向指南；验证章节补"应出现 ✓ 自检通过、total ≈ 实际技能数"

#### 验证（本机实测）
- [x] skill-tree-guide.md 生成（30+ 行，含命令/平台/自检/FAQ）
- [x] SKILL.md / README / installation 三处命令带 SKILLS_DIR 且指向指南
- [x] 版本全文件核查 2.18.0

## [2.17.0] - 2026-08-24

### 技能树重建（本机 757 技能全入库）+ 注入块记忆瘦身 + semantic_index 可选标注
**背景**：核查发现省 token 机制三处失效——① skill_tree.json 是作者 HUAWEI 机器快照（402 技能 vs 本地 757，覆盖不到一半，查树即"无匹配"）；② 注入块记忆层按固定 marker 取前 4 段或前 800 字符，与任务相关性低，把技能树省下的 token 又吃回去；③ semantic_index.py 依赖未装、向量文件不存在，是"死机制"却无标注。

#### 修复
- **技能树重建**：本机运行 `SKILLS_DIR=~/.workbuddy/skills python scripts/build_skill_tree.py`，**402 → 757 技能全入库**（15 分类，含 binaries 库 3 个），`skills_dir` 改为本机路径，`generated_at` 更新；SKILL_TREE.md 同步。技术边界章节补充"使用者应在本机生成自己的树，替换作者快照"
- **注入块记忆瘦身（`pre-hook.py` 新增 `extract_memory_relevant`）**：按 `## ` 切分 MEMORY.md → ①铁律/偏好类 section 总是注入（≤2 个×300 字）②其余按任务扩展文本重叠打分取 top2（各 400 字）③兜底前 400 字。**MEMORY.md 42KB 全文 → 注入 0.8-1.1K 字符（任务相关片段）**，且"推送代码到github"实测命中"GitHub 网页建仓排坑""抖音推广 GitHub 项目"等相关 section
- **semantic_index.py 明确标注可选（默认未启用）**：README / reference/gate-details.md / SKILL.md 技术边界三处标注启用方式（`pip install sentence-transformers faiss-cpu` 约 90MB + `python scripts/semantic_index.py build`），避免"死机制"误导

#### 验证（本机实测）
- [x] build_skill_tree 自检通过（分类 860 >= total 757）；顶层 version 2.17.0
- [x] extract_memory_relevant：爬虫/github/周报/翻译 4 任务注入 788-1104 字符（全文 42K 的 ~2.5%），含铁律+任务相关 section
- [x] pre-hook.py 编译通过、injected-context.json 生成仍合法
- [x] 版本全文件核查 2.17.0

## [2.16.0] - 2026-08-24

### Token 瘦身：description 只留触发条件 + SKILL.md 渐进式披露 + 注入 JSON 修复
**背景**：复盘确认项目在"增加 token"方向上只进不出——description 2069 字符中 90% 是版本历史（每次对话扫描技能列表都付 ~2K token）；SKILL.md 膨胀到 682 行/42KB（每次加载全付）；injected-context.json 用 heredoc 手写，PRE_HOOK_ERR 含反斜杠导致 JSON 非法 → UserPromptSubmit 钩子读不到 status → 每次专业任务误报"【宪法拦截】"。

#### 修复
- **description 瘦身**：2069 字符 → ~415 字符，版本历史全移出（放 CHANGELOG），只留触发条件（文章公式：[做什么]+[怎么做]+[什么时候用]）。**每次对话省 ~1.8K token**
- **SKILL.md 渐进式披露**：平台映射表/安装与验证/门禁详解拆到 `reference/`（platform-mapping.md 51 行 / installation.md 101 行 / gate-details.md 132 行）；主文件加"参考文档（按需加载）"契约式引用。**SKILL.md 682 行/42KB → 327 行/8.4KB（省 80%）**
- **修复 injected-context.json JSON 转义**：session-start.sh 有 python 时改用 `json.dump`（环境变量传值防 shell 注入），无 python 保留 heredoc 兜底。修复后 UserPromptSubmit 钩子能正常读到 status，不再误报拦截
- **注入去重确认**：user-prompt-submit.sh 只校验不注入，SessionStart 注入一次，无重复
- 版本史迁移：SKILL.md description 不再堆版本历史，统一看 CHANGELOG.md

#### 验证（本机实测）
- [x] description 415 字符（原 2069）；SKILL.md 327 行/8.4KB（原 682 行/42KB）
- [x] 六条宪法/第五条 v2.15 排除已装/快速注入模板/违规判定 全部保留
- [x] reference/ 三文件生成，主文件契约引用 3 处
- [x] session-start.sh 运行后 injected-context.json 合法（json.load 通过），bash -n 语法通过
- [x] 版本全文件核查 2.16.0

## [2.15.0] - 2026-08-24

### 修复：推荐板块把本地已装技能列入推荐（第五条缺口 + Layer E 硬校验）
**背景**：2026-08-24 复盘——交付推荐板块时把**本地已装（24/24）的 addyosmani/agent-skills** 列入 GitHub 推荐。根因：第五条只禁"以本地已装清单替代搜索"，未防"搜索结果恰好命中已装仓库"；step5 门禁只校验"有链接+star+获取方式"，不校验"是否已装"。与 v2.14.0 假查漏洞同构：条文有缺口 + 门禁不拦。

#### 修复
- **第五条补硬性条款（SKILL.md / AGENTS.md / 快速注入模板 / README 模板四处同步）**："推荐候选必须排除本地已装技能——推荐前先核对本地已装清单（如 `ls ~/.workbuddy/skills/`），已装项一律不推，包括'搜索结果恰好命中已装仓库'的情况；仅可作背景说明"
- **`step5-check.py` 新增 Layer E 本地已装排除校验**：
  - E1：推荐仓库 repo 名 与 本地技能目录名（去 `__skillhub` 等后缀）完全匹配 → FAIL
  - E2：本地存在 `_<name>-references` 已装框架标记目录，推荐 repo 名与该框架名匹配（如本地 `_agent-skills-references` 存在 → 推荐 agent-skills FAIL）→ FAIL
  - 支持 `--skills-dir` 参数指定本地技能目录（默认 `~/.workbuddy/skills`）
- **违规判定新增**："推荐了本地已装技能（Layer E 校验 FAIL）"

#### 验证（本机实测）
- [x] Layer E：推荐 `github.com/addyosmani/agent-skills`（本地已装）→ FAIL（E2 框架标记命中）
- [x] Layer E：推荐 `github.com/xxx/test-driven-development`（本地已装同名技能）→ FAIL（E1）
- [x] Layer E：推荐未装仓库（如 rjmurillo/ai-agents）→ PASS
- [x] 版本全文件核查：SKILL.md / README / CHANGELOG / skill_tree.json 均 2.15.0

## [2.14.0] - 2026-08-24

### 修复："假装查技能"漏洞闭环（WorkBuddy 宿主钩子）
**背景**：复盘发现 Agent 可以"口头假装查了技能树然后说无匹配"，旧门禁拦不住——UserPromptSubmit 只重置状态、PreToolUse 只查状态文件是否 PASS（旧 PASS 一次通过、后续所有 Write/Edit 永久放行）、Stop 校验只软提示不记录。

#### 修复
- **新增 `scripts/constitution-gate.py`（v2.14.0）**：WorkBuddy settings.json 钩子的正式实现，三事件：
  - `PreToolUse` 新鲜度校验：step1 的 ts 必须 ≥ 本任务 UserPromptSubmit 写入的 `reset_ts`，旧任务 PASS 不再赦免（exit 2 阻断 + 指引如何合规通过）
  - `Stop` 违规硬记录：校验最终回复（`--step 1 --strict --task <last_task>`，Layer C 任务相关技能命中），FAIL 写入 `.constitution-violations.json`（累计计数 + 时间 + 原因 + 任务），PASS 清空违规标记
  - `UserPromptSubmit` 违规警告注入：有违规记录时输出到 stdout（平台注入 Agent 上下文），下个任务开头 Agent 即见"上轮假查被抓"警告
- **去掉 HUAWEI 硬编码**：`hooks/session-start.sh`、`hooks/user-prompt-submit.sh`、SKILL.md frontmatter 三处 `PLUGIN_ROOT` 改为 `CODEBUDDY_PLUGIN_ROOT` 环境变量优先 + 脚本自定位兜底；session-start 定位失败报错退出、user-prompt-submit 定位失败静默放行（fail-open）
- **SKILL.md frontmatter 移除 hooks 块**：跨平台仓库不再写死机器路径；WorkBuddy 钩子改走 `~/.workbuddy/settings.json`（见安装章节），CodeBuddy 走 `hooks/hooks.json`
- **文档补齐**：安装章节新增 WorkBuddy settings.json 三步注册示例；README 改版说明；skill_tree.json version 同步
- **验证中发现并修复**：
  - `scripts/lib/text.py`：`read_input` 支持 `-` 显式 stdin（原 `--input -` 会 FileNotFoundError——**v2.11.0 遗留 bug，Stop 钩子校验因此从未真正生效**，是"假查从没被 Stop 拦过"的根因之一）
  - `hooks/session-start.sh`：内联 python 解析改 `printf` + generator（`echo` 对反斜杠/横线开头不安全、嵌套方括号偶发解析问题）；`rm -f pre-hook.err` 容忍失败（部分沙箱拦截 rm）

#### 验证（本机实测）
- [x] `bash -n` 两个 .sh 语法通过；gate.py 三事件模拟运行（UserPromptSubmit 重置+警告注入 / PreToolUse 新鲜度拦截 / Stop 违规记录）
- [x] PreToolUse 新鲜度：旧 PASS 状态（ts < reset_ts）→ 阻断；本任务内新 PASS → 放行
- [x] Stop：假查文本（无技能名）→ 违规计数 +1；合规文本（含三查+技能名）→ 清零
- [x] skill_tree.json / SKILL.md / README / CHANGELOG 版本号全文件核查一致

## [2.13.3] - 2026-08-21

### 修复：python 分支失败原因可定位 + 兜底文案动态化

**背景**：复盘发现 edge case——session-start.sh 的 python 分支失败时 stderr 被 `2>/dev/null` 丢弃，失败原因无从定位；bash 兜底模板固定写「无 python 环境」，与真实原因（python 分支失败）不符，导致误判环境。

#### 修复
- `session-start.sh`：python 分支 stderr 捕获到临时文件并快照进 `debug.pre_hook_stderr`（不再丢弃），失败原因可定位
- 兜底模板文案动态化：`fallback_reason` 区分 `no_python`（PATH 无 python3/python/py）与 `python_branch_failed`（有 python 但 pre-hook.py 未产出注入块），注入块标题与提示按真实原因生成
- `injected-context.json` 新增 `python_branch_ok` / `fallback_reason` / `debug.pre_hook_stderr` 三个字段

#### 验证
- 成功路径：`branch_ok=yes`、`injected_cats=doc,code,browser,email,memory`、注入块 3266 字符 ✅
- 模拟 python 分支崩溃：`fallback=python_branch_failed`、`debug.pre_hook_stderr` 捕获到模拟错误信息 ✅
- 无 python 环境（PATH 受限）：`fallback=no_python`、bash 兜底注入块含记忆+技能树路径 ✅

## [2.13.2] - 2026-08-21

### 修复：宪法 hooks 未真正执行的三大根因

**背景**：v2.13.0 上线后实测发现，Agent 上下文只注入了一行 `宪法上下文已注入: memory=1237字 tree=0分类`，技能树分类为 0、无任何可执行内容，宪法形同虚设。逐层排查确认三大根因并全部修复：

#### 根因1：hook 环境 PATH 无 `python3`，技能树注入静默归零
- `session-start.sh` / `user-prompt-submit.sh` 硬编码调用 `python3`，而平台 hook 进程的 PATH 不含 managed python → `2>/dev/null || echo 0` 把所有失败静默吞掉 → `tree_categories=0`、注入分类为空
- **修复**：解释器检测 `python3 → python → py` 逐个尝试（`command -v`），全部缺失时降级到 bash 兜底注入

#### 根因2（最致命）：脚本只输出一行统计，完整注入块从未进入 Agent 上下文
- `pre-hook.py` 能生成 3500+ 字符的完整注入块（宪法三查要求 + 记忆层 + 技能树分类 + SAD 候选技能），但 `session-start.sh` 只 `echo` 了一行统计信息 → Agent 上下文里从来没有宪法实体内容，无从执行
- **修复**：`session-start.sh` 把 `pre-hook.py` 生成的 `injection` 字段**完整输出到 stdout**（平台 hook 会注入 Agent 上下文）；无 python 环境用 bash 兜底注入宪法三查核心条款 + 记忆原文 + 技能树路径

#### 根因3：UserPromptSubmit 拦截被 `|| exit 0` 中和，永不阻断
- `hooks.json` 中钩子命令带 `|| exit 0`，脚本 `exit 1`（拦截）被强制转成 0 → 拦截机制永远不生效
- **修复**：去掉 `|| exit 0`，保留真实退出码；SessionStart 去掉 `>/dev/null 2>&1 &` 后台丢输出，改为前台执行

#### 其他修复
- bash 兜底分类计数：grep 模式匹配数组结构 `"doc": [`（原 `{` 模式匹配不到）；排除技能对象内嵌 `"categories": [`；`tr -d '\r\n'` 防换行污染 JSON
- `injected-context.json` 增加 `python` / `injection_len` 字段，便于排查注入是否成功

#### 验证
- 有 python3 环境：完整注入块（记忆+技能树+SAD 候选）✅，tree=14
- 无 python 环境（模拟平台 hook PATH）：bash 兜底注入块 ✅，tree=14，JSON 合法
- 分类器：专业任务放行（注入 ready）、简单任务放行 ✅

## [2.13.1] - 2026-08-21

### 安装到 WorkBuddy：钩子真正跑起来（settings.json 注册 + stdin JSON 兼容）

#### 新增

- **`~/.workbuddy/settings.json` 注册钩子**：SessionStart + UserPromptSubmit 写入用户级 settings.json，全局生效（不再依赖 hooks.json 单点声明）
- **SKILL.md frontmatter 增加 `hooks` 字段**：技能随包分发时钩子跟着走，与 settings.json 注册形成双保险

#### 修复

- **`user-prompt-submit.sh` 兼容 WorkBuddy stdin JSON payload**：支持解析 `{"prompt": ...}` 字段，同时兼容 `--input` 传参，两种入口都能正确分类

#### 验证

- SessionStart 注入 ✅ / 专业任务放行 ✅ / 简单任务跳过 ✅ / 无注入拦截 ✅

## [2.13.0] - 2026-08-21

### 重大更新：宪法强制拦截上线 — hooks + Ruler 跨平台分发

**核心目标**：把宪法从"建议性规则"升级为"可强制拦截的运行时机制"。

#### 新增：WorkBuddy 钩子系统（`hooks/`）
- `hooks.json`：注册 `SessionStart` + `UserPromptSubmit` 两个系统事件钩子
- `session-start.sh/.ps1`：会话启动时自动运行 pre-hook.py，注入记忆+技能树上下文到 `injected-context.json`
- `user-prompt-submit.sh`：任务提交前调用分类器判断通道（简单→A 跳过 | 专业→B 强制门禁）

#### 新增：Ruler 跨平台分发
- `.ruler/AGENTS.md`：宪法核心条款单一源文件
- `ruler apply` 一键分发到 10 个平台：Claude Code / Cursor / Cline / Codex / Copilot / Windsurf / Aider / Goose / OpenCode / Gemini CLI
- 生成分发文件：`CLAUDE.md` / `AGENTS.md` / `.clinerules` / `.goosehints` / `.aider.conf.yml` / `.gemini/settings.json` / `.codex/config.toml` / `opencode.json` / `.mcp.json`

#### 修复
- **pre-hook.py --classify 模式忽略 --task 参数**：之前只从 stdin 读取，导致命令行调用始终返回 ambiguous
- **Windows 路径兼容**：Git Bash `/c/Users/...` 路径在 Windows Python 中不被识别，新增 `to_win()` 路径转换函数

### 影响范围
- WorkBuddy 用户：需在插件管理页面点击"Trust"激活 hooks（否则仅作为建议规则生效）
- Claude Code / Cursor / Windsurf 等用户：将 `.ruler/AGENTS.md` 内容复制到对应规则文件即可生效
- 所有平台：宪法从"被动读取"升级为"主动拦截"

---

## [2.12.1] - 2026-08-19

### 修复：宪法自举 — 技能关键词映射 + SAD 排除逻辑

**问题复盘**：用户任务「把最新版本的 skills 宪法，安装到元规则层」未触发 skills-constitution，宪法自己接不到自己的活。

#### 修复

- **关键词映射补缺**：`REQUIRED_CATEGORY_KEYWORDS` 新增 `skill` / `skills` / `技能` → meta 分类映射（此前缺失导致任务分类失败）；补充 `安装` / `install` / `配置` 相关映射
- **SAD 排除逻辑改条件排除**：`loose_retrieve_skills()` 原硬编码排除 skills-constitution 自身（防空头汇报），但在「安装/配置宪法」类任务中宪法本身就是目标，不应排除。现改为**条件排除**——仅当任务不含「安装/install/配置/configure」时才排除自身

#### 验证

- 宪法自举任务实测：skills-constitution 排 SAD 检索第 1 位（score=0.673）✅

## [2.12.0] - 2026-08-19

### 重大改版：SkillWeaver 启发 —— 语义增强 + 防蒙混升级

**核心问题**（对照 SkillWeaver 论文解读逐条评审后确认）：
1. 关键词硬编码存在双向缺陷：子串误杀（`code` 命中 `encode`、`search` 命中 `research`）+
   口语漏判（"我要把代码传上去"无 git 关键词 → Layer C 失效）
2. Agent 可引用**真实存在但与任务无关**的技能名蒙混过关（Layer B 只验"名在树中"，不验"与任务相关"）
3. 单技能匹配假设无法覆盖"下载→清洗→出报告"类多步骤任务
4. 论文的 sentence-transformers/FAISS/cross-encoder 方案为重依赖，与项目
   "主链路零依赖、确定性、任何平台可跑"原则冲突 → 全部做零依赖适配，重依赖只作可选增强层

#### 新增：任务同义词扩展（`pre-hook.py` TASK_SYNONYM_MAP）
- 口语/近义表达 → 正式关键词确定性映射："传上去/推上去/上传代码/同步代码"→git/push；
  "抓一下/爬一下/采集"→爬虫/抓取；"上线/发布"→部署 等
- 同步作用于任务分类器（--classify）、必需分类映射（Layer C 依据）、注入块分类过滤

#### 新增：SAD 宽松语义检索（`pre-hook.py` loose_retrieve_skills）
- SkillWeaver SAD 反馈循环的确定性实现：粗检索环节代码化，
  按任务与技能描述的 token 重叠度（零依赖：中文单字+二元组、英文词+连字符子词拆分、
  git/github 子串近似）检索 top-K 候选注入上下文
- 注入块新增「🧠 SAD 候选技能」段落，Agent 起草方案时带着候选完成第二轮用词对齐

#### 新增：Layer D 语义相关性校验（`steps/step3-check.py`）
- 输出引用的技能中至少一个与任务文本 overlap_score ≥ 0.10（保守阈值防误杀），否则 FAIL
- 任务文本先经同义词扩展再打分，避免口语任务误判零相关

#### 新增：多技能编排兼容性检查（`steps/step4-check.py` + `registry.json`）
- registry.json 16 条全部增加 input_schema / output_schema
- step4 识别技能链（`A` → `B`），校验相邻技能 output→input 兼容；无 schema 覆盖跳过（保守）

#### 新增：可选语义向量索引（`scripts/semantic_index.py`，SkillWeaver 启发一完整实现）
- sentence-transformers（all-MiniLM-L6-v2，本地免费）构建全量技能 embedding 索引
- query 语义检索 top-K；faiss-cpu 可选（缺省 numpy 余弦，功能等价）
- 缺依赖明确提示安装并 exit 2（功能开关非兜底），不影响主链路

#### 修复：分类子串误杀（`build_skill_tree.py`）
- 英文关键词改词边界正则匹配（`lib/text.py` keyword_in）：code≠encode、search≠research

#### 顺手修复（2026-08-19 调研发现的 4 个已核实 Bug）
- SKILL.md 正文头部版本号过期（v2.8.0 → 与 frontmatter 同步）
- CHANGELOG [Unreleased] 链接指向错误（v2.10.0...HEAD → v2.11.0...HEAD）
- ci.yml 补 workflow_dispatch 触发器（原 SKILLS_DIR inputs 永远为空，rebuild 步骤是死代码）
- README 静态 badge 技能数硬编码失真（去掉数字，标注 author snapshot）

#### 验证测试（本机实测通过，见 scripts/tests/run_tests.py）
| 场景 | 结果 |
|------|------|
| 口语任务"我要把代码传上去"（无 git 关键词） | 同义词扩展命中 code 必需分类 ✅ |
| 分类误杀用例（encode/research） | 词边界匹配不再误入对应分类 ✅ |
| SAD 候选检索（git 任务 top-K） | 含 git 类技能且按相关度排序 ✅ |
| Layer D：引用与任务无关的真实技能 | FAIL ✅ |
| Layer D：引用相关技能 | PASS ✅ |
| 技能链 schema 不兼容 | step4 FAIL ✅ |
| semantic_index.py 缺依赖 | 提示安装 exit 2 ✅ |

### 新增文件
- `scripts/semantic_index.py` - 可选语义向量索引（增强层）
- `scripts/tests/run_tests.py` - 零依赖回归测试（CI 可跑）

### 修改文件
- `scripts/lib/text.py` - keyword_in 词边界匹配 / tokenize / overlap_score 轻语义工具
- `scripts/pre-hook.py` - 同义词扩展 + SAD 宽松检索 + 注入块新段落
- `scripts/build_skill_tree.py` - 分类改词边界匹配
- `scripts/steps/step3-check.py` - Layer D 语义相关性校验
- `scripts/steps/step4-check.py` - 多技能编排兼容性检查
- `registry.json` - 16 条增加 input/output schema
- `.github/workflows/ci.yml` - 补 workflow_dispatch + 跑回归测试
- `SKILL.md` / `README.md` - 同步 v2.12.0

## [2.11.0] - 2026-08-16

### 重大改版：任务相关硬校验（Layer C）+ 命中清单强制 + 推荐定位修正

**核心问题**：v2.10.0 的硬校验只验证"是否引用了 MEMORY.md/skill_tree.json 的任何内容"，
导致 Agent 可以用"查了 skills-constitution 就算查了技能"糊弄——任务要编代码/推 GitHub，
输出却只写"已读技能树"，没有任何代码类技能名被引用，门禁照样过。

**解决方案**：把"查技能树"从"读文件"升级为"命中任务对应分类的实际技能"：

#### 新增 Layer C：任务相关硬校验（step1/2/3 + pre-hook）
- `pre-hook.py` 新增 `REQUIRED_CATEGORY_KEYWORDS` 确定性映射（40+ 关键词 → 必需分类）：
  - `git/github/push/commit/deploy/部署/代码/编码/编程/写一个/实现/开发` → `code` 分类
  - `爬虫/抓取` → `browser` + `data`；`网页/网站/前端/浏览器` → `browser`
  - `文档/word/excel/ppt/pdf/表格` → `doc`；`数据/分析/报表/图表/可视化` → `data`
  - `邮件` → `email`；`图片/图像/设计` → `image`；`视频` → `video`
  - `金融/股票/基金` → `finance`；`记忆/知识库` → `memory`；`文件` → `file`
- `required_skills_for_task()` 从 skill_tree.json 提取必需分类下的实际技能名
- **校验规则**：任务命中关键词 → 输出必须引用对应分类的**实际技能名**（如 `git-workflow-and-versioning`）
  - 只写"已查 skills-constitution"或"已读技能树"而无具体技能名 → FAIL
  - 引用了错误分类技能（任务要代码，却只列 doc 分类）→ FAIL
- `constitution-check` 新增 `--task` 参数，透传给 step1/2/3 和 pre-hook 检查

#### 三查汇报强制命中清单
- 【宪法三查】②技能树必须**列出命中的技能名清单**（名称+依据）：
  `命中技能清单：git-workflow-and-versioning（代码/部署）、web-deploy-github（GitHub 推送）…`
- 禁止只写"已读技能树"——这属于 v2.11.0 新增违规项「空头查技能」

#### 第五条推荐定位修正（用户设计初衷确认）
- **初衷**：既然查了本地技能，还是没有完美解决工作 → 就应该去 GitHub 搜索相关技能，推荐给用户，用户自己决定是否下载安装
- **修正**：推荐触发场景 = 本地技能不足/效果不理想/超出范围；推荐内容 = GitHub 高 Star 技能（含链接+star+获取方式）；本地不足却不去搜索 → 违规

#### 验证测试
| 场景 | 结果 |
|------|------|
| 简单任务（翻译） | 通道A SKIP，零号条款豁免 |
| 专业任务（推送github）未注入三查 | 通道B BLOCKED |
| 专业任务写了三查但只写"已查宪法"无技能名 | Layer C FAIL ✅（本次修复目标） |
| 专业任务引用 `git-workflow-and-versioning` | Layer C PASS |
| 任务要代码却只引用 doc 分类技能 | Layer C FAIL（查错分支） |

### 修改文件
- `scripts/pre-hook.py` - 新增 REQUIRED_CATEGORY_KEYWORDS / required_categories_for_task / required_skills_for_task；注入块增加任务必需技能清单
- `scripts/steps/step1-check.py` - 新增 Layer C 任务相关硬校验
- `scripts/steps/step2-check.py` - 新增 Layer C 任务相关硬校验
- `scripts/steps/step3-check.py` - 新增 Layer C 任务相关硬校验
- `scripts/constitution-check` - 新增 --task 参数传递
- `SKILL.md` - 更新至 v2.11.0（三查模板/第五条/违规判定/门禁章节）
- `README.md` - 同步 v2.11.0

## [2.10.0] - 2026-08-16

### 重大改版：输入拦截 + 双通道执行

**核心问题**：v2.9.0 的门禁是"事后校验"（任务跑完才检查输出），拦不住 Agent 一开始就直接干活不查记忆/技能树。

**解决方案**：把门禁从"输出校验"升级为"输入拦截"，并协调零号条款豁免：

#### 新增 pre-hook.py（输入拦截）
- 任务开始前强制读取 MEMORY.md + skill_tree.json，生成注入块
- 注入块直接喂给 Agent，上下文"被迫"已有记忆规则和技能树分类
- `--check` 校验模式：检查开场是否已输出【宪法三查】，未注入即阻断（exit 1）

#### 双通道分流（零号条款协调）
- `--classify` 确定性分类器：简单任务关键词（翻译/润色/解释/概念）→ **通道A** 跳过门禁直接通用能力
- 专业任务关键词（编码/爬虫/API/文件/部署）→ **通道B** 强制注入校验 + step1-5 全量校验
- 模糊任务 → 宁可不放过，按通道B处理
- **关键**：分类器是确定性代码，不依赖 Agent 自觉判断任务类型，杜绝"把专业任务误判为简单任务"逃逸

#### 验证测试
| 场景 | 结果 |
|------|------|
| 简单任务（翻译） | 通道A SKIP，exit=0，零号条款豁免 |
| 专业任务（爬虫）未注入三查 | 通道B BLOCKED，exit=1，开始前被拦截 |
| 专业任务已注入三查 | 通道B 继续 step1-5 校验 |

### 新增文件
- `scripts/pre-hook.py` - 输入拦截 + 任务分类器

### 修改文件
- `scripts/constitution-check` - 增加 `--pre-hook` / `--classify` 双通道分流
- `SKILL.md` - 更新至 v2.10.0，文档新增双通道执行说明

## [2.9.0] - 2026-08-16

### 重大改版：引入「三明治架构」两层校验

**核心问题**：之前的门禁校验只检查文本是否包含关键词（软校验），
导致 Agent 可以"空头汇报"通过——嘴上说查了记忆和技能树，
实际上根本没执行，只是写了几个字就算过。

**解决方案**：参考微信公众号文章《我给Agent装了「三明治」架构——
90%的「忘记查知识库」问题被代码消灭了》，引入确定性代码包夹概率模型：

#### Pre-hook 层（输入前强制约束）
- **Step1 硬校验**：验证回复是否真实引用了 `MEMORY.md` 的内容
  - 提取 unique_markers：技能数量（389/388/385等）、铁律标记、技能目录名
  - 验证回复中是否出现了这些实际内容
  - 空头汇报（只写"已查"但没引用内容）→ FAIL
  
- **Step2 硬校验**：验证回复是否真实引用了 `skill_tree.json` 的内容
  - 提取分类名（browser/code/data/doc等）和技能名
  - 验证回复中是否出现了这些实际内容
  - 空头声明（只写"已读"但没引用内容）→ FAIL

#### Post-hook 层（输出后自动重试）
- **新增 retry-wrapper.py**：带重试循环的校验包装器
  - 单次校验失败时自动注入错误提示并重试
  - 最多重试 3 次（可配置），超限标记为需人工介入
  - 错误报告包含具体失败的步骤和修正建议
  - 严格模式与软模式双支持

#### 验证测试结果
| 场景 | 结果 |
|------|------|
| 合格输出 | 第2次尝试PASS（第一次step5 FAIL → 自动重试 → PASS） |
| 空头汇报 | 连续3次FAIL → 标记需人工介入 ✅ |

### 新增文件
- `scripts/retry-wrapper.py` - Post-hook重试循环机制
- `scripts/test_*.txt` (已清理)

### 修改文件
- `scripts/steps/step1-check.py` - 增加硬校验验证MEMORY.md内容
- `scripts/steps/step2-check.py` - 增加硬校验验证skill_tree.json内容
- `scripts/steps/step3-check.py` - 增加硬校验验证技能名引用
- `scripts/steps/step5-check.py` - 增加硬校验验证GitHub链接有效性
- `scripts/constitution-check` - 传递memory/tree参数到步骤函数

### 技术债务
- Git推送需要SSH密钥或Token认证，当前沙箱环境无法交互输入密码
- 本地commit已就绪，需手动`git push`到GitHub

## [2.8.0] - 2026-08-14

### 新增功能
- 精选技能注册表 `registry.json`（16条开源技能推荐）
- README/SKILL.md 增加注册表章节与指向

### 优化
- 技能树索引定位修正：明确索引为作者快照/示例，使用者应生成自己的索引

## [2.7.0] - 2026-08-13

### 修复
- 技能树索引定位修正：从"使用作者快照"改为"生成自己的技能树"

## [2.6.0] - 2026-08-12

### 新增
- 门禁自检脚本 `constitution-check`
  - 5个step独立校验
  - 默认软校验 + `--strict` 可选阻断
  - 状态文件链式依赖

## [2.5.0] - 2026-08-11

### 新增
- 技能树纳入已装 Python 库/工具（🧩 分类）
- 第一条升级为"查技能树无条件第一步 + 宪法三查汇报"

## [2.0.0] - 2026-08-10

### 重大更新
- 从零号条款到第五条完整闭环
- 跨平台通用适配表（WorkBuddy/Claude/Cursor/Gemini等20+框架）

## [1.0.0] - 2026-08-09

### 初始版本
- 宪法五步闭环：①先查 → ②匹配必用 → ③无匹配必搜 → ④能力边界确认 → ⑤答复时自动推荐
- 解决痛点：不调用、调用幻觉、调用混乱、能力误判、无复盘、扫描全量

---

**版本说明**：
- `MAJOR`（主版本号）：不兼容的 API 或架构变更
- `MINOR`（次版本号）：向后兼容的功能性新增
- `PATCH`（修订版本号）：向后兼容的问题修正

[Unreleased]: https://github.com/jiabaobei/skills-constitution/compare/v2.17.0...HEAD
[2.18.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.18.0
[2.17.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.17.0
[2.12.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.12.0
[2.11.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.11.0
[2.10.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.10.0
[2.9.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.9.0
[2.8.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.8.0
[2.7.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.7.0
[2.6.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.6.0
[2.5.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.5.0
[2.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.0.0
[1.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v1.0.0
