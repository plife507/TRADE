interface SkeletonProps {
  width?: number | string
  height?: number | string
  variant?: 'text' | 'rect' | 'circle' | 'chart'
  className?: string
}

/**
 * Base skeleton component for loading states.
 * Uses shimmer animation for modern UX.
 */
export function Skeleton({
  width,
  height,
  variant = 'rect',
  className = '',
}: SkeletonProps) {
  const variantClass = {
    text: 'skeleton-text',
    rect: 'skeleton-rect',
    circle: 'skeleton-circle',
    chart: 'skeleton-chart',
  }[variant]

  const style: React.CSSProperties = {
    width: typeof width === 'number' ? `${width}px` : width,
    height: typeof height === 'number' ? `${height}px` : height,
  }

  return (
    <div
      className={`skeleton ${variantClass} ${className}`}
      style={style}
      aria-hidden="true"
    />
  )
}

/**
 * Skeleton for metric cards in the dashboard.
 */
export function MetricCardSkeleton() {
  return (
    <div className="metric-card-skeleton">
      <Skeleton variant="text" width="60%" height={12} />
      <Skeleton variant="text" width="80%" height={24} className="skeleton-value" />
      <Skeleton variant="text" width="40%" height={10} />
    </div>
  )
}
