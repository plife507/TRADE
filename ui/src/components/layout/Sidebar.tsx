import type { RunSummary } from '../../api/client'

type AppView = 'backtests' | 'indicators'

interface SidebarProps {
  runs: RunSummary[]
  selectedRunId: string | null
  onSelectRun: (runId: string) => void
  onDeleteRun: (runId: string) => void
  isLoading: boolean
  currentView: AppView
  onViewChange: (view: AppView) => void
}

function Logo() {
  return (
    <div className="sidebar-logo">
      <div className="logo-mark">
        <div className="logo-glow" />
        <div className="logo-icon">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
          </svg>
        </div>
      </div>
      <div className="logo-text">
        <h1>TRADE</h1>
        <p>Backtest Viz</p>
      </div>
    </div>
  )
}

function formatRelativeDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return date.toLocaleDateString('en-US', { weekday: 'short' })
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function RunCard({
  run,
  isSelected,
  onClick,
  onDelete,
  index,
}: {
  run: RunSummary
  isSelected: boolean
  onClick: () => void
  onDelete: () => void
  index: number
}) {
  const isPositive = run.net_pnl_usdt >= 0
  const staggerClass = `stagger-${Math.min(index + 1, 8)}`

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`Delete backtest ${run.play_id}?`)) {
      onDelete()
    }
  }

  return (
    <div
      onClick={onClick}
      className={`run-item animate-fade-in ${staggerClass} ${isSelected ? 'selected' : ''}`}
      style={{ animationFillMode: 'backwards' }}
    >
      <div className="run-item-row">
        <span className="run-item-name">{run.play_id}</span>
        <div className="run-item-actions">
          <span className={`run-item-pnl ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '+' : ''}{run.net_pnl_usdt.toFixed(0)}
          </span>
          <button className="run-item-delete" onClick={handleDelete} title="Delete run">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" />
            </svg>
          </button>
        </div>
      </div>
      <div className="run-item-meta">
        {run.symbol} · {run.tf_exec} · {formatRelativeDate(run.created_at)}
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="skeleton-runs">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="skeleton skeleton-run"
          style={{ animationDelay: `${i * 0.1}s` }}
        />
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
      </div>
      <h3>No backtest runs found</h3>
      <p>Run a backtest to see results here</p>
    </div>
  )
}

function NavTabs({
  currentView,
  onViewChange,
}: {
  currentView: AppView
  onViewChange: (view: AppView) => void
}) {
  return (
    <div className="sidebar-nav">
      <div className="sidebar-nav-tabs">
        <button
          className={`sidebar-nav-tab ${currentView === 'backtests' ? 'active' : ''}`}
          onClick={() => onViewChange('backtests')}
        >
          Backtests
        </button>
        <button
          className={`sidebar-nav-tab ${currentView === 'indicators' ? 'active' : ''}`}
          onClick={() => onViewChange('indicators')}
        >
          Indicators
        </button>
      </div>
    </div>
  )
}

export function Sidebar({
  runs,
  selectedRunId,
  onSelectRun,
  onDeleteRun,
  isLoading,
  currentView,
  onViewChange,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Logo />
      </div>

      <NavTabs currentView={currentView} onViewChange={onViewChange} />

      {currentView === 'backtests' && (
        <div className="sidebar-runs">
          <div className="runs-header">
            <h2 className="runs-title">Recent Runs</h2>
            <span className="badge">{runs.length}</span>
          </div>

          {isLoading ? (
            <LoadingSkeleton />
          ) : runs.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="runs-list">
              {runs.map((run, index) => (
                <RunCard
                  key={run.run_id}
                  run={run}
                  isSelected={selectedRunId === run.run_id}
                  onClick={() => onSelectRun(run.run_id)}
                  onDelete={() => onDeleteRun(run.run_id)}
                  index={index}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {currentView === 'indicators' && (
        <div className="sidebar-runs">
          <div className="runs-header">
            <h2 className="runs-title">Reference</h2>
          </div>
          <div className="empty-state">
            <div className="empty-state-icon">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
              </svg>
            </div>
            <h3>42 Indicators</h3>
            <p>Browse the full indicator registry</p>
          </div>
        </div>
      )}

      <div className="sidebar-footer">
        <div className="footer-badges">
          <div className="footer-badge">
            <span className="dot signal" />
            <span>Non-repaint</span>
          </div>
          <div className="footer-badge">
            <span className="dot info" />
            <span>Closed only</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
