---
allowed-tools: Bash(git:*), Read, Grep
description: Auto-generate conventional commit message for staged changes
argument-hint: [--push]
---

# Commit Command

Generate and create a conventional commit for staged changes.

## Usage

```
/trade-workflow:commit [--push]
```

- `--push` - Also push to origin after commit

## Process

1. Check staged changes:

```bash
git status
git diff --staged
git log -3 --oneline
```

2. Analyze changes:
- Determine change type (feat, fix, refactor, docs, etc.)
- Identify affected module (backtest, core, data, tools)
- Summarize the "why" not the "what"

3. Create commit with conventional format:

```bash
git commit -m "$(cat <<'EOF'
type(scope): description

Body explaining the change.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

4. If `--push` specified:

```bash
git push origin HEAD
```

## Commit Types

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring |
| `docs` | Documentation only |
| `test` | Adding/updating tests |
| `chore` | Build, config changes |

## Scopes

| Scope | Path |
|-------|------|
| `backtest` | src/backtest/ |
| `engine` | src/backtest/engine*.py |
| `sim` | src/backtest/sim/ |
| `core` | src/core/ |
| `data` | src/data/ |
| `tools` | src/tools/ |
| `cli` | trade_cli.py, src/cli/ |

## Example Output

```
feat(engine): add direct array access for 1m quote lookup

BUG-001 fix: Replaced get_quote_at_exec_close() binary search with
direct O(1) array access via FeedStore._get_ts_close_ms_at(idx).

Co-Authored-By: Claude <noreply@anthropic.com>
```
