# v2.33.0 零号条款自检：默认简单，仅动作型任务判 professional
import importlib.util, os

p = os.path.join(os.path.dirname(__file__), "..", "pre-hook.py")
spec = importlib.util.spec_from_file_location("pre_hook_v2330", p)
ph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ph)

CASES = [
    ("这几天千问出了最新模型版本,你还没列入模型选型吗", "simple"),
    ("上网搜索千问最新模型和 workbuddy 模型列表", "simple"),
    ("解释一下这个概念,顺便看看有没有更新", "simple"),
    ("现在两点项目分别多少星了", "simple"),
    ("我要把代码传上去", "professional"),
    ("安装最新版的 skills 宪法", "professional"),
    ("写一个脚本改配置文件", "professional"),
    ("帮我解释这个报错然后修复代码并部署", "professional"),
]
for text, want in CASES:
    got = ph.classify_task(text)
    assert got == want, "%s: got %s, want %s" % (text, got, want)
print("PASS v2.33.0 classify: %d/%d" % (len(CASES), len(CASES)))
