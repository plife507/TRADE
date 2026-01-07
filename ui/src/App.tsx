import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRuns, fetchIndicators, fetchOHLCVMTF, deleteRun } from './api/client'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { MetricsDashboard } from './components/metrics/MetricsDashboard'
import { TimeframeChartStack } from './components/charts/TimeframeChartStack'
import { IndicatorPane } from './components/charts/IndicatorPane'
import { EquityCurve } from './components/charts/EquityCurve'
import { IndicatorReference } from './components/indicators/IndicatorReference'

type AppView = 'backtests' | 'indicators'

function EmptyState({ runsCount }: { runsCount: number }) {
  return (
    <div className="page-empty">
      <div className="page-empty-content animate-fade-in">
        <div className="page-empty-illustration">
          <div className="page-empty-glow" />
          <div className="page-empty-icon-wrapper">
            <div className="page-empty-icon-bg" />
            <div className="page-empty-icon">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
              </svg>
            </div>
          </div>
        </div>

        <h2>Select a Backtest Run</h2>
        <p>
          Choose a run from the sidebar to visualize trading performance, analyze indicators, and review trade execution.
        </p>

        <div className="page-empty-stats">
          <div className="page-empty-stat">
            <span className="dot" />
            <span>{runsCount}</span> runs available
          </div>
        </div>

        <div className="page-empty-hint">
          Tip: Click on any run in the sidebar to begin analysis
        </div>
      </div>
    </div>
  )
}

function ErrorState() {
  return (
    <div className="page-empty">
      <div className="page-empty-content animate-fade-in">
        <div className="page-empty-illustration">
          <div className="page-empty-glow page-error-glow" />
          <div className="page-empty-icon-wrapper">
            <div className="page-empty-icon page-error-icon">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
          </div>
        </div>

        <h2>Connection Failed</h2>
        <p>
          Unable to connect to the API server. Make sure the visualization server is running.
        </p>

        <div className="code-block">
          <p className="comment"># Start the server:</p>
          <p className="command">python trade_cli.py viz serve</p>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [currentView, setCurrentView] = useState<AppView>('backtests')
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: deleteRun,
    onSuccess: (_, deletedRunId) => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      if (selectedRunId === deletedRunId) {
        setSelectedRunId(null)
      }
    },
  })

  const handleDeleteRun = (runId: string) => {
    deleteMutation.mutate(runId)
  }

  const {
    data: runsData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['runs'],
    queryFn: () => fetchRuns(),
  })

  // Fetch MTF OHLCV for mark price
  const { data: mtfOhlcvData } = useQuery({
    queryKey: ['ohlcv-mtf', selectedRunId],
    queryFn: () => fetchOHLCVMTF(selectedRunId!),
    enabled: !!selectedRunId,
  })

  // Fetch indicators for panes
  const { data: indicatorsData } = useQuery({
    queryKey: ['indicators', selectedRunId],
    queryFn: () => fetchIndicators(selectedRunId!),
    enabled: !!selectedRunId,
  })

  const runs = runsData?.runs ?? []
  const selectedRun = runs.find((r) => r.run_id === selectedRunId)
  const indicatorPanes = indicatorsData?.panes ?? []

  return (
    <div className="app-layout">
      <Sidebar
        runs={runs}
        selectedRunId={selectedRunId}
        onSelectRun={(id) => {
          setSelectedRunId(id)
          setCurrentView('backtests')
        }}
        onDeleteRun={handleDeleteRun}
        isLoading={isLoading}
        currentView={currentView}
        onViewChange={setCurrentView}
      />

      <div className="main-area">
        {currentView === 'backtests' ? (
          <>
            <Header selectedRun={selectedRun} markPrice={mtfOhlcvData?.mark_price ?? undefined} />
            <main className="main-content">
              {error ? (
                <ErrorState />
              ) : !selectedRunId ? (
                <EmptyState runsCount={runs.length} />
              ) : (
                <div className="content-stack animate-fade-in">
                  {/* Charts first - main focus */}
                  <TimeframeChartStack runId={selectedRunId} description={selectedRun?.description} />
                  {indicatorPanes.map((pane) => (
                    <IndicatorPane key={pane.type} pane={pane} height={120} />
                  ))}
                  <EquityCurve runId={selectedRunId} height={180} />
                  {/* Metrics at bottom */}
                  <MetricsDashboard runId={selectedRunId} />
                </div>
              )}
            </main>
          </>
        ) : (
          <main className="main-content">
            <IndicatorReference />
          </main>
        )}
      </div>
    </div>
  )
}

export default App
