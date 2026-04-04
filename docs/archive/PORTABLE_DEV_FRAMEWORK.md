# Portable AI-Assisted Development Framework

**Extracted from the TRADE project. Copy this into any new project's CLAUDE.md and adapt the domain-specific sections.**

---

## How to Use This Document

1. Copy the **CLAUDE.md Template** (Section 1) into your project root as `CLAUDE.md`
2. Copy the **TODO.md Template** (Section 2) into `docs/TODO.md`
3. Copy the **Agent Definitions** (Section 3) into `.claude/agents/`
4. Copy the **Hook Scripts** (Section 4) into `.claude/hooks/scripts/`
5. Copy the **Settings** (Section 5) into `.claude/settings.local.json`
6. Replace all `{{PLACEHOLDER}}` values with your project specifics

---

## Section 1: CLAUDE.md Template

```markdown
# CLAUDE.md

## Project Overview

This is a {{LANGUAGE}} project. Primary language is {{LANGUAGE}} with {{CONFIG_FORMAT}} for configuration and Markdown for documentation. Use {{TYPE_CHECKER}} for type checking. Always validate changes with existing test suites before committing.

## Prime Directives

- **ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it. No backward-compat shims.
- **TODO-DRIVEN** - Every change maps to `docs/TODO.md`. No code without a checkbox.
- **CLI VALIDATION** - Use CLI commands for validation, not scattered test files.
- **PLAN → TODO.md** - Every plan mode output MUST be written into `docs/TODO.md`.

## Project Structure

```text
src/{{module_1}}/     # Description
src/{{module_2}}/     # Description
src/{{module_3}}/     # Description
config/               # Configuration files
docs/                 # Documentation and TODO tracking
```

## Key Patterns

| Pattern | Rule |
|---------|------|
| Validation | Always run `{{validate_command}}` after changes |
| Configuration | Single source of truth in `config/defaults.{{ext}}` |
| Type checking | `{{type_checker_config}}` is the single source of truth |
| Logging | Use `get_module_logger(__name__)` — never bare `logging.getLogger()` |

## Quick Commands

```bash
# Validation tiers (staged parallel execution)
{{cli}} validate quick                    # Pre-commit (~2min)
{{cli}} validate standard                 # Pre-merge (~5min)
{{cli}} validate full                     # Pre-release (~10min)
{{cli}} validate module --module X --json # Single module (preferred for agents)

# Debug
{{cli}} debug {{subcommand}}             # Diagnostic tools
```

## Validation Coverage

The `coverage` module automatically detects which components lack validation. Run:

```bash
{{cli}} validate module --module coverage --json
```

## Plan Mode Rules (ENFORCED)

When exiting plan mode, the plan MUST be written into `docs/TODO.md` as a new gated section.

**Format requirements:**
1. **New section** with clear title and priority (e.g., `## P0: Critical Fix`)
2. **Gated phases** — checkboxes that must ALL pass before next phase starts
3. **Validation gate** between phases — `- [ ] **GATE**: {{validate_command}} passes`
4. **Reference doc** — link supporting analysis if applicable

## Where to Find Details

| Topic | Location |
|-------|----------|
| Architecture | `docs/architecture/ARCHITECTURE.md` |
| Project status & active work | `docs/TODO.md` |
| System defaults | `config/defaults.{{ext}}` |
```

---

## Section 2: TODO.md Template (Gated Phase System)

```markdown
# {{PROJECT}} TODO

Open work, bugs, and priorities. Completed work is archived in `docs/COMPLETED.md`.

---

## Active Work

### P0: {{Critical Priority Item}}

See `docs/{{ANALYSIS_DOC}}.md` for full analysis.

#### Phase 1: {{First Logical Group}}
- [ ] Task description with file references
- [ ] Another task
- [ ] **GATE**: `{{cli}} validate quick` passes

#### Phase 2: {{Second Logical Group}}
- [ ] Task that depends on Phase 1 being done
- [ ] Another task
- [ ] **GATE**: `{{cli}} validate standard` passes
- [ ] **GATE**: All existing tests still pass

