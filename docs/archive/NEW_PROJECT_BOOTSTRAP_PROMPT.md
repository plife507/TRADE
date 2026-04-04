# New Project Bootstrap Prompt

**Copy everything below the line into a fresh Claude Code session. Replace {{PLACEHOLDERS}} first.**

---

I want you to set up a professional AI-assisted development infrastructure for this project. This framework enforces quality through gated phases, tiered validation, automated hooks, and specialist agents. Adapt everything to fit THIS project's language, tools, and domain.

## Project Details (FILL THESE IN)

- **Project name**: {{PROJECT_NAME}}
- **Language**: {{LANGUAGE}} (e.g., Python 3.12, TypeScript, Rust, Go)
- **Type checker**: {{TYPE_CHECKER}} (e.g., pyright, mypy, tsc, clippy)
- **Type checker config**: {{CONFIG_FILE}} (e.g., pyrightconfig.json, tsconfig.json)
- **Package manager**: {{PKG_MGR}} (e.g., pip, npm, cargo)
- **CLI entry point**: {{CLI}} (e.g., `python main.py`, `npm run`, `cargo run`)
- **Source directory**: {{SRC_DIR}} (e.g., `src/`, `app/`, `lib/`)
- **Config format**: {{CONFIG_FMT}} (e.g., YAML, TOML, JSON)
- **Key modules**: {{LIST_YOUR_MODULES}} (e.g., `src/api/`, `src/data/`, `src/auth/`)

## What to Create

### 1. CLAUDE.md (project root)

Create `CLAUDE.md` with these sections. Make it specific to this project:

```
## Project Overview
One paragraph: language, purpose, key tools.

## Prime Directives
- **ALL FORWARD, NO LEGACY** — Delete old code, don't wrap it. No backward-compat shims, no deprecation wrappers. Old signatures fail loudly.
- **TODO-DRIVEN** — Every code change maps to `docs/TODO.md`. No code without a checkbox.
- **CLI VALIDATION** — Unified validation through CLI commands, not scattered test files.
- **PLAN → TODO.md** — Every plan MUST be written into `docs/TODO.md` with gated phases before implementation begins. Plans left only in conversation will be lost to context compaction.

## Project Structure
ASCII tree of the source directory with one-line descriptions per module.

## Key Patterns
Table of project-specific conventions (naming, imports, error handling, logging, etc.)

## Logging
- Use a centralized logger factory (e.g., `get_module_logger(__name__)`)
- Never use bare `logging.getLogger()` or `console.log()` without structure
- Gate verbose/debug output behind flags so it doesn't destroy performance

## Quick Commands
Validation tiers + debug commands with actual CLI syntax:
  {{cli}} validate quick      # Pre-commit
  {{cli}} validate standard   # Pre-merge
  {{cli}} validate full       # Pre-release
  {{cli}} validate module --module X --json   # Single module (preferred for agents)

## Plan Mode Rules (ENFORCED)
When exiting plan mode, the plan MUST be written into `docs/TODO.md` as a new section with:
1. Clear title and priority (P0 = critical, P1 = high, T1 = tactical)
2. Gated phases — checkboxes that must ALL pass before next phase starts
3. Validation gates between phases: `- [ ] **GATE**: {{validate_command}} passes`
4. Links to supporting analysis docs if applicable

## Where to Find Details
Table mapping topics to file paths.
```

### 2. docs/TODO.md

Create `docs/TODO.md` with this structure:

```markdown
# {{PROJECT_NAME}} TODO

Open work, bugs, and priorities.

---

## Active Work

### P0: {{First Priority}}

#### Phase 1: {{Logical Group}}
- [ ] Task with file references (`src/module/file.py`)
- [ ] Another task
- [ ] **GATE**: `{{cli}} validate quick` passes

#### Phase 2: {{Next Group}}
- [ ] Depends on Phase 1 being complete
- [ ] **GATE**: `{{cli}} validate standard` passes

#### Phase 3: {{Final Group}}
- [ ] Integration work
- [ ] **GATE**: `{{cli}} validate full` passes

---

## P1: {{Next Priority}}

### Phase 1: {{Group}}
- [ ] Task
- [ ] **GATE**: `{{cli}} validate quick` passes

---

## Tactical Items

### T1: {{Small Task}}
- [ ] Description
- [ ] **GATE**: `{{cli}} validate quick` passes

---

## Rules
- Mark items `[x]` as completed during implementation
- **GATE** checkboxes between phases must pass before advancing
- Convert relative dates to absolute (e.g., "Thursday" → "2026-03-20")
- Priority: P0 (critical) > P1 > P2 > T1-T9 (tactical)
- Link supporting analysis docs from `docs/`
```

### 3. Agent Definitions (`.claude/agents/`)

