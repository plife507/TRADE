"""
Logging module stress tests for TRADE.

Validates the structlog pipeline (P18 migration) under edge conditions:
cross-thread context, file rotation, concurrent writes, redaction,
shutdown draining, verbosity gating, and RunLogger lifecycle.

Run via: python scripts/test_logging_module.py

Exit code 0 = all pass, 1 = any fail.
"""

from __future__ import annotations

import io
import json
import logging
import logging.handlers
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure project root is importable
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import structlog
import structlog.contextvars

import src.utils.logging_config as logging_config
import src.utils.debug as debug_mod
from src.utils.logger import (
    get_module_logger,
    suppress_for_validation,
)
from src.utils.logging_config import (
    bind_engine_context,
    clear_engine_context,
    configure_logging,
    shutdown_logging,
)

# ---------------------------------------------------------------------------
# Reset helper — clean slate before every test
# ---------------------------------------------------------------------------

def _reset_logging_state() -> None:
    """Tear down ALL logging state so the next test starts clean."""
    # 1. Stop QueueListener, reset _configured flag
    shutdown_logging()

    # 2. Wipe structlog contextvars
    structlog.contextvars.clear_contextvars()

    # 3. Reset structlog global config
    structlog.reset_defaults()

    # 4. Clear handlers on root + trade.* loggers
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)

    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("trade"):
            lgr = logging.getLogger(name)
            lgr.handlers.clear()
            lgr.setLevel(logging.NOTSET)

    # 5. Reset debug/verbose flags
    debug_mod._debug_enabled = False
    debug_mod._verbose_enabled = False

    # 6. Forcibly reset module-level globals in logging_config
    logging_config._configured = False
    logging_config._queue_listener = None
    logging_config._log_queue = None


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------

_results: list[tuple[int, str, bool, str]] = []  # (num, name, passed, detail)


def _record(num: int, name: str, passed: bool, detail: str = "") -> None:
    tag = "PASS" if passed else "FAIL"
    _results.append((num, name, passed, detail))
    print(f"[TEST {num:02d}] {name}")
    if detail:
        print(f"          [{tag}] {detail}")
    else:
        print(f"          [{tag}]")
    print()


# ===================================================================
# TEST 01: Contextvars cross-thread survival
# ===================================================================

def test_01_contextvars_cross_thread() -> None:
    """play_hash/symbol/mode appear in JSONL via QueueListener."""
    tmpdir = tempfile.mkdtemp(prefix="log_test01_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")
        bind_engine_context(play_hash="abcd1234abcd1234", symbol="BTCUSDT", mode="backtest")

        logger = get_module_logger("test.cross_thread")
        logger.info("cross-thread marker")

        # Give QueueListener time to drain
        time.sleep(0.3)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(1, "Contextvars cross-thread survival", False, "trade.jsonl not created")
            return

        found_play_hash = False
        found_symbol = False
        found_mode = False
        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "cross-thread marker" in entry.get("event", ""):
                found_play_hash = entry.get("play_hash") == "abcd1234abcd1234"
                found_symbol = entry.get("symbol") == "BTCUSDT"
                found_mode = entry.get("mode") == "backtest"
                break

        all_ok = found_play_hash and found_symbol and found_mode
        missing = []
        if not found_play_hash:
            missing.append("play_hash")
        if not found_symbol:
            missing.append("symbol")
        if not found_mode:
            missing.append("mode")

        detail = "Found play_hash, symbol, mode in JSONL" if all_ok else f"Missing: {', '.join(missing)}"
        _record(1, "Contextvars cross-thread survival", all_ok, detail)
    finally:
        clear_engine_context()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 02: File rotation
# ===================================================================

