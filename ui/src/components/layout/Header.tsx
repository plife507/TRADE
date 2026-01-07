import type { RunSummary } from '../../api/client'

interface HeaderProps {
  selectedRun: RunSummary | undefined
  markPrice?: number
}

function EmptyHeader() {
  return (
    <header className="header">
      <div className="header-empty">
        <div className="dot" />
        <span>Select a backtest run to begin analysis</span>
      </div>
    </header>
  )
}

export function Header({ selectedRun, markPrice }: HeaderProps) {
  if (!selectedRun) {
    return <EmptyHeader />
  }

  const isPositive = selectedRun.net_pnl_usdt >= 0

  return (
    <header className="header">
      <div className="header-content">
        {/* Left section - Run identity */}
        <div className="header-left">
          {/* Play ID - Primary identifier */}
          <div className="header-identity">
            <div className={`header-dot ${isPositive ? 'positive' : 'negative'}`} />
            <h1 className="header-play-id">{selectedRun.play_id}</h1>
          </div>

          <div className="divider-vertical" style={{ height: 24 }} />

          {/* Symbol + TF */}
          <div className="header-symbol">
            <span className="header-symbol-name">{selectedRun.symbol}</span>
            <span className="badge">{selectedRun.tf_exec}</span>
          </div>

          {/* Mark Price */}
          {markPrice && (
            <>
              <div className="divider-vertical" style={{ height: 24 }} />
              <div className="header-mark-price">
                <span className="label">Mark</span>
                <span className="value">${markPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            </>
          )}

          <div className="divider-vertical" style={{ height: 24 }} />

          {/* Date window */}
          <div className="header-dates">
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <span>{selectedRun.window_start}</span>
            <span className="arrow">→</span>
            <span>{selectedRun.window_end}</span>
          </div>
        </div>

        {/* Right section - Key metrics */}
        <div className="header-right">
          {/* Net P&L - The hero stat */}
          <div className="header-pnl">
            <span className="header-pnl-label">Net P&L</span>
            <span className={`header-pnl-value ${isPositive ? 'positive' : 'negative'}`}>
              {isPositive ? '+' : ''}${selectedRun.net_pnl_usdt.toFixed(2)}
            </span>
          </div>

          {/* Return % */}
          <div className="header-stat">
            <span className="header-stat-label">Return</span>
            <span className={`header-stat-value ${selectedRun.net_return_pct >= 0 ? 'positive' : 'negative'}`}>
              {selectedRun.net_return_pct >= 0 ? '+' : ''}
              {selectedRun.net_return_pct.toFixed(2)}%
            </span>
          </div>

          <div className="divider-vertical" style={{ height: 32 }} />

          {/* Hash verification badge */}
          {selectedRun.has_snapshots && (
            <div className="badge badge-signal">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
              <span>Verified</span>
            </div>
          )}

          {/* Run ID */}
          <div className="header-stat">
            <span className="header-stat-label">Run ID</span>
            <span className="header-stat-value" style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {selectedRun.run_id.slice(0, 8)}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
