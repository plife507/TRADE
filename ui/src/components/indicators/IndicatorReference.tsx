import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchIndicatorReference,
  fetchIndicatorSample,
  type IndicatorInfo,
  type SampleDataPoint,
} from '../../api/client'

// Category configuration
const CATEGORY_CONFIG: Record<
  string,
  { label: string; color: string; icon: JSX.Element }
> = {
  trend: {
    label: 'Trend',
    color: 'var(--signal)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      </svg>
    ),
  },
  momentum: {
    label: 'Momentum',
    color: 'var(--info)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
  },
  volatility: {
    label: 'Volatility',
    color: 'var(--caution)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M2 12h4l3-9 4 18 3-9h6" />
      </svg>
    ),
  },
  volume: {
    label: 'Volume',
    color: '#9b59b6',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="4" y="10" width="4" height="10" rx="1" />
        <rect x="10" y="4" width="4" height="16" rx="1" />
        <rect x="16" y="8" width="4" height="12" rx="1" />
      </svg>
    ),
  },
  other: {
    label: 'Other',
    color: 'var(--text-tertiary)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4M12 8h.01" />
      </svg>
    ),
  },
}

// Mini sparkline chart for indicator preview
function MiniChart({
  data,
  color,
  height = 40,
  showZero = false,
}: {
  data: SampleDataPoint[]
  color: string
  height?: number
  showZero?: boolean
}) {
  if (data.length === 0) return null

  const values = data.map((d) => d.y)
  const min = showZero ? Math.min(0, ...values) : Math.min(...values)
  const max = showZero ? Math.max(100, ...values) : Math.max(...values)
  const range = max - min || 1

  const width = 120
  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - ((d.y - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg
      width={width}
      height={height}
      className="indicator-mini-chart"
      style={{ display: 'block' }}
    >
      {/* Reference line at zero for oscillators */}
      {showZero && min < 0 && max > 0 && (
        <line
          x1="0"
          y1={height - ((0 - min) / range) * height}
          x2={width}
          y2={height - ((0 - min) / range) * height}
          stroke="var(--surface-border)"
          strokeWidth="1"
          strokeDasharray="2,2"
        />
      )}
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        points={points}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// Indicator card component
function IndicatorCard({
  indicator,
  isExpanded,
  onToggle,
}: {
  indicator: IndicatorInfo
  isExpanded: boolean
  onToggle: () => void
}) {
  const categoryConfig = CATEGORY_CONFIG[indicator.category] || CATEGORY_CONFIG.other

  // Fetch sample data when expanded
  const { data: sampleData, isLoading: sampleLoading } = useQuery({
    queryKey: ['indicator-sample', indicator.name],
    queryFn: () => fetchIndicatorSample(indicator.name),
    enabled: isExpanded,
  })

  // Get first series for mini chart preview
  const firstSeriesKey = Object.keys(sampleData?.sample_data?.series || {})[0]
  const firstSeries = firstSeriesKey
    ? sampleData?.sample_data?.series[firstSeriesKey]
    : null

  // Determine if this is an oscillator (bounded between values)
  const isOscillator = ['rsi', 'stoch', 'stochrsi', 'mfi', 'willr', 'cci', 'cmo'].includes(
    indicator.name
  )

  return (
    <div
      className={`indicator-card ${isExpanded ? 'expanded' : ''}`}
      onClick={onToggle}
    >
      <div className="indicator-card-header">
        <div className="indicator-card-title">
          <span
            className="indicator-category-dot"
            style={{ background: categoryConfig.color }}
          />
          <span className="indicator-name">{indicator.name.toUpperCase()}</span>
          {indicator.is_multi_output && (
            <span className="badge badge-info">
              {indicator.output_keys.length} outputs
            </span>
          )}
        </div>
        <div className="indicator-card-preview">
          {firstSeries && !sampleLoading ? (
            <MiniChart
              data={firstSeries}
              color={categoryConfig.color}
              showZero={isOscillator}
            />
          ) : (
            <div className="indicator-chart-placeholder" />
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="indicator-card-details">
          {/* Input Series */}
          <div className="indicator-detail-row">
            <span className="indicator-detail-label">Inputs:</span>
            <span className="indicator-detail-value">
              {indicator.input_series.join(', ')}
            </span>
          </div>

          {/* Parameters */}
          {indicator.params.length > 0 && (
            <div className="indicator-detail-row">
              <span className="indicator-detail-label">Params:</span>
              <span className="indicator-detail-value">
                {indicator.params.map((p) => (
                  <span key={p.name} className="indicator-param">
                    {p.name}
                    {p.default !== null && (
                      <span className="indicator-param-default">={String(p.default)}</span>
                    )}
                  </span>
                ))}
              </span>
            </div>
          )}

          {/* Output Keys */}
          {indicator.is_multi_output && (
            <div className="indicator-detail-row">
              <span className="indicator-detail-label">Outputs:</span>
              <span className="indicator-detail-value">
                {indicator.outputs.map((o) => (
                  <span key={o.key} className="indicator-output">
                    {o.key}
                    <span className="indicator-output-type">{o.output_type}</span>
                  </span>
                ))}
              </span>
            </div>
          )}

          {/* Warmup */}
          <div className="indicator-detail-row">
            <span className="indicator-detail-label">Warmup:</span>
            <span className="indicator-detail-value indicator-warmup">
              {indicator.warmup_description}
            </span>
          </div>

          {/* Expanded chart */}
          {sampleData && Object.keys(sampleData.sample_data.series).length > 0 && (
            <div className="indicator-chart-expanded">
              {Object.entries(sampleData.sample_data.series).map(([key, series]) => (
                <div key={key} className="indicator-series-row">
                  <span className="indicator-series-label">{key}</span>
                  <MiniChart
                    data={series}
                    color={categoryConfig.color}
                    height={30}
                    showZero={isOscillator}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Category filter tabs
function CategoryTabs({
  categories,
  selectedCategory,
  onSelect,
}: {
  categories: Record<string, number>
  selectedCategory: string | null
  onSelect: (category: string | null) => void
}) {
  return (
    <div className="indicator-category-tabs">
      <button
        className={`indicator-category-tab ${selectedCategory === null ? 'active' : ''}`}
        onClick={() => onSelect(null)}
      >
        All
        <span className="indicator-category-count">
          {Object.values(categories).reduce((a, b) => a + b, 0)}
        </span>
      </button>
      {Object.entries(CATEGORY_CONFIG).map(([key, config]) => {
        const count = categories[key] || 0
        if (count === 0) return null
        return (
          <button
            key={key}
            className={`indicator-category-tab ${selectedCategory === key ? 'active' : ''}`}
            onClick={() => onSelect(key)}
            style={
              selectedCategory === key
                ? { borderColor: config.color, color: config.color }
                : {}
            }
          >
            <span className="indicator-category-icon">{config.icon}</span>
            {config.label}
            <span className="indicator-category-count">{count}</span>
          </button>
        )
      })}
    </div>
  )
}

// Search input
function SearchInput({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="indicator-search-wrapper">
      <input
        type="text"
        className="indicator-search-input"
        placeholder="Search indicators..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <svg
        className="indicator-search-icon"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
    </div>
  )
}

// Main component
export function IndicatorReference() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [expandedIndicator, setExpandedIndicator] = useState<string | null>(null)

  const {
    data: referenceData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['indicator-reference'],
    queryFn: fetchIndicatorReference,
  })

  // Filter indicators
  const filteredIndicators = useMemo(() => {
    if (!referenceData) return []

    return referenceData.indicators.filter((indicator) => {
      // Category filter
      if (selectedCategory && indicator.category !== selectedCategory) {
        return false
      }
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        return (
          indicator.name.toLowerCase().includes(query) ||
          indicator.input_series.some((s) => s.toLowerCase().includes(query)) ||
          indicator.params.some((p) => p.name.toLowerCase().includes(query))
        )
      }
      return true
    })
  }, [referenceData, selectedCategory, searchQuery])

  // Group by category for display
  const groupedIndicators = useMemo(() => {
    const groups: Record<string, IndicatorInfo[]> = {}
    for (const indicator of filteredIndicators) {
      if (!groups[indicator.category]) {
        groups[indicator.category] = []
      }
      groups[indicator.category].push(indicator)
    }
    return groups
  }, [filteredIndicators])

  if (error) {
    return (
      <div className="indicator-reference-error">
        <div className="indicator-reference-error-icon">
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h3>Failed to load indicator reference</h3>
        <p>Make sure the visualization server is running.</p>
      </div>
    )
  }

  return (
    <div className="indicator-reference">
      {/* Header */}
      <div className="indicator-reference-header">
        <div className="indicator-reference-title">
          <h2>Indicator Reference</h2>
          <span className="badge">
            {referenceData?.total || 0} indicators
          </span>
        </div>
        <SearchInput value={searchQuery} onChange={setSearchQuery} />
      </div>

      {/* Category tabs */}
      {referenceData && (
        <CategoryTabs
          categories={referenceData.categories}
          selectedCategory={selectedCategory}
          onSelect={setSelectedCategory}
        />
      )}

      {/* Content */}
      {isLoading ? (
        <div className="indicator-reference-loading">
          <div className="spinner" />
          <span>Loading indicators...</span>
        </div>
      ) : (
        <div className="indicator-reference-content">
          {selectedCategory ? (
            // Show flat grid when category selected
            <div className="indicator-grid">
              {filteredIndicators.map((indicator) => (
                <IndicatorCard
                  key={indicator.name}
                  indicator={indicator}
                  isExpanded={expandedIndicator === indicator.name}
                  onToggle={() =>
                    setExpandedIndicator(
                      expandedIndicator === indicator.name ? null : indicator.name
                    )
                  }
                />
              ))}
            </div>
          ) : (
            // Show grouped by category
            Object.entries(groupedIndicators).map(([category, indicators]) => {
              const config = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.other
              return (
                <div key={category} className="indicator-category-section">
                  <div className="indicator-category-header">
                    <span
                      className="indicator-category-icon-large"
                      style={{ color: config.color }}
                    >
                      {config.icon}
                    </span>
                    <h3>{config.label}</h3>
                    <span className="badge">{indicators.length}</span>
                  </div>
                  <div className="indicator-grid">
                    {indicators.map((indicator) => (
                      <IndicatorCard
                        key={indicator.name}
                        indicator={indicator}
                        isExpanded={expandedIndicator === indicator.name}
                        onToggle={() =>
                          setExpandedIndicator(
                            expandedIndicator === indicator.name
                              ? null
                              : indicator.name
                          )
                        }
                      />
                    ))}
                  </div>
                </div>
              )
            })
          )}

          {filteredIndicators.length === 0 && (
            <div className="indicator-reference-empty">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <h3>No indicators found</h3>
              <p>Try adjusting your search or filter criteria.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
