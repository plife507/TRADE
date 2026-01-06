import { useQuery } from '@tanstack/react-query'
import { fetchMetricsSummary, type MetricCard } from '../../api/client'

interface MetricsDashboardProps {
  runId: string
}

// Icon components for different metric types
const Icons = {
  profit: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  percentage: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  ),
  trades: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
    </svg>
  ),
  risk: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  ratio: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  time: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  default: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
}

function getIconForLabel(label: string) {
  const lower = label.toLowerCase()
  if (lower.includes('pnl') || lower.includes('profit')) return Icons.profit
  if (lower.includes('%') || lower.includes('rate') || lower.includes('return')) return Icons.percentage
  if (lower.includes('trade')) return Icons.trades
  if (lower.includes('drawdown') || lower.includes('risk')) return Icons.risk
  if (lower.includes('ratio') || lower.includes('sharpe') || lower.includes('sortino')) return Icons.ratio
  if (lower.includes('time') || lower.includes('duration')) return Icons.time
  return Icons.default
}

function StatCard({ card, index }: { card: MetricCard; index: number }) {
  const valueClass =
    card.trend === 'up'
      ? 'positive'
      : card.trend === 'down'
        ? 'negative'
        : 'neutral'

  const icon = getIconForLabel(card.label)
  const staggerClass = `stagger-${Math.min(index + 1, 8)}`

  return (
    <div
      className={`stat-card animate-scale-in ${staggerClass}`}
      style={{ animationFillMode: 'backwards' }}
      title={card.tooltip ?? undefined}
    >
      <div className="stat-card-header">
        <div className="stat-card-icon">{icon}</div>
        <span className="stat-card-label">{card.label}</span>
      </div>

      <div className={`stat-card-value ${valueClass}`}>
        {card.value}
      </div>

      {card.change && (
        <div className={`stat-card-change ${valueClass}`}>
          {card.trend === 'up' && (
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
            </svg>
          )}
          {card.trend === 'down' && (
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          )}
          <span>{card.change}</span>
        </div>
      )}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="panel animate-fade-in">
      <div className="panel-header">
        <div className="panel-title">
          <div className="skeleton" style={{ width: 24, height: 24, borderRadius: 6 }} />
          <div className="skeleton" style={{ width: 96, height: 20, borderRadius: 6 }} />
        </div>
      </div>
      <div className="metrics-grid">
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="skeleton"
            style={{ height: 96, borderRadius: 12, animationDelay: `${i * 0.05}s` }}
          />
        ))}
      </div>
    </div>
  )
}

function ErrorState() {
  return (
    <div className="panel animate-fade-in" style={{ padding: 24, textAlign: 'center' }}>
      <div className="panel-icon" style={{
        display: 'inline-flex',
        width: 48,
        height: 48,
        marginBottom: 16,
        background: 'var(--danger-subtle)',
        color: 'var(--danger)',
        borderRadius: 12
      }}>
        <svg style={{ width: 24, height: 24, margin: 'auto' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Failed to load metrics</p>
      <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
        Check if the backtest has completed successfully
      </p>
    </div>
  )
}

export function MetricsDashboard({ runId }: MetricsDashboardProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['metrics', runId],
    queryFn: () => fetchMetricsSummary(runId),
    enabled: !!runId,
  })

  if (isLoading) {
    return <LoadingSkeleton />
  }

  if (error || !data) {
    return <ErrorState />
  }

  return (
    <div className="panel animate-fade-in">
      <div className="panel-header">
        <div className="panel-title">
          <div className="panel-icon signal">
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h2>Performance Metrics</h2>
        </div>
        <span className="badge">{data.cards.length} metrics</span>
      </div>

      <div className="metrics-grid">
        {data.cards.map((card, index) => (
          <StatCard key={index} card={card} index={index} />
        ))}
      </div>
    </div>
  )
}
