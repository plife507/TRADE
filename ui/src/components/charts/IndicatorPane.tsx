import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts'
import type { IndicatorPane as IndicatorPaneType } from '../../api/client'
import { getIndicatorRenderer } from '../../renderers'

interface IndicatorPaneProps {
  pane: IndicatorPaneType
  height?: number
}

// Data Observatory theme colors
const CHART_COLORS = {
  background: '#0a0e14',
  text: '#e8eaed',
  textDim: '#5f6368',
  grid: '#1a2029',
  border: '#2d3748',
}

// Indicator-specific scale configurations
const INDICATOR_SCALES: Record<string, { min?: number; max?: number }> = {
  RSI: { min: 0, max: 100 },
  STOCHRSI: { min: 0, max: 100 },
  MFI: { min: 0, max: 100 },
  ADX: { min: 0, max: 100 },
}

// Reference lines for indicators
const INDICATOR_LINES: Record<string, number[]> = {
  RSI: [30, 70],
  STOCHRSI: [20, 80],
  MFI: [20, 80],
  ADX: [25],
}

// Icons for different indicator types
const INDICATOR_ICONS: Record<string, JSX.Element> = {
  RSI: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  MACD: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  ),
  ADX: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
    </svg>
  ),
  DEFAULT: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
}

export function IndicatorPane({ pane, height = 120 }: IndicatorPaneProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRefs = useRef<ISeriesApi<'Line' | 'Histogram'>[]>([])

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
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
      timeScale: {
        borderColor: CHART_COLORS.border,
        timeVisible: true,
        secondsVisible: false,
        visible: true,
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
    })

    // Apply indicator-specific scale
    const scaleConfig = INDICATOR_SCALES[pane.type]
    if (scaleConfig) {
      chart.priceScale('right').applyOptions({
        autoScale: false,
        scaleMargins: {
          top: 0.05,
          bottom: 0.05,
        },
      })
    }

    chartRef.current = chart

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
      seriesRefs.current = []
    }
  }, [height, pane.type])

  // Update indicator data using renderer registry
  useEffect(() => {
    if (!chartRef.current || !pane.indicators) return

    // Remove existing series
    for (const series of seriesRefs.current) {
      try {
        chartRef.current.removeSeries(series)
      } catch {
        // Series might already be removed
      }
    }
    seriesRefs.current = []

    // Add indicator series using renderer registry
    for (const indicator of pane.indicators) {
      try {
        const renderer = getIndicatorRenderer(indicator.render_method)
        const series = renderer(chartRef.current, indicator)
        seriesRefs.current.push(...series)
      } catch (error) {
        console.error(`Failed to render indicator ${indicator.key}:`, error)
        // Fallback to simple line
        const lineSeries = chartRef.current.addLineSeries({
          color: indicator.color,
          lineWidth: 1,
          title: indicator.label,
          priceLineVisible: false,
          lastValueVisible: true,
        })
        const lineData: LineData[] = indicator.data.map((point) => ({
          time: point.time as Time,
          value: point.value,
        }))
        lineSeries.setData(lineData)
        seriesRefs.current.push(lineSeries)
      }
    }

    // Add reference lines from API response or fallback to hardcoded
    const refLines = pane.reference_lines?.length > 0
      ? pane.reference_lines
      : INDICATOR_LINES[pane.type]
    if (refLines && pane.indicators.length > 0) {
      // Use the first indicator's data to get time range
      const firstData = pane.indicators[0].data
      if (firstData.length > 0) {
        for (const level of refLines) {
          const refSeries = chartRef.current.addLineSeries({
            color: CHART_COLORS.textDim,
            lineWidth: 1,
            lineStyle: 2, // Dashed
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          })

          // Create line at constant level
          const refData: LineData[] = [
            { time: firstData[0].time as Time, value: level },
            { time: firstData[firstData.length - 1].time as Time, value: level },
          ]

          refSeries.setData(refData)
        }
      }
    }

    // Fit content
    chartRef.current.timeScale().fitContent()
  }, [pane])

  // Get labels for display
  const labels = pane.indicators.map((i) => i.label).join(', ')
  const icon = INDICATOR_ICONS[pane.type] || INDICATOR_ICONS.DEFAULT

  return (
    <div className="panel animate-fade-in">
      {/* Pane header */}
      <div className="chart-header" style={{ paddingTop: 8, paddingBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="panel-icon caution">
            {icon}
          </div>
          <h3 className="chart-title" style={{ fontSize: 14 }}>{pane.type}</h3>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{labels}</span>
        </div>
      </div>

      {/* Chart container */}
      <div ref={chartContainerRef} style={{ height }} />
    </div>
  )
}