#### Phase 3: {{Final Group}}
- [ ] Integration task
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

- Mark items `[x]` as completed
- Add `**GATE**` checkboxes between phases
- Gates must pass before moving to next phase
- Link supporting analysis docs from `docs/`
- Convert relative dates to absolute (e.g., "Thursday" → "2026-03-05")
- Priority order: P0 (critical) > P1 > P2 > T1-T9 (tactical)
```

---

## Section 3: Agent Definitions

### 3a. Orchestrator (`.claude/agents/orchestrator.md`)

```markdown
---
name: orchestrator
description: Master coordinator for complex tasks. Delegates to specialist agents.
tools: Read, Write, Edit, Glob, Grep, Bash, Task, TodoWrite
model: opus
permissionMode: default
---

# Orchestrator Agent

You are a senior architect coordinating work on {{PROJECT}}.

## Core Responsibilities

1. **Analyze the Task** — Check `docs/TODO.md` for current priorities
2. **Create Execution Plan** — Use TodoWrite for detailed task list
3. **Delegate to Specialists**:
   - `validator` for running validation
   - `debugger` for bug investigation
   - `refactorer` for code improvements
   - `code-reviewer` for quality checks
   - `security-auditor` for security review
   - `docs-writer` for documentation updates
4. **Coordinate Results** — Ensure changes follow CLAUDE.md rules

## Workflow Pattern

1. UNDERSTAND -> Read TODO.md, CLAUDE.md
2. PLAN -> Create todo list aligned with project phases
3. DELEGATE -> Assign to specialist agents
4. VALIDATE -> {{cli}} validate quick (or higher tier)
5. INTEGRATE -> Combine results, update docs
6. VERIFY -> Confirm all gates pass

## Match Validation to Changes

| Changed Code | Required Validation |
|--------------|---------------------|
| Core modules | `validate quick` |
| Infrastructure | `validate standard` |
| Multiple modules | `validate full` |
| Config/YAML files | `validate quick` |
```

### 3b. Validator (`.claude/agents/validate.md`)

```markdown
---
name: validate
description: Validation specialist. Runs tests, audits, and parity checks.
tools: Bash, Read, Grep, Glob
model: sonnet
---

# Validator Agent

## CRITICAL: Break Work into Small Modules

**NEVER run `validate full` as a background agent.** Run individual modules:

```bash
{{cli}} validate module --module core --json
{{cli}} validate module --module {{module_name}} --json
```

## Validation Tiers

| Tier | When | Time |
|------|------|------|
| quick | Pre-commit | ~2min |
| standard | Pre-merge | ~5min |
| full | Pre-release | ~10min |

## Match Validation to What Changed

| If You Changed... | Minimum Validation |
|-------------------|--------------------|
| Core logic | `validate module --module core` |
| Data layer | `validate module --module data` |
| Config files | `validate quick` |
| Multiple modules | `validate standard` or `full` |

## Reporting

Always report:
1. What you validated and why
2. Pass/fail with specific counts
3. Tier or module used
```

### 3c. Code Reviewer (`.claude/agents/code-reviewer.md`)

```markdown
---
name: code-reviewer
description: Expert code review. Use PROACTIVELY after writing or modifying code.
tools: Read, Grep, Glob, Bash
model: opus
permissionMode: default
---

# Code Reviewer Agent

## Review Checklist

### Project Rules Compliance
- [ ] No backward compatibility shims (ALL FORWARD, NO LEGACY)
- [ ] No legacy code preserved (delete unused paths)
- [ ] Naming conventions followed
- [ ] No test files outside CLI validation system

### Architecture Boundaries
- [ ] Code in correct module
- [ ] No cross-boundary leaks
- [ ] Proper abstractions used

### Security
- [ ] No hardcoded secrets
- [ ] Input validation at system boundaries
- [ ] Proper error handling for external calls

## Output Format

