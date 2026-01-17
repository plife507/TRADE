"""
Charts API endpoints.

Provides OHLCV and indicator data for charting.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..data.artifact_loader import find_run_path
from ..data.ohlcv_loader import (
    load_ohlcv_from_duckdb,
    load_ohlcv_for_timeframes,
    ohlcv_df_to_chart_data,
    get_run_metadata,
)
from ..data.indicator_loader import load_indicators_for_run
from ..data.play_loader import (
    PlayHashMismatchError,
    PlayNotFoundError,
    load_play_for_run,
    get_unique_timeframes,
)
from ..renderers.indicators import UnsupportedIndicatorError
from ..renderers.structures import UnsupportedStructureError

router = APIRouter(prefix="/charts", tags=["charts"])


class OHLCVBar(BaseModel):
    """Single OHLCV bar."""

    time: int  # Unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class OHLCVResponse(BaseModel):
    """Response for GET /api/charts/{run_id}/ohlcv."""

    run_id: str
    symbol: str
    tf: str
    data: list[OHLCVBar]
    total_bars: int
    warmup_bars: int = 0
    mark_price: float | None = None  # Last close price


@router.get("/{run_id}/ohlcv", response_model=OHLCVResponse)
async def get_ohlcv(
    run_id: str,
    limit: int = Query(2000, ge=100, le=10000, description="Max bars"),
    offset: int = Query(0, ge=0, description="Offset from start"),
) -> OHLCVResponse:
    """
    Get OHLCV candlestick data for a run.

    Loads data from DuckDB using run metadata for symbol/tf/window.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Get run metadata for symbol/tf info
    metadata = get_run_metadata(run_path)
    if not metadata:
        raise HTTPException(status_code=404, detail="Could not load run metadata")

    symbol = metadata.get("symbol", "")
    tf = metadata.get("tf_exec", metadata.get("tf", ""))
    warmup_bars = metadata.get("warmup_bars", 0)
    window_start = metadata.get("window_start")
    window_end = metadata.get("window_end")

    # Load from DuckDB
    df = load_ohlcv_from_duckdb(
        symbol=symbol,
        tf=tf,
        start_ts=window_start,
        end_ts=window_end,
    )

    if df is None:
        raise HTTPException(
            status_code=404, detail=f"Could not load OHLCV data for run {run_id}"
        )

    # Convert to chart data
    data = ohlcv_df_to_chart_data(df)

    # Apply pagination
    total_bars = len(data)

    # Mark price is the last close price before pagination
    mark_price = data[-1]["close"] if data else None

    data = data[offset : offset + limit]

    return OHLCVResponse(
        run_id=run_id,
        symbol=symbol,
        tf=tf,
        data=[OHLCVBar(**bar) for bar in data],
        total_bars=total_bars,
        warmup_bars=warmup_bars,
        mark_price=mark_price,
    )


class VolumeBar(BaseModel):
    """Single volume bar."""

    time: int
    value: float
    color: str  # green or red based on price direction


class VolumeResponse(BaseModel):
    """Response for GET /api/charts/{run_id}/volume."""

    run_id: str
    data: list[VolumeBar]


