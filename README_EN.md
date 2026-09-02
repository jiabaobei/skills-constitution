# Skills Constitution

> **A meta-rule above all skills/tools** — forces AI agents to *check first, use what matches, search before refusing*. Cross-platform (Claude Code / WorkBuddy / Cursor / ChatGPT / Gemini / ...).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.25.1-blue.svg)](SKILL.md)

**中文文档**: [README.md](README.md)

---

## The problem

The biggest waste in the agent ecosystem: you install 100 skills and the agent uses 3.

- **Skipped skills** — the agent hand-rolls what an installed skill already does
- **Selection hallucination** — picks skills from memory instead of reading descriptions
- **False refusal** — says "I can't do that" without searching for a capability
- **No growth** — never recommends a better tool after finishing

Skills Constitution turns "check capabilities → match → mandatory use → search → recommend" into an **enforced pipeline**, and turns "honor system" into **verifiable, blockable gates**.

## How it works

```
task arrives
    │
    ├─ Article Zero: deterministic classifier (code, not the model's judgment)
    │    simple task (translate/polish) → skip the gates entirely
    │    professional / ambiguous      → enforced pipeline below
    │
    ├─ Pre-hook injection: MEMORY.md + skill tree forced into context
    ├─ Gate checks (5 steps, Layer A–E):
    │    A: report present        (soft)
    │    B: real content quoted   (hard — memory/tree fingerprints)
    │    C: task-relevant skill names quoted (anti "I checked, trust me")
    │    D: quoted skills semantically relevant to the task
    │    E: recommendations exclude already-installed skills
    ├─ Freshness: a PASS from the previous task doesn't unlock this one
    └─ Violation ledger: caught faking → warning injected into the next task
```

Design principles: **default soft checks** (`--strict` to block), **fail-open** (a gate bug never bricks the host), and the rule text never says "you must run the scripts" — so it stays satisfiable on prompt-only platforms.

**What's new in v2.25.1 — hook hang fix (no more 20s host timeouts freezing tasks):**

- **Root cause**: on Windows, `python`/`python3` can resolve to the Microsoft Store stub alias that hangs on launch. The old hooks only checked interpreter *existence*, so every python invocation inside a hook hung; a few stacked invocations blew past the host's 20000ms hook timeout, `UserPromptSubmit` was force-killed and the task froze.
- **Liveness probe**: `user-prompt-submit.sh` / `session-start.sh` now actually run `timeout 3 <py> -c pass` while detecting python3/python/py; a timing-out interpreter is treated as absent and the hook degrades (bash fallback / fail-open) instead of hanging.
- **Bounded blocking points**: stdin read capped with `read -t 2`; the self-heal re-run of SessionStart capped with `timeout 10`, so a nested hook hang can't drag the parent past the host budget. Fail-open discipline unchanged — worst case (all interpreters hanging) degrades in ~9s, healthy env 0.2s.

**What's new in v2.23.0 — the skill graph (deterministic relational intelligence, inspired by GitNexus):**

- A **skill graph** (`skill_graph.json`) now sits on top of the skill tree, rebuilt automatically whenever the tree is rebuilt. Three edge kinds, all extracted deterministically with zero dependencies: `chains_to` (one skill's output schema feeds another's input), `co_anchor` (shared entity anchors — with stopword + document-frequency filtering), and `alternative` (same-category substitutes).
- **Deterministic label-propagation clustering** groups skills into functional clusters (e.g. a "code publishing" cluster of git workflow + review + deploy skills). Discipline borrowed from GitNexus: only structural edges cluster or grant gate passage — similarity ("alternative") edges do neither.
- **Injection narrows to the task line (token diet)**: the injected block gains a graph section — the anchor skills' cluster-mates and one-hop neighbors, each annotated with *why* it is relevant (provenance), round-robin filled so one cluster can't eat the budget.
- **Gate Layer F (step3)**: when the task carries required keywords, quoted skills must be graph-connected to the task anchors (same cluster / structural one-hop); a quoted skill with zero graph connectivity fails with cluster-membership evidence. Missing graph → graceful pass (never bricks new installs).

**What's new in v2.22.0 — evidence-chain gating (anti-bypass + anti-interruption + token diet):**

- *Anti-bypass*: the gate's own state files (check records / exemption flag / violation ledger / injection context) can no longer be written by the agent — previously, creating one exemption-flag file exempted everything. Bash write detection now covers `sed -i`; a step-1 PASS is only accepted when it is a genuine `level=PASS` verdict.
- *Anti-interruption*: the gate accepts **"platform injected memory + skill tree AND a matched skill was actually invoked in this task"** as complete evidence of the three checks (Skill invocations are recorded automatically) — no need to manually run the check command mid-task. Follow-up messages within the same task no longer reset the gate, and the Stop hook no longer re-verifies (or mis-records violations for) tasks that already hold an evidence chain.
- *Self-healing injection*: if the injected context is missing/stale at prompt time, the SessionStart injector is re-run in place instead of blocking the task.
- *Token diet*: default injection block slimmed ~30% (SAD candidates 6→4, description truncation 60→40 chars, per-category listings 12→8, memory excerpt 1200→900 chars); the ~8KB keyword matcher in `hooks.json` reduced to `.*` (classification happens inside the hook).

