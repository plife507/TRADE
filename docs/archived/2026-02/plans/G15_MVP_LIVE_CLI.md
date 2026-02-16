# G15: MVP Live CLI

**Entry**: G14 verification passes
**Theme**: Operator can run, monitor, and stop a demo/live trading session
**Exit**: All new commands functional + existing validation passes

## Tasks

- [x] G15.1: Pre-live gate auto-runs on `play run --mode live`
- [x] G15.2: Live/demo mode banner (red=live, blue=demo)
- [x] G15.3: Enhanced `play status` with orders, reconnects, duration, last candle, --json
- [x] G15.4: Enhanced `play stop` with position check, --close-positions, --force, --all
- [x] G15.5: `play watch` -- Rich Live dashboard with 2s refresh
- [x] G15.6: Non-interactive commands: account balance/exposure, position list/close, panic
- [x] G15.7: Windows signal handling fix (signal.signal for win32)
