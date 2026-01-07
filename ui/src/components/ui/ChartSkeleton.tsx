import { Skeleton } from './Skeleton'

interface ChartSkeletonProps {
  height?: number
  showHeader?: boolean
  showFooter?: boolean
  tfRole?: 'exec' | 'mtf' | 'htf'
}

/**
 * Skeleton for chart panels during loading.
 * Mimics the structure of actual charts for smooth transitions.
 */
export function ChartSkeleton({
  height = 380,
  showHeader = true,
  showFooter = true,
  tfRole,
}: ChartSkeletonProps) {
  const tfClass = tfRole ? `tf-chart-${tfRole}` : ''

  return (
    <div className={`panel chart-skeleton ${tfClass}`}>
      {showHeader && (
        <div className="chart-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Skeleton variant="circle" width={24} height={24} />
            <Skeleton variant="text" width={100} height={16} />
            <Skeleton variant="rect" width={80} height={20} className="skeleton-badge" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Skeleton variant="rect" width={60} height={20} className="skeleton-badge" />
            <Skeleton variant="rect" width={70} height={20} className="skeleton-badge" />
          </div>
        </div>
      )}

      <div className="chart-skeleton-body" style={{ height }}>
        {/* Simulated candlestick pattern */}
        <div className="chart-skeleton-candles">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="skeleton-candle"
              style={{
                height: `${30 + Math.random() * 40}%`,
                animationDelay: `${i * 0.05}s`,
              }}
            />
          ))}
        </div>

        {/* Simulated volume bars at bottom */}
        <div className="chart-skeleton-volume">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="skeleton-volume-bar"
              style={{
                height: `${10 + Math.random() * 20}%`,
                animationDelay: `${i * 0.05}s`,
              }}
            />
          ))}
        </div>
      </div>

      {showFooter && (
        <div className="chart-footer">
          <Skeleton variant="text" width={60} height={12} />
          <Skeleton variant="text" width={80} height={12} />
          <span className="chart-footer-separator">|</span>
          <Skeleton variant="text" width={100} height={12} />
        </div>
      )}
    </div>
  )
}

/**
 * Skeleton for indicator panes (RSI, MACD, etc.)
 */
export function IndicatorPaneSkeleton({ height = 120 }: { height?: number }) {
  return (
    <div className="panel chart-skeleton">
      <div className="chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Skeleton variant="circle" width={20} height={20} />
          <Skeleton variant="text" width={60} height={14} />
        </div>
      </div>
      <div className="chart-skeleton-body indicator-pane-skeleton" style={{ height }}>
        <div className="skeleton-indicator-line" />
        <div className="skeleton-reference-line" style={{ top: '30%' }} />
        <div className="skeleton-reference-line" style={{ top: '70%' }} />
      </div>
    </div>
  )
}

/**
 * Skeleton for equity curve
 */
export function EquityCurveSkeleton({ height = 200 }: { height?: number }) {
  return (
    <div className="panel chart-skeleton">
      <div className="chart-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Skeleton variant="circle" width={20} height={20} />
          <Skeleton variant="text" width={80} height={14} />
        </div>
      </div>
      <div className="chart-skeleton-body equity-skeleton" style={{ height }}>
        <div className="skeleton-equity-line" />
        <div className="skeleton-drawdown-area" />
      </div>
    </div>
  )
}
