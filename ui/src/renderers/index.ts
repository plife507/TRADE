/**
 * Frontend Renderer Registry.
 *
 * Maps render_method from API to chart rendering logic.
 * Fail-loud: throws Error for unsupported types.
 */

import type { IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts'
import type { IndicatorSeries, StructureData } from '../api/client'

// Render function signature for overlays/indicators
export type OverlayRenderFn = (
  chart: IChartApi,
  indicator: IndicatorSeries
) => ISeriesApi<'Line' | 'Histogram'>[]

// Render function signature for structures
export type StructureRenderFn = (
  chart: IChartApi,
  structure: StructureData,
  candleSeries: ISeriesApi<'Candlestick'>
) => void

// Supported indicator render methods
const INDICATOR_RENDERERS: Record<string, OverlayRenderFn> = {
  line: renderLine,
  bands: renderBands,
  macd_pane: renderMacdPane,
  dual_line: renderDualLine,
  adx_pane: renderAdxPane,
  channel: renderChannel,
  supertrend: renderSupertrend,
  markers: renderMarkers,
}

// Supported structure render methods
const STRUCTURE_RENDERERS: Record<string, StructureRenderFn> = {
  pivot_markers: renderPivotMarkers,
  fib_levels: renderFibLevels,
  zone_boxes: renderZoneBoxes,
  trend_arrows: renderTrendArrows,
  line: renderStructureLine,
}

/**
 * Get indicator renderer for a render_method.
 * Fails loud with explicit error if unsupported.
 */
export function getIndicatorRenderer(renderMethod: string): OverlayRenderFn {
  const renderer = INDICATOR_RENDERERS[renderMethod]
  if (!renderer) {
    throw new Error(
      `No renderer for indicator render_method '${renderMethod}'. ` +
        `Supported: ${Object.keys(INDICATOR_RENDERERS).join(', ')}`
    )
  }
  return renderer
}

/**
 * Get structure renderer for a render_method.
 * Fails loud with explicit error if unsupported.
 */
export function getStructureRenderer(renderMethod: string): StructureRenderFn {
  const renderer = STRUCTURE_RENDERERS[renderMethod]
  if (!renderer) {
    throw new Error(
      `No renderer for structure render_method '${renderMethod}'. ` +
        `Supported: ${Object.keys(STRUCTURE_RENDERERS).join(', ')}`
    )
  }
  return renderer
}

/**
 * Get list of supported indicator render methods.
 */
export function getSupportedIndicatorMethods(): string[] {
  return Object.keys(INDICATOR_RENDERERS)
}

/**
 * Get list of supported structure render methods.
 */
export function getSupportedStructureMethods(): string[] {
  return Object.keys(STRUCTURE_RENDERERS)
}

// =============================================================================
// Indicator Render Functions
// =============================================================================

/**
 * Render a simple line series (EMA, SMA, RSI, ATR, etc.)
 */
function renderLine(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  const lineSeries = chart.addLineSeries({
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
  return [lineSeries]
}

/**
 * Render Bollinger Bands (upper, middle, lower with fill).
 * Expects indicator.data to have { time, value } for the middle line,
 * and additional data in params for upper/lower.
 */
function renderBands(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // For bands, we expect the data to be the middle line
  // Upper/lower would come from related indicators with same key prefix
  // For now, render as a single line (full bands implementation needs multi-output)
  const lineSeries = chart.addLineSeries({
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
  return [lineSeries]
}

/**
 * Render MACD pane (histogram + signal + macd lines).
 * For pane indicators, returns series for separate pane chart.
 */
function renderMacdPane(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line' | 'Histogram'>[] {
  // MACD is typically multi-output - for single output, render as line
  const lineSeries = chart.addLineSeries({
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
  return [lineSeries]
}

/**
 * Render dual-line indicator (Stoch %K/%D, StochRSI).
 */
function renderDualLine(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // For dual-line, render the single series we have
  // Full implementation needs multi-output support
  return renderLine(chart, indicator)
}

/**
 * Render ADX pane (ADX + DI+/DI- lines).
 */
function renderAdxPane(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // ADX is multi-output - for single output, render as line
  return renderLine(chart, indicator)
}

/**
 * Render channel indicator (Keltner, Donchian).
 */
function renderChannel(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // Channel is multi-output - for single output, render as line
  return renderLine(chart, indicator)
}

/**
 * Render Supertrend (color changes on direction).
 */
function renderSupertrend(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // Supertrend with direction-based coloring
  // Full implementation needs color segments
  return renderLine(chart, indicator)
}

/**
 * Render marker-style indicator (PSAR dots).
 */
function renderMarkers(
  chart: IChartApi,
  indicator: IndicatorSeries
): ISeriesApi<'Line'>[] {
  // PSAR as line with markers for now
  const lineSeries = chart.addLineSeries({
    color: indicator.color,
    lineWidth: 1,
    lineStyle: 3, // Dotted
    title: indicator.label,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  const lineData: LineData[] = indicator.data.map((point) => ({
    time: point.time as Time,
    value: point.value,
  }))

  lineSeries.setData(lineData)
  return [lineSeries]
}

// =============================================================================
// Structure Render Functions
// =============================================================================

/**
 * Render swing pivot markers (triangle markers at pivot points).
 */
function renderPivotMarkers(
  _chart: IChartApi,
  structure: StructureData,
  candleSeries: ISeriesApi<'Candlestick'>
): void {
  if (!structure.pivots || structure.pivots.length === 0) return

  // Use series markers for pivots
  const existingMarkers = candleSeries.markers() || []
  const pivotMarkers = structure.pivots.map((pivot) => ({
    time: pivot.time as Time,
    position: pivot.type === 'high' ? ('aboveBar' as const) : ('belowBar' as const),
    color: pivot.type === 'high' ? '#F44336' : '#4CAF50',
    shape: pivot.type === 'high' ? ('arrowDown' as const) : ('arrowUp' as const),
    text: pivot.type === 'high' ? 'H' : 'L',
  }))

  // Merge with existing markers, sorted by time
  const allMarkers = [...existingMarkers, ...pivotMarkers].sort(
    (a, b) => (a.time as number) - (b.time as number)
  )
  candleSeries.setMarkers(allMarkers)
}

/**
 * Render Fibonacci levels (horizontal lines with labels).
 */
function renderFibLevels(
  chart: IChartApi,
  structure: StructureData,
  _candleSeries: ISeriesApi<'Candlestick'>
): void {
  if (!structure.levels || structure.levels.length === 0) return

  // Each fib level as a horizontal line
  for (const level of structure.levels) {
    const lineSeries = chart.addLineSeries({
      color: '#FF9800',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      title: `${(level.ratio * 100).toFixed(1)}%`,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    const lineData: LineData[] = [
      { time: level.start_time as Time, value: level.price },
      { time: level.end_time as Time, value: level.price },
    ]
    lineSeries.setData(lineData)
  }
}

/**
 * Render zone boxes (filled rectangles for S/R zones).
 */
function renderZoneBoxes(
  chart: IChartApi,
  structure: StructureData,
  _candleSeries: ISeriesApi<'Candlestick'>
): void {
  if (!structure.zones || structure.zones.length === 0) return

  // Zone boxes as area between two lines (approximation)
  // Full implementation would use custom series or primitives
  for (const zone of structure.zones) {
    const color =
      zone.state === 'supply'
        ? 'rgba(244, 67, 54, 0.2)'
        : zone.state === 'demand'
          ? 'rgba(76, 175, 80, 0.2)'
          : 'rgba(158, 158, 158, 0.2)'

    // Upper line
    const upperSeries = chart.addLineSeries({
      color: color,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    // Lower line
    const lowerSeries = chart.addLineSeries({
      color: color,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    const endTime = zone.end_time || Date.now() / 1000

    upperSeries.setData([
      { time: zone.start_time as Time, value: zone.upper },
      { time: endTime as Time, value: zone.upper },
    ])

    lowerSeries.setData([
      { time: zone.start_time as Time, value: zone.lower },
      { time: endTime as Time, value: zone.lower },
    ])
  }
}

/**
 * Render trend arrows (direction arrows or background coloring).
 */
function renderTrendArrows(
  _chart: IChartApi,
  structure: StructureData,
  candleSeries: ISeriesApi<'Candlestick'>
): void {
  if (!structure.segments || structure.segments.length === 0) return

  // Trend segments as markers at segment boundaries
  const markers = structure.segments.flatMap((segment) => [
    {
      time: segment.start_time as Time,
      position: segment.direction === 'up' ? ('belowBar' as const) : ('aboveBar' as const),
      color: segment.direction === 'up' ? '#4CAF50' : '#F44336',
      shape: segment.direction === 'up' ? ('arrowUp' as const) : ('arrowDown' as const),
      text: segment.direction === 'up' ? 'UP' : 'DN',
    },
  ])

  // Merge with existing markers
  const existingMarkers = candleSeries.markers() || []
  const allMarkers = [...existingMarkers, ...markers].sort(
    (a, b) => (a.time as number) - (b.time as number)
  )
  candleSeries.setMarkers(allMarkers)
}

/**
 * Render structure as simple line (rolling_window).
 */
function renderStructureLine(
  _chart: IChartApi,
  structure: StructureData,
  _candleSeries: ISeriesApi<'Candlestick'>
): void {
  // Rolling window as line - but we don't have data array in structure
  // This would need the structure to include computed values
  // For now, this is a placeholder
  console.warn(`Structure ${structure.key} uses 'line' render but has no data array`)
}