Create these 7 agent markdown files. Each has YAML frontmatter defining name, tools, model, and permissions. The key insight is **narrow scope** — each agent can only use the tools it needs:

**orchestrator.md** — Master coordinator.
- Reads TODO.md, identifies affected modules, creates execution plan
- Delegates to specialist agents (validator, debugger, refactorer, code-reviewer, security-auditor, docs-writer)
- Runs validation after changes, coordinates results
- Tools: Read, Write, Edit, Glob, Grep, Bash, Task, TodoWrite
- Model: opus

**validate.md** — Validation specialist (read-only, cannot edit code).
- Runs individual modules: `{{cli}} validate module --module X --json`
- **NEVER** runs `validate full` as a background agent (hangs). Always individual modules.
- Reports: what was validated, pass/fail counts, tier used
- Includes a table mapping "if you changed X → run module Y"
- Tools: Bash, Read, Grep, Glob
- Model: sonnet (fast, cheap — just runs commands and reports)

**code-reviewer.md** — Reviews code PROACTIVELY after changes (read-only, cannot edit).
- Checklist: no legacy shims, naming conventions, architecture boundaries, security basics
- Output format: Critical (must fix) / Warning (should fix) / Suggestion (consider)
- Ends with validation reminder
- Tools: Read, Grep, Glob, Bash
- Model: opus

**debugger.md** — 4-phase protocol (can edit code).
- Phase 1: Reproduce (run validation)
- Phase 2: Isolate (stack trace, TODO.md known issues, recent git diff)
- Phase 3: Fix (minimal change, no legacy fallbacks, update TODO.md)
- Phase 4: Verify (run validation again)
- Output: Symptom / Location / Root Cause / Fix / Validation status
- Tools: Read, Edit, Bash, Grep, Glob, Write
- Model: opus, permissionMode: acceptEdits

**security-auditor.md** — Security specialist (read-only).
- Checks: credentials from env vars only, input validation at boundaries, no PII in logs
- Output: Critical / High Risk / Medium Risk / Recommendations
- Tools: Read, Grep, Glob, Bash
- Model: opus

**refactorer.md** — Refactoring specialist (can edit code).
- Always baselines with `validate quick` BEFORE touching anything
- ALL FORWARD, NO LEGACY — remove old code, never add compat shims
- Verifies with `validate quick` AFTER changes
- Tools: Read, Write, Edit, Glob, Grep, Bash
- Model: opus, permissionMode: acceptEdits

**docs-writer.md** — Documentation specialist (can edit docs).
- Updates TODO.md after every code change with completion status
- Documents: what was done, validation results, next steps
- Rules: no speculation, document facts only, ALL FORWARD applies to docs too
- Tools: Read, Write, Edit, Glob, Grep, Bash
- Model: opus, permissionMode: acceptEdits

Each agent file uses this format:
```markdown
---
name: {{agent_name}}
description: {{one-line description}}
tools: {{comma-separated tool list}}
model: {{opus or sonnet}}
permissionMode: {{default or acceptEdits}}
---

# {{Agent Name}} Agent

## Context
Brief description of the project and this agent's role.

## Responsibilities
What this agent does. What it does NOT do (boundaries).

## Process
Step-by-step workflow with actual CLI commands.

## Output Format
How to structure the report.

## Rules
Project rules this agent enforces.
```

### 4. Hook Scripts (`.claude/hooks/scripts/`)

Create 4 Python scripts. These run automatically on every file edit — they are the guardrails that prevent quality from degrading:

