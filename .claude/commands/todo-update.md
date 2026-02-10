---
allowed-tools: Read, Edit, Write
description: Update TODO.md with completed work or new tasks
argument-hint: [complete|add|status]
---

# TODO Update Command

Update the project TODO.md file.

## Usage

```
/todo-update [action]
```

- `complete` - Mark items as completed
- `add` - Add new TODO items
- `status` - Show current TODO status

## Location

Main TODO: `docs/TODO.md`

## Actions

### Complete Items

1. Read current TODO.md
2. Find items to mark complete
3. Update checkboxes: `- [ ]` to `- [x]`
4. Add validation status

### Add Items

1. Determine priority (P0-P5)
2. Add to appropriate section
3. Include:
   - Description
   - File:line reference
   - Checkboxes for subtasks

### Status

1. Read TODO.md
2. Count completed vs pending
3. Report current phase and focus

## Format

```markdown
### Completed Work (YYYY-MM-DD)

- [x] Task description
- [x] Task description
- **Validation**: validate quick PASS
```
