import { useEffect, useRef, useState, useMemo } from 'react'
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
import type { OHLCVBar, IndicatorSeries, TradeMarker, MarkPricePoint } from '../../api/client'
import { getIndicatorRenderer } from '../../renderers'
import { ChartSkeleton } from '../ui/ChartSkeleton'

interface TimeframeChartProps {
  tfRole: 'exec' | 'mtf' | 'htf'
  tfLabel: string
  tfValue?: string  // Actual timeframe value (e.g., "15m")
  ohlcvData: OHLCVBar[]
  volumeData?: OHLCVBar[]
  indicators?: IndicatorSeries[]
  trades?: TradeMarker[]
  markPriceLine?: MarkPricePoint[]  // 1m close prices for line overlay
  height?: number
  isLoading?: boolean
  onCrosshairMove?: (time: number | null) => void
  syncTime?: number | null
}

interface OHLCLegend {
  open: number
  high: number
  low: number
  close: number
  volume: number
  change: number
  changePct: number
}

const CHART_COLORS = {
  background: '#0a0e14',
  text: '#e8eaed',
  textDim: '#5f6368',
  grid: '#1a2029',
  border: '#2d3748',
  upColor: '#00d4aa',
  downColor: '#ff6b6b',
  wickUp: '#00d4aa',
  wickDown: '#ff6b6b',
  volumeUp: 'rgba(0, 212, 170, 0.3)',
  volumeDown: 'rgba(255, 107, 107, 0.3)',
  entryLong: '#00d4aa',
  entryShort: '#ff6b6b',
  exitWin: '#00d4aa',
  exitLoss: '#ff6b6b',
  markPrice: '#ffa726',
}

const TF_ROLE_COLORS = {
  exec: { border: '#00d4aa', bg: 'rgba(0, 212, 170, 0.15)' },
  mtf: { border: '#ffa726', bg: 'rgba(255, 167, 38, 0.15)' },
  htf: { border: '#42a5f5', bg: 'rgba(66, 165, 245, 0.15)' },
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (price >= 1) return price.toFixed(4)
  return price.toFixed(6)
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(2)}M`
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`
  return vol.toFixed(0)
}

