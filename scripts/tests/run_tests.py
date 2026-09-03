#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests — Skills Constitution 零依赖回归测试(v2.12.0 新增)

把 CHANGELOG 里各版本的"验证测试"表格固化为可重复执行的代码,
不再靠手工跑一遍 —— 用项目自己的理念 dogfooding:
"不靠自觉,靠确定性代码"。

覆盖:
  1. 同义词扩展(口语任务命中必需分类 / 任务分类器)
  2. 词边界匹配修复子串误杀(code≠encode, search≠research)
  3. SAD 宽松语义检索(top-K 候选非空且按相关度排序)
  4. Layer D 语义相关性校验(无关技能 FAIL / 相关技能 PASS)
  5. 多技能编排兼容性检查(不兼容链 FAIL / 兼容链 PASS)
  6. 可选语义索引缺依赖行为(exit 2 + 安装指引;已装依赖则跳过)
  7. 对抗性防伪造用例(v2.19.0):实测可打穿旧校验的糊弄向量,全部固化为"必须失败"
  8. 插件技能扫描(v2.21.0):双机制平台 技能+插件 全覆盖 —— 布局无关扫描 /
     版本去重 / .DISABLED 停用跳过 / 启用表过滤 / 入树集成 / 完整调用名渲染
  9. 门禁证据链(v2.22.0):防绕过(门禁文件保护/写检测) + 防干扰(追加式消息/
     证据链放行) + 注入瘦身断言
  10. 技能图谱(v2.23.0):锚点抽取/三种边/聚类纪律(替代边不并簇)/门禁图证据
      (LayerF 连通放行/零连通失败/缺图降级)/注入集成/确定性复现
  13. 钩子超时保护(v2.25.1):解释器存活探针/stdin 限时/自愈限时/fail-open 不卡任务

