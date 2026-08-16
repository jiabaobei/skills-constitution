# Changelog

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

[Unreleased]: https://github.com/jiabaobei/skills-constitution/compare/v2.10.0...HEAD
[2.11.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.11.0
[2.10.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.10.0
[2.9.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.9.0
[2.8.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.8.0
[2.7.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.7.0
[2.6.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.6.0
[2.5.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.5.0
[2.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.0.0
[1.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v1.0.0
