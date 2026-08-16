# Changelog

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

[Unreleased]: https://github.com/jiabaobei/skills-constitution/compare/v2.9.0...HEAD
[2.9.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.9.0
[2.8.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.8.0
[2.7.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.7.0
[2.6.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.6.0
[2.5.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.5.0
[2.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v2.0.0
[1.0.0]: https://github.com/jiabaobei/skills-constitution/releases/tag/v1.0.0
