# Skills Constitution

> **A meta-rule above all skills/tools** — forces AI agents to *check first, use what matches, search before refusing*. Cross-platform (Claude Code / WorkBuddy / Cursor / ChatGPT / Gemini / ...).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.20.0-blue.svg)](SKILL.md)

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

## Quick start

### One-line install (recommended)

```bash
git clone https://github.com/jiabaobei/skills-constitution.git
bash skills-constitution/install.sh                 # auto-detects platform
```

`install.sh` routes by platform mechanism (v2.20.0):

| Platform kind | Command | What happens |
|---------------|---------|--------------|
| Skills-dir hosts (WorkBuddy / Claude Code) | `bash install.sh` | copy + **auto-rebuild your skill tree** + self-check |
| Same + enforcement | `bash install.sh --register-hooks` | plus auto-registers the 4 host hooks (backup/rollback/idempotent) |
| Rules-file hosts (Cursor / Windsurf / Cline) | `bash install.sh --platform cursor --target-dir <project>` | constitution written into the rules file (advisory level) |
| Prompt-only (ChatGPT / Gemini / Coze ...) | `bash install.sh --platform prompt` | extracts the injection template for pasting |
| Windows | `powershell -File install.ps1` | same skills-dir flow (first-run check on a real machine appreciated) |

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
registry.json               # curated open-source skill registry
scripts/
  constitution-check        # gate entry point (5 steps, soft/strict)
  constitution-gate.py      # host-level hook (pre-block + audit + warn-next)
  register_hooks.py         # auto-register/unregister host hooks (backup+rollback)
  pre-hook.py               # forced context injection + task classifier
  build_skill_tree.py       # rebuild YOUR skill tree index
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