用法: python scripts/tests/run_tests.py
返回码: 0=全部通过, 1=有失败
"""
import importlib.util
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
TREE_PATH = os.path.join(ROOT_DIR, "skill_tree.json")
REGISTRY_PATH = os.path.join(ROOT_DIR, "registry.json")

sys.path.insert(0, SCRIPTS_DIR)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ph = load_module("pre_hook_under_test", os.path.join(SCRIPTS_DIR, "pre-hook.py"))
bst = load_module("build_skill_tree_under_test", os.path.join(SCRIPTS_DIR, "build_skill_tree.py"))
step1 = load_module("step1_under_test", os.path.join(SCRIPTS_DIR, "steps", "step1-check.py"))
step3 = load_module("step3_under_test", os.path.join(SCRIPTS_DIR, "steps", "step3-check.py"))
step4 = load_module("step4_under_test", os.path.join(SCRIPTS_DIR, "steps", "step4-check.py"))
gate = load_module("gate_under_test", os.path.join(SCRIPTS_DIR, "constitution-gate.py"))
rw = load_module("retry_wrapper_under_test", os.path.join(SCRIPTS_DIR, "retry-wrapper.py"))
from lib import text as T  # noqa: E402

RESULTS = []


def check(case, actual, expect=True):
    ok = (actual == expect) if isinstance(expect, bool) else bool(actual)
    RESULTS.append((case, ok, actual))
    print(f"[{'PASS' if ok else 'FAIL'}] {case}" + ("" if ok else f"  (actual={actual!r})"))
    return ok


def main():
    print("=" * 60)
    print("Skills Constitution 回归测试 (v2.25.1)")
    print("=" * 60)

    # ---- 1. 同义词扩展:口语任务命中必需分类 ----
    print("\n[1] 同义词扩展(TASK_SYNONYM_MAP)")
    check("口语'我要把代码传上去'命中 code 必需分类",
          "code" in ph.required_categories_for_task("我要把代码传上去"))
    check("口语'帮我抓一下网页数据'命中 browser+data",
          set(ph.required_categories_for_task("帮我抓一下网页数据")) >= {"browser", "data"})
    check("口语任务分类器判 professional",
          ph.classify_task("我要把代码传上去") == "professional")
    check("简单任务仍判 simple(不受扩展影响)",
          ph.classify_task("帮我翻译这段话") == "simple")

    # ---- 2. 词边界匹配修复子串误杀 ----
    print("\n[2] 词边界匹配(code≠encode, search≠research)")
    check("keyword_in: 'encode video' 不命中 'code'",
          T.keyword_in("encode video files", "code") is False)
    check("keyword_in: 'research tool' 不命中 'search'",
          T.keyword_in("deep research tool", "search") is False)
    check("keyword_in: 'code review' 命中 'code'",
          T.keyword_in("code review tool", "code") is True)
    check("keyword_in: 中文子串保持命中",
          T.keyword_in("抓取网页数据", "抓取") is True)
    check("classify_skill: encoder 技能不误入 code 分类",
          "code" not in bst.classify_skill("video-encoder", "encode video files tool"))
    check("classify_skill: 代码审查技能正入 code 分类",
          "code" in bst.classify_skill("code-reviewer", "代码审查工具 code review"))

    # ---- 3. SAD 宽松语义检索 ----
    print("\n[3] SAD 宽松语义检索(loose_retrieve_skills)")
    skills = ph.load_tree_full(TREE_PATH)
    check("load_tree_full 读到技能", len(skills) > 0)
    results = ph.loose_retrieve_skills(skills, "推送github代码")
    check("SAD 检索返回非空候选", len(results) > 0)
    check("SAD 候选按相关度降序",
          all(results[i][0] >= results[i + 1][0] for i in range(len(results) - 1)))
    if results:
        top_names = [s["name"] for _, s in results]
        print(f"       top 候选: {top_names}")
        # v2.21.0:技能树内容随机器/插件而异,"top-K 含 git 命名技能"的断言不再
        # 机器无关;改断言确定性信号 —— 分类加成保证任务必需分类的技能必进前排
        check("SAD top-K 含任务必需分类(code)技能",
              any("code" in s.get("categories", []) for _, s in results))
    check("SAD 空任务返回空", ph.loose_retrieve_skills(skills, "") == [])

    # ---- 4. Layer D 语义相关性校验 ----
    print("\n[4] Layer D 语义相关性校验(step3)")
    ok4a, msg4a, lv4a = step3.layer_d_relevance_check(
        "已调用 agnes-video-generator 完成任务", TREE_PATH, "推送github代码")
    check("引用与任务无关的真实技能 → FAIL", lv4a == "FAIL")
    if lv4a != "FAIL":
        print(f"       (got {lv4a}: {msg4a})")
    ok4b, msg4b, lv4b = step3.layer_d_relevance_check(
        "已调用 git-workflow-and-versioning 完成推送", TREE_PATH, "推送github代码")
    check("引用相关技能 → PASS", lv4b == "PASS")
    if lv4b != "PASS":
        print(f"       (got {lv4b}: {msg4b})")
    ok4c, _, lv4c = step3.layer_d_relevance_check(
        "随便一段输出", TREE_PATH, "")
    check("无任务描述 → 跳过(不误伤)", lv4c in ("PASS", "SKIP"))

    # ---- 5. 多技能编排兼容性检查 ----
    print("\n[5] 多技能编排兼容性(step4 + registry schema)")
    chain = step4.extract_skill_chain("先 `docx` → `git-workflow-and-versioning` 两步走")
    check("技能链提取", chain == ["docx", "git-workflow-and-versioning"])
    _, _, lv5a = step4.check_chain_compatibility(
        ["docx", "git-workflow-and-versioning"], REGISTRY_PATH)
    check("不兼容链(docx→git) → FAIL", lv5a == "FAIL")
    _, _, lv5b = step4.check_chain_compatibility(
        ["spec-driven-development", "test-driven-development"], REGISTRY_PATH)
    check("兼容链(spec→tdd) → PASS", lv5b == "PASS")
    _, _, lv5c = step4.check_chain_compatibility(
        ["docx", "不存在的技能xyz"], REGISTRY_PATH)
    check("无 schema 覆盖 → 跳过不误杀", lv5c in ("PASS", "SKIP"))

    # ---- 6. 可选语义索引缺依赖行为 ----
    print("\n[6] 可选语义索引(semantic_index.py)")
    try:
        import sentence_transformers  # noqa: F401
        has_st = True
    except ImportError:
        has_st = False
    if has_st:
        print("[SKIP] 本环境已装 sentence-transformers,缺依赖用例不适用")
    else:
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "semantic_index.py"), "query", "测试"],
            capture_output=True, text=True)
        check("缺依赖 exit 2", r.returncode == 2)
        check("缺依赖提示安装指引", "pip install" in (r.stderr or ""))

    # ---- 7. 对抗性防伪造用例（v2.19.0：实测打穿旧校验的糊弄向量，必须全被拦下） ----
    print("\n[7] 对抗性防伪造(伪造文本必须失败)")

    # 7.1 分类器逃逸：混合任务不再被简单词整体豁免
    check("混合任务'解释报错并修复部署'判 professional",
          ph.classify_task("帮我解释这个报错然后修复代码并部署") == "professional")
    check("混合任务(英文)判 professional",
          ph.classify_task("please explain how to fix this bug and commit the code")
          == "professional")
    check("'hi'⊂'this' 碰撞不再豁免",
          ph.classify_task("help with this deployment") == "professional")
    check("'介绍一下'+专业词 不再整体豁免",
          ph.classify_task("介绍一下这个仓库然后帮我部署") == "professional")
    check("纯简单任务仍豁免(不误伤)",
          ph.classify_task("帮我翻译这段话") == "simple")
    check("gate 与 classify 口径一致(介绍一下+爬虫)",
          gate.is_simple("介绍一下如何用 python 写爬虫抓取数据") is False)

    # 7.2 Layer C 打穿：'encoded' 含 'code' 子串不再蒙混
    _, _, lv = step1.layer_c_task_hard_check(
        "totally unrelated encoded output", TREE_PATH, "帮我写代码")
    check("LayerC: 'encoded' 不再误命中分类名 'code'", lv == "FAIL")
    _, _, lv = step1.layer_c_task_hard_check(
        "【宪法三查】命中技能 git-workflow-and-versioning", TREE_PATH, "帮我写代码")
    check("LayerC: 真实引用技能名仍通过", lv == "PASS")

    # 7.3 伪造全套文本：只写「铁律」+ 假链接，未查记忆/技能树 → step1 必须 FAIL
    forged = ("【宪法三查】\n铁律铭记于心。\n"
              "推荐仓库: https://github.com/fake/nonexistent-repo 12k★")
    passed, _, _ = step1.check(forged, "/nonexistent/MEMORY.md", TREE_PATH, "帮我写代码")
    check("伪造套话(无真实技能名) → step1 FAIL", passed is False)

    # 7.4 假链接冒充技能调用：推荐链接里的 'github' 不算"调用过技能"
    _, _, lv = step3.layer_b_hard_check(
        "推荐 https://github.com/fake/repo 12k★", TREE_PATH)
    check("假链接不再被误判为技能调用证据", lv == "FAIL")

    # 7.5 崩溃回归：skill_tree.json 缺失且传 --task 时不再 UnboundLocalError
    try:
        ok, msg = ph.check_injection(
            "【宪法三查】", tree_path="/nonexistent/tree.json", task="帮我写代码")
        check("check_injection 缺树不崩溃", True)
    except UnboundLocalError as e:
        check(f"check_injection 缺树不崩溃(实际:{e})", False)

    # 7.6 Bash 写文件绕行：重定向/tee/heredoc 必须进入门禁视野
    check("Bash 'cat > file.py' 被识别为写文件",
          gate.is_bash_file_write("Bash", {"command": "cat > x.py <<EOF\nprint(1)\nEOF"}) is True)
    check("Bash 'grep xxx' 不误报",
          gate.is_bash_file_write("Bash", {"command": "grep -r TODO src"}) is False)
    check("非 Bash 工具不受该检测影响",
          gate.is_bash_file_write("Read", {"command": "cat > x.py"}) is False)

    # 7.7 retry-wrapper：task 已透传(含必需关键词的任务,无技能名 → step1 失败)
    results, all_ok = rw.run_checks(
        "【宪法三查】已完成任务。", "/nonexistent/MEMORY.md", TREE_PATH, task="帮我写代码")
    s1_res = next(r for r in results if r["step"] == "step1")
    check("retry-wrapper 透传 task 后 LayerC 生效(step1 FAIL)",
          s1_res["passed"] is False)

    # ---- 8. 插件技能扫描（v2.21.0：双机制平台 技能+插件 全覆盖） ----
    print("\n[8] 插件技能扫描(build_skill_tree 双机制覆盖)")
    import tempfile
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as td:
        td = _P(td)
        cache = td / "cache" / "mktofficial" / "myplug" / "0.2.0" / "skills" / "doc-helper"
        cache.mkdir(parents=True)
        (cache / "SKILL.md").write_text(
            "---\nname: doc-helper\ndescription: 文档处理助手 docx 文档\nversion: 1.0\n---\nbody",
            encoding="utf-8")
        # 同插件旧版本共存 → 应去重取最高插件版本
        old = td / "cache" / "mktofficial" / "myplug" / "0.1.0" / "skills" / "doc-helper"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text(
            "---\nname: doc-helper\ndescription: 旧版文档助手 docx\nversion: 0.9\n---\nbody",
            encoding="utf-8")
        # 停用市场(.DISABLED) → 整棵子树跳过
        dis = td / "cache" / "dead-mkt.DISABLED" / "deadplug" / "1.0" / "skills" / "nope"
        dis.mkdir(parents=True)
        (dis / "SKILL.md").write_text("---\nname: nope\ndescription: 不应入树\n---\n", encoding="utf-8")

        entries = bst.scan_plugin_skills(td / "cache", agent="custom")
        e0 = next((e for e in entries if e["name"] == "doc-helper"), None)
        check("插件技能被扫描到", e0 is not None)
        if e0:
            check("qualified_name = 插件名:技能名", e0["qualified_name"] == "myplug:doc-helper")
            check("source 标记为 plugin", e0["source"] == "plugin")
            check("多版本去重取最高插件版本 0.2.0", e0["plugin_version"] == "0.2.0")
            check("插件技能正确分类(doc)", "doc" in e0["categories"])
        check(".DISABLED 停用市场整棵跳过", not any(e["plugin"] == "deadplug" for e in entries))

        # 启用表: 值为 False 的插件跳过(ZCode config.json enabledPlugins 形态)
        entries_off = bst.scan_plugin_skills(
            td / "cache", agent="custom", enabled_map={"myplug@mktofficial": False})
        check("启用表 false 的插件被跳过", not any(e["name"] == "doc-helper" for e in entries_off))

        # 集成: build_skill_tree 把插件技能与独立技能同权重编入分类
        skills_dir = td / "skills"
        skills_dir.mkdir()
        (skills_dir / "local-only").mkdir()
        (skills_dir / "local-only" / "SKILL.md").write_text(
            "---\nname: local-only\ndescription: 本地独立技能 excel 表格处理\nversion: 1.0\n---\n",
            encoding="utf-8")
        tree = bst.build_skill_tree(str(skills_dir), "", plugin_cache_dirs=[("custom", td / "cache")])
        doc_names = [e["name"] for e in tree["categories"].get("doc", [])]
        check("插件技能入树(doc 分类)", "doc-helper" in doc_names)
        check("独立技能与插件技能同树共存", "local-only" in doc_names)
        check("plugin_skills_count 统计正确", tree.get("plugin_skills_count") == 1)
        check("插件条目带 qualified_name 字段",
              any(e.get("qualified_name") == "myplug:doc-helper"
                  for e in tree["categories"].get("doc", [])))

        # pre-hook 侧: 完整调用名进注入块与 SAD 候选
        tmp_tree = td / "tree.json"
        tmp_tree.write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
        aliases = ph.load_skill_aliases(str(tmp_tree))
        check("load_skill_aliases 提取插件调用名", aliases.get("doc-helper") == "myplug:doc-helper")
        full = ph.load_tree_full(str(tmp_tree))
        check("load_tree_full 携带 qualified_name",
              any(s.get("qualified_name") == "myplug:doc-helper" for s in full))
        inj = ph.build_injection("铁律:测试", ph.load_tree(str(tmp_tree)), ["doc"],
                                 "处理文档", aliases=aliases)
        check("注入块渲染完整调用名", "myplug:doc-helper" in inj)
        check("注入块含双机制提示", "双机制平台" in inj)

        # 打包层布局(真实案例: mimosa/1.0.3/payload/skills/...):
        # 插件名应取市场段后的第一个非版本目录,停用检查覆盖全部路径段
        nested = td / "cache" / "mktofficial" / "sleepyplug" / "2.0.0" / "payload" / "skills" / "sec-scan"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(
            "---\nname: sec-scan\ndescription: 安全扫描 docx\nversion: 1.0\n---\n", encoding="utf-8")
        entries_n = bst.scan_plugin_skills(td / "cache", agent="custom",
                                           enabled_map={"sleepyplug@mktofficial": False})
        check("打包层不漏过停用过滤(全路径段检查)",
              not any(e["plugin"] == "sleepyplug" for e in entries_n))
        entries_p = bst.scan_plugin_skills(td / "cache", agent="custom")
        e_n = next((e for e in entries_p if e["name"] == "sec-scan"), None)
        check("打包层下插件名正确推导",
              e_n is not None and e_n["qualified_name"] == "sleepyplug:sec-scan")

    # resolve_plugin_cache_dirs: PLUGIN_CACHE_DIRS 环境变量接入任意新 agent 的缓存
    with tempfile.TemporaryDirectory() as td2:
        extra = _P(td2) / "some-new-agent" / "plugins"
        (extra / "xplug" / "1.0" / "skills" / "x-skill").mkdir(parents=True)
        (extra / "xplug" / "1.0" / "skills" / "x-skill" / "SKILL.md").write_text(
            "---\nname: x-skill\ndescription: 新平台插件技能 data 分析\n---\n", encoding="utf-8")
        old_env = os.environ.get("PLUGIN_CACHE_DIRS")
        try:
            os.environ["PLUGIN_CACHE_DIRS"] = str(extra)
            resolved = bst.resolve_plugin_cache_dirs()
            check("PLUGIN_CACHE_DIRS 环境变量被接入", any(str(extra) in str(p) for _, p in resolved))
            entries_x = []
            for agent, p in resolved:
                entries_x.extend(bst.scan_plugin_skills(p, agent=agent))
            check("新 agent 插件技能可扫描(布局无关)",
                  any(e["qualified_name"] == "xplug:x-skill" for e in entries_x))
        finally:
            if old_env is None:
                os.environ.pop("PLUGIN_CACHE_DIRS", None)
            else:
                os.environ["PLUGIN_CACHE_DIRS"] = old_env

    # ---- 9. 门禁证据链（v2.22.0：防绕过 + 防干扰 + 瘦身） ----
    print("\n[9] 门禁证据链(constitution-gate v2.22.0)")
    import inspect as _inspect

    # 9.1 防绕过:门禁自身文件保护(篡改判定依据 = 给自己发通行证,必须拦)
    check("Write 改状态文件被识别为篡改",
          gate.gate_file_targeted("Write", {"file_path": "/repo/.constitution-state.json"}) is True)
    check("Bash 写豁免旗标被识别为篡改",
          gate.gate_file_targeted("Bash", {"command": "echo simple > .constitution-simple"}) is True)
    check("Bash rm 违规记录文件被识别为篡改",
          gate.gate_file_targeted("Bash", {"command": "rm -f .constitution-violations.json"}) is True)
    check("只读门禁文件不拦(不误伤)",
          gate.gate_file_targeted("Bash", {"command": "cat .constitution-state.json"}) is False)
    check("普通文件写入不受保护规则影响",
          gate.gate_file_targeted("Write", {"file_path": "/repo/src/app.py"}) is False)

    # 9.2 防绕过:Bash 写文件检测补 sed -i
    check("Bash 'sed -i' 就地改写被识别为写文件",
          gate.is_bash_file_write("Bash", {"command": "sed -i 's/a/b/' config.txt"}) is True)
    check("Bash 'sed -n' 只读不误报",
          gate.is_bash_file_write("Bash", {"command": "sed -n '1,10p' config.txt"}) is False)

    # 9.3 防干扰:追加式消息不重置门禁状态
    check("追加消息'继续'判延续", gate.is_continuation("继续") is True)
    check("追加消息'好的，开始吧'判延续", gate.is_continuation("好的，开始吧") is True)
    check("追加标记英文'continue...'判延续",
          gate.is_continuation("continue with the next step") is True)
    check("新任务'帮我写爬虫并部署'不判延续",
          gate.is_continuation("帮我写一个爬虫脚本并部署到服务器上") is False)
    check("含追加子串的新任务不误判('可以'在句中)",
          gate.is_continuation("帮我写一个可以自动运行的数据抓取脚本") is False)

    # 9.4 证据链:手动路径(本任务内新鲜 step1 PASS)与注入路径(注入+技能调用)
    fresh = {"reset_ts": "2026-09-01 10:00:00",
             "steps": {"step1": {"passed": True, "level": "PASS",
                                  "ts": "2026-09-01 10:01:00"}}}
    check("本任务内新鲜 step1 PASS → 证据链完整", gate.task_evidence_ok(fresh) is True)
    stale = {"reset_ts": "2026-09-01 10:00:00",
             "steps": {"step1": {"passed": True, "level": "PASS",
                                  "ts": "2026-08-31 09:00:00"}}}
    check("旧任务的 step1 PASS 不赦免新任务", gate.task_evidence_ok(stale) is False)
    injected_ok = {"reset_ts": "2026-09-01 10:00:00", "injected": True,
                   "skill_invoked": {"ts": "2026-09-01 10:02:00", "skill": "git-workflow"}}
    check("注入+本任务内技能调用 → 证据链完整(无需手动跑校验)",
          gate.task_evidence_ok(injected_ok) is True)
    injected_only = {"reset_ts": "2026-09-01 10:00:00", "injected": True}
    check("只注入未调用技能 → 证据链不完整(仍需查技能)",
          gate.task_evidence_ok(injected_only) is False)

    # 9.5 注入块瘦身断言(默认参数收紧,防回归改回大注入)
    check("SAD 候选默认 4 条(原 6)",
          _inspect.signature(ph.loose_retrieve_skills).parameters["top_k"].default == 4)
    check("记忆片段上限默认 900 字(原 1200)",
          _inspect.signature(ph.extract_memory_relevant).parameters["max_total"].default == 900)

    # 9.6 hooks.json matcher 精简(分类在 hook 脚本内做,巨型列表纯属冗余)
    hooks_json_path = os.path.join(ROOT_DIR, "hooks", "hooks.json")
    with open(hooks_json_path, encoding="utf-8") as f:
        hooks_cfg = json.load(f)
    ups = hooks_cfg["hooks"]["UserPromptSubmit"][0]
    check("UserPromptSubmit matcher 精简为 '.*'", ups.get("matcher") == ".*")

    # ---- 10. 技能图谱（v2.23.0：GitNexus 启发的预计算关系智能） ----
    print("\n[10] 技能图谱(lib/graph + step3 LayerF + 注入集成)")
    graph = load_module("graph_under_test", os.path.join(SCRIPTS_DIR, "lib", "graph.py"))
    step3_f = step3  # step3 已加载,含 layer_f_graph_check
    GRAPH_PATH = os.path.join(ROOT_DIR, "skill_graph.json")

    # 10.1 锚点抽取:停用词过滤 + 复数归一
    anch = graph.extract_anchors("excel-formula-generator",
                                 "Creates formulas for excel sheets, supports word")
    check("锚点抽取保留领域词 excel", "excel" in anch)
    check("锚点抽取滤掉套话动词 creates/supports",
          "create" not in anch and "support" not in anch)
    anch2 = graph.extract_anchors("img-tool", "processes images and image files")
    check("复数归一:images 与 image 算同一锚点", "image" in anch2 and "images" not in anch2)

    # 10.2 三种边:chains_to / co_anchor / alternative(用 fixture 小图,不依赖本机树)
    fx_skills = [
        {"name": "spec-dev", "description": "spec driven development code", "categories": ["code"]},
        {"name": "code-review2", "description": "review code quality code", "categories": ["code"]},
        {"name": "doc-maker", "description": "docx word document creation", "categories": ["doc"]},
        {"name": "doc-writer", "description": "docx word document editing", "categories": ["doc"]},
    ]
    fx_registry = os.path.join(os.path.dirname(SCRIPTS_DIR), "tests_fx_registry.json")
    with open(fx_registry, "w", encoding="utf-8") as f:
        json.dump({"skills": [
            {"name": "spec-dev", "input_schema": ["text"], "output_schema": ["code"]},
            {"name": "code-review2", "input_schema": ["code"], "output_schema": ["review"]},
        ]}, f)
    try:
        g = graph.build_graph(fx_skills, fx_registry)
        kinds = {(e["source"], e["target"], e["kind"]) for e in g["edges"]}
        check("chains_to 边由 registry schema 交集产生",
              ("spec-dev", "code-review2", "chains_to") in kinds)
        check("co_anchor 边由共享锚点产生(docx+word)",
              ("doc-maker", "doc-writer", "co_anchor") in kinds)
        check("每条边都带证据(溯源)", all(e["evidence"] for e in g["edges"]))
        # 10.3 聚类纪律:doc 对经 co_anchor 同簇;跨域不误并
        cl_members = [set(c["members"]) for c in g["clusters"].values()]
        check("共享锚点技能同簇", any({"doc-maker", "doc-writer"} <= m for m in cl_members))
        # 10.4 确定性:重建两次结果完全一致
        g2 = graph.build_graph(fx_skills, fx_registry)
        check("建图完全确定性(两次一致)",
              json.dumps(g, sort_keys=True) == json.dumps(g2, sort_keys=True))
    finally:
        # v2.24.0:清理容错 —— Windows 沙箱回收站不可用时 os.remove 会被
        # safe-delete 拦截并抛错,临时文件残留不应让整个测试套件崩溃
        try:
            os.remove(fx_registry)
        except OSError:
            pass

    # 10.5 快照图谱质量:无巨簇(防套话词/跨域桥接把全图连成一片)
    snap = graph.load_graph(GRAPH_PATH)
    check("快照图谱存在(作者快照已提交)", bool(snap))
    if snap:
        max_cluster = max((c["size"] for c in snap["clusters"].values()), default=0)
        check(f"最大簇 {max_cluster} ≤ 80(无巨簇)", max_cluster <= 80)
        check("chains_to 边已固化进快照图",
              any(e["kind"] == "chains_to" for e in snap["edges"]))

    # 10.6 门禁图证据(密封 fixture:code 任务 + git 簇 vs doc 簇):
    #     相关放行 / 零连通 FAIL / 缺图降级
    import tempfile as _tf10
    with _tf10.TemporaryDirectory() as td10:
        fx_tree10 = os.path.join(td10, "tree.json")
        fx_graph10 = os.path.join(td10, "graph.json")
        with open(fx_tree10, "w", encoding="utf-8") as f:
            json.dump({"categories": {
                "code": [
                    {"name": "git-alpha", "description": "git push deploy 推送代码", "categories": ["code"]},
                    {"name": "git-beta", "description": "git commit version 代码版本", "categories": ["code"]},
                ],
                "doc": [
                    {"name": "doc-skill", "description": "docx word 文档处理", "categories": ["doc"]},
                    {"name": "doc-skill2", "description": "docx word 文档编辑", "categories": ["doc"]},
                ]}, "total": 4, "version": "test"}, f, ensure_ascii=False)
        with open(fx_graph10, "w", encoding="utf-8") as f:
            json.dump({"version": "test", "edges": [
                {"source": "git-alpha", "target": "git-beta", "kind": "co_anchor", "evidence": "共享锚点: git"},
                {"source": "doc-skill", "target": "doc-skill2", "kind": "co_anchor", "evidence": "共享锚点: docx, word"},
            ], "clusters": {
                "git": {"members": ["git-alpha", "git-beta"], "size": 2},
                "docx": {"members": ["doc-skill", "doc-skill2"], "size": 2},
            }}, f, ensure_ascii=False)
        ok, msg, lv = step3_f.layer_f_graph_check(
            "已调用 git-beta 完成推送", fx_tree10, "帮我写代码", graph_path=fx_graph10)
        check("LayerF: 与任务锚点同簇 → 放行", lv == "PASS")
        ok, msg, lv = step3_f.layer_f_graph_check(
            "已调用 doc-skill 完成", fx_tree10, "帮我写代码", graph_path=fx_graph10)
        check("LayerF: 与任务锚点图谱零连通 → FAIL", lv == "FAIL")
        check("LayerF FAIL 带簇归属证据(溯源)", "簇" in msg)
        ok, msg, lv = step3_f.layer_f_graph_check(
            "已调用 git-beta", fx_tree10, "帮我写代码", graph_path="/nonexistent/g.json")
        check("LayerF: 图缺失降级放行(不误杀新装用户)", lv == "PASS")

    # 10.7 相关性判断纪律:alternative 边不做门禁放行凭证(密封 fixture)
    fg = {"edges": [
        {"source": "skill-a", "target": "skill-b", "kind": "alternative", "evidence": "x"},
        {"source": "skill-a", "target": "skill-c", "kind": "co_anchor", "evidence": "y"},
    ], "clusters": {"y": {"members": ["skill-a", "skill-c"], "size": 2}}}
    rel = graph.graph_relevant_set(fg, ["skill-a"])
    check("结构边邻居在相关集合(放行凭证)", "skill-c" in rel)
    check("alternative 邻居不做放行凭证", "skill-b" not in rel)

    # 10.8 注入集成:图谱候选带边证据进注入块
    inj_tree = ph.load_tree(TREE_PATH)
    cands = ph.graph_candidates_for_task(inj_tree, "推送代码到github", GRAPH_PATH)
    check("图谱候选非空(任务有锚点时)", len(cands) > 0)
    check("图谱候选均带相关理由", all(c["evidence"] for c in cands))
    check("图谱候选受 token 预算约束(≤8)", len(cands) <= 8)
    inj = ph.build_injection("铁律:测试", inj_tree, ["code"], "推送代码到github",
                             graph_items=cands)
    check("注入块含技能图谱段落", "技能图谱" in inj)
    check("无图时注入行为不变(候选为空)",
          ph.graph_candidates_for_task(inj_tree, "推送代码到github",
                                       "/nonexistent/g.json") == [])

    # ---- 11. v2.24.0 回归:块标量解析 / 描述完整性 / 隐形技能诊断 ----
    # 背景:ponytail 全套"装了却隐形"—— ① parse_frontmatter 不支持 YAML
    # 块标量(description: >)导致 137 个技能描述失效;② 索引把描述截断到
    # 200 字符,触发词(第 400+ 字符)被丢掉,检索永远命中不到。全部固化为用例。
    print("\n[11] v2.24.0:块标量解析 + 描述完整性 + skill_doctor")
    spec24 = importlib.util.spec_from_file_location(
        "bst24", os.path.join(SCRIPTS_DIR, "build_skill_tree.py"))
    bst24 = importlib.util.module_from_spec(spec24)
    spec24.loader.exec_module(bst24)
    fm_block = bst24.parse_frontmatter(
        "---\nname: ponytail\ndescription: >\n  Forces the laziest solution.\n"
        "  Supports \"yagni\" triggers.\n  Use on ANY coding task.\n"
        "disable-model-invocation: true\n---\n# body")
    _bd = fm_block.get("description", "")
    check("块标量 > 折叠并保留全部行(laziest/yagni/ANY)",
          "laziest" in _bd and "yagni" in _bd and "ANY" in _bd)
    check("块标量之后的普通字段仍可解析",
          fm_block.get("disable-model-invocation") == "true")
    fm_lit = bst24.parse_frontmatter(
        "---\nname: x\ndescription: |\n  line one\n  line two\n---\n")
    check("块标量 | 保留换行", fm_lit.get("description") == "line one\nline two")
    check("索引描述上限放开(DESC_LIMIT>=2000,触发词不再被截断)",
          getattr(bst24, "DESC_LIMIT", 0) >= 2000)

    spec24b = importlib.util.spec_from_file_location(
        "sd24", os.path.join(SCRIPTS_DIR, "skill_doctor.py"))
    sd24 = importlib.util.module_from_spec(spec24b)
    spec24b.loader.exec_module(sd24)
    _kws = sd24.extract_tail_keywords(
        ' senior dev who has seen everything: question whether the task '
        'needs to exist at all (YAGNI), reach for the standard library. '
        'Also use whenever the user says "ponytail", "be lazy", "lazy mode", '
        '"do less", or "shortest path"')
    check("截断补偿提取触发词(yagni/be lazy/lazy mode/do less)",
          {"yagni", "be lazy", "lazy mode", "do less"} <= set(_kws))
    check("截断补偿丢弃被腰斩的首词残片",
          not any(k.startswith("senior dev who") for k in _kws))
    import tempfile as _tf24
    with _tf24.TemporaryDirectory() as td24:
        _mi = os.path.join(td24, "min.json")
        with open(_mi, "w", encoding="utf-8") as f24:
            json.dump({"skills": [
                {"n": "ponytail", "c": ["code"], "d": "Forces the laz",
                 "k": ["yagni", "lazy mode", "do less"]},
                {"n": "other", "c": ["x"], "d": "lazy and mode together",
                 "k": []}]}, f24)
        _r24 = sd24.query_min_index("lazy mode", min_path=_mi)
        check("短语整体命中优先(不按空格拆分误配)",
              bool(_r24) and _r24[0]["name"] == "ponytail")

    # ---- 12. v2.25.0 回归:排行榜快照推荐(第五条省 token 改造) ----
    # 背景:旧版推荐环节每次答复都"去 GitHub 全盘搜索", token 浪费严重。
    # v2.25.0 改为:读本地排行榜快照(data/skill_rankings.json) + 确定性规则,
    # 零网络、自动排除已装、过期只提示不拉取。全部固化为用例。
    print("\n[12] v2.25.0:排行榜快照推荐(省 token)")
    spec25u = importlib.util.spec_from_file_location(
        "ur25", os.path.join(SCRIPTS_DIR, "update_skill_rankings.py"))
    ur25 = importlib.util.module_from_spec(spec25u)
    spec25u.loader.exec_module(ur25)
    spec25r = importlib.util.spec_from_file_location(
        "rc25", os.path.join(SCRIPTS_DIR, "recommend_skills.py"))
    rc25 = importlib.util.module_from_spec(spec25r)
    spec25r.loader.exec_module(rc25)

    # 12.1 排行榜表格解析(样例 README 表格)
    _md = ("| # | Repo Name | Description | Stars | Subs | Plugins |\n"
           "|---|-----------|-------------|-------|------|---------|\n"
           "| 1 | [ppt-master](https://github.com/hugohe3/ppt-master) | "
           "AI presentation deck generator | 47146 | 96 | 1 |\n"
           "| 2 | [superpowers](https://github.com/obra/superpowers) | "
           "agentic skills framework | 279372 | 1026 | 1 |\n")
    _it25, _meta25 = ur25.parse_quemsah(_md)
    check("表格解析: 条目数正确", len(_it25) == 2)
    check("表格解析: repo/stars 字段完整",
          _it25[0]["repo"] == "ppt-master" and _it25[0]["stars"] == 47146)
    _kw25 = ur25.extract_keywords("ppt-master", "AI presentation deck generator")
    check("keywords 提取: 去停用词保留实义词",
          "presentation" in _kw25 and "generator" in _kw25 and "ai" not in _kw25)

    # 12.2-12.7 推荐器核心路径(临时快照 fixture)
    import tempfile as _tf25
    with _tf25.TemporaryDirectory() as td25:
        _snap25 = os.path.join(td25, "r.json")
        _sitems25 = [
            {"rank": 1, "name": "ppt-master", "owner": "hugohe3", "repo": "ppt-master",
             "stars": 47146, "subs": 0, "plugins": 1,
             "desc": "AI presentation deck generator", "keywords": ["presentation", "ppt"]},
            {"rank": 2, "name": "superpowers", "owner": "obra", "repo": "superpowers",
             "stars": 279372, "subs": 0, "plugins": 1,
             "desc": "agentic skills framework", "keywords": ["framework"]},
            {"rank": 3, "name": "agent-skills", "owner": "addyosmani", "repo": "agent-skills",
             "stars": 87506, "subs": 0, "plugins": 1,
             "desc": "production grade engineering skills", "keywords": ["engineering", "skills"]},
            {"rank": 4, "name": "graphify", "owner": "safishamsi", "repo": "graphify",
             "stars": 64351, "subs": 0, "plugins": 1,
             "desc": "knowledge graph for large codebases", "keywords": ["graph"]},
        ]
        with open(_snap25, "w", encoding="utf-8") as f25:
            json.dump({"format": 1, "source": "test", "source_url": "", "title": "",
                       "updated": "2026-09-01", "stale_days": 30, "count": 3,
                       "meta": {}, "items": _sitems25}, f25, ensure_ascii=False)
        # 12.3 E1 已装排除: 本地目录同名
        _sd1 = os.path.join(td25, "skills1")
        os.makedirs(os.path.join(_sd1, "ppt-master"), exist_ok=True)
        _ln1, _ = rc25.recommend("make a presentation deck", _snap25, _sd1, top=3)
        check("E1 已装排除: 同名 ppt-master 不推",
              not any("ppt-master" in l for l in _ln1))
        check("E1 排除后按星数补位: superpowers 在推荐中",
              any("superpowers" in l for l in _ln1))
        # 12.4 E2 references 标记排除(_agent-skills-references → agent-skills)
        _sd2 = os.path.join(td25, "skills2")
        os.makedirs(_sd2, exist_ok=True)
        with open(os.path.join(_sd2, "_agent-skills-references"), "w") as f25:
            f25.write("")
        _ln2, _ = rc25.recommend("engineering skills", _snap25, _sd2, top=3)
        check("E2 references 排除: agent-skills 不推",
              not any("agent-skills" in l for l in _ln2))
        # 12.5 中文零命中回退: 仍输出 3 条(星数排序)
        _ln3, _ = rc25.recommend("帮我写周报", _snap25, _sd2, top=3)
        check("零命中回退: 仍输出 3 条推荐",
              len([l for l in _ln3 if l.startswith("- ")]) == 3)
        check("零命中回退: 星数最高优先(superpowers 279K)",
              any("superpowers" in l for l in _ln3))
        # 12.6 快照过期: 只提示不自动拉取
        _snap_old25 = os.path.join(td25, "r_old.json")
        with open(_snap_old25, "w", encoding="utf-8") as f25:
            json.dump({"format": 1, "source": "test", "source_url": "", "title": "",
                       "updated": "2026-01-01", "stale_days": 30, "count": 1,
                       "meta": {}, "items": _sitems25[:1]}, f25, ensure_ascii=False)
        _ln4, _ = rc25.recommend("ppt", _snap_old25, None, top=3)
        check("快照过期: 顶部提示刷新(不自动拉取)",
              any("已过期" in l for l in _ln4))
        # 12.7 快照缺失: 提示先运行 update 脚本
        _ln5, _ = rc25.recommend("ppt", os.path.join(td25, "missing.json"), None, top=3)
        check("快照缺失: 提示运行 update_skill_rankings",
              any("update_skill_rankings" in l for l in _ln5))

    # 12.8 step5 推荐来源标注(软校验,不破坏旧行为)
    spec25s = importlib.util.spec_from_file_location(
        "s525", os.path.join(SCRIPTS_DIR, "steps", "step5-check.py"))
    s525 = importlib.util.module_from_spec(spec25s)
    spec25s.loader.exec_module(s525)
    _txt_snap25 = ("🔍 本次相关技能推荐(来源: 本地排行榜快照 data/skill_rankings.json):\n"
                   "- ppt-master — AI PPT 生成 (https://github.com/hugohe3/ppt-master, 50K★)\n"
                   "  安装: git clone https://github.com/hugohe3/ppt-master")
    _ok25, _msg25, _lv25 = s525.check(_txt_snap25, "/nonexistent_skills_dir_xyz")
    check("step5: 快照来源标注 PASS 且含最佳实践提示",
          _lv25 == "PASS" and "省 token 最佳实践" in _msg25)

    # ---- 13. 钩子超时保护（v2.25.1）----
    # 回归背景：Windows 上 python 可能是 Microsoft Store 占位别名（启动即挂起），
    # 旧钩子只查存在不真跑，每次调用挂起 → 超宿主 20s 强杀、任务卡死。
    import shutil
    import tempfile
    import time as _time
    HOOK_PATH = os.path.join(ROOT_DIR, "hooks", "user-prompt-submit.sh")
    # 13.0 静态断言：三道超时保护必须存在（防手滑删回归）
    with open(HOOK_PATH, encoding="utf-8") as fh:
        _hook_src = fh.read()
    check("13.0a 钩子: 解释器存活探针(timeout 3)在位", "timeout 3" in _hook_src)
    check("13.0b 钩子: stdin 读取限时(read -r -t 2)在位", "read -r -t 2" in _hook_src)
    # v2.27.2: 旧断言检查 "timeout 10"(bash 层嵌套自愈限时)——v2.27.0 钩子单进程化后
    # 自愈改为 pre-hook.py 进程内 refresh_injection()(1.5s 级,无需外层限时),
    # 嵌套自愈已删除。现断言:钩子委托单进程 hook-mode,且不再重跑 session-start.sh。
    check("13.0c 钩子: 单进程委托(--hook-mode)在位", "--hook-mode" in _hook_src)
    check("13.0d 钩子: 嵌套自愈已删除(不重跑 session-start.sh)", "session-start.sh" not in _hook_src)

    # 挂起解释器桩：三个名字都启动即睡 30s，模拟 Store 占位别名
    _stub_dir = tempfile.mkdtemp(prefix="stubpy_")
    try:
        for _c in ("python3", "python", "py"):
            _sp = os.path.join(_stub_dir, _c)
            with open(_sp, "w") as f:
                f.write("#!/bin/sh\nsleep 30\n")
            os.chmod(_sp, 0o755)
        _env_stub = dict(os.environ, PATH=_stub_dir + os.pathsep + os.environ.get("PATH", ""))

        # 13.1 最坏：三解释器全挂 → 探针 3s×3 降级 fail-open，低于宿主 20s 上限
        # v2.27.2: 超时不再让套件崩溃,记失败继续跑(套件健壮性)
        _t0 = _time.time()
        try:
            _r = subprocess.run(["bash", HOOK_PATH], input='{"prompt":"推送代码到github"}',
                                capture_output=True, text=True, env=_env_stub, timeout=25)
            _dt = _time.time() - _t0
            check("13.1 解释器全挂: 钩子 fail-open 放行(exit 0)", _r.returncode == 0)
            check("13.1 解释器全挂: %.1fs 内完成(<20s)" % _dt, _dt < 20)
        except subprocess.TimeoutExpired:
            check("13.1 解释器全挂: 25s 仍阻塞(挂起,须修复)", False)

        # 13.2 stdin 开着却无数据：read -t 2 不得无限阻塞
        _t0 = _time.time()
        _p = subprocess.Popen(["bash", HOOK_PATH], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env_stub)
        try:
            _rc = _p.wait(timeout=25)  # 不写不关 stdin
        except subprocess.TimeoutExpired:
            _p.kill()
            _rc = -1
        _dt = _time.time() - _t0
        check("13.2 stdin 开着无数据: 不无限阻塞(exit 0)", _rc == 0)
        check("13.2 stdin 开着无数据: %.1fs 内完成(<20s)" % _dt, _dt < 20)
    finally:
        shutil.rmtree(_stub_dir, ignore_errors=True)

    # 13.3 正常环境：钩子完成不挂起
    # v2.27.2: 阈值 10s→18s。慢机器(每进程 2-3s)+Defender 首扫/负载尖峰时
    # 实测 6~18s 波动(热路径均值 ~7s),原 10s 阈值误报;18s 仍低于宿主 20s 上限,
    # 且足以捕获真挂起(30s 级)。超时记失败,不让套件崩溃。
    _t0 = _time.time()
    try:
        subprocess.run(["bash", HOOK_PATH], input='{"prompt":"你好"}',
                       capture_output=True, text=True, timeout=25)
        _dt = _time.time() - _t0
        check("13.3 正常环境: 钩子 %.1fs 内完成(不挂起)" % _dt, _dt < 18)
    except subprocess.TimeoutExpired:
        check("13.3 正常环境: 25s 仍阻塞(挂起,须修复)", False)

    # ---- 汇总 ----
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"结果: {passed}/{total} 通过")
    print("=" * 60)
    failed = [c for c, ok, _ in RESULTS if not ok]
    if failed:
        print("失败用例:")
        for c in failed:
            print(f"  - {c}")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
