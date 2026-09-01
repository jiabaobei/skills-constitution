# 门禁校验机制详解（渐进式披露·附录）

> 按需加载：仅当调试/扩展 constitution-check 或 hooks 时引用本文件。

---

## v2.22.0：三查证据链（防绕过 + 防干扰双向修正）

> 背景（真实使用反馈）：① Agent 仍能骗过门禁直接跑任务；② 任务开始已查记忆/查技能/调用技能，中途门禁又拦截干扰；③ 项目整体要省 token。

### 证据链定义（constitution-gate.py）

「三查已完成」认两种证据，满足其一即放行写操作、收尾不重复校验：

1. **手动路径**：本任务内 `constitution-check --step 1` 真实校验通过（状态新鲜度：step1 的 ts ≥ 本任务 reset_ts，且 level 必须为 PASS——只认脚本真实判定结果）
2. **注入路径（v2.22.0 新增）**：平台注入上下文就绪（`hooks/injected-context.json` status=ready，24h 内）= 记忆+技能树已由平台强制注入视为已查；再叠加本任务内**实际调用过技能**（PreToolUse 观察到 `Skill` 工具调用自动记录进 state）即证据链完整。注入就绪但任务无必需分类（任务关键词未映射到任何技能分类）时直接放行——无技能可匹配

### 防绕过加固

- **门禁自身文件保护**：`.constitution-state.json` / `.constitution-simple` / `.constitution-violations.json` / `injected-context.json` 禁止被 Agent 经 Write/Edit/MultiEdit/NotebookEdit 或 Bash（重定向/tee/heredoc/rm/mv/cp/sed -i）篡改——旧版写一个豁免旗标文件即可全局豁免
- **Bash 写文件检测补 `sed -i`**（就地改写也是写文件）
- 防护只拦"写门禁文件"，读门禁文件与跑 `constitution-check` 不受影响（防死锁）

### 防干扰修正

- **追加式消息不重置**：超短消息（≤8 字符）或以追加标记开头（继续/好的/下一步/ok/continue…）视为同一任务延续，保留既有证据——消除"任务中途每条追加消息都要求重新三查"
- **Stop 防误记**：本任务内已有证据链时跳过最终回复的重复文本校验——修复"任务开头已查过、收尾回复没复述三查就被误记违规、下任务开头被误注入警告"
- **注入自愈（hooks/user-prompt-submit.sh）**：注入上下文缺失/过期时现场重跑 SessionStart 注入（幂等），不再直接【宪法拦截】挡任务；自愈仍失败才拦截
- **阻断文案精简**：提示补救路径（先调技能 / 手动跑 step1），文案约省一半

### Token 瘦身

- 注入块默认参数收紧：SAD 候选 6→4 条、描述截断 60→40 字、每分类技能清单 12→8 个、记忆片段上限 1200→900 字、执行要求文案精简（单次注入约省 30%）
- `hooks/hooks.json` UserPromptSubmit matcher 由约 8KB 关键词列表改为 `.*`（分类在 hook 脚本内做，简单任务秒级 exit 0，matcher 列表纯属冗余）
- SKILL.md 顶部多版本史压缩为一行，详情移入 CHANGELOG.md

---

## 门禁校验机制（v2.6.0 新增；v2.10.0 升级为输入拦截 + 双通道；v2.11.0 升级为任务相关硬校验）

> 目的：把「靠 Agent 自觉」变成「可校验、可拦截」。校验脚本只负责 PASS/FAIL；真正的强制触发依赖宿主 hook（如 WorkBuddy/Claude Code 的钩子），无 hook 环境退化为软校验。
>
> ⚠️ **仅适用专业任务**：简单问答（翻译、润色、解释概念、一般知识问答）按**零号条款**跳过，**不跑门禁**——调用方应传 `--simple` 声明（脚本直接 SKIP 退出），防止简单任务被误拉去校验（如无推荐板块导致误 FAIL）。

### 双通道执行（v2.10.0）

零号条款与强制拦截的协调：**用确定性代码分类，而不是靠 Agent 自觉判断任务简不简单**。

```
任务进入
  │
  ├─ pre-hook.py --classify（零号条款分类器）
  │    ├─ 命中简单关键词（翻译/润色/解释/概念/闲聊…）→ 【通道A】跳过门禁，直接通用能力 ✅
  │    └─ 命中专业关键词（编码/爬虫/API/文件/部署…）→ 【通道B】强制注入校验
  │         ├─ v2.11.0: pre-hook.py --task 提取任务必需分类（代码/git/部署→code 分类）
  │         └─ 未输出【宪法三查】或未引用任务对应分类技能名 → BLOCKED（exit 1）
  │         └─ 已输出【宪法三查】且命中任务分类技能 → 继续 step1-5 全量校验
  └─ 模糊任务 → 宁可不放过，按通道B处理（宪法零号条款：模糊任务 ✅ 查一下）
```

