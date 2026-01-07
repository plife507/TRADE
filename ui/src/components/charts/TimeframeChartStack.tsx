import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchOHLCVMTF,
  fetchTradeMarkers,
  fetchIndicators,
  fetchMarkPriceLine,
  type IndicatorSeries,
} from '../../api/client'
import { TimeframeChart } from './TimeframeChart'
import { ChartSkeleton } from '../ui/ChartSkeleton'

interface TimeframeChartStackProps {
  runId: string
  description?: string
}

/**
 * Group indicators by their timeframe to route to correct chart.
 */
function groupIndicatorsByTF(
  overlays: IndicatorSeries[] | undefined,
  tfConfig: { exec: string; mtf: string | null; htf: string | null }
): {
  exec: IndicatorSeries[]
  mtf: IndicatorSeries[]
  htf: IndicatorSeries[]
} {
  const result = { exec: [] as IndicatorSeries[], mtf: [] as IndicatorSeries[], htf: [] as IndicatorSeries[] }

  if (!overlays) return result

  for (const overlay of overlays) {
    if (overlay.tf === tfConfig.exec) {
      result.exec.push(overlay)
    } else if (overlay.tf === tfConfig.mtf) {
      result.mtf.push(overlay)
    } else if (overlay.tf === tfConfig.htf) {
      result.htf.push(overlay)
    } else {
      // Default to exec TF
      result.exec.push(overlay)
    }
  }

  return result
}

export function TimeframeChartStack({ runId, description }: TimeframeChartStackProps) {
  // Crosshair sync state
  const [syncTime, setSyncTime] = useState<number | null>(null)

  const handleCrosshairMove = useCallback((time: number | null) => {
    setSyncTime(time)
  }, [])

  // Fetch MTF OHLCV data
  const { data: mtfData, isLoading: mtfLoading } = useQuery({
    queryKey: ['ohlcv-mtf', runId],
    queryFn: () => fetchOHLCVMTF(runId),
    enabled: !!runId,
  })

  // Fetch trade markers
  const { data: tradesData } = useQuery({
    queryKey: ['trades', runId],
    queryFn: () => fetchTradeMarkers(runId),
    enabled: !!runId,
  })

  // Fetch indicators
  const { data: indicatorsData } = useQuery({
    queryKey: ['indicators', runId],
    queryFn: () => fetchIndicators(runId),
    enabled: !!runId,
  })

  // Fetch 1m mark price line for overlay on all charts
  const { data: markPriceLineData } = useQuery({
    queryKey: ['mark-price-line', runId],
    queryFn: () => fetchMarkPriceLine(runId),
    enabled: !!runId,
  })

  const isLoading = mtfLoading

  // Group indicators by TF
  const tfConfig = mtfData?.tf_config || { exec: '', mtf: null, htf: null }
  const indicatorsByTF = groupIndicatorsByTF(indicatorsData?.overlays, tfConfig)

  if (isLoading) {
    return (
      <div className="tf-stack">
        <ChartSkeleton height={480} tfRole="exec" />
      </div>
    )
  }

  if (!mtfData) {
    return (
      <div className="tf-stack">
        <div className="panel" style={{ padding: 24, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>No chart data available</p>
        </div>
      </div>
    )
  }

  const { timeframes } = mtfData
  const hasMtf = !!timeframes.mtf
  const hasHtf = !!timeframes.htf

  return (
    <div className="tf-stack">
      {/* Exec TF - Always shown first (main chart) */}
      {timeframes.exec && (
        <TimeframeChart
          tfRole="exec"
          tfLabel={description || timeframes.exec.tf}
          tfValue={timeframes.exec.tf}
          ohlcvData={timeframes.exec.data}
          indicators={indicatorsByTF.exec}
          trades={tradesData?.markers}
          markPriceLine={markPriceLineData?.data}
          height={480}
          syncTime={syncTime}
          onCrosshairMove={handleCrosshairMove}
        />
      )}

      {/* MTF - Middle (if configured) */}
      {hasMtf && timeframes.mtf && (
        <TimeframeChart
          tfRole="mtf"
          tfLabel={timeframes.mtf.tf}
          ohlcvData={timeframes.mtf.data}
          indicators={indicatorsByTF.mtf}
          markPriceLine={markPriceLineData?.data}
          height={280}
          syncTime={syncTime}
          onCrosshairMove={handleCrosshairMove}
        />
      )}

      {/* HTF - Bottom (if configured) */}
      {hasHtf && timeframes.htf && (
        <TimeframeChart
          tfRole="htf"
          tfLabel={timeframes.htf.tf}
          ohlcvData={timeframes.htf.data}
          indicators={indicatorsByTF.htf}
          markPriceLine={markPriceLineData?.data}
          height={280}
          syncTime={syncTime}
          onCrosshairMove={handleCrosshairMove}
        />
      )}
    </div>
  )
}
