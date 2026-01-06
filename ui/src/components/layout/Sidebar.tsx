import type { RunSummary } from '../../api/client'

type AppView = 'backtests' | 'indicators'

interface SidebarProps {
  runs: RunSummary[]
  selectedRunId: string | null
  onSelectRun: (runId: string) => void
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

function RunCard({
  run,
  isSelected,
  onClick,
  index,
}: {
  run: RunSummary
  isSelected: boolean
  onClick: () => void
  index: number
}) {
  const isPositive = run.net_pnl_usdt >= 0
  const staggerClass = `stagger-${Math.min(index + 1, 8)}`

  return (
    <button
      onClick={onClick}
      className={`run-card animate-fade-in ${staggerClass} ${isSelected ? 'selected' : ''}`}
      style={{ animationFillMode: 'backwards' }}
    >
      <div className="run-card-header">
        <span className="run-card-name">{run.play_id}</span>
        <span className={`run-card-pnl ${isPositive ? 'positive' : 'negative'}`}>
          {isPositive ? '+' : ''}
          {run.net_pnl_usdt.toFixed(0)}
        </span>
      </div>

      <div className="run-card-meta">
        <span className="run-card-symbol">{run.symbol}</span>
        <span className="run-card-separator">/</span>
        <span className="run-card-tf">{run.tf_exec}</span>
      </div>

      <div className="run-card-stats">
        <span><span>{run.trades_count}</span> trades</span>
        <span>|</span>
        <span>
          <span className={run.win_rate >= 50 ? 'wr-good' : 'wr-bad'}>
            {run.win_rate.toFixed(0)}%
          </span>{' '}
          WR
        </span>
        {run.sharpe !== 0 && (
          <>
            <span>|</span>
            <span><span>{run.sharpe.toFixed(1)}</span> SR</span>
          </>
        )}
      </div>
    </button>
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
        <>
          <div className="sidebar-search">
            <div className="search-input-wrapper">
              <input
                type="text"
                placeholder="Search runs..."
                className="search-input"
              />
              <svg className="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
          </div>

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
                    index={index}
                  />
                ))}
              </div>
            )}
          </div>
        </>
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
