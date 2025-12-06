# TRADE Project Context

## Active Project
**The active project is the `TRADE/` folder.** This is the main trading bot project.

## Project Scope
- All development, features, and changes should focus on the `TRADE/` directory
- The `trade_cli.py` file should remain in the `TRADE/` root folder
- CLI functionality is the primary interface for this project

## Reference Folder
**`C:\CODE\AI\TRADE\reference\`** contains reference materials for this project:
- **Bybit Exchange Documentation**: `C:\CODE\AI\TRADE\reference\exchanges\bybit\`
  - Official Bybit V5 API documentation
  - API specifications in `docs/v5/`
  - Rate limit documentation
  - WebSocket documentation
- **Official Bybit Python Library**: `C:\CODE\AI\TRADE\reference\exchanges\pybit\`
  - Official `pybit` Python SDK source code
  - Examples and usage patterns
  - Library documentation

**When working on Bybit integration:**
- Consult `reference/exchanges/bybit/docs/v5/` for API endpoint details
- Reference `reference/exchanges/pybit/` for official library usage patterns
- Check rate limit rules in `reference/exchanges/bybit/docs/v5/rate-limit/`

## Reference Projects
- `moon-dev-ai-agents/` is a separate project in the workspace, used only for:
  - Architecture suggestions
  - Pattern references
  - Design inspiration
  - **NOT** for direct integration or code copying

## Development Focus
When implementing features (like REST API, FastAPI, etc.):
- Keep `trade_cli.py` in its current location (`TRADE/trade_cli.py`)
- Maintain CLI as the primary interface
- Any new API/web features should be additive, not replacements
- All new code should go in `TRADE/src/` structure