@router.get("/{run_id}/volume", response_model=VolumeResponse)
async def get_volume(
    run_id: str,
    limit: int = Query(2000, ge=100, le=10000),
    offset: int = Query(0, ge=0),
) -> VolumeResponse:
    """
    Get volume data for a run.

    Returns volume with color based on candle direction.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    metadata = get_run_metadata(run_path)
    if not metadata:
        raise HTTPException(status_code=404, detail="Could not load run metadata")

    symbol = metadata.get("symbol", "")
    tf = metadata.get("tf_exec", metadata.get("tf", ""))
    window_start = metadata.get("window_start")
    window_end = metadata.get("window_end")

    # Load from DuckDB
    df = load_ohlcv_from_duckdb(
        symbol=symbol,
        tf=tf,
        start_ts=window_start,
        end_ts=window_end,
    )

    if df is None:
        raise HTTPException(
            status_code=404, detail=f"Could not load volume data for run {run_id}"
        )

    # Convert to chart data
    data = ohlcv_df_to_chart_data(df)

    # Apply pagination
    data = data[offset : offset + limit]

    # Convert to volume bars with color
    volume_bars = []
    for bar in data:
        volume = bar.get("volume", 0) or 0
        # Green if close >= open, red otherwise
        color = (
            "rgba(38, 166, 154, 0.5)"
            if bar["close"] >= bar["open"]
            else "rgba(239, 83, 80, 0.5)"
        )
        volume_bars.append(
            VolumeBar(
                time=bar["time"],
                value=volume,
                color=color,
            )
        )

    return VolumeResponse(run_id=run_id, data=volume_bars)


# --- Multi-Timeframe OHLCV Models ---


class TFOHLCVData(BaseModel):
    """OHLCV data for a single timeframe."""

    tf: str
    role: str  # "exec", "med_tf", or "high_tf"
    data: list[OHLCVBar]
    total_bars: int


class TFConfig(BaseModel):
    """Timeframe configuration from Play."""

    exec: str  # Always present
    med_tf: str | None = None
    high_tf: str | None = None


class MTFOHLCVResponse(BaseModel):
    """Response for GET /api/charts/{run_id}/ohlcv-mtf."""

    run_id: str
    symbol: str
    exec_tf: str
    tf_config: TFConfig
    timeframes: dict[str, TFOHLCVData]  # role -> data
    mark_price: float | None = None


@router.get("/{run_id}/ohlcv-mtf", response_model=MTFOHLCVResponse)
async def get_ohlcv_mtf(
    run_id: str,
    limit: int = Query(2000, ge=100, le=10000, description="Max bars per TF"),
) -> MTFOHLCVResponse:
    """
    Get OHLCV data for all timeframes configured in the Play.

    Returns exec TF (always), plus MTF and HTF if configured.
    Each TF's data is loaded separately from DuckDB.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Get run metadata
    metadata = get_run_metadata(run_path)
    if not metadata:
        raise HTTPException(status_code=404, detail="Could not load run metadata")

    symbol = metadata.get("symbol", "")
    exec_tf = metadata.get("tf_exec", metadata.get("tf", ""))
    window_start = metadata.get("window_start")
    window_end = metadata.get("window_end")

    # Try to load Play to get med_tf/high_tf config
    med_tf_val: str | None = None
    high_tf_val: str | None = None

    try:
        play, _ = load_play_for_run(run_path, verify_hash=False)

        # Extract med_tf/high_tf from Play.timeframes if available
        if hasattr(play, "timeframes") and play.timeframes:
            med_tf_val = play.timeframes.get("med_tf")
            high_tf_val = play.timeframes.get("high_tf")
    except Exception as e:
        # Play not found or error - continue with exec TF only
        logger.debug(f"Could not load play for med_tf/high_tf: {e}")

    # Build TF config
    tf_config = TFConfig(exec=exec_tf, med_tf=med_tf_val, high_tf=high_tf_val)

    # Collect all unique TFs to load
    tfs_to_load = {exec_tf}
    if med_tf_val:
        tfs_to_load.add(med_tf_val)
    if high_tf_val:
        tfs_to_load.add(high_tf_val)

    # Load OHLCV for all timeframes
    tf_data = load_ohlcv_for_timeframes(
        symbol=symbol,
        timeframes=tfs_to_load,
        start_ts=window_start,
        end_ts=window_end,
    )

    # Build response with role mapping
    timeframes_response: dict[str, TFOHLCVData] = {}
    mark_price: float | None = None

    # Exec TF
    if exec_tf in tf_data:
        df = tf_data[exec_tf]
        chart_data = ohlcv_df_to_chart_data(df)
        if chart_data:
            mark_price = chart_data[-1]["close"]
        chart_data = chart_data[:limit]
        timeframes_response["exec"] = TFOHLCVData(
            tf=exec_tf,
            role="exec",
            data=[OHLCVBar(**bar) for bar in chart_data],
            total_bars=len(df),
        )

    # med_tf
    if med_tf_val and med_tf_val in tf_data:
        df = tf_data[med_tf_val]
        chart_data = ohlcv_df_to_chart_data(df)[:limit]
        timeframes_response["med_tf"] = TFOHLCVData(
            tf=med_tf_val,
            role="med_tf",
            data=[OHLCVBar(**bar) for bar in chart_data],
            total_bars=len(df),
        )

    # high_tf
    if high_tf_val and high_tf_val in tf_data:
        df = tf_data[high_tf_val]
        chart_data = ohlcv_df_to_chart_data(df)[:limit]
        timeframes_response["high_tf"] = TFOHLCVData(
            tf=high_tf_val,
            role="high_tf",
            data=[OHLCVBar(**bar) for bar in chart_data],
            total_bars=len(df),
        )

    return MTFOHLCVResponse(
        run_id=run_id,
        symbol=symbol,
        exec_tf=exec_tf,
        tf_config=tf_config,
        timeframes=timeframes_response,
        mark_price=mark_price,
    )


