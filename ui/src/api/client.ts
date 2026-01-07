import axios from 'axios'

// In development, Vite proxy handles /api -> localhost:8765
// In production, same origin serves both frontend and API
const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types matching Python Pydantic models
export interface RunSummary {
  run_id: string
  play_id: string
  symbol: string
  tf_exec: string
  category: string
  window_start: string
  window_end: string
  created_at: string | null
  trades_count: number
  net_pnl_usdt: number
  net_return_pct: number
  win_rate: number
  sharpe: number
  max_drawdown_pct: number
  artifact_path: string
  has_snapshots: boolean
  description: string
}

export interface RunListResponse {
  runs: RunSummary[]
  total: number
  offset: number
  limit: number
}

export interface MetricCard {
  label: string
  value: string
  change: string | null
  trend: 'up' | 'down' | 'neutral'
  tooltip: string | null
}

export interface MetricsCategory {
  name: string
  icon: string
  cards: MetricCard[]
}

export interface MetricsSummaryResponse {
  run_id: string
  cards: MetricCard[]
  categories: MetricsCategory[]
}

// API functions
export async function fetchRuns(params?: {
  category?: string
  play_id?: string
  symbol?: string
  limit?: number
  offset?: number
}): Promise<RunListResponse> {
  const response = await api.get<RunListResponse>('/runs', { params })
  return response.data
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  const response = await api.get<RunSummary>(`/runs/${runId}`)
  return response.data
}

export async function fetchMetricsSummary(
  runId: string
): Promise<MetricsSummaryResponse> {
  const response = await api.get<MetricsSummaryResponse>(
    `/metrics/${runId}/summary`
  )
  return response.data
}

export async function checkHealth(): Promise<{ status: string }> {
  const response = await api.get<{ status: string }>('/health')
  return response.data
}

export async function deleteRun(runId: string): Promise<void> {
  await api.delete(`/runs/${runId}`)
}

