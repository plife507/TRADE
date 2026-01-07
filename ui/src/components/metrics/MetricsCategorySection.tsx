import { useState } from 'react'
import type { MetricsCategory, MetricCard } from '../../api/client'

interface MetricsCategorySectionProps {
  category: MetricsCategory
  defaultExpanded?: boolean
}

// Icon components for category headers
const CategoryIcons: Record<string, JSX.Element> = {
  profit: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  risk: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  trades: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
    </svg>
  ),
  ratio: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  percentage: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  ),
  time: (
    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      style={{
        width: 16,
        height: 16,
        transition: 'transform 0.2s',
        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
      }}
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  )
}

function StatCard({ card }: { card: MetricCard }) {
  const valueClass =
    card.trend === 'up'
      ? 'positive'
      : card.trend === 'down'
        ? 'negative'
        : 'neutral'

  return (
    <div className="stat-card-compact" title={card.tooltip ?? undefined}>
      <span className="stat-card-label">{card.label}</span>
      <span className={`stat-card-value ${valueClass}`}>{card.value}</span>
      {card.change && (
        <span className={`stat-card-change ${valueClass}`}>{card.change}</span>
      )}
    </div>
  )
}

export function MetricsCategorySection({
  category,
  defaultExpanded = true,
}: MetricsCategorySectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  const icon = CategoryIcons[category.icon] || CategoryIcons.ratio

  return (
    <div className="metrics-category">
      <button
        className="metrics-category-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="metrics-category-title">
          <span className="metrics-category-icon">{icon}</span>
          {category.name}
          <span className="metrics-category-count">({category.cards.length})</span>
        </span>
        <ChevronIcon expanded={expanded} />
      </button>

      {expanded && (
        <div className="metrics-category-grid">
          {category.cards.map((card, idx) => (
            <StatCard key={`${card.label}-${idx}`} card={card} />
          ))}
        </div>
      )}
    </div>
  )
}