# --- Mark Price Line ---


class MarkPricePoint(BaseModel):
    """Single mark price point (1m close)."""

    time: int  # Unix timestamp (seconds)
    price: float


class MarkPriceResponse(BaseModel):
    """Response for GET /api/charts/{run_id}/mark-price."""

    run_id: str
    symbol: str
    data: list[MarkPricePoint]
    total_points: int


@router.get("/{run_id}/mark-price", response_model=MarkPriceResponse)
async def get_mark_price_line(run_id: str) -> MarkPriceResponse:
    """
    Get 1m close prices for mark price line overlay.

    Returns 1m close prices that can be rendered as a line
    moving through candles on any timeframe chart.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Get run metadata
    metadata = get_run_metadata(run_path)
    if not metadata:
        raise HTTPException(status_code=404, detail="Could not load run metadata")

    symbol = metadata.get("symbol", "")
    window_start = metadata.get("window_start")
    window_end = metadata.get("window_end")

    # Load 1m data from DuckDB
    df = load_ohlcv_from_duckdb(
        symbol=symbol,
        tf="1m",
        start_ts=window_start,
        end_ts=window_end,
    )

    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not load 1m data for {symbol}",
        )

    # Convert to chart format
    chart_data = ohlcv_df_to_chart_data(df)
    total_points = len(chart_data)

    # Downsample if too many points (>20000 for performance)
    if total_points > 20000:
        step = total_points // 20000 + 1
        chart_data = chart_data[::step]

    # Convert to MarkPricePoint (just time + close price)
    data = [
        MarkPricePoint(time=bar["time"], price=bar["close"])
        for bar in chart_data
    ]

    return MarkPriceResponse(
        run_id=run_id,
        symbol=symbol,
        data=data,
        total_points=total_points,
    )


# --- Indicator Models ---


class IndicatorPoint(BaseModel):
    """Single indicator data point."""

    time: int
    value: float


class IndicatorSeries(BaseModel):
    """Single indicator series."""

    key: str
    type: str
    render_method: str
    params: dict
    tf: str
    label: str
    color: str
    data: list[IndicatorPoint]


class IndicatorPane(BaseModel):
    """Pane with one or more indicators."""

    type: str  # RSI, MACD, etc.
    indicators: list[IndicatorSeries]
    reference_lines: list[float] = []


class StructureData(BaseModel):
    """Structure visualization data."""

    key: str
    type: str
    render_method: str
    params: dict
    tf: str
    label: str
    status: str | None = None
    message: str | None = None
    # For swing pivots
    pivots: list[dict] | None = None
    # For fib levels
    levels: list[dict] | None = None
    # For zones
    zones: list[dict] | None = None
    # For trend
    segments: list[dict] | None = None


class IndicatorsResponse(BaseModel):
    """Response for GET /api/charts/{run_id}/indicators."""

    run_id: str
    play_id: str | None = None
    play_hash: str | None = None
    hash_verified: bool = False
    overlays: list[IndicatorSeries]
    panes: list[IndicatorPane]
    structures: list[StructureData]
    error: str | None = None


class UnsupportedTypeResponse(BaseModel):
    """Error response for unsupported indicator/structure types."""

    error: str
    message: str
    unsupported_type: str
    supported_indicators: list[str]
    supported_structures: list[str]


@router.get("/{run_id}/indicators", response_model=IndicatorsResponse)
async def get_indicators(
    run_id: str,
    verify_hash: bool = Query(True, description="Verify Play hash matches"),
) -> IndicatorsResponse:
    """
    Get indicator data for chart overlays and panes.

    Loads indicators from Play definition and computes via FeatureFrameBuilder.
    Multi-TF indicators are forward-filled to exec bar timestamps.

    Returns overlays (EMA, SMA on price chart), panes (RSI, MACD), and structures.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    try:
        data = load_indicators_for_run(run_path, verify_hash=verify_hash)

    except PlayHashMismatchError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "PlayHashMismatch",
                "message": str(e),
                "play_id": e.play_id,
                "stored_hash": e.stored_hash,
                "computed_hash": e.computed_hash,
            },
        )

    except PlayNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "PlayNotFound",
                "message": str(e),
                "play_id": e.play_id,
                "run_id": e.run_id,
            },
        )

    except UnsupportedIndicatorError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "UnsupportedIndicator",
                "message": str(e),
                "unsupported_type": e.indicator_type,
                "supported_indicators": e.supported,
                "supported_structures": [],
            },
        )

    except UnsupportedStructureError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "UnsupportedStructure",
                "message": str(e),
                "unsupported_type": e.structure_type,
                "supported_indicators": [],
                "supported_structures": e.supported,
            },
        )

    # Check for error in response
    if data.get("error"):
        return IndicatorsResponse(
            run_id=run_id,
            play_id=data.get("play_id"),
            play_hash=data.get("play_hash"),
            hash_verified=data.get("hash_verified", False),
            overlays=[],
            panes=[],
            structures=[],
            error=data["error"],
        )

    # Convert to response models
    overlays = []
    for overlay in data.get("overlays", []):
        overlays.append(
            IndicatorSeries(
                key=overlay["key"],
                type=overlay["type"],
                render_method=overlay["render_method"],
                params=overlay["params"],
                tf=overlay["tf"],
                label=overlay["label"],
                color=overlay["color"],
                data=[IndicatorPoint(**p) for p in overlay["data"]],
            )
        )

    panes = []
    for pane in data.get("panes", []):
        indicators = []
        for ind in pane.get("indicators", []):
            indicators.append(
                IndicatorSeries(
                    key=ind["key"],
                    type=ind["type"],
                    render_method=ind["render_method"],
                    params=ind["params"],
                    tf=ind["tf"],
                    label=ind["label"],
                    color=ind["color"],
                    data=[IndicatorPoint(**p) for p in ind["data"]],
                )
            )
        panes.append(
            IndicatorPane(
                type=pane["type"],
                indicators=indicators,
                reference_lines=pane.get("reference_lines", []),
            )
        )

    structures = []
    for struct in data.get("structures", []):
        structures.append(StructureData(**struct))

    return IndicatorsResponse(
        run_id=run_id,
        play_id=data.get("play_id"),
        play_hash=data.get("play_hash"),
        hash_verified=data.get("hash_verified", False),
        overlays=overlays,
        panes=panes,
        structures=structures,
    )