- **通道A（简单）**：零号条款豁免，直接通用能力，不查记忆/技能树，不拦截
- **通道B（专业/模糊）**：pre-hook 强制注入记忆+技能树，未汇报三查即阻断；**v2.11.0 任务关键词硬校验**——任务含"代码/git/部署"等关键词时，输出必须引用 skill_tree.json 对应分类的实际技能名（如 `git-workflow-and-versioning`），否则 BLOCKED

### 目录结构
```
scripts/
├── constitution-gate.py        # v2.22.0 WorkBuddy 宿主钩子（三查证据链：注入+技能调用 / 手动 step1 PASS；门禁文件保护）
├── pre-hook.py                 # v2.10.0 输入拦截 + 任务分类器；v2.11.0 任务必需技能映射
├── constitution-check          # 主入口（--pre-hook / --classify / --simple / --task）
├── retry-wrapper.py            # v2.9.0 Post-hook 重试循环
├── steps/
│   ├── step1-check.py          # 三查汇报校验（软+硬两层 + v2.11.0 Layer C 任务相关校验）
│   ├── step2-check.py          # 技能树已读/无匹配声明（软+硬两层 + Layer C）
│   ├── step3-check.py          # 匹配技能调用（软+硬两层 + Layer C）
│   ├── step4-check.py          # 交付自检（非版本类任务自动跳过）
│   └── step5-check.py          # 推荐板块（GitHub 链接 + star 数，软+硬两层）
└── lib/
    ├── state.py                # 状态文件（.constitution-state.json，链式依赖）
    └── text.py                 # 文本/正则工具
```

### 用法
```bash
# 双通道分流（推荐入口）：自动判定任务类型，简单跳过/专业强制
python scripts/constitution-check --classify --input task.txt

# 双通道 + 任务相关硬校验（v2.11.0）：专业任务必须引用对应分类技能名
python scripts/constitution-check --classify --task "推送github代码" --input output.txt --strict

# 输入拦截：先校验开场是否已注入三查，未注入即阻断
python scripts/constitution-check --pre-hook --input output.txt --strict

# 全量软校验（默认：FAIL 只警告，不阻断）
python scripts/constitution-check --input output.txt

# 严格模式：FAIL 即阻断（exit 1）
python scripts/constitution-check --input output.txt --strict

# 简单任务豁免（零号条款：翻译/润色/概念解释，跳过门禁）
python scripts/constitution-check --simple

# 只跑指定 step（如推荐板块校验）
python scripts/constitution-check --step 5 --input output.txt

# 机器可读输出 / 重置状态
python scripts/constitution-check --input output.txt --json
python scripts/constitution-check --reset

# 直接生成注入块（任务开始前喂给 Agent；v2.11.0 含任务必需技能清单）
python scripts/pre-hook.py --task "推送github代码"
```

### 设计要点
- **默认软校验、`--strict` 可选**：宪法正文永远是"行为规则"（任何平台可遵守的兜底）；脚本是"增强层"。**禁止**把"必须先跑脚本"写进宪法正文——在跑不了脚本的环境（ChatGPT/Kimi/豆包等建议型平台）会被 Agent 判为"不可满足"而整体跳过宪法
- **链式依赖**：状态文件记录每步 PASS/FAIL，strict 模式下前置 step 未通过则拒绝执行下一步（逐步验证再往下走）
- **校验输入 = Agent 输出文本 + 状态痕迹**：设计上要求 Agent 每步显式输出产物并调用 check 写状态，脚本才有内容可查
- **校验失败在软模式下仅警告**，脚本 bug/状态丢失不会卡死任务
- **分类器是确定性代码**：简单/专业关键词硬编码，不依赖 Agent 自觉判断任务类型，杜绝"把专业任务误判为简单任务"的逃逸
- **v2.14.0 防"假装查技能"闭环**：① PreToolUse 只认**本任务内新鲜 PASS**（step1 的 ts ≥ UserPromptSubmit 的 reset_ts），旧任务 PASS 不赦免任何 Write/Edit；② Stop 硬记录——最终回复未含三查+任务相关技能名（Layer C）即写入 `.constitution-violations.json` 累计计数；③ 下个任务 UserPromptSubmit 把违规警告注入 Agent 上下文（stdout），"事前拦 + 事后记 + 下次警"。违规记录文件不影响任何平台行为，仅作威慑与审计。