## Quick start

### One-line install (recommended)

```bash
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh                 # auto-detects platform
```

`install.sh` routes by platform mechanism (v2.21.0):

| Platform kind | Command | What happens |
|---------------|---------|--------------|
| Skills-dir hosts (WorkBuddy / Claude Code / ZCode) | `bash install.sh` | copy + **auto-rebuild your skill tree (incl. plugin skills)** + self-check |
| Same + enforcement | `bash install.sh --register-hooks` | plus auto-registers the 4 host hooks (backup/rollback/idempotent) |
| Rules-file hosts (Cursor / Windsurf / Cline) | `bash install.sh --platform cursor --target-dir <project>` | constitution written into the rules file (advisory level) |
| Prompt-only (ChatGPT / Gemini / Coze ...) | `bash install.sh --platform prompt` | extracts the injection template for pasting |
| Windows | `powershell -File install.ps1` | same skills-dir flow (first-run check on a real machine appreciated) |

**Dual-mechanism coverage (v2.21.0)**: on hosts where capabilities come from two
parallel channels — standalone skills *and* plugin-bundled skills (ZCode, Claude
Code, DeepSeek Harness, ...) — the skill tree now indexes **both**. Known plugin
cache paths are discovered automatically (disabled plugins excluded); any other
host plugs in via the `PLUGIN_CACHE_DIRS` env var or a `plugin_roots.json` file.
Plugin skills are recorded with their fully qualified invocation name
(`plugin:skill`, e.g. `document-skills:docx`) and the constitution treats a
plugin-skill match as binding, same as a standalone skill.

Hook registration also runs standalone: `python skills-constitution/scripts/register_hooks.py`
(`--dry-run` to preview, `--uninstall` to remove).

### Manual install

```bash
# Claude Code
cp -r skills-constitution ~/.claude/skills/skills-constitution/
SKILLS_DIR="$HOME/.claude/skills" python skills-constitution/scripts/build_skill_tree.py

# Cursor / Windsurf / Cline (prompt-level only)
cp skills-constitution/SKILL.md .cursor/rules/skills-constitution.md

# ChatGPT / Gemini / others: paste the "quick injection template" from README.md
```

> ⚠️ **Always rebuild the skill tree after install.** The committed
> `skill_tree.json` is the author's snapshot — with it, lookups against *your*
> machine silently find nothing. See `reference/skill-tree-guide.md`.

### Enforcement (optional)

Without host hooks the constitution is advisory. On hosts with hook support
(WorkBuddy/CodeBuddy; Claude Code hooks compatible) run:

```bash
python skills-constitution/scripts/register_hooks.py   # or: bash install.sh --register-hooks
```

It registers `scripts/constitution-gate.py` for `UserPromptSubmit` /
`PreToolUse` / `Stop` (plus the bash `SessionStart` injector when bash is
present), backing up your settings file first and rolling back on any error.
See `reference/gate-details.md` for the event semantics.

## The articles

| # | Article | Rule |
|---|---------|------|
| 0 | Task classification | Simple tasks skip; professional/ambiguous must check |
| 1 | Pre-check | Query memory layer + skill index; list the matched skill names |
| 2 | Mandatory use | A match must be used — no bypassing with general ability |
| 3 | Search first | No match? Search for installable capabilities before improvising |
| 4 | Honest boundary | Never say "can't do" before confirming no capability exists |
| 5 | Auto-discovery | Recommend high-star GitHub skills when local ones fall short (excluding installed) |

## Project layout

```
SKILL.md                    # the constitution (main rule file)
install.sh                  # one-click installer, routes by platform mechanism
install.ps1                 # Windows PowerShell installer
skill_tree.json             # author's snapshot — rebuild for your machine
plugin_roots.json           # optional: extra plugin cache dirs for dual-mechanism hosts
registry.json               # curated open-source skill registry
scripts/
  constitution-check        # gate entry point (5 steps, soft/strict)
  constitution-gate.py      # host-level hook (pre-block + audit + warn-next)
  register_hooks.py         # auto-register/unregister host hooks (backup+rollback)
  pre-hook.py               # forced context injection + task classifier
  build_skill_tree.py       # rebuild YOUR skill tree (standalone + plugin skills)
  steps/                    # the 5 independent check scripts
  tests/run_tests.py        # regression + adversarial anti-forgery tests
reference/                  # platform mapping, install guide, gate details
```

## Testing

```bash
python scripts/tests/run_tests.py
```

Includes an **adversarial suite**: real forgery vectors that once bypassed the
gates (substring faking, fake recommendation links posing as skill usage,
mixed-task exemption escapes) are pinned as must-FAIL cases.

## Roadmap ideas

- Real network verification of recommended repos (optional flag)
- Behavior-level evidence from host tool-call logs (beyond text traces)
- More host hook adapters

## License

[MIT](LICENSE) — use, modify, redistribute freely.
