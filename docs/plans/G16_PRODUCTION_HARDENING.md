# G16: Production Hardening

**Entry**: G15 verification passes
**Theme**: Safe for unsupervised running. Crash recovery works.
**Exit**: Drawdown breaker tested + state serialization round-trips + cross-process status works

## Tasks

- [x] G16.1: Drawdown circuit breaker in RiskManager (Check 7 in check(), _peak_equity tracking)
- [x] G16.2: Structure state serialization (to_json / from_json on TFIncrementalState + MultiTFIncrementalState)
- [x] G16.3: Structure history ring buffer for live (deque(maxlen=500) per structure key per TF)
- [x] G16.4: Cross-process EngineManager (PID file + list_all() + _is_pid_alive())
