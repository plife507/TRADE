"""
Application lifecycle manager.

Provides centralized initialization, startup, and shutdown management
for all core trading bot components.

This is the single entry point for:
- Component initialization in correct dependency order
- WebSocket auto-start (if enabled)
- Graceful shutdown with cleanup
- Signal handling (SIGINT/SIGTERM)

Usage:
    from src.core.application import Application, get_application
    
    # Option 1: Context manager (recommended)
    with Application() as app:
        # WebSocket started, components ready
        cli.main_menu()
    # Automatic cleanup on exit
    
    # Option 2: Manual control
    app = Application()
    app.initialize()
    app.start()
    try:
        # ... your code ...
    finally:
        app.stop()
"""

import signal
import threading
import time
import atexit
from typing import Optional, List, Callable
from dataclasses import dataclass

from ..config.config import get_config, Config
from ..utils.logger import get_logger, setup_logger


@dataclass
class ApplicationStatus:
    """Application status snapshot."""
    initialized: bool = False
    running: bool = False
    websocket_connected: bool = False
    websocket_public: bool = False
    websocket_private: bool = False
    symbols: List[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        self.symbols = self.symbols or []
    
    def to_dict(self) -> dict:
        return {
            "initialized": self.initialized,
            "running": self.running,
            "websocket_connected": self.websocket_connected,
            "websocket_public": self.websocket_public,
            "websocket_private": self.websocket_private,
            "symbols": self.symbols,
            "error": self.error,
        }


class Application:
    """
    Central application lifecycle manager.
    
    Manages:
    - Component initialization in correct order
    - WebSocket auto-start
    - Graceful shutdown
    - Signal handling
    
    Components are initialized lazily to avoid circular imports.
    """
    
    _instance: Optional['Application'] = None
    _lock = threading.Lock()
    
    def __init__(self, config: Config = None):
        """
        Initialize application manager.
        
        Args:
            config: Configuration instance (uses global if None)
        """
        self.config = config or get_config()
        self.logger = get_logger()
        
        # State tracking
        self._initialized = False
        self._running = False
        self._shutting_down = False
        
        # Component references (lazy-loaded)
        self._exchange_manager = None
        self._position_manager = None
        self._risk_manager = None
        self._realtime_bootstrap = None
        self._realtime_state = None
        
        # Shutdown callbacks
        self._shutdown_callbacks: List[Callable] = []
        
        # Error tracking
        self._last_error: Optional[str] = None
        
        # Signal handler state
        self._original_sigint_handler = None
        self._suppress_shutdown = False
    
    # ==================== Context Manager ====================
    
    def __enter__(self) -> 'Application':
        """Context manager entry - initialize and start."""
        self.initialize()
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop and cleanup."""
        self.stop()
        return False  # Don't suppress exceptions
    
    # ==================== Lifecycle Methods ====================
    
    def initialize(self) -> bool:
        """
        Initialize all components in correct dependency order.
        
        Order:
        1. Logger (already initialized)
        2. Config (already loaded)
        3. ExchangeManager
        4. RiskManager
        5. PositionManager
        6. RealtimeState
        7. RealtimeBootstrap
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            self.logger.debug("Application already initialized")
            return True
        
        self.logger.info("Initializing application...")
        
        # Emit app.init.start event
        self.logger.event(
            "app.init.start",
            component="application",
            trading_mode=str(self.config.trading.mode),
            use_demo=self.config.bybit.use_demo,
        )
        
        try:
            # Validate config
            is_valid, messages = self.config.validate()
            if not is_valid:
                for msg in messages:
                    self.logger.error(msg)
                self._last_error = "Configuration validation failed"
                return False
            
            # Log warnings
            for msg in messages:
                if msg.startswith("[WARN]"):
                    self.logger.warning(msg[7:])
            
            # Initialize components (lazy imports to avoid circular deps)
            self._init_exchange_manager()
            self._init_risk_manager()
            self._init_position_manager()
            self._init_realtime_state()
            self._init_realtime_bootstrap()
            
            # Register signal handlers
            self._register_signal_handlers()
            
            # Register atexit handler
            atexit.register(self._atexit_handler)
            
            self._initialized = True
            self.logger.info("Application initialized successfully")
            
            # Emit app.init.end event
            self.logger.event(
                "app.init.end",
                component="application",
                success=True,
            )
            return True
            
        except Exception as e:
            self._last_error = str(e)
            self.logger.error(f"Application initialization failed: {e}")
            
            # Emit app.init.end event (failure)
            self.logger.event(
                "app.init.end",
                level="ERROR",
                component="application",
                success=False,
                error=str(e),
            )
            return False
    
    def start(self) -> bool:
        """
        Start the application (including WebSocket if risk manager needs it).
        
        WebSocket is only started if:
        1. Risk Manager has GlobalRiskView enabled (needs real-time data)
        2. OR auto_start is explicitly enabled in config
        
        Returns:
            True if started successfully, False otherwise
        """
        if not self._initialized:
            self.logger.error("Application not initialized - call initialize() first")
            return False
        
        if self._running:
            self.logger.debug("Application already running")
            return True
        
        self.logger.info("Starting application...")
        
        # Emit app.start.start event
        self.logger.event(
            "app.start.start",
            component="application",
        )
        
        try:
            # Check if risk manager needs websocket
            risk_needs_ws = False
            if self._risk_manager:
                risk_needs_ws = self._risk_manager.needs_websocket()
            
            # Start WebSocket if:
            # 1. Risk manager needs it (GlobalRiskView enabled)
            # 2. OR auto_start is explicitly enabled
            should_start_ws = (
                self.config.websocket.enable_websocket and 
                (risk_needs_ws or self.config.websocket.auto_start)
            )
            
            if should_start_ws:
                if risk_needs_ws:
                    self.logger.info("Starting WebSocket for Risk Manager (GlobalRiskView)")
                else:
                    self.logger.info("Starting WebSocket (auto_start enabled)")
                self._start_websocket()
            
            self._running = True
            self.logger.info("Application started")
            
            # Emit app.start.end event
            self.logger.event(
                "app.start.end",
                component="application",
                success=True,
                websocket_started=should_start_ws,
            )
            return True
            
        except Exception as e:
            self._last_error = str(e)
            self.logger.error(f"Application start failed: {e}")
            
            # Emit app.start.end event (failure)
            self.logger.event(
                "app.start.end",
                level="ERROR",
                component="application",
                success=False,
                error=str(e),
            )
            return False
    
    def stop(self) -> None:
        """
        Stop the application and clean up resources.
        
        Safe to call multiple times.
        """
        if self._shutting_down:
            return
        
        self._shutting_down = True
        self.logger.info("Stopping application...")
        
        # Emit app.stop.start event
        self.logger.event(
            "app.stop.start",
            component="application",
        )
        
        try:
            # Run shutdown callbacks
            for callback in self._shutdown_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.logger.warning(f"Shutdown callback error: {e}")
            
            # Stop WebSocket
            self._stop_websocket()
            
            self._running = False
            self.logger.info("Application stopped")
            
            # Emit app.stop.end event
            self.logger.event(
                "app.stop.end",
                component="application",
                success=True,
            )
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            
            # Emit app.stop.end event (with error)
            self.logger.event(
                "app.stop.end",
                level="WARNING",
                component="application",
                success=False,
                error=str(e),
            )
        
        finally:
            self._shutting_down = False
    
    # ==================== Component Initialization ====================
    
    def _init_exchange_manager(self):
        """Initialize ExchangeManager."""
        from .exchange_manager import ExchangeManager
        self._exchange_manager = ExchangeManager()
        self.logger.debug("ExchangeManager initialized")
    
    def _init_risk_manager(self):
        """Initialize RiskManager."""
        from .risk_manager import RiskManager
        self._risk_manager = RiskManager(
            config=self.config.risk,
            enable_global_risk=self.config.websocket.enable_global_risk_view,
        )
        self.logger.debug("RiskManager initialized")
    
    def _init_position_manager(self):
        """Initialize PositionManager."""
        from .position_manager import PositionManager
        self._position_manager = PositionManager(
            exchange_manager=self._exchange_manager,
            prefer_websocket=self.config.websocket.prefer_websocket_data,
            staleness_threshold=self.config.websocket.position_staleness,
        )
        self.logger.debug("PositionManager initialized")
    
    def _init_realtime_state(self):
        """Initialize RealtimeState."""
        from ..data.realtime_state import get_realtime_state
        self._realtime_state = get_realtime_state()
        self.logger.debug("RealtimeState initialized")
    
    def _init_realtime_bootstrap(self):
        """Initialize RealtimeBootstrap (but don't start yet)."""
        from ..data.realtime_bootstrap import get_realtime_bootstrap
        self._realtime_bootstrap = get_realtime_bootstrap()
        self.logger.debug("RealtimeBootstrap initialized")
    
    # ==================== WebSocket Management ====================
    
    def _get_symbols_to_monitor(self) -> list:
        """
        Get symbols that need WebSocket monitoring.
        
        Only includes symbols with open positions - no default symbols.
        WebSocket is for risk management, not general market watching.
        
        Symbols are dynamically added/removed as positions open/close.
        
        Returns:
            List of symbols with open positions to monitor
        """
        symbols = set()
        
        # Only get symbols with open positions (the source of truth)
        try:
            if self._exchange_manager:
                positions = self._exchange_manager.get_all_positions()
                for pos in positions:
                    # Position is a dataclass with .symbol and .size attributes
                    if pos.size != 0:  # Has open position
                        symbols.add(pos.symbol)
                        self.logger.debug(f"Found open position: {pos.symbol}")
        except Exception as e:
            self.logger.warning(f"Could not fetch positions for WebSocket: {e}")
        
        # Do NOT add default symbols - websocket is only for positions
        # Default symbols are for REST API queries, not websocket subscriptions
        
        return list(symbols)
    
    def _start_websocket(self) -> bool:
        """
        Start WebSocket connections.
        
        Returns:
            True if started successfully
        """
        if not self._realtime_bootstrap:
            self.logger.warning("RealtimeBootstrap not initialized")
            return False
        
        if self._realtime_bootstrap.is_running:
            self.logger.debug("WebSocket already running")
            return True
        
        # Get symbols to monitor: open positions + configured defaults
        symbols = self._get_symbols_to_monitor()
        if not symbols:
            self.logger.info("No positions or symbols to monitor - WebSocket not needed")
            return True  # Not an error, just nothing to monitor
        
        self.logger.info(f"Starting WebSocket for symbols: {symbols}")
        
        try:
            # Start the bootstrap
            self._realtime_bootstrap.start(
                symbols=symbols,
                include_private=True,
            )
            
            # Wait for connection (with timeout)
            timeout = self.config.websocket.startup_timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self._realtime_bootstrap.is_connected:
                    self.logger.info("WebSocket connected successfully")
                    return True
                time.sleep(0.1)
            
            # Timeout - log warning but don't fail
            self.logger.warning(
                f"WebSocket connection timeout after {timeout}s - "
                "continuing with REST fallback"
            )
            return True  # Still return True - REST fallback will work
            
        except Exception as e:
            # Suppress verbose rate limit errors
            error_msg = str(e)
            if "Too many connection attempts" in error_msg or "connection failed" in error_msg:
                # Already logged by realtime_bootstrap, just silently fall back
                pass
            else:
                self.logger.error(f"Failed to start WebSocket: {e}")
            
            if self.config.websocket.fallback_to_polling:
                self.logger.info("Falling back to REST API polling")
                return True  # Allow REST fallback
            return False
    
    def _stop_websocket(self) -> None:
        """Stop WebSocket connections."""
        if not self._realtime_bootstrap:
            return
        
        if not self._realtime_bootstrap.is_running:
            return
        
        self.logger.info("Stopping WebSocket...")
        
        try:
            # Give a timeout for graceful shutdown
            timeout = self.config.websocket.shutdown_timeout
            
            # Stop in a thread to handle timeout
            stop_thread = threading.Thread(
                target=self._realtime_bootstrap.stop,
                daemon=True,
            )
            stop_thread.start()
            stop_thread.join(timeout=timeout)
            
            if stop_thread.is_alive():
                self.logger.warning(f"WebSocket shutdown timed out after {timeout}s")
            else:
                self.logger.info("WebSocket stopped")
                
        except Exception as e:
            self.logger.warning(f"Error stopping WebSocket: {e}")
    
    def start_websocket(self) -> bool:
        """
        Public method to start WebSocket on demand.
        
        Returns:
            True if WebSocket is now running
        """
        return self._start_websocket()
    
    def stop_websocket(self) -> None:
        """Public method to stop WebSocket on demand."""
        self._stop_websocket()
    
    def get_websocket_health(self) -> dict:
        """
        Get WebSocket connection health status.
        
        Returns:
            Dict with health status information
        """
        if not self._realtime_bootstrap:
            return {
                "healthy": False,
                "error": "RealtimeBootstrap not initialized",
            }
        
        try:
            return self._realtime_bootstrap.get_health()
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }
    
    # ==================== Signal Handling ====================
    
    def _register_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        try:
            # Save original handler
            self._original_sigint_handler = signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            self.logger.debug("Signal handlers registered")
        except Exception as e:
            # Signal handling may fail in non-main threads
            self.logger.debug(f"Could not register signal handlers: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        # If shutdown is suppressed (e.g., during data operations),
        # raise KeyboardInterrupt directly so it can be caught by try/except blocks
        # This prevents the ugly "Received SIGINT - initiating shutdown" message
        if self._suppress_shutdown:
            raise KeyboardInterrupt("Operation cancelled")
        
        signal_name = signal.Signals(signum).name
        self.logger.info(f"Received {signal_name} - initiating shutdown")
        self.stop()
    
    def suppress_shutdown(self):
        """Temporarily suppress shutdown on SIGINT (for cancellable operations)."""
        self._suppress_shutdown = True
    
    def restore_shutdown(self):
        """Restore shutdown handling on SIGINT."""
        self._suppress_shutdown = False
        # Re-register handler if it was changed
        if self._original_sigint_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._signal_handler)
            except Exception:
                pass
    
    def _atexit_handler(self):
        """Handle process exit."""
        if self._running and not self._shutting_down:
            self.stop()
    
    # ==================== Callbacks ====================
    
    def on_shutdown(self, callback: Callable) -> None:
        """
        Register a callback to be called on shutdown.
        
        Args:
            callback: Function to call during shutdown
        """
        self._shutdown_callbacks.append(callback)
    
    # ==================== Status & Accessors ====================
    
    def get_status(self) -> ApplicationStatus:
        """Get current application status."""
        ws_public = False
        ws_private = False
        ws_connected = False
        
        if self._realtime_state:
            pub_status = self._realtime_state.get_public_ws_status()
            priv_status = self._realtime_state.get_private_ws_status()
            ws_public = pub_status.is_connected
            ws_private = priv_status.is_connected
            ws_connected = ws_public or ws_private
        
        return ApplicationStatus(
            initialized=self._initialized,
            running=self._running,
            websocket_connected=ws_connected,
            websocket_public=ws_public,
            websocket_private=ws_private,
            symbols=list(self.config.trading.default_symbols),
            error=self._last_error,
        )
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_websocket_connected(self) -> bool:
        if not self._realtime_state:
            return False
        return (
            self._realtime_state.is_public_ws_connected or
            self._realtime_state.is_private_ws_connected
        )
    
    @property
    def exchange_manager(self):
        """Get ExchangeManager instance."""
        return self._exchange_manager
    
    @property
    def position_manager(self):
        """Get PositionManager instance."""
        return self._position_manager
    
    @property
    def risk_manager(self):
        """Get RiskManager instance."""
        return self._risk_manager
    
    @property
    def realtime_state(self):
        """Get RealtimeState instance."""
        return self._realtime_state
    
    @property
    def realtime_bootstrap(self):
        """Get RealtimeBootstrap instance."""
        return self._realtime_bootstrap


# ==============================================================================
# Singleton Instance
# ==============================================================================

_application: Optional[Application] = None
_app_lock = threading.Lock()


def get_application(config: Config = None) -> Application:
    """
    Get or create the global Application instance.
    
    Args:
        config: Optional config (only used on first call)
    
    Returns:
        Application singleton
    """
    global _application
    with _app_lock:
        if _application is None:
            _application = Application(config)
        return _application


def reset_application():
    """Reset the global Application instance (for testing)."""
    global _application
    with _app_lock:
        if _application and _application.is_running:
            _application.stop()
        _application = None