### Critical (Must Fix)
Issues that violate project rules or will cause bugs.

### Warning (Should Fix)
Issues that may cause problems.

### Suggestion (Consider)
Improvements for readability or maintainability.

### Validation Reminder
After review: `{{cli}} validate quick`
```

### 3d. Debugger (`.claude/agents/debugger.md`)

```markdown
---
name: debugger
description: Expert debugging specialist. Use PROACTIVELY when encountering errors.
tools: Read, Edit, Bash, Grep, Glob, Write
model: opus
permissionMode: acceptEdits
---

# Debugger Agent

## Debugging Protocol

### Phase 1: Reproduce and Capture
```bash
{{cli}} validate quick    # Run validation first
```

### Phase 2: Isolate
1. Read the full stack trace
2. Check `docs/TODO.md` for known issues
3. Trace data flow
4. Check recent changes: `git diff HEAD~5`

### Phase 3: Fix
1. **Minimal fix** - Change only what's necessary
2. **No legacy fallbacks** - Fix forward
3. **Update TODO.md** - Document the fix

### Phase 4: Verify
```bash
{{cli}} validate quick    # Always verify after fixing
```

## Output Format

**Symptom**: [What was observed]
**Location**: [file:line]
**Root Cause**: [Why it happened]
**Fix**: [What was changed]
**Validation**: {{cli}} validate quick - PASS
```

### 3e. Security Auditor (`.claude/agents/security-auditor.md`)

```markdown
---
name: security-auditor
description: Security specialist. Use PROACTIVELY when handling credentials, APIs, or sensitive operations.
tools: Read, Grep, Glob, Bash
model: opus
permissionMode: default
---

# Security Auditor Agent

## Security Checklist

### Credential Security
- [ ] Secrets from environment variables only
- [ ] No hardcoded credentials in source
- [ ] Separate dev/staging/prod credentials
- [ ] Credential source logged (not the credential itself)

### Input Validation
- [ ] User input sanitized at boundaries
- [ ] No command injection in shell calls
- [ ] No SQL injection in database queries
- [ ] No XSS in web output

### Data Protection
- [ ] Sensitive data not logged
- [ ] No PII in artifacts or debug output
- [ ] Audit trail maintained

## Output Format

### Critical Security — Issues that could cause data loss or breaches
### High Risk — Credential exposure or validation bypass
### Medium Risk — Logging sensitive data or missing validation
### Recommendations — Hardening suggestions
```

### 3f. Refactorer (`.claude/agents/refactorer.md`)

```markdown
---
name: refactorer
description: Code refactoring specialist. Use for improving code quality and reducing tech debt.
tools: Read, Write, Edit, Glob, Grep, Bash
model: opus
permissionMode: acceptEdits
---

# Refactorer Agent

## Process

### Phase 1: Assessment
```bash
{{cli}} validate quick    # Baseline BEFORE refactoring
```

### Phase 2: Identify Opportunities
- Duplicate computation paths
- Multiple patterns that should merge
- Legacy compatibility shims (remove them!)
- Dead code paths

### Phase 3: Apply
**ALL FORWARD, NO LEGACY**: Never add backward compatibility.

### Phase 4: Verify
```bash
{{cli}} validate quick    # Verify after refactoring
```

## Output Format

### Changes Made
1. **[Refactoring]** in `file.py` — Before/After/Lines removed

### Validation
{{cli}} validate quick - PASS
```

### 3g. Docs Writer (`.claude/agents/docs-writer.md`)

```markdown
---
name: docs-writer
description: Documentation specialist. Updates TODO.md, project docs, and session handoffs.
tools: Read, Write, Edit, Glob, Grep, Bash
model: opus
permissionMode: acceptEdits
---

# Docs Writer Agent

## Key Files
- `docs/TODO.md` — Active work tracking (ALWAYS UPDATE)
- `CLAUDE.md` — Root project rules

## After Bug Fixes
```markdown
- [x] Fix description
- **Validation**: validate quick PASS
```