---

## v2.12.0：SkillWeaver 启发改版（语义增强 + 防蒙混升级）

> 背景：对照 SkillWeaver 论文解读（语义检索 / SAD 反馈循环 / 多技能编排 / 语义校验）逐条评审后落地。
> 原则不变：**主链路零依赖、确定性**；重依赖语义模型（sentence-transformers）只作可选增强层。

### ① 任务同义词扩展（修复"词不对就抓瞎"）
- `pre-hook.py` 新增 `TASK_SYNONYM_MAP`：口语/近义表达 → 正式关键词（确定性映射，不需要 LLM-in-loop）
- 案例（v2.11.0 真实漏洞）：用户说"我要把代码传上去"，无 git/push 关键词 → Layer C 失效；
  v2.12.0 经同义词扩展后命中 `code` 必需分类，门禁恢复生效
- 扩展同步作用于：任务分类器（`--classify`）、必需分类映射、注入块分类过滤

### ② SAD 宽松语义检索（Skill-Aware Decomposition 的确定性实现）
- SkillWeaver 的 SAD 需要 LLM 草拟→检索→喂回→重写；本实现把"粗检索"环节代码化：
  `loose_retrieve_skills()` 按任务与技能描述的 **token 重叠度**（零依赖，中文单字+二元组、英文词+子词拆分、git/github 子串近似）检索 top-K 候选
- 注入块新增「🧠 SAD 候选技能」段落：Agent 起草方案时天然带着候选技能完成"第二轮重写对齐"
- 收益：从"扫描整个分类 ~50 个技能"收窄到"重点看 5-6 个最相关候选"，token 再降一档

### ③ Layer D 语义相关性校验（step3 新增）
- 防的漏洞：Agent 引用一个**真实存在但与任务无关**的技能名蒙混过关（Layer B 只验"名在树中"，不验"与任务相关"）
- 规则：输出引用的技能中，至少一个与任务文本 overlap_score ≥ 0.10（保守阈值防误杀），否则 FAIL
- 任务文本先经同义词扩展再打分，避免"口语任务"被误判零相关

### ④ 多技能编排兼容性检查（step4 新增，启发三轻量落地）
- `registry.json` 16 条全部增加 `input_schema` / `output_schema` 字段
- step4 识别输出中的技能链（`` `A` → `B` ``），按 schema 校验相邻技能 输出→输入 是否兼容；
  无 schema 覆盖的相邻对跳过（保守，不误杀）

### ⑤ 可选语义向量索引（`scripts/semantic_index.py`，启发一完整实现）
> **⚠️ v2.17.0 明确标注：默认未启用（需手动安装依赖 + 构建索引）**。SAD 宽松语义检索（零依赖确定性实现）已覆盖日常检索需求；本模块是锦上添花的可选增强，不启用不影响主链路任何功能。
- 启用方式：`pip install sentence-transformers faiss-cpu`（约 90MB）→ `python scripts/semantic_index.py build` → 生成 `skill_vectors.npz`
- `build`：sentence-transformers（all-MiniLM-L6-v2，本地免费）为全量技能描述生成 embedding，存 `skill_vectors.npz`
- `query`：任务文本语义检索 top-K；装了 faiss-cpu 走 FAISS，没装走 numpy 余弦（功能等价）
- **缺依赖时明确提示安装并退出（exit 2）**——这是功能开关不是兜底；不装不影响主链路任何功能

### ⑥ 分类子串误杀修复（`build_skill_tree.py`）
- 英文关键词改用**词边界正则**匹配：`code` 不再误杀 `encode`、`search` 不再误杀 `research`；中文关键词保持子串匹配

### 验证测试（v2.12.0 已本机实测）
| 场景 | 结果 |
|------|------|
| 口语任务"我要把代码传上去"（无 git 关键词） | 同义词扩展命中 code 必需分类，pre-hook 校验生效 ✅ |
| 分类误杀用例（encode/research 描述） | 词边界匹配不再误入 code/search 分类 ✅ |
| SAD 候选检索（git 任务） | top-K 含 git 类技能且按相关度排序 ✅ |
| Layer D：引用与任务无关的真实技能 | FAIL（疑似乱引用）✅ |
| Layer D：引用相关技能 | PASS ✅ |
| 技能链 schema 不兼容（docx→git-workflow） | step4 FAIL ✅ |
| semantic_index.py 缺依赖 | 明确提示安装，exit 2，不影响主链路 ✅ |

---