// Chart data types
export interface OHLCVBar {
  time: number // Unix timestamp (seconds)
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface OHLCVResponse {
  run_id: string
  symbol: string
  tf: string
  data: OHLCVBar[]
  total_bars: number
  warmup_bars: number
  mark_price: number | null
}

// Multi-Timeframe OHLCV types
export interface TFOHLCVData {
  tf: string
  role: 'exec' | 'mtf' | 'htf'
  data: OHLCVBar[]
  total_bars: number
}

export interface TFConfig {
  exec: string
  mtf: string | null
  htf: string | null
}

export interface MTFOHLCVResponse {
  run_id: string
  symbol: string
  exec_tf: string
  tf_config: TFConfig
  timeframes: {
    exec?: TFOHLCVData
    mtf?: TFOHLCVData
    htf?: TFOHLCVData
  }
  mark_price: number | null
}

export interface VolumeBar {
  time: number
  value: number
  color: string
}

export interface VolumeResponse {
  run_id: string
  data: VolumeBar[]
}

// Trade marker types
export interface TradeMarker {
  trade_id: string
  side: 'long' | 'short'
  entry_time: number
  entry_price: number
  exit_time: number | null
  exit_price: number | null
  exit_reason: string | null
  stop_loss: number | null
  take_profit: number | null
  net_pnl: number
  is_winner: boolean
}

export interface TradeMarkersResponse {
  run_id: string
  markers: TradeMarker[]
  total_trades: number
  winners: number
  losers: number
}

// Indicator types (updated for Play-based rendering)
export interface IndicatorPoint {
  time: number
  value: number
}

export interface IndicatorSeries {
  key: string
  type: string // Indicator type (ema, rsi, macd, etc.)
  render_method: string // How to render (line, bands, macd_pane, etc.)
  params: Record<string, unknown> // Indicator params
  tf: string // Timeframe
  label: string // Display label with TF
  color: string
  data: IndicatorPoint[]
}

export interface IndicatorPane {
  type: string // RSI, MACD, etc.
  indicators: IndicatorSeries[]
  reference_lines: number[] // e.g., [30, 70] for RSI
}

// Structure types
export interface StructureData {
  key: string
  type: string // swing, fibonacci, zone, etc.
  render_method: string // pivot_markers, fib_levels, zone_boxes
  params: Record<string, unknown>
  tf: string
  label: string
  status?: string // "pending" if computation needed
  message?: string
  // Type-specific data
  pivots?: Array<{ time: number; type: 'high' | 'low'; level: number }>
  levels?: Array<{ ratio: number; price: number; start_time: number; end_time: number }>
  zones?: Array<{ upper: number; lower: number; state: string; start_time: number; end_time?: number }>
  segments?: Array<{ start_time: number; end_time: number; direction: 'up' | 'down' }>
}

export interface IndicatorsResponse {
  run_id: string
  play_id: string | null
  play_hash: string | null
  hash_verified: boolean
  overlays: IndicatorSeries[] // On price chart
  panes: IndicatorPane[] // Separate panes
  structures: StructureData[]
  error?: string
}

// Equity curve types
export interface EquityPoint {
  time: number
  equity: number
  drawdown: number
  drawdown_pct: number
}

export interface EquityStats {
  start_equity: number
  end_equity: number
  max_equity: number
  min_equity: number
  total_return_pct: number
  max_drawdown_pct: number
}

export interface EquityResponse {
  run_id: string
  data: EquityPoint[]
  stats: EquityStats | null
}

export async function fetchOHLCV(
  runId: string,
  params?: {
    limit?: number
    offset?: number
  }
): Promise<OHLCVResponse> {
  const response = await api.get<OHLCVResponse>(`/charts/${runId}/ohlcv`, {
    params,
  })
  return response.data
}

export async function fetchOHLCVMTF(
  runId: string,
  params?: {
    limit?: number
  }
): Promise<MTFOHLCVResponse> {
  const response = await api.get<MTFOHLCVResponse>(`/charts/${runId}/ohlcv-mtf`, {
    params,
  })
  return response.data
}

export async function fetchVolume(
  runId: string,
  params?: {
    limit?: number
    offset?: number
  }
): Promise<VolumeResponse> {
  const response = await api.get<VolumeResponse>(`/charts/${runId}/volume`, {
    params,
  })
  return response.data
}

export async function fetchTradeMarkers(
  runId: string
): Promise<TradeMarkersResponse> {
  const response = await api.get<TradeMarkersResponse>(
    `/trades/${runId}/markers`
  )
  return response.data
}

export async function fetchIndicators(
  runId: string,
  params?: {
    verify_hash?: boolean
  }
): Promise<IndicatorsResponse> {
  const response = await api.get<IndicatorsResponse>(
    `/charts/${runId}/indicators`,
    { params }
  )
  return response.data
}

export async function fetchEquity(runId: string): Promise<EquityResponse> {
  const response = await api.get<EquityResponse>(`/equity/${runId}`)
  return response.data
}

// Mark Price Line types (1m close prices for overlay)
export interface MarkPricePoint {
  time: number
  price: number
}

export interface MarkPriceResponse {
  run_id: string
  symbol: string
  data: MarkPricePoint[]
  total_points: number
}

export async function fetchMarkPriceLine(runId: string): Promise<MarkPriceResponse> {
  const response = await api.get<MarkPriceResponse>(`/charts/${runId}/mark-price`)
  return response.data
}

// Indicator Reference types
export interface IndicatorParam {
  name: string
  default: unknown | null
}

export interface IndicatorOutput {
  key: string
  output_type: string // FLOAT, INT, BOOL, ENUM
}

export interface IndicatorInfo {
  name: string
  is_multi_output: boolean
  input_series: string[]
  params: IndicatorParam[]
  output_keys: string[]
  outputs: IndicatorOutput[]
  primary_output: string | null
  warmup_description: string
  category: string // "momentum", "trend", "volatility", "volume", "other"
}

export interface IndicatorReferenceResponse {
  total: number
  indicators: IndicatorInfo[]
  categories: Record<string, number>
}

export interface SampleDataPoint {
  x: number
  y: number
}

export interface SampleChartData {
  indicator_name: string
  series: Record<string, SampleDataPoint[]>
  price_data: SampleDataPoint[] | null
}

export interface IndicatorSampleResponse {
  indicator: IndicatorInfo
  sample_data: SampleChartData
}

export async function fetchIndicatorReference(): Promise<IndicatorReferenceResponse> {
  const response = await api.get<IndicatorReferenceResponse>(
    '/indicators/reference'
  )
  return response.data
}

export async function fetchIndicatorSample(
  indicatorName: string
): Promise<IndicatorSampleResponse> {
  const response = await api.get<IndicatorSampleResponse>(
    `/indicators/reference/${indicatorName}/sample`
  )
  return response.data
}

export default api
