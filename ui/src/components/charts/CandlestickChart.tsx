import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
  type SeriesMarker,
} from 'lightweight-charts'
import {
  fetchOHLCV,
  fetchVolume,
  fetchTradeMarkers,
  fetchIndicators,
} from '../../api/client'
import {
  getIndicatorRenderer,
  getStructureRenderer,
} from '../../renderers'

interface CandlestickChartProps {
  runId: string
  height?: number
}

// Data Observatory theme colors
const CHART_COLORS = {
  background: '#0a0e14',
  text: '#e8eaed',
  textDim: '#5f6368',
  textMuted: '#3c4043',
  grid: '#1a2029',
  border: '#2d3748',
  // Signal colors - teal/cyan palette
  upColor: '#00d4aa',
  downColor: '#ff6b6b',
  wickUp: '#00d4aa',
  wickDown: '#ff6b6b',
  // Trade marker colors
  entryLong: '#00d4aa',
  entryShort: '#ff6b6b',
  exitWin: '#00d4aa',
  exitLoss: '#ff6b6b',
  // Volume
  volumeUp: 'rgba(0, 212, 170, 0.3)',
  volumeDown: 'rgba(255, 107, 107, 0.3)',
}

export function CandlestickChart({
  runId,
  height = 400,
}: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlaySeriesRef = useRef<ISeriesApi<'Line' | 'Histogram'>[]>([])

  // Fetch OHLCV data
  const { data: ohlcvData, isLoading: ohlcvLoading } = useQuery({
    queryKey: ['ohlcv', runId],
    queryFn: () => fetchOHLCV(runId),
    enabled: !!runId,
  })

  // Fetch volume data
  const { data: volumeData, isLoading: volumeLoading } = useQuery({
    queryKey: ['volume', runId],
    queryFn: () => fetchVolume(runId),
    enabled: !!runId,
  })

  // Fetch trade markers
  const { data: tradesData, isLoading: tradesLoading } = useQuery({
    queryKey: ['trades', runId],
    queryFn: () => fetchTradeMarkers(runId),
    enabled: !!runId,
  })

  // Fetch indicators
  const { data: indicatorsData, isLoading: indicatorsLoading } = useQuery({
    queryKey: ['indicators', runId],
    queryFn: () => fetchIndicators(runId),
    enabled: !!runId,
  })

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.text,
        fontFamily: '"JetBrains Mono", "SF Mono", monospace',
      },
      grid: {
        vertLines: { color: CHART_COLORS.grid, style: 1 },
        horzLines: { color: CHART_COLORS.grid, style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: CHART_COLORS.textDim,
          width: 1,
          style: 2,
          labelBackgroundColor: CHART_COLORS.border,
        },
        horzLine: {
          color: CHART_COLORS.textDim,
          width: 1,
          style: 2,
          labelBackgroundColor: CHART_COLORS.border,
        },
      },
      rightPriceScale: {
        borderColor: CHART_COLORS.border,
        textColor: CHART_COLORS.textDim,
      },
      timeScale: {
        borderColor: CHART_COLORS.border,
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
    })

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: CHART_COLORS.upColor,
      downColor: CHART_COLORS.downColor,
      borderUpColor: CHART_COLORS.upColor,
      borderDownColor: CHART_COLORS.downColor,
      wickUpColor: CHART_COLORS.wickUp,
      wickDownColor: CHART_COLORS.wickDown,
    })

    // Volume series (histogram at bottom)
    const volumeSeries = chart.addHistogramSeries({
      color: CHART_COLORS.upColor,
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })

    // Configure volume scale
    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      overlaySeriesRef.current = []
    }
  }, [height])

  // Update candlestick data
  useEffect(() => {
    if (!candleSeriesRef.current || !ohlcvData?.data) return

    const candleData: CandlestickData[] = ohlcvData.data.map((bar) => ({
      time: bar.time as Time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }))

    candleSeriesRef.current.setData(candleData)

    // Fit content after data loads
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [ohlcvData])

  // Update volume data
  useEffect(() => {
    if (!volumeSeriesRef.current || !volumeData?.data) return

    const histogramData: HistogramData[] = volumeData.data.map((bar) => ({
      time: bar.time as Time,
      value: bar.value,
      color: bar.color.includes('26a69a') ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
    }))

    volumeSeriesRef.current.setData(histogramData)
  }, [volumeData])

  // Update trade markers
  useEffect(() => {
    if (!candleSeriesRef.current || !tradesData?.markers) return

    const markers: SeriesMarker<Time>[] = []

    for (const trade of tradesData.markers) {
      // Entry marker
      markers.push({
        time: trade.entry_time as Time,
        position: trade.side === 'long' ? 'belowBar' : 'aboveBar',
        color:
          trade.side === 'long'
            ? CHART_COLORS.entryLong
            : CHART_COLORS.entryShort,
        shape: trade.side === 'long' ? 'arrowUp' : 'arrowDown',
        text: trade.side === 'long' ? 'L' : 'S',
      })

      // Exit marker (if trade is closed)
      if (trade.exit_time && trade.exit_price) {
        markers.push({
          time: trade.exit_time as Time,
          position: trade.side === 'long' ? 'aboveBar' : 'belowBar',
          color: trade.is_winner ? CHART_COLORS.exitWin : CHART_COLORS.exitLoss,
          shape: 'circle',
          text: trade.exit_reason?.toUpperCase() || 'X',
        })
      }
    }

    // Sort markers by time (required by Lightweight Charts)
    markers.sort((a, b) => (a.time as number) - (b.time as number))

    candleSeriesRef.current.setMarkers(markers)
  }, [tradesData])

  // Update indicator overlays using renderer registry
  useEffect(() => {
    if (!chartRef.current || !indicatorsData?.overlays) return

    // Remove existing overlay series
    for (const series of overlaySeriesRef.current) {
      try {
        chartRef.current.removeSeries(series)
      } catch {
        // Series might already be removed
      }
    }
    overlaySeriesRef.current = []

    // Add new overlay series using renderer registry
    for (const overlay of indicatorsData.overlays) {
      try {
        const renderer = getIndicatorRenderer(overlay.render_method)
        const series = renderer(chartRef.current, overlay)
        overlaySeriesRef.current.push(...series)
      } catch (error) {
        console.error(`Failed to render overlay ${overlay.key}:`, error)
        // Fallback to simple line for unsupported types
        const lineSeries = chartRef.current.addLineSeries({
          color: overlay.color,
          lineWidth: 1,
          title: overlay.label,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const lineData: LineData[] = overlay.data.map((point) => ({
          time: point.time as Time,
          value: point.value,
        }))
        lineSeries.setData(lineData)
        overlaySeriesRef.current.push(lineSeries)
      }
    }

    // Render structures
    if (candleSeriesRef.current && indicatorsData.structures) {
      for (const structure of indicatorsData.structures) {
        // Skip pending structures (not yet computed)
        if (structure.status === 'pending') {
          console.info(`Structure ${structure.key}: ${structure.message}`)
          continue
        }
        try {
          const renderer = getStructureRenderer(structure.render_method)
          renderer(chartRef.current, structure, candleSeriesRef.current)
        } catch (error) {
          console.error(`Failed to render structure ${structure.key}:`, error)
        }
      }
    }
  }, [indicatorsData])

  const isLoading =
    ohlcvLoading || volumeLoading || tradesLoading || indicatorsLoading

  // Get indicator labels for display
  const overlayLabels = indicatorsData?.overlays?.map((o) => o.label) || []

  return (
    <div className="panel animate-fade-in">
      {/* Chart header */}
      <div className="chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="panel-icon signal">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
              </svg>
            </div>
            <h2 className="chart-title">Price Chart</h2>
          </div>
          {ohlcvData && (
            <span className="badge">
              {ohlcvData.symbol} / {ohlcvData.tf}
            </span>
          )}
          {overlayLabels.length > 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {overlayLabels.join(', ')}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {tradesData && tradesData.total_trades > 0 && (
            <span className="badge">
              {tradesData.total_trades} trades ({tradesData.winners}W / {tradesData.losers}L)
            </span>
          )}
          {indicatorsData?.play_id && (
            <span className="badge">{indicatorsData.play_id}</span>
          )}
          {indicatorsData?.hash_verified && (
            <span className="badge badge-signal">
              <svg style={{ width: 12, height: 12 }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Verified
            </span>
          )}
          <span className="badge badge-signal">Non-repaint</span>
        </div>
      </div>

      {/* Chart container */}
      <div style={{ position: 'relative' }}>
        {isLoading && (
          <div className="chart-loading">
            <div className="chart-loading-content">
              <div className="spinner" />
              <span>Loading chart data...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} style={{ height }} />
      </div>

      {/* Chart footer with info */}
      {ohlcvData && (
        <div className="chart-footer">
          <span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{ohlcvData.total_bars}</span> bars
          </span>
          {ohlcvData.warmup_bars > 0 && (
            <span>
              Warmup: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{ohlcvData.warmup_bars}</span>
            </span>
          )}
          <span className="chart-footer-separator">|</span>
          <span className="chart-footer-indicator">
            <span className="dot" />
            Closed candles only
          </span>
        </div>
      )}
    </div>
  )
}
