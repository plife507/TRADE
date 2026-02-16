# Unified Play Validator - Implementation TODO

## Goal
Single function that validates user-facing YAML, runs ALL checks, and returns a complete list of errors.

## Tasks

- [x] **1. Add ValidationErrorCode values** (`play_yaml_builder.py`)
  - `INVALID_TIMEFRAME_VALUE`, `INVALID_EXEC_POINTER`, `INVALID_ACCOUNT_FIELD`
  - `DSL_PARSE_ERROR`, `PLAY_CONSTRUCTION_FAILED`, `PLAY_FIELD_ERROR`

- [x] **2. Add dict-level validation functions** (`play_yaml_builder.py`)
  - `validate_required_keys(play_dict)` — checks id/name, version, symbol, timeframes, account, actions, features|structures
  - `validate_timeframes_section(play_dict)` — canonical TFs via TF_MINUTES, exec pointer valid
  - `validate_account_section(play_dict)` — starting_equity > 0, max_leverage > 0
  - `validate_features_section(play_dict)` — indicator type in registry, params accepted

- [x] **3. Add unified orchestrator** (`play_validator.py`)
  - `validate_play_unified(play_dict)` — Phase 1 dict checks + Phase 2 Play.from_dict()
  - `validate_play_file_unified(file_path)` — file wrapper

- [x] **4. Wire into CLI** (`backtest_play_tools.py`)
  - Update `backtest_play_normalize_tool()` to call `validate_play_unified()` before normalization

- [x] **5. Verify**
  - sol_ema_cross_demo: PASS (valid=True, 0 errors)
  - Missing keys: 6 errors caught (version, timeframes, account, actions, symbol, features)
  - Bad exec pointer (exec="15m"): INVALID_EXEC_POINTER caught with suggestions
  - Unknown indicator: UNSUPPORTED_INDICATOR caught
  - CLI play-normalize: PASS
  - `python trade_cli.py validate quick`: ALL 4 GATES PASSED (307.6s)