## After Feature Work
```markdown
- [x] Feature task
- [x] Validation: validate quick PASS
```

## Rules
- ALWAYS update docs/TODO.md after code changes
- No speculation — document what was done
- ALL FORWARD applies to docs too
```

---

## Section 4: Hook Scripts

### 4a. Security Scan — PreToolUse (`.claude/hooks/scripts/security_scan.py`)

Blocks tool execution when hardcoded secrets are detected.

```python
#!/usr/bin/env python3
"""
PreToolUse hook: Block potential secrets in code.
Exit code 2 + stderr = blocking feedback shown to Claude.
"""

import sys
import json
import re

# Customize these patterns for your project
SECRET_PATTERNS = [
    (r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded API key"),
    (r'secret\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded secret"),
    (r'password\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded password"),
    (r'AWS_SECRET_ACCESS_KEY\s*=\s*["\'][^"\']+["\']', "Hardcoded AWS secret"),
    (r'OPENAI_API_KEY\s*=\s*["\'][^"\']+["\']', "Hardcoded OpenAI key"),
    (r'DATABASE_URL\s*=\s*["\']postgres://[^"\']+["\']', "Hardcoded DB URL"),
    # Add project-specific patterns here
]


def main():
    input_data = json.load(sys.stdin)
    tool_input = input_data.get("tool_input", {})
    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    file_path = tool_input.get("file_path", "")

    # Skip env files (they're supposed to have secrets)
    if ".env" in file_path:
        sys.exit(0)

    for pattern, description in SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            print(
                f"SECURITY BLOCK: {description} detected in {file_path}. "
                "Use environment variables instead.",
                file=sys.stderr,
            )
            sys.exit(2)  # Exit 2 = blocking

    sys.exit(0)


if __name__ == "__main__":
    main()
```

### 4b. TODO Reminder — PreToolUse (`.claude/hooks/scripts/todo_check.py`)

Non-blocking reminder that code changes need a TODO entry.

```python
#!/usr/bin/env python3
"""
PreToolUse hook: Remind about TODO-driven development.
Non-blocking (exit 0 with stdout message).
"""

import sys
import json


def main():
    input_data = json.load(sys.stdin)
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Customize: which files trigger the reminder
    if file_path.endswith(".py") and "src/" in file_path:
        print(
            "Rule: Ensure TODO exists in docs/TODO.md "
            "before writing code. Every code change maps to a TODO checkbox."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
```

### 4c. Type Checker — PostToolUse (`.claude/hooks/scripts/typecheck_hook.py`)

Runs your type checker on edited files after every edit.

```python
#!/usr/bin/env python3
"""
PostToolUse hook: Run type checker on edited files.
Exit 2 + stderr = blocking feedback shown to Claude.
Runs from project root so config file is found.
"""

import sys
import json
import subprocess
from pathlib import Path

# Customize: your type checker command and config file
TYPE_CHECKER = "pyright"          # or "mypy", "tsc", etc.
CONFIG_FILE = "pyrightconfig.json"  # or "mypy.ini", "tsconfig.json"
FILE_EXTENSION = ".py"            # or ".ts", ".tsx", etc.
ERROR_PATTERN = "- error:"        # pattern that indicates real errors
TIMEOUT_SEC = 25


def find_project_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / CONFIG_FILE).exists():
            return parent
    return start


def main():
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    cwd = Path(data.get("cwd", ".")).resolve()

    if not file_path.endswith(FILE_EXTENSION):
        sys.exit(0)

    project_root = find_project_root(cwd)

    try:
        path = Path(file_path).resolve()
        root = project_root.resolve()
        if path.is_relative_to(root):
            file_path = str(path.relative_to(root))
    except (ValueError, OSError):
        pass

    try:
        result = subprocess.run(
            [TYPE_CHECKER, file_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            cwd=str(project_root),
        )
    except Exception as e:
        print(f"{TYPE_CHECKER} hook error: {e}", file=sys.stderr)
        sys.exit(0)

    if result.returncode != 0:
        lines = result.stdout.strip().split("\n")
        errors = [ln.strip() for ln in lines if ERROR_PATTERN in ln]
        if errors:
            msg = f"{TYPE_CHECKER}: {len(errors)} error(s)\n" + "\n".join(errors)
            print(msg, file=sys.stderr)
            sys.exit(2)  # Block on type errors

    sys.exit(0)


if __name__ == "__main__":
    main()
```

### 4d. Validation Reminder — PostToolUse (`.claude/hooks/scripts/validation_reminder.py`)

Non-blocking reminder after editing core code.

```python
#!/usr/bin/env python3
"""
PostToolUse hook: Remind to run validation after editing core code.
Non-blocking (exit 0 with stdout message).
"""

import sys
import json


def main():
    input_data = json.load(sys.stdin)
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Customize: which paths trigger validation reminder
    WATCHED_PATHS = ["src/core", "src/engine", "src/data"]

    if any(path in file_path for path in WATCHED_PATHS):
        print(
            "Core code modified. Remember to validate:\n"
            "  {{cli}} validate quick\n"
            "  {{cli}} validate module --module core --json"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
```

---

## Section 5: Settings Configuration

### `.claude/settings.json` (shared, committed to repo)

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### `.claude/settings.local.json` (per-user, gitignored)

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
      "Bash(cat:*)",
      "Bash(grep:*)",
      "Bash(find:*)",
      "Bash(mkdir:*)",
      "Bash(npm:*)",
      "Bash(pip:*)",
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
          {
            "type": "command",
            "command": "python3 \".claude/hooks/scripts/security_scan.py\"",
            "timeout": 10
          },
          {
            "type": "command",
            "command": "python3 \".claude/hooks/scripts/todo_check.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \".claude/hooks/scripts/typecheck_hook.py\"",
            "timeout": 30
          },
          {
            "type": "command",
            "command": "python3 \".claude/hooks/scripts/validation_reminder.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

---

## Section 6: Validation System Architecture

The validation system is the backbone. Here's how to build one for any project.

### 6a. Tiered Gate System

```
┌──────────────────────────────────────────────────────┐
│  QUICK (pre-commit)                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │ Stage 0  │→ │ Stage 1  │→ │ Stage 2  │             │
│  │ (fast)   │  │ (audits) │  │ (core)   │             │
│  │ G1: Parse│  │ G2: Reg  │  │ G4: Core │             │
│  │ G16: Lint│  │ G3: Parity│  │ G4b: Risk│             │
│  │ G17: Ts  │  │          │  │          │             │
│  └─────────┘  └─────────┘  └─────────┘              │
├──────────────────────────────────────────────────────┤
│  STANDARD (pre-merge) — adds stages 3-5              │
│  Stage 3: Structure/rollup parity + sim orders       │
│  Stage 4: Feature suites (operators, structures)     │
│  Stage 5: Metrics audit                              │
├──────────────────────────────────────────────────────┤
│  FULL (pre-release) — adds stages 6-7                │
│  Stage 6: Indicator + pattern suites                 │
│  Stage 7: Determinism (run twice, compare hashes)    │
└──────────────────────────────────────────────────────┘
```

**Key design principles:**
- **Stages are sequential barriers** — if any gate in stage N fails, stages N+1+ are skipped
- **Gates within a stage run in parallel** — maximize throughput
- **Each gate returns a `GateResult`** — standardized struct with pass/fail, timing, detail, failures list
- **Modules** — any gate or group can run independently via `validate module --module X`
- **Timeout protection** — per-item timeout (120s) and per-gate timeout (600s), nothing blocks forever
- **Incremental reporting** — each gate prints immediately + checkpoints to disk

### 6b. Gate Function Pattern

```python
@dataclass
class GateResult:
    gate_id: str          # "G1", "G2", etc.
    name: str             # Human-readable name
    passed: bool
    checked: int          # Number of items validated
    duration_sec: float
    detail: str           # Summary string
    failures: list[str]   # Specific failure messages


def _gate_example() -> GateResult:
    """Every gate follows this pattern."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    # --- validation logic ---
    for item in items_to_check:
        checked += 1
        result = validate_item(item)
        if not result.ok:
            failures.append(f"{item}: {result.error}")

    return GateResult(
        gate_id="G1",
        name="Config Parse Validation",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"Parsed {checked} configs, {len(failures)} failed",
        failures=failures,
    )
```

### 6c. Module Map

```python
# Map module names to gate functions
MODULES = {
    "core":        [gate_core_tests],
    "data":        [gate_data_integrity],
    "api":         [gate_api_contracts],
    "security":    [gate_security_scan],
    "lint":        [gate_lint_check],
    "types":       [gate_type_check],
    "determinism": [gate_determinism],
    "coverage":    [gate_coverage_check],
}
```

### 6d. Staged Execution

```python
# Stages: list of lists of gate functions
STAGES_QUICK = [
    [gate_parse, gate_lint, gate_types],       # Stage 0: fast checks
    [gate_registry, gate_parity],              # Stage 1: audits
    [gate_core_tests, gate_risk_tests],        # Stage 2: core validation
]

STAGES_STANDARD = STAGES_QUICK + [
    [gate_integration, gate_data_parity],      # Stage 3: integration
    [gate_feature_suite_a, gate_feature_suite_b],  # Stage 4: feature suites
    [gate_metrics_audit],                      # Stage 5: metrics
]

STAGES_FULL = STAGES_STANDARD + [
    [gate_full_suite, gate_pattern_suite],     # Stage 6: exhaustive
    [gate_determinism],                        # Stage 7: reproducibility
]

def run_tiered(stages: list[list[Callable]]) -> list[GateResult]:
    results = []
    for stage in stages:
        # Run gates within stage in parallel
        with ThreadPoolExecutor() as pool:
            futures = {pool.submit(gate): gate for gate in stage}
            stage_results = [f.result(timeout=GATE_TIMEOUT) for f in futures]

        results.extend(stage_results)

        # Stage barrier: stop if any gate failed
        if any(not r.passed for r in stage_results):
            break

    return results
```

---

## Section 7: Memory System

Claude Code's memory system (`.claude/projects/{{project}}/memory/`) persists across conversations. Structure it:

### `MEMORY.md` (index file, auto-loaded)

```markdown
# {{PROJECT}} Memory

## User Preferences
- [user_role.md](user_role.md) — User's role and expertise
- [feedback_style.md](feedback_style.md) — Response style preferences

## Project Context
- [project_status.md](project_status.md) — Current priorities and deadlines
- [active_patterns.md](active_patterns.md) — Known bugs and workarounds

## References
- [external_systems.md](external_systems.md) — Links to external docs/tools
```

### Memory Types

| Type | When to Save | Example |
|------|-------------|---------|
| `user` | Learn user's role/preferences | "Senior backend eng, new to React" |
| `feedback` | User corrects your approach | "Don't mock the DB — use real integration tests" |
| `project` | Learn about ongoing work/deadlines | "Merge freeze starts March 5" |
| `reference` | External system pointers | "Bugs tracked in Linear project INGEST" |

### What NOT to Save
- Code patterns (read the code)
- Git history (use `git log`)
- Debugging solutions (the fix is in the code)
- Anything in CLAUDE.md (already loaded)
- Ephemeral task details

---

## Section 8: The Complete Workflow Loop

```
┌─────────────────────────────────────────────────────────┐
│                    DEVELOPMENT LOOP                      │
│                                                         │
│  1. CHECK TODO.md          ← What needs doing?          │
│  2. PLAN (if non-trivial)  ← Write gated phases         │
│  3. WRITE TODO.md          ← Persist the plan           │
│  4. CODE                   ← Hooks enforce quality:     │
│     ├─ PreToolUse:  security scan, TODO reminder        │
│     └─ PostToolUse: type check, validation reminder     │
│  5. VALIDATE               ← Match tier to change scope │
│     ├─ Quick:    single module or pre-commit            │
│     ├─ Standard: pre-merge                              │
│     └─ Full:     pre-release                            │
│  6. REVIEW (code-reviewer agent)                        │
│  7. UPDATE TODO.md         ← Mark [x], advance phase    │
│  8. COMMIT                 ← Only when gates pass       │
│                                                         │
│  On errors → debugger agent                             │
│  On security concerns → security-auditor agent          │
│  On complexity → orchestrator delegates to specialists  │
│  On refactoring → refactorer agent (baseline first)     │
└─────────────────────────────────────────────────────────┘
```

---

## Section 9: Anti-Patterns (Things That Break AI-Assisted Dev)

| Anti-Pattern | Why It Fails | What to Do Instead |
|-------------|-------------|-------------------|
| Plans in conversation only | Context compaction deletes them | Write to `docs/TODO.md` |
| `validate full` as background agent | Hangs, times out, no partial results | Run individual modules |
| Legacy fallbacks | Hidden bugs, two code paths to maintain | Delete old code, fail loudly |
| No validation gates | Agents make changes that break other things | Gate between every phase |
| Agents with broad tool access | Agents modify code they shouldn't | Narrow tools per agent role |
| No type checking hook | Type errors accumulate silently | PostToolUse pyright/mypy hook |
| No security hook | Secrets get committed | PreToolUse credential scan |
| Parallel DB writes | File lock conflicts | Sequential DB access |
| Tests scattered across files | Hard to find, maintain, run | CLI-only validation system |
| Amending commits after hook failure | Destroys previous commit | Always NEW commit after fix |

---

## Section 10: Adaptation Guide

### For a Web Application (Next.js/React)

```
Validation tiers:
  Quick:    ESLint + TypeScript + unit tests
  Standard: + integration tests + accessibility
  Full:     + E2E (Playwright) + Lighthouse + bundle size

Hooks:
  PreToolUse:  security_scan.py (secrets), todo_check.py
  PostToolUse: tsc_check.py (TypeScript), eslint_check.py

Agents:
  orchestrator, code-reviewer, debugger, docs-writer
  + frontend-specialist (accessibility, performance)
  + api-designer (OpenAPI, REST patterns)
```

### For a Data Pipeline (Python/Airflow)

```
Validation tiers:
  Quick:    Schema validation + pyright + unit tests
  Standard: + integration tests + data quality checks
  Full:     + full pipeline run + output comparison

Hooks:
  PreToolUse:  security_scan.py (credentials), todo_check.py
  PostToolUse: pyright_check.py, data_quality_reminder.py

Agents:
  orchestrator, code-reviewer, debugger, docs-writer
  + data-quality-auditor (schema drift, null checks)
  + pipeline-specialist (DAG design, idempotency)
```

### For a CLI Tool (Rust/Go)

```
Validation tiers:
  Quick:    Compile + clippy/vet + unit tests
  Standard: + integration tests + help text verification
  Full:     + cross-platform build + release checks

Hooks:
  PreToolUse:  security_scan.py, todo_check.py
  PostToolUse: compile_check.sh, lint_check.sh

Agents:
  orchestrator, code-reviewer, debugger, docs-writer
  + ux-reviewer (CLI ergonomics, error messages)
```

---

## Quick Start Checklist

- [ ] Copy CLAUDE.md template → project root
- [ ] Create `docs/TODO.md` with gated phases
- [ ] Create `.claude/agents/` with at least: orchestrator, validate, code-reviewer, debugger
- [ ] Create `.claude/hooks/scripts/` with at least: security_scan.py, typecheck_hook.py
- [ ] Configure `.claude/settings.local.json` with hooks and permissions
- [ ] Build your validation CLI with `GateResult` pattern and tiered stages
- [ ] Set up memory system in `.claude/projects/{{project}}/memory/`
- [ ] Replace all `{{PLACEHOLDER}}` values
- [ ] Run your first `validate quick` to verify everything works
