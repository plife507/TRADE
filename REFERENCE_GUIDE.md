# Reference Materials Guide

## Where to Find Reference Documentation

### Reference Materials Location
**Reference materials should be kept OUTSIDE this repository.**

Recommended location:
```
C:\CODE\AI\reference\
```

This includes:
- **Bybit API Documentation**: `C:\CODE\AI\reference\exchanges\bybit\`
- **Pybit SDK**: `C:\CODE\AI\reference\exchanges\pybit\`
- Other exchange documentation and research materials

### External References
- **AI Engineering Toolkit**: `C:\CODE\AI\ai-engineering-toolkit\` - Curated list of AI/LLM tools and frameworks

### Why Not in This Repo?

Large reference materials (like full API documentation) are **excluded** from this repository because:
1. **Size**: They're too large (hundreds of files, thousands of lines)
2. **Maintenance**: They're maintained independently by their respective projects
3. **Updates**: They change frequently and don't need to be versioned with this project
4. **Clarity**: Keeps the repository focused on the TRADE project code

### What IS in This Repo?

Project-specific documentation that's directly relevant to TRADE:
- `README.md` - Project overview and quick start
- `CLAUDE.md` - Development guidance for AI assistants
- `PROJECT_RULES.md` - Coding standards and project rules
- `SYSTEM_REVIEW.md` - Architecture documentation
- `PROJECT_DESCRIPTION.md` - Detailed project description
- `SETUP_GITHUB.md` - GitHub setup instructions

### Accessing Reference Materials

When developing, reference materials should be in the central reference library:
```python
# Bybit API docs are at:
C:\CODE\AI\reference\exchanges\bybit\docs\v5\

# Pybit SDK examples:
C:\CODE\AI\reference\exchanges\pybit\examples\
```

**Note:** If you have a `reference/` folder in this project, it's for local development only and is excluded from git.

### If You Need Reference in Repo

If you need specific reference files in the repo (e.g., for CI/CD or documentation generation):
1. Create a `docs/reference/` folder
2. Copy only the specific files you need
3. Keep them small and focused
4. Document why they're needed

### Best Practices

✅ **DO:**
- Keep project-specific docs in the repo
- Reference external docs via links or paths
- Use the central reference library for development

❌ **DON'T:**
- Commit large reference documentation
- Duplicate external documentation
- Track embedded git repositories

