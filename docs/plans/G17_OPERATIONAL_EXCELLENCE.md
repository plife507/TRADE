# G17: Operational Excellence

**Entry**: G16 verification passes
**Theme**: Full operational tooling for monitoring, debugging, and controlling live bots
**Exit**: Trade journal writes entries, logs stream, pause/resume works

## Tasks

- [x] G17.1: Trade journal -- JSONL at `~/.trade/journal/`, wired into LiveRunner signal processing
- [x] G17.2: `play logs` command -- reads journal JSONL, supports --follow, --lines
- [x] G17.3: `play pause` / `play resume` -- file-based IPC via `.pause` files, skip signal eval when paused
- [x] G17.4: Notification adapter -- Telegram + Discord via env vars, NoopAdapter as default
- [x] G17.5: Unify `play run --mode backtest` -- delegates to `backtest_run_play_tool` (golden path)
