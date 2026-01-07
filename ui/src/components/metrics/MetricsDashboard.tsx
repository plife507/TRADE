import { useQuery } from '@tanstack/react-query'
import { fetchMetricsSummary } from '../../api/client'
import { MetricCardSkeleton } from '../ui/Skeleton'
import { MetricsCategorySection } from './MetricsCategorySection'

interface MetricsDashboardProps {
  runId: string
}

function LoadingSkeleton() {
  return (
    <div className="panel animate-fade-in">
      <div className="panel-header">
        <div className="panel-title">
          <div className="skeleton skeleton-circle" style={{ width: 24, height: 24 }} />
          <div className="skeleton skeleton-text" style={{ width: 160, height: 20 }} />
        </div>
      </div>
      <div className="metrics-categories">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="metrics-category">
            <div className="metrics-category-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="skeleton skeleton-circle" style={{ width: 20, height: 20 }} />
                <div className="skeleton skeleton-text" style={{ width: 100, height: 16 }} />
              </div>
            </div>
            <div className="metrics-category-grid">
              {[...Array(4)].map((_, j) => (
                <MetricCardSkeleton key={j} />
              ))}
            </div>
          </div>
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

  // Count total metrics across all categories
  const totalMetrics = data.categories.reduce((sum, cat) => sum + cat.cards.length, 0)

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
        <span className="badge">{totalMetrics} metrics in {data.categories.length} categories</span>
      </div>

      {/* All categories - expanded by default */}
      <div className="metrics-categories">
        {data.categories.map((category) => (
          <MetricsCategorySection
            key={category.name}
            category={category}
            defaultExpanded={true}
          />
        ))}
      </div>
    </div>
  )
}
