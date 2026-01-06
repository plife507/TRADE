"""
FastAPI server for backtest visualization.

Usage:
    python trade_cli.py viz serve --port 8765
"""

import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="TRADE Backtest Visualization",
        description="TradingView-style backtest result visualization",
        version="1.0.0",
    )

    # CORS middleware for React dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative dev port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    from .api.runs import router as runs_router
    from .api.metrics import router as metrics_router
    from .api.charts import router as charts_router
    from .api.trades import router as trades_router
    from .api.equity import router as equity_router
    from .api.indicators import router as indicators_router

    app.include_router(runs_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(charts_router, prefix="/api")
    app.include_router(trades_router, prefix="/api")
    app.include_router(equity_router, prefix="/api")
    app.include_router(indicators_router, prefix="/api")

    # Health check endpoint
    @app.get("/api/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "ok", "service": "trade-viz"}

    # Serve React build if available
    ui_build_path = Path("ui/dist")
    if ui_build_path.exists():
        # Serve static files
        app.mount("/assets", StaticFiles(directory=ui_build_path / "assets"), name="assets")

        @app.get("/")
        async def serve_index() -> FileResponse:
            """Serve React app index.html."""
            return FileResponse(ui_build_path / "index.html")

        # Catch-all for client-side routing
        @app.get("/{path:path}")
        async def serve_spa(path: str) -> FileResponse:
            """Serve React app for all routes (SPA routing)."""
            file_path = ui_build_path / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(ui_build_path / "index.html")
    else:
        # No build available - show development message
        @app.get("/")
        async def dev_message() -> HTMLResponse:
            """Show development message when UI is not built."""
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>TRADE Viz - Development</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background: #131722;
                        color: #d1d4dc;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .container {
                        text-align: center;
                        max-width: 600px;
                        padding: 40px;
                    }
                    h1 { color: #26a69a; }
                    code {
                        background: #363c4e;
                        padding: 2px 8px;
                        border-radius: 4px;
                    }
                    .endpoint {
                        background: #1e222d;
                        padding: 15px;
                        border-radius: 8px;
                        margin: 10px 0;
                        text-align: left;
                    }
                    .endpoint a {
                        color: #26a69a;
                        text-decoration: none;
                    }
                    .endpoint a:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>TRADE Backtest Visualization</h1>
                    <p>API server is running. UI not built yet.</p>
                    <p>To build the UI:</p>
                    <code>cd ui && npm install && npm run build</code>

                    <h3>Available API Endpoints:</h3>
                    <div class="endpoint">
                        <a href="/api/health">/api/health</a> - Health check
                    </div>
                    <div class="endpoint">
                        <a href="/api/runs">/api/runs</a> - List backtest runs
                    </div>
                    <div class="endpoint">
                        <a href="/docs">/docs</a> - OpenAPI documentation
                    </div>

                    <p style="margin-top: 30px; color: #787b86;">
                        For development, run the React dev server:<br>
                        <code>cd ui && npm run dev</code>
                    </p>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html)

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    reload: bool = False,
) -> None:
    """
    Run the visualization server.

    Args:
        host: Host to bind to
        port: Port to listen on
        open_browser: Open browser after starting
        reload: Enable auto-reload for development
    """
    import uvicorn

    if open_browser:
        # Open browser after a short delay
        import threading
        import time

        def open_after_delay():
            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=open_after_delay, daemon=True).start()

    print(f"\n  TRADE Backtest Visualization")
    print(f"  Server: http://{host}:{port}")
    print(f"  API Docs: http://{host}:{port}/docs")
    print(f"  Press Ctrl+C to stop\n")

    uvicorn.run(
        "src.viz.server:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
