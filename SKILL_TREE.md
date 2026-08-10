# 技能树索引

**生成时间**: 2026-08-10T15:52:00
**总技能数**: 655
**技能目录**: `~/.workbuddy/skills`

---

## 分类概览

本索引按功能类型分类全部技能，Agent 执行时**按分支定位**，减少 80% 扫描量。

### 📜 元规则类 (2 个)
- `skills-constitution` (v2.2.0): Skills 宪法 —— 凌驾于全部技能之上的元规则
- `skills-security-check` (v1.0.0): Skill 安全审查工具，对技能进行全面安全审计

### 🧠 记忆管理类 (6 个)
- `aiweko-memory-reports` (v1.0.0): 一键为工作空间搭建本地三层记忆体系
- `agent-memory` (v1.0.0): Agent Memory — 持久化记忆系统
- `elite-longterm-memory` (v1.0.0): 精英长期记忆系统
- `memory-hygiene` (v1.0.0): 记忆卫生清理工具
- `memory-manager` (v1.0.0): 记忆管理器
- `memory-setup` (v1.0.0): 记忆系统初始化配置

### 🌐 网页自动化类 (2 个)
- `browser-skill` (v0.1.9): 腾讯开源浏览器自动化工具 bsk CLI
- `agent-browser` (v0.25.3): Playwright 浏览器自动化 CLI

### 💻 代码开发类 (1 个)
- `code-review` (v1.0.0): 代码审查工具

### 📄 文档处理类 (4 个)
- `pdf` (v1.0.0): PDF 处理工具
- `docx` (v1.0.0): Word 文档处理工具
- `xlsx` (v1.0.0): Excel 表格处理工具
- `pptx` (v1.0.0): PowerPoint 演示文稿处理

### 🎬 视频生成类 (1 个)
- `agnes-video-generator` (v1.0.0): Agnes 视频生成工具

### 💰 金融投资类 (2 个)
- `wind-finance` (v1.0.0): Wind 金融数据服务
- `wb-finance-skill` (v0.1.0): 金融/投资/股票/基金场景总入口

### 🔧 通用工具类 (2 个)
- `find-skills` (v1.0.0): 搜索和发现 OpenClaw 技能
- `skill-creator` (v1.0.0): 创建有效技能的指南

---

## 使用说明

### Agent 执行流程
1. 判断任务类型（代码/文档/搜索/生成/金融...）
2. 查对应分支（如"代码类"→ `skill_tree.json.categories.code`）
3. 在分支内匹配 description
4. 命中 → 加载执行；未命中 → 全量扫描兜底

### 定期更新
```bash
python scripts/build_skill_tree.py
```

或等待 GitHub Actions 自动更新（每天凌晨 2 点）。

---

## 分类规则

| 分类 | 关键词 |
|------|--------|
| meta | constitution, rule, 规范, 元规则, 宪法 |
| memory | memory, memor, recall, remember, 记忆, 持久化 |
| browser | browser, bsk, 自动化, 网页, 爬虫, search, 搜索 |
| code | code, 编程, 开发, review, git, commit, 测试 |
| doc | docx, pdf, xlsx, pptx, 文档, wps, office |
| video | video, 视频, agnes |
| finance | finance, 金融, 股票, 投资 |
| general | 其他未匹配技能 |

---

*本索引由 `scripts/build_skill_tree.py` 自动生成，请勿手动编辑。*
