# Release v2.19.0 — 校验层防伪造升级 + 一键安装 + 对抗性测试

> 主题：**让"防糊弄"真的防得住**。外部测评实测发现旧校验器本身可被低成本伪造打穿
> （一个 `"encoded"` 子串打穿 Layer C、一段假链接套话五步全过），本版本把校验层
> 升级到词边界 + 证据白名单，并把全部糊弄向量固化为必须失败的自动化测试。

## ⚠️ 升级必读

- **重新运行 `bash install.sh` 或手工重跑技能树重建**（逻辑无变化，但校验更严格）
- 若你曾依赖"分类名出现即算命中"的旧行为：v2.19.0 起 **只有实际技能名才算证据**，
  汇报时请引用具体技能名（如 `git-workflow-and-versioning`），不要只写分类名

## 🔒 安全/正确性修复（P0）

### 校验层防伪造（核心）
- **词边界匹配全面替代裸子串**：Layer B/C 所有匹配改用 `lib.text.keyword_in`。
  `"encoded"` 不再误命中 `"code"`、`"hi"` 不再命中 `"this"`、`"rapid"` 不再误命中 `"api"`
- **废除 Layer C "分类名兜底"**：`code`/`doc` 等常见短词出现在任意技术文本里的概率极高，
  不再算证据；必需技能校验只认**实际技能名**
- **证据白名单**：技能树中名为 `github`/`code`/`data` 的单短词技能不再被误判为
  "调用过技能"（修复：推荐链接里出现 `github` 就被当成调用证据的漏洞）
- **记忆证据动态化**：Layer B 记忆标记改从你的 MEMORY.md 实际内容提取指纹，
  不再硬编码作者个人标记（旧实现对其他用户恒 FAIL）

### 分类器（零号条款）
- **专业词优先**："帮我解释这个报错然后修复代码并部署" 不再被"解释"整体豁免
- **简单词词边界**：`"hi"`⊂`"this"` 等碰撞不再造成误豁免；专业词保持宽松子串
  （误报只会多查一次，符合"宁可不放过"）
- **统一执法口径**：gate 与 `--classify` 走同一分类器，修复两套词表不同步

### 崩溃与死锁
- 修复 `check_injection` **UnboundLocalError**（skill_tree.json 缺失且传 `--task` 时崩溃）
- 修复**新装用户死锁**：MEMORY.md / skill_tree.json 缺失时降级放行（记 WARN），
  不再恒 FAIL 阻断所有写文件操作
- gate 新增 **Bash 写文件检测**（重定向/tee/heredoc/cp/mv/touch/mkdir），
  堵住 Write/Edit 之外最大的绕行通道；`>/dev/null` 不误报

### retry-wrapper
- 废除语义无效的"自我重试"（旧版把错误报告拼进输入再校验，等于把自己的提示词
  喂给自己的检查器）→ 改为单次真实校验 + 结构化错误报告，重试由宿主驱动
- 补传 `--task`：修复 retry 链路中 Layer C 永远被跳过的问题

## 🧪 测试与 CI

- **第 7 组对抗性防伪造用例（15 条）**：全部实测过的糊弄向量固化为"必须失败"
- **测试套件真正接入 CI**（此前从未在 CI 执行）；移除装了从未 import 的 pyyaml 死依赖
- 本地实测 **39/39 全绿**

## 🚀 易用性（P1）

- **`install.sh` 一键安装**：自动探测平台 → 复制 → **自动重建本机技能树**（最易漏的一步）
  → 自检 → 下一步指引
- **英文 README**（README_EN.md）：打开英语社区的入口
- 修复 build_skill_tree 只探测 Windows venv 路径的问题（Linux/macOS 现在也能扫到）

## 升级方式

```bash
# 已安装用户
bash install.sh            # 或手工覆盖后重跑技能树重建

# 新用户
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh
```

---

*完整改动逐条见 [CHANGELOG](../CHANGELOG.md)；本版本由外部深度测评驱动，
测评发现的 6 类可复现伪造向量已全部固化为回归测试。*