**security_scan.py** (PreToolUse, triggers on: `Edit|Write`):
- Reads JSON from stdin — Claude provides `tool_input.content` or `tool_input.new_string`
- Regex-scans for hardcoded secrets (API keys, passwords, connection strings, tokens)
- Skips `.env` files (they're supposed to have secrets)
- **Exit 2 + stderr message = BLOCKS the tool call** (Claude cannot proceed)
- Exit 0 = allows the edit

```python
#!/usr/bin/env python3
import sys, json, re

SECRET_PATTERNS = [
    (r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded API key"),
    (r'secret\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded secret"),
    (r'password\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded password"),
    (r'DATABASE_URL\s*=\s*["\'][^"\']+["\']', "Hardcoded DB URL"),
    (r'OPENAI_API_KEY\s*=\s*["\'][^"\']+["\']', "Hardcoded OpenAI key"),
    (r'AWS_SECRET_ACCESS_KEY\s*=\s*["\'][^"\']+["\']', "Hardcoded AWS secret"),
]

def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    file_path = tool_input.get("file_path", "")
    if ".env" in file_path:
        sys.exit(0)
    for pattern, desc in SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            print(f"SECURITY BLOCK: {desc} in {file_path}. Use env vars.", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**todo_check.py** (PreToolUse, triggers on: `Edit|Write`):
- Non-blocking reminder (always exit 0)
- If editing a source file, prints: "Ensure TODO exists in docs/TODO.md before writing code"

```python
#!/usr/bin/env python3
import sys, json

def main():
    data = json.load(sys.stdin)
    fp = data.get("tool_input", {}).get("file_path", "")
    # Customize the extension and path for your project
    if fp.endswith((".py", ".ts", ".tsx", ".rs", ".go")) and "src/" in fp:
        print("Rule: Ensure TODO exists in docs/TODO.md before writing code.")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**typecheck_hook.py** (PostToolUse, triggers on: `Edit|Write`):
- Runs the type checker on the file that was just edited
- Walks up directories to find the config file, runs from project root
- **Exit 2 + stderr = blocks** if type errors found
- 25-second timeout per file

```python
#!/usr/bin/env python3
import sys, json, subprocess
from pathlib import Path

TYPE_CHECKER = "pyright"            # CUSTOMIZE: "mypy", "tsc", etc.
CONFIG_FILE = "pyrightconfig.json"  # CUSTOMIZE: "tsconfig.json", "mypy.ini"
FILE_EXT = ".py"                    # CUSTOMIZE: ".ts", ".rs", ".go"
ERROR_PATTERN = "- error:"          # CUSTOMIZE: pattern for real errors in output

def find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / CONFIG_FILE).exists():
            return p
    return start

def main():
    data = json.load(sys.stdin)
    fp = data.get("tool_input", {}).get("file_path", "")
    if not fp.endswith(FILE_EXT):
        sys.exit(0)
    root = find_root(Path(data.get("cwd", ".")).resolve())
    try:
        rel = str(Path(fp).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        rel = fp
    try:
        r = subprocess.run([TYPE_CHECKER, rel], capture_output=True, text=True, timeout=25, cwd=str(root))
    except Exception as e:
        print(f"{TYPE_CHECKER} hook error: {e}", file=sys.stderr)
        sys.exit(0)
    if r.returncode != 0:
        errs = [l.strip() for l in r.stdout.split("\n") if ERROR_PATTERN in l]
        if errs:
            print(f"{TYPE_CHECKER}: {len(errs)} error(s)\n" + "\n".join(errs), file=sys.stderr)
            sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**validation_reminder.py** (PostToolUse, triggers on: `Edit|Write`):
- Non-blocking reminder (always exit 0)
- If a core module was edited, prints reminder to run validation

```python
#!/usr/bin/env python3
import sys, json

def main():
    data = json.load(sys.stdin)
    fp = data.get("tool_input", {}).get("file_path", "")
    # CUSTOMIZE: which paths are "core" for your project
    WATCHED = ["src/core", "src/engine", "src/data", "src/api", "src/auth"]
    if any(p in fp for p in WATCHED):
        print("Core code modified. Run: {{cli}} validate quick")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 5. Settings

**`.claude/settings.json`** (committed to repo — enables agent teams):
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

**`.claude/settings.local.json`** (per-user — hooks + permissions):
```json
{
  "permissions": {
    "allow": [
      "Bash(python:*)",
      "Bash(python3:*)",
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(ls:*)",
      "Bash(mkdir:*)",
      "WebSearch",
      "Skill(validate)",
      "Skill(commit)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {"type": "command", "command": "python3 \".claude/hooks/scripts/security_scan.py\"", "timeout": 10},
          {"type": "command", "command": "python3 \".claude/hooks/scripts/todo_check.py\"", "timeout": 10}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {"type": "command", "command": "python3 \".claude/hooks/scripts/typecheck_hook.py\"", "timeout": 30},
          {"type": "command", "command": "python3 \".claude/hooks/scripts/validation_reminder.py\"", "timeout": 10}
        ]
      }
    ]
  }
}
```

### 6. Validation System

Build a validation CLI command (`{{cli}} validate`) with this architecture:

**Core concept: GateResult** — Every validation check returns the same structure:
```
gate_id: str       # "G1", "G2", etc.
name: str          # Human-readable name
passed: bool       # Did it pass?
checked: int       # How many items were checked
duration_sec: float
detail: str        # Summary string
failures: list[str] # Specific failure messages
```

**Tiered stages** — Each stage is a barrier. If any gate in a stage fails, later stages are skipped. Gates WITHIN a stage run in parallel (ThreadPoolExecutor):

- **Quick** (pre-commit, ~1-2 min):
  - Stage 0: Config parsing, linting, type checking (fast, parallel)
  - Stage 1: Contract/registry audits (parallel)
  - Stage 2: Core tests (parallel)

- **Standard** (pre-merge, ~3-5 min):
  - Quick stages +
  - Stage 3: Integration tests (parallel)
  - Stage 4: Feature test suites (parallel)
  - Stage 5: Metrics/output validation

- **Full** (pre-release, ~5-10 min):
  - Standard stages +
  - Stage 6: Exhaustive test suites (parallel)
  - Stage 7: Full regression

**Module system** — Any gate or group of gates can run independently:
```
{{cli}} validate module --module core --json
{{cli}} validate module --module api --json
{{cli}} validate module --module lint --json
```

**Timeout protection** — Per-item timeout (120s default) and per-gate timeout (600s default). Nothing blocks forever. Timeouts report as FAIL.

**Incremental reporting** — Each gate prints its result immediately. After each gate, checkpoint to `.validate_report.json` on disk. If a run hangs or is killed, partial results survive.

**JSON output** — `--json` flag for agent consumption. Standard envelope: `{"status": "passed"|"failed", "gates": [...], "summary": "..."}`.

### 7. Memory System

The memory system persists knowledge across conversations. Set up in the Claude Code memory directory:

**`MEMORY.md`** (index file, auto-loaded every conversation, keep under 200 lines):
```markdown
# {{PROJECT_NAME}} Memory

## User
- [user_role.md](user_role.md) — Role, expertise, preferences

## Feedback
- [feedback_style.md](feedback_style.md) — Corrections to approach

## Project
- [project_status.md](project_status.md) — Current priorities

## References
- [external_systems.md](external_systems.md) — External docs/tools
```

**Memory types**:
- `user` — Role, expertise, preferences ("senior backend eng, new to React")
- `feedback` — Corrections ("don't mock the DB, use real integration tests")
- `project` — Active context ("merge freeze starts 2026-03-20")
- `reference` — External pointers ("bugs tracked in Linear project X")

**What NOT to save**: Code patterns (read the code), git history (use git log), anything already in CLAUDE.md.

## Key Principles

1. **Plans persist in TODO.md** — Context compaction WILL delete plans left in conversation. Always write to disk.
2. **Gated phases** — Every phase must pass its validation gate before the next phase starts. No skipping.
3. **ALL FORWARD** — Delete old code. No deprecation warnings, no backward compat, no legacy wrappers.
4. **Hooks enforce quality** — Security scan blocks secrets. Type checker blocks type errors. TODO reminder keeps you honest. These run on EVERY edit automatically.
5. **Agents have narrow scope** — Validator can't edit code. Code reviewer can't write files. Debugger gets acceptEdits. This prevents agents from overstepping.
6. **Match validation to scope** — Single module = `validate module --module X`. Multi-module = `validate standard`. Release = `validate full`.
7. **No scattered tests** — One CLI entry point for all validation. Tests organized by gates, not sprinkled across the tree.
8. **Background agents run modules, not tiers** — `validate full` as a background task will hang. Always run individual modules.
9. **Incremental reporting** — Checkpoint results to `.validate_report.json`. If a run dies, partial results survive.

## The Development Loop

```
1. CHECK TODO.md           → What needs doing?
2. PLAN (if non-trivial)   → Write gated phases
3. WRITE TODO.md           → Persist the plan to disk
4. CODE                    → Hooks auto-enforce quality:
   ├─ PreToolUse:  security scan, TODO reminder
   └─ PostToolUse: type check, validation reminder
5. VALIDATE                → Match tier to change scope
6. REVIEW (code-reviewer)  → Proactive quality check
7. UPDATE TODO.md          → Mark [x], advance phase
8. COMMIT                  → Only when gates pass

On errors        → debugger agent
On security      → security-auditor agent
On complexity    → orchestrator delegates to specialists
On refactoring   → refactorer agent (baseline first)
On docs needed   → docs-writer agent
```

## Anti-Patterns to Avoid

| Don't Do This | Why It Fails | Do This Instead |
|--------------|-------------|----------------|
| Plans in conversation only | Context compaction deletes them | Write to docs/TODO.md |
| `validate full` as background agent | Hangs, times out | Run individual modules |
| Legacy fallbacks / compat shims | Hidden bugs, two code paths | Delete old code, fail loudly |
| No validation gates between phases | Changes break previous work | Gate between every phase |
| Agents with broad tool access | Agents modify code they shouldn't | Narrow tools per agent role |
| No type checking hook | Type errors accumulate silently | PostToolUse type checker |
| No security hook | Secrets get committed | PreToolUse credential scan |
| Amending commits after hook failure | Destroys the previous commit | Always NEW commit after fix |
| Tests scattered across files | Hard to find, maintain, run | Unified CLI validation |

## After Setup

1. Verify the hook scripts work: edit a source file, confirm you see the TODO reminder and type check
2. Run `{{cli}} validate quick` to verify the validation pipeline
3. Create your first gated phase in TODO.md for the actual work
4. Start coding — the infrastructure enforces quality automatically

Now please set up this entire infrastructure for my project. Start by examining the existing codebase structure, then create all the files listed above, adapted to fit what's actually here.
