# CLI Redesign Plan

## Context

The current CLI has 125+ commands across 12+ files. This redesign makes it faster, context-aware, and better organized while keeping all functionality.

## Design Decisions

- **Deferred connection**: App starts disconnected. "Connect to Exchange" unlocks trading menus.
- **Orders**: 2 groups (unified Place Order + Manage). Kill 4 nested sub-menus.
- **Account**: Keep all 14 options unchanged.
- **Data**: Keep all 24 operations, reorganize into sub-menus (top level: 9 items).
- **Main menu**: Context-aware (offline vs connected, Demo vs Live, running plays visible).
- **Forge/Backtest**: Keep separate, add cross-links and shared audit module.
- **Symbol input**: Recent symbols quick-pick (session-only, last 5).

---

## Completed Gates

| Gate | Summary | Status |
|------|---------|--------|
| G1: Foundation | `symbol_memory.py`, symbol helpers, running plays helper | DONE |
| G2: App Entrance | Deferred connection, offline/connected menus, PANIC button | DONE (pyright clean, manual test pending) |
| G3: Symbol Quick-Pick | Replaced all `get_input("Symbol...")` across 4 menu files | DONE |
| G6: Context-Aware Header | Offline indicator, running plays panel, LIVE banner | DONE (pyright clean, manual test pending) |
| G7: Forge/Backtest Cross-Links | Shared audits module, cross-navigation | DONE (pyright clean, manual test pending) |
| G9: Plays Menu | 9-option plays lifecycle menu, wired to connected main menu | DONE (pyright clean, manual test pending) |

---

## Open Work

### Gate 4: Orders Menu Restructure

Build unified `_place_order()` function:
- [ ] Step 1: Order type selector (Market / Limit / Stop Market / Stop Limit)
- [ ] Step 2: Side (Buy / Sell)
- [ ] Step 3: Symbol via `get_symbol_input()`
- [ ] Step 4: USD amount via `get_float_input()`
- [ ] Step 5: Conditional fields (price, TIF, reduce-only, trigger)
- [ ] Step 6: Optional TP/SL (market orders only, blank to skip)
- [ ] Step 7: Preview via `print_order_preview()`
- [ ] Step 8: Confirm + execute via existing tool functions
- [ ] Route to: `market_buy_tool`, `market_sell_tool`, `limit_buy_tool`, etc.

Old sub-menu functions already deleted. Wire option 1 to `_place_order()`.

### Gate 5: Data Menu Reorganization

Sub-menu files already created (`data_sync_menu.py`, `data_info_menu.py`, `data_query_menu.py`, `data_maintenance_menu.py`).

Remaining:
- [ ] Rewrite `data_menu.py` top level to delegate to sub-menus
- [ ] `data_env` state passed to all sub-menus
- [ ] All 24 original operations still accessible
- [ ] `pyright` on all data menu files = 0 errors

### Gate 8: Final Validation

- [ ] `python trade_cli.py validate quick` passes
- [ ] Manual: app starts -> offline menu -> backtest works without connection
- [ ] Manual: "Connect to Exchange" (demo) -> full menu appears
- [ ] Manual: place market order via unified form
- [ ] Manual: symbol quick-picks appear after first use
- [ ] Manual: data sub-menus accessible, all 24 operations reachable
- [ ] Manual: cross-links between Forge and Backtest work