export function TimeframeChart({
  tfRole,
  tfLabel,
  tfValue,
  ohlcvData,
  volumeData,
  indicators = [],
  trades = [],
  markPriceLine,
  height = tfRole === 'exec' ? 480 : 280,
  isLoading = false,
  onCrosshairMove,
  syncTime,
}: TimeframeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlaySeriesRef = useRef<ISeriesApi<'Line' | 'Histogram'>[]>([])
  const markPriceLineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const [legend, setLegend] = useState<OHLCLegend | null>(null)

  const barMap = useMemo(() => {
    const map = new Map<number, OHLCVBar>()
    for (const bar of ohlcvData) {
      map.set(bar.time, bar)
    }
    return map
  }, [ohlcvData])

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
        vertLine: { color: CHART_COLORS.textDim, width: 1, style: 2, labelVisible: true, labelBackgroundColor: CHART_COLORS.border },
        horzLine: { color: CHART_COLORS.textDim, width: 1, style: 2, labelVisible: true, labelBackgroundColor: CHART_COLORS.border },
      },
      rightPriceScale: { borderColor: CHART_COLORS.border, textColor: CHART_COLORS.textDim },
      timeScale: { borderColor: CHART_COLORS.border, timeVisible: true, secondsVisible: false },
      width: chartContainerRef.current.clientWidth,
      height: height,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: CHART_COLORS.upColor,
      downColor: CHART_COLORS.downColor,
      borderUpColor: CHART_COLORS.upColor,
      borderDownColor: CHART_COLORS.downColor,
      wickUpColor: CHART_COLORS.wickUp,
      wickDownColor: CHART_COLORS.wickDown,
    })

    const volumeSeries = chart.addHistogramSeries({
      color: CHART_COLORS.upColor,
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    chart.subscribeCrosshairMove((param) => {
      if (param.time) {
        const time = param.time as number
        const bar = barMap.get(time)
        if (bar) {
          const change = bar.close - bar.open
          const changePct = (change / bar.open) * 100
          setLegend({ open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume || 0, change, changePct })
        }
        if (onCrosshairMove) onCrosshairMove(time)
      } else {
        setLegend(null)
        if (onCrosshairMove) onCrosshairMove(null)
      }
    })

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
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
      markPriceLineSeriesRef.current = null
    }
  }, [height, onCrosshairMove, barMap])

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !ohlcvData.length) return
    const candleData: CandlestickData[] = ohlcvData.map((bar) => ({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close }))
    candleSeriesRef.current.setData(candleData)
    const volData = volumeData || ohlcvData
    const histogramData: HistogramData[] = volData.map((bar) => ({ time: bar.time as Time, value: bar.volume || 0, color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown }))
    volumeSeriesRef.current.setData(histogramData)
    if (chartRef.current) chartRef.current.timeScale().fitContent()
  }, [ohlcvData, volumeData])

  // 1m Mark Price Line overlay - shows price movement through candles
  useEffect(() => {
    if (!chartRef.current || !markPriceLine?.length) return
    
    // Remove existing series if any
    if (markPriceLineSeriesRef.current) {
      try {
        chartRef.current.removeSeries(markPriceLineSeriesRef.current)
      } catch {}
    }
    
    // Create new line series for mark price
    const lineSeries = chartRef.current.addLineSeries({
      color: CHART_COLORS.markPrice,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      title: '1m',
    })
    
    // Convert mark price points to line data
    const lineData: LineData[] = markPriceLine.map((point) => ({
      time: point.time as Time,
      value: point.price,
    }))
    
    lineSeries.setData(lineData)
    markPriceLineSeriesRef.current = lineSeries
  }, [markPriceLine])

  useEffect(() => {
    if (!candleSeriesRef.current || tfRole !== 'exec' || !trades.length || !ohlcvData.length) return
    const markers: SeriesMarker<Time>[] = []
    for (const trade of trades) {
      markers.push({ time: trade.entry_time as Time, position: trade.side === 'long' ? 'belowBar' : 'aboveBar', color: trade.side === 'long' ? CHART_COLORS.entryLong : CHART_COLORS.entryShort, shape: trade.side === 'long' ? 'arrowUp' : 'arrowDown', text: trade.side === 'long' ? 'L' : 'S' })
      if (trade.exit_time && trade.exit_price) {
        markers.push({ time: trade.exit_time as Time, position: trade.side === 'long' ? 'aboveBar' : 'belowBar', color: trade.is_winner ? CHART_COLORS.exitWin : CHART_COLORS.exitLoss, shape: 'circle', text: trade.exit_reason?.toUpperCase() || 'X' })
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number))
    candleSeriesRef.current.setMarkers(markers)
  }, [trades, tfRole, ohlcvData])

  useEffect(() => {
    if (!chartRef.current || !indicators.length) return
    for (const series of overlaySeriesRef.current) { try { chartRef.current.removeSeries(series) } catch {} }
    overlaySeriesRef.current = []
    for (const indicator of indicators) {
      try {
        const renderer = getIndicatorRenderer(indicator.render_method)
        const series = renderer(chartRef.current, indicator)
        overlaySeriesRef.current.push(...series)
      } catch (error) {
        console.error(`Failed to render indicator ${indicator.key}:`, error)
        const lineSeries = chartRef.current.addLineSeries({ color: indicator.color, lineWidth: 1, title: indicator.label, priceLineVisible: false, lastValueVisible: false })
        const lineData: LineData[] = indicator.data.map((point) => ({ time: point.time as Time, value: point.value }))
        lineSeries.setData(lineData)
        overlaySeriesRef.current.push(lineSeries)
      }
    }
  }, [indicators])

  useEffect(() => { if (!chartRef.current || syncTime === undefined) return }, [syncTime])

  const roleColors = TF_ROLE_COLORS[tfRole]
  if (isLoading) return <ChartSkeleton height={height} tfRole={tfRole} />

  const isUp = legend ? legend.close >= legend.open : true

  return (
    <div className={`panel tf-chart tf-chart-${tfRole}`}>
      <div className="chart-header" style={{ borderLeft: `3px solid ${roleColors.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {tfValue && <span className={`tf-label tf-label-${tfRole}`} style={{ background: roleColors.bg, color: roleColors.border }}>{tfValue}</span>}
          <span className="chart-description" style={{ color: 'var(--text-primary)', fontWeight: 500, fontSize: 13 }}>{tfLabel}</span>
          {legend && (
            <div className="ohlc-legend">
              <div className="ohlc-item"><span className="ohlc-label">O</span><span className={isUp ? 'positive' : 'negative'}>{formatPrice(legend.open)}</span></div>
              <div className="ohlc-item"><span className="ohlc-label">H</span><span className={isUp ? 'positive' : 'negative'}>{formatPrice(legend.high)}</span></div>
              <div className="ohlc-item"><span className="ohlc-label">L</span><span className={isUp ? 'positive' : 'negative'}>{formatPrice(legend.low)}</span></div>
              <div className="ohlc-item"><span className="ohlc-label">C</span><span className={isUp ? 'positive' : 'negative'}>{formatPrice(legend.close)}</span></div>
              <div className="ohlc-item"><span className="ohlc-label">V</span><span style={{ color: 'var(--text-secondary)' }}>{formatVolume(legend.volume)}</span></div>
              <div className={`ohlc-change ${isUp ? 'positive' : 'negative'}`}>{isUp ? '+' : ''}{legend.change.toFixed(2)} ({isUp ? '+' : ''}{legend.changePct.toFixed(2)}%)</div>
            </div>
          )}
          {!legend && indicators.length > 0 && <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{indicators.map((i) => i.label).join(', ')}</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{ohlcvData.length} bars</span>
          <span className="badge badge-signal">Non-repaint</span>
        </div>
      </div>
      <div ref={chartContainerRef} style={{ height }} />
    </div>
  )
}
