import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type HistogramData,
  type Time,
} from 'lightweight-charts'
import { fetchEquity } from '../../api/client'

interface EquityCurveProps {
  runId: string
  height?: number
}

// Data Observatory theme colors
const CHART_COLORS = {
  background: '#0a0e14',
  text: '#e8eaed',
  textDim: '#5f6368',
  grid: '#1a2029',
  border: '#2d3748',
  equity: '#42a5f5', // Cool blue for equity line
  drawdown: '#ff6b6b', // Coral red for drawdown area
}

export function EquityCurve({ runId, height = 200 }: EquityCurveProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const equitySeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const drawdownSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  // Fetch equity data
  const { data: equityData, isLoading } = useQuery({
    queryKey: ['equity', runId],
    queryFn: () => fetchEquity(runId),
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

    // Equity line series
    const equitySeries = chart.addLineSeries({
      color: CHART_COLORS.equity,
      lineWidth: 2,
      title: 'Equity',
      priceLineVisible: false,
      lastValueVisible: true,
    })

    // Drawdown histogram (negative values shown as area below zero)
    const drawdownSeries = chart.addHistogramSeries({
      color: CHART_COLORS.drawdown,
      priceFormat: {
        type: 'percent',
      },
      priceScaleId: 'drawdown',
    })

    // Configure drawdown scale
    chart.priceScale('drawdown').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })

    chartRef.current = chart
    equitySeriesRef.current = equitySeries
    drawdownSeriesRef.current = drawdownSeries

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
      equitySeriesRef.current = null
      drawdownSeriesRef.current = null
    }
  }, [height])

  // Update equity data
  useEffect(() => {
    if (!equitySeriesRef.current || !drawdownSeriesRef.current || !equityData?.data)
      return

    // Equity line
    const equityLineData: LineData[] = equityData.data.map((point) => ({
      time: point.time as Time,
      value: point.equity,
    }))
    equitySeriesRef.current.setData(equityLineData)

    // Drawdown histogram (negative values)
    const drawdownData: HistogramData[] = equityData.data.map((point) => ({
      time: point.time as Time,
      value: -Math.abs(point.drawdown_pct), // Negative to show below line
      color: `rgba(255, 107, 107, ${Math.min(0.8, Math.abs(point.drawdown_pct) / 20)})`,
    }))
    drawdownSeriesRef.current.setData(drawdownData)

    // Fit content
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [equityData])

  const stats = equityData?.stats
  const isPositive = stats ? stats.total_return_pct >= 0 : true

  return (
    <div className="panel animate-fade-in">
      {/* Chart header */}
      <div className="chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="panel-icon info">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <h2 className="chart-title">Equity Curve</h2>
          </div>
          {stats && (
            <span
              className={`header-pnl-value ${isPositive ? 'positive' : 'negative'}`}
              style={{ fontSize: 14 }}
            >
              {isPositive ? '+' : ''}
              {stats.total_return_pct.toFixed(2)}%
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12 }}>
          {stats && (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Start</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  ${stats.start_equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>End</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  ${stats.end_equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Max DD</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--danger)' }}>
                  -{stats.max_drawdown_pct.toFixed(2)}%
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Chart container */}
      <div style={{ position: 'relative' }}>
        {isLoading && (
          <div className="chart-loading">
            <div className="chart-loading-content">
              <div className="spinner info" />
              <span>Loading equity data...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} style={{ height }} />
      </div>
    </div>
  )
}