def test_02_file_rotation() -> None:
    """RotatingFileHandler rotates at limit, keeps <=7 backups."""
    tmpdir = tempfile.mkdtemp(prefix="log_test02_")
    try:
        log_file = Path(tmpdir) / "rotation_test.log"
        handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=100_000,   # 100 KB
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        test_logger = logging.getLogger("test.rotation")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        # Write ~500 KB of data (each line ~100 bytes → 5000 lines)
        line = "X" * 95 + "\n"  # ~100 bytes with overhead
        for _ in range(5000):
            test_logger.info(line.rstrip())

        handler.close()
        test_logger.removeHandler(handler)

        # Count rotated files: rotation_test.log, rotation_test.log.1, ..., .7
        log_files = list(Path(tmpdir).glob("rotation_test.log*"))
        # Should have main + up to 7 backups = 8 max
        ok = 2 <= len(log_files) <= 8

        _record(
            2,
            "File rotation",
            ok,
            f"Found {len(log_files)} files (expected 2-8)",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 03: Concurrent thread logging
# ===================================================================

def test_03_concurrent_thread_logging() -> None:
    """4 threads x 50 msgs, all valid JSON, none lost."""
    tmpdir = tempfile.mkdtemp(prefix="log_test03_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        n_threads = 4
        msgs_per_thread = 50
        barrier = threading.Barrier(n_threads)

        def worker(thread_id: int) -> None:
            logger = get_module_logger(f"test.concurrent.t{thread_id}")
            barrier.wait()  # synchronize start
            for i in range(msgs_per_thread):
                logger.info(f"thread={thread_id} msg={i}")

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(3, "Concurrent thread logging", False, "trade.jsonl not created")
            return

        lines = jsonl_path.read_text().splitlines()
        valid_json = 0
        invalid_json = 0
        marker_count = 0
        for line in lines:
            try:
                entry = json.loads(line)
                valid_json += 1
                if "thread=" in entry.get("event", ""):
                    marker_count += 1
            except json.JSONDecodeError:
                invalid_json += 1

        expected = n_threads * msgs_per_thread
        ok = invalid_json == 0 and marker_count == expected
        _record(
            3,
            "Concurrent thread logging",
            ok,
            f"{marker_count}/{expected} msgs, {invalid_json} invalid JSON lines",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 04: suppress_for_validation
# ===================================================================

def test_04_suppress_for_validation() -> None:
    """INFO silenced, WARNING flows, structlog pipeline intact."""
    tmpdir = tempfile.mkdtemp(prefix="log_test04_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        suppress_for_validation()

        logger = get_module_logger("test.suppress")

        # Capture console output via a StringIO handler
        buf = io.StringIO()
        stream_handler = logging.StreamHandler(buf)
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        logging.getLogger("trade.test.suppress").addHandler(stream_handler)

        logger.info("should_be_hidden")
        logger.warning("should_be_visible")

        output = buf.getvalue()
        info_hidden = "should_be_hidden" not in output
        warning_visible = "should_be_visible" in output

        logging.getLogger("trade.test.suppress").removeHandler(stream_handler)

        ok = info_hidden and warning_visible
        detail_parts = []
        if not info_hidden:
            detail_parts.append("INFO not suppressed")
        if not warning_visible:
            detail_parts.append("WARNING not visible")
        detail = "INFO suppressed, WARNING flows" if ok else "; ".join(detail_parts)
        _record(4, "suppress_for_validation", ok, detail)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 05: Verbosity flags
# ===================================================================

def test_05_verbosity_flags() -> None:
    """-q/-v/--debug correctly gate verbose_log/debug_log.

    Uses JSONL output as the end-to-end check: verbose_log/debug_log emit
    through trade.utils.debug's internal _logger, which propagates to root
    -> QueueHandler -> JSONL.
    """
    tmpdir = tempfile.mkdtemp(prefix="log_test05_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        # --- Phase 1: quiet mode (neither verbose nor debug) ---
        debug_mod._debug_enabled = False
        debug_mod._verbose_enabled = False

        debug_mod.verbose_log("verbose_quiet_test")
        debug_mod.debug_log("debug_quiet_test")

        # --- Phase 2: verbose mode ---
        debug_mod.enable_verbose(True)

        debug_mod.verbose_log("verbose_on_test")
        debug_mod.debug_log("debug_off_test")

        # --- Phase 3: debug mode ---
        debug_mod.enable_debug(True)

        debug_mod.verbose_log("verbose_debug_test")
        debug_mod.debug_log("debug_on_test")

        time.sleep(0.3)
        shutdown_logging()

        # Check JSONL for correct gating
        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(5, "Verbosity flags", False, "trade.jsonl not created")
            return

        events: set[str] = set()
        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            evt = entry.get("event", "")
            for marker in (
                "verbose_quiet_test", "debug_quiet_test",
                "verbose_on_test", "debug_off_test",
                "verbose_debug_test", "debug_on_test",
            ):
                if marker in evt:
                    events.add(marker)

        # Phase 1 (quiet): NEITHER should appear
        quiet_ok = "verbose_quiet_test" not in events and "debug_quiet_test" not in events

        # Phase 2 (verbose only): verbose appears, debug does NOT
        verbose_ok = "verbose_on_test" in events and "debug_off_test" not in events

        # Phase 3 (debug): BOTH appear
        debug_ok = "verbose_debug_test" in events and "debug_on_test" in events

        ok = quiet_ok and verbose_ok and debug_ok
        issues = []
        if not quiet_ok:
            issues.append("quiet mode leaked")
        if not verbose_ok:
            issues.append("verbose mode incorrect")
        if not debug_ok:
            issues.append("debug mode incorrect")

        detail = "All 3 verbosity levels gate correctly" if ok else "; ".join(issues)
        _record(5, "Verbosity flags", ok, detail)
    finally:
        debug_mod._debug_enabled = False
        debug_mod._verbose_enabled = False
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 06: Redaction in JSONL
# ===================================================================

def test_06_redaction_in_jsonl() -> None:
    """api_key, secret, token, passphrase, signature -> REDACTED.

    Tests both paths:
    - stdlib logger + contextvars (production path)
    - structlog-native logger with inline fields (fixed by _StructlogQueueHandler)
    """
    tmpdir = tempfile.mkdtemp(prefix="log_test06_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        # Path 1: stdlib logger + contextvars (production pattern)
        structlog.contextvars.bind_contextvars(
            api_key="my_secret_api_key",
            secret="super_secret_value",
        )
        logger = get_module_logger("test.redaction")
        logger.info("stdlib_sensitive_test")
        structlog.contextvars.clear_contextvars()

        # Path 2: structlog-native logger with inline fields
        slog = structlog.get_logger("test.redaction.native")
        slog.info(
            "native_sensitive_test",
            token="bearer_token_abc",
            passphrase="my_passphrase",
            signature="sig_xyz_123",
        )

        time.sleep(0.3)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(6, "Redaction in JSONL output", False, "trade.jsonl not created")
            return

        # Check stdlib path
        stdlib_ok = False
        stdlib_leaked: list[str] = []
        # Check native path
        native_ok = False
        native_leaked: list[str] = []

        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            evt = entry.get("event", "")
            if "stdlib_sensitive_test" in evt:
                stdlib_ok = True
                for field in ("api_key", "secret"):
                    val = entry.get(field, "")
                    if val and val != "***REDACTED***":
                        stdlib_leaked.append(f"{field}={val!r}")
            elif "native_sensitive_test" in evt:
                native_ok = True
                for field in ("token", "passphrase", "signature"):
                    val = entry.get(field, "")
                    if val and val != "***REDACTED***":
                        native_leaked.append(f"{field}={val!r}")

        issues = []
        if not stdlib_ok:
            issues.append("stdlib event missing from JSONL")
        elif stdlib_leaked:
            issues.append(f"stdlib leaked: {', '.join(stdlib_leaked)}")
        if not native_ok:
            issues.append("native event missing from JSONL")
        elif native_leaked:
            issues.append(f"native leaked: {', '.join(native_leaked)}")

        ok = stdlib_ok and not stdlib_leaked and native_ok and not native_leaked
        detail = "Both stdlib + native paths redacted" if ok else "; ".join(issues)
        _record(6, "Redaction in JSONL output", ok, detail)
    finally:
        structlog.contextvars.clear_contextvars()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 07: Shutdown drain
# ===================================================================

def test_07_shutdown_drain() -> None:
    """500 rapid msgs, shutdown_logging(), count = 500."""
    tmpdir = tempfile.mkdtemp(prefix="log_test07_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        logger = get_module_logger("test.drain")
        n_msgs = 500
        for i in range(n_msgs):
            logger.info(f"drain_marker_{i}")

        # Shutdown should drain the queue completely
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(7, "Shutdown drain", False, "trade.jsonl not created")
            return

        count = 0
        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "drain_marker_" in entry.get("event", ""):
                count += 1

        ok = count == n_msgs
        _record(7, "Shutdown drain", ok, f"{count}/{n_msgs} messages drained")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 08: bind/clear lifecycle
# ===================================================================

def test_08_bind_clear_lifecycle() -> None:
    """Fields present when bound, absent after clear."""
    tmpdir = tempfile.mkdtemp(prefix="log_test08_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        logger = get_module_logger("test.lifecycle")

        # Phase 1: bind context, log
        bind_engine_context(play_hash="bind1234bind1234", symbol="ETHUSDT", mode="demo")
        logger.info("bound_marker")

        # Phase 2: clear context, log
        clear_engine_context()
        logger.info("cleared_marker")

        time.sleep(0.3)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(8, "bind/clear lifecycle", False, "trade.jsonl not created")
            return

        bound_ok = False
        cleared_ok = False
        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            evt = entry.get("event", "")
            if "bound_marker" in evt:
                bound_ok = (
                    entry.get("play_hash") == "bind1234bind1234"
                    and entry.get("symbol") == "ETHUSDT"
                    and entry.get("mode") == "demo"
                )
            elif "cleared_marker" in evt:
                cleared_ok = (
                    "play_hash" not in entry
                    and "symbol" not in entry
                    and "mode" not in entry
                )

        ok = bound_ok and cleared_ok
        issues = []
        if not bound_ok:
            issues.append("context not present when bound")
        if not cleared_ok:
            issues.append("context leaked after clear")
        detail = "Context present when bound, absent after clear" if ok else "; ".join(issues)
        _record(8, "bind/clear lifecycle", ok, detail)
    finally:
        clear_engine_context()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 09: Debug gating overhead
# ===================================================================

def test_09_debug_gating_overhead() -> None:
    """100k no-op calls < 0.5s when debug disabled."""
    try:
        _reset_logging_state()
        debug_mod._debug_enabled = False
        debug_mod._verbose_enabled = False

        n = 100_000
        start = time.perf_counter()
        for _ in range(n):
            debug_mod.debug_log("no-op msg", bar_idx=42, action="ENTRY_LONG")
        elapsed = time.perf_counter() - start

        ok = elapsed < 0.5
        _record(
            9,
            "Debug gating overhead",
            ok,
            f"{n} no-op calls in {elapsed:.3f}s (limit: 0.5s)",
        )
    finally:
        debug_mod._debug_enabled = False
        debug_mod._verbose_enabled = False


# ===================================================================
# TEST 10: RunLogger finalize
# ===================================================================

def test_10_run_logger_finalize() -> None:
    """Handler removed, index.jsonl written, no handler leak."""
    tmpdir = tempfile.mkdtemp(prefix="log_test10_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        # Redirect RunLogger's GLOBAL_LOGS_DIR to tmpdir
        import src.backtest.logging.run_logger as rl_mod
        orig_global_dir = rl_mod.GLOBAL_LOGS_DIR
        rl_mod.GLOBAL_LOGS_DIR = Path(tmpdir) / "global_logs"

        artifact_dir = Path(tmpdir) / "artifacts" / "test_run"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        from src.backtest.logging.run_logger import RunLogger

        run_logger = RunLogger(
            play_hash="finalize1234hash",
            run_id="run_test_01",
            artifact_dir=artifact_dir,
            play_id="TEST_FINALIZE",
            symbol="BTCUSDT",
            tf="15m",
        )

        # Count handlers before finalize
        backtest_logger = logging.getLogger("trade.backtest.run")
        handlers_before = len(backtest_logger.handlers)

        run_logger.info("test log entry")
        run_logger.finalize(
            net_pnl=42.50,
            trades_count=5,
            status="success",
            trades_hash="th_abc123",
            run_hash="rh_xyz789",
        )

        handlers_after = len(backtest_logger.handlers)

        # Check handler was removed
        handler_removed = handlers_after < handlers_before

        # Check index.jsonl was written
        from src.utils.debug import short_hash
        play_log_dir = Path(tmpdir) / "global_logs" / short_hash("finalize1234hash")
        index_path = play_log_dir / "index.jsonl"
        index_exists = index_path.exists()

        index_valid = False
        if index_exists:
            for line in index_path.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("run_id") == "run_test_01":
                        index_valid = True
                        break
                except json.JSONDecodeError:
                    pass

        # Check per-run log was written
        engine_log = artifact_dir / "logs" / "engine_debug.log"
        engine_log_exists = engine_log.exists()

        ok = handler_removed and index_valid and engine_log_exists
        issues = []
        if not handler_removed:
            issues.append("handler not removed")
        if not index_valid:
            issues.append("index.jsonl not written/valid")
        if not engine_log_exists:
            issues.append("engine_debug.log missing")

        detail = "Handler removed, index.jsonl written, per-run log created" if ok else "; ".join(issues)
        _record(10, "RunLogger finalize", ok, detail)

        # Restore
        rl_mod.GLOBAL_LOGS_DIR = orig_global_dir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 11: JSONL validity
# ===================================================================

def test_11_jsonl_validity() -> None:
    """Special chars, unicode, long msgs — all lines parse as JSON."""
    tmpdir = tempfile.mkdtemp(prefix="log_test11_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        logger = get_module_logger("test.jsonl_valid")

        # Edge-case messages
        test_messages = [
            'quote "test" with \\backslash',
            "unicode: \u00e9\u00e8\u00ea\u00eb \u2603 \U0001f680 \u4e16\u754c",
            "newline\\nin\\nmessage",
            "tabs\there\tand\tthere",
            "A" * 5000,  # long message
            '{"nested": "json", "value": 42}',
            "null bytes: \x00 should survive",
            "<html>&amp; entities &lt;br/&gt;</html>",
            "",  # empty message
        ]

        for msg in test_messages:
            logger.info(msg)

        time.sleep(0.3)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(11, "JSONL validity", False, "trade.jsonl not created")
            return

        lines = jsonl_path.read_text().splitlines()
        invalid_lines: list[int] = []
        for i, line in enumerate(lines, 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                invalid_lines.append(i)

        ok = len(invalid_lines) == 0 and len(lines) >= len(test_messages)
        detail = (
            f"All {len(lines)} lines valid JSON"
            if ok
            else f"{len(invalid_lines)} invalid lines: {invalid_lines[:5]}"
        )
        _record(11, "JSONL validity", ok, detail)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 12: Console vs file format
# ===================================================================

def test_12_console_vs_file_format() -> None:
    """Console = human-readable, file = JSON."""
    tmpdir = tempfile.mkdtemp(prefix="log_test12_")
    try:
        _reset_logging_state()

        # Capture console output by replacing stderr with StringIO
        old_stderr = sys.stderr
        captured = io.StringIO()
        sys.stderr = captured

        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        logger = get_module_logger("test.format_check")
        logger.info("format_marker_12")

        time.sleep(0.3)
        shutdown_logging()
        sys.stderr = old_stderr

        console_output = captured.getvalue()

        # Console should NOT be valid JSON (it's human-readable)
        console_is_json = False
        for line in console_output.splitlines():
            if "format_marker_12" in line:
                try:
                    json.loads(line)
                    console_is_json = True
                except json.JSONDecodeError:
                    pass

        # File should be valid JSON
        jsonl_path = Path(tmpdir) / "trade.jsonl"
        file_is_json = False
        if jsonl_path.exists():
            for line in jsonl_path.read_text().splitlines():
                if "format_marker_12" in line:
                    try:
                        json.loads(line)
                        file_is_json = True
                    except json.JSONDecodeError:
                        pass

        ok = not console_is_json and file_is_json
        issues = []
        if console_is_json:
            issues.append("console output is JSON (should be human-readable)")
        if not file_is_json:
            issues.append("file output is not JSON")

        detail = "Console=human, file=JSON" if ok else "; ".join(issues)
        _record(12, "Console vs file format", ok, detail)
    finally:
        sys.stderr = sys.__stderr__
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 13: Idempotency
# ===================================================================

def test_13_idempotency() -> None:
    """configure_logging() twice -> same handler count."""
    tmpdir = tempfile.mkdtemp(prefix="log_test13_")
    try:
        _reset_logging_state()

        configure_logging(log_dir=tmpdir, log_level="INFO")
        root = logging.getLogger()
        count_first = len(root.handlers)

        # Call again — should be no-op due to _configured guard
        configure_logging(log_dir=tmpdir, log_level="DEBUG")
        count_second = len(root.handlers)

        ok = count_first == count_second and count_first > 0
        _record(
            13,
            "Idempotency",
            ok,
            f"Handlers: first={count_first}, second={count_second}",
        )
    finally:
        shutdown_logging()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# TEST 14: Empty context
# ===================================================================

def test_14_empty_context() -> None:
    """No engine context bound -> no spurious fields in JSONL."""
    tmpdir = tempfile.mkdtemp(prefix="log_test14_")
    try:
        _reset_logging_state()
        configure_logging(log_dir=tmpdir, log_level="DEBUG")

        # Explicitly do NOT call bind_engine_context
        logger = get_module_logger("test.empty_ctx")
        logger.info("empty_context_marker")

        time.sleep(0.3)
        shutdown_logging()

        jsonl_path = Path(tmpdir) / "trade.jsonl"
        if not jsonl_path.exists():
            _record(14, "Empty context", False, "trade.jsonl not created")
            return

        spurious_fields: list[str] = []
        engine_fields = ("play_hash", "symbol", "mode", "bar_idx")
        for line in jsonl_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "empty_context_marker" in entry.get("event", ""):
                for field in engine_fields:
                    if field in entry:
                        spurious_fields.append(f"{field}={entry[field]!r}")
                break

        ok = len(spurious_fields) == 0
        detail = "No spurious engine fields" if ok else f"Spurious: {', '.join(spurious_fields)}"
        _record(14, "Empty context", ok, detail)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===================================================================
# Runner
# ===================================================================

ALL_TESTS = [
    test_01_contextvars_cross_thread,
    test_02_file_rotation,
    test_03_concurrent_thread_logging,
    test_04_suppress_for_validation,
    test_05_verbosity_flags,
    test_06_redaction_in_jsonl,
    test_07_shutdown_drain,
    test_08_bind_clear_lifecycle,
    test_09_debug_gating_overhead,
    test_10_run_logger_finalize,
    test_11_jsonl_validity,
    test_12_console_vs_file_format,
    test_13_idempotency,
    test_14_empty_context,
]


def main() -> int:
    print("=" * 64)
    print("  LOGGING MODULE STRESS TESTS")
    print("=" * 64)
    print()

    for test_fn in ALL_TESTS:
        try:
            test_fn()
        except Exception as exc:
            # Extract test number from function name
            num = int(test_fn.__name__.split("_")[1])
            name = test_fn.__name__.replace(f"test_{num:02d}_", "").replace("_", " ")
            _record(num, name, False, f"EXCEPTION: {type(exc).__name__}: {exc}")

    print("=" * 64)
    passed = sum(1 for _, _, ok, _ in _results if ok)
    total = len(_results)
    print(f"  SUMMARY: {passed}/{total} tests passed")
    print("=" * 64)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
