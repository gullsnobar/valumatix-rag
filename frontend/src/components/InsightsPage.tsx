import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import type { RecentMetricOut } from '../api/types.ts'
import { useShell } from '../hooks/shell.ts'
import { InlineError, SkeletonRows } from './Notice.tsx'

const clock = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'medium' })
const count = new Intl.NumberFormat()
const percent = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 })
const currency = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 })
const latency = (value: number) => count.format(Math.round(value)) + ' ms'

function providerName(provider: string | null): string {
  if (!provider) return 'No provider'
  return provider === 'groq' ? 'Groq' : provider === 'ollama' ? 'Ollama' : provider
}

function providerClass(provider: string | null): string {
  return provider === 'groq' ? 'provider-groq' : provider === 'ollama' ? 'provider-ollama' : 'provider-other'
}

function LatencyChart({ rows }: { rows: RecentMetricOut[] }) {
  if (!rows.length) return <p className="empty-chart muted">Ask a question to record latency.</p>
  const ordered = [...rows].reverse()
  const maximum = Math.max(100, ...ordered.map((row) => row.latency_ms))
  const outer = 700
  const top = 10
  const bottom = 142
  const points = ordered.map((row, index) => ({
    row,
    x: ordered.length === 1 ? outer / 2 : 8 + index * (outer - 16) / (ordered.length - 1),
    y: bottom - row.latency_ms / maximum * (bottom - top),
  }))
  const linePoints = points.map(({ x, y }) => x + ',' + y).join(' ')
  return (
    <figure className="latency-figure">
      <div className="chart-body">
        <div className="chart-axis mono secondary-text" aria-hidden="true">
          <span>{latency(maximum)}</span><span>{latency(maximum / 2)}</span><span>0 ms</span>
        </div>
        <svg className="latency-chart" viewBox="0 0 700 152" preserveAspectRatio="none"
          role="img" aria-label="Latency by recent request, with refused requests marked by crosses">
          {[top, (bottom + top) / 2, bottom].map((y) => <line key={y}
            x1="0" x2="700" y1={y} y2={y} className="chart-grid" />)}
          {points.length > 1 && <>
            <polygon className="chart-area" points={`${points[0].x},${bottom} ${linePoints} ${points[points.length - 1].x},${bottom}`} />
            <polyline className="chart-line" points={linePoints} />
          </>}
          {points.map(({ row, x, y }, index) => (
            <g key={row.created_at + '-' + index} className={providerClass(row.provider)}>
              <title>{[dateTime.format(new Date(row.created_at)), latency(row.latency_ms), providerName(row.provider),
                row.refused && 'Refused'].filter(Boolean).join(' · ')}</title>
              {row.refused
                ? <path d={`M ${x - 4} ${y - 4} l 8 8 M ${x - 4} ${y + 4} l 8 -8`} className="chart-cross" />
                : <circle cx={x} cy={y} r="3.5" className="chart-point" />}
            </g>
          ))}
        </svg>
      </div>
      <div className="chart-time mono muted secondary-text" aria-hidden="true">
        <span>{clock.format(new Date(ordered[0].created_at))}</span>
        <span>{ordered.length > 1 && clock.format(new Date(ordered[ordered.length - 1].created_at))}</span>
      </div>
      <figcaption className="chart-legend secondary-text muted">
        {['groq', 'ollama', null].filter((provider) => ordered.some((row) => row.provider === provider)).map((provider) =>
          <span key={provider ?? 'none'}><i className={'legend-dot ' + providerClass(provider)} />{providerName(provider)}</span>)}
        <span><span className="chart-refused" aria-hidden="true">×</span> Refused</span>
      </figcaption>
      <ol className="sr-only">
        {ordered.map((row, index) => <li key={row.created_at + '-' + index}>
          {dateTime.format(new Date(row.created_at))}, {latency(row.latency_ms)}, {providerName(row.provider)}
          {row.refused ? ', refused' : ''}
        </li>)}
      </ol>
    </figure>
  )
}

function Providers({ counts }: { counts: Record<string, number> }) {
  const entries = ['groq', 'ollama', ...Object.keys(counts).filter((key) => key !== 'groq' && key !== 'ollama')]
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0)
  return (
    <div className="provider-breakdown">
      <div className="provider-track" aria-hidden="true">
        {entries.map((provider) => <span key={provider} className={providerClass(provider)}
          style={{ width: total ? ((counts[provider] ?? 0) / total) * 100 + '%' : '0%' }} />)}
      </div>
      <ul>
        {entries.map((provider) => <li key={provider}>
          <span><i className={'legend-dot ' + providerClass(provider)} />{providerName(provider)}</span>
          <span className="mono">{count.format(counts[provider] ?? 0)}</span>
        </li>)}
      </ul>
    </div>
  )
}

export function InsightsPage() {
  const { ownerId } = useShell()
  const metrics = useQuery({
    queryKey: ['metrics', ownerId],
    queryFn: ({ signal }) => api.metrics(signal), refetchInterval: 15_000,
  })
  const recent = useQuery({
    queryKey: ['metrics-recent', ownerId],
    queryFn: ({ signal }) => api.recentMetrics(signal), refetchInterval: 15_000,
  })
  const data = metrics.data
  const stats = [
    ['Requests', data && count.format(data.total_requests)],
    ['p50 latency', data && latency(data.p50_latency_ms)],
    ['p95 latency', data && latency(data.p95_latency_ms)],
    ['Error rate', data && percent.format(data.error_rate)],
    ['Refusal rate', data && percent.format(data.refusal_rate)],
    ['Estimated cost', data && currency.format(data.estimated_cost_usd)],
  ]
  return (
    <div className="page-container standard-page">
      <div className="insights-period muted">{data?.window === 'last_7_days' ? 'Last 7 days' : '\u00a0'}</div>
      {metrics.isError && <InlineError message="Could not load metrics." retry={() => { void metrics.refetch() }} />}
      <dl className="stats-grid" aria-busy={metrics.isPending}>
        {stats.map(([label, value]) => <div className="stat" key={label}>
          <dt className="muted">{label}</dt>
          <dd className="mono">{metrics.isPending ? <span className="skeleton-bar" /> : value ?? '—'}</dd>
        </div>)}
      </dl>
      <div className="insight-grid">
        <section className="insight-panel">
          <div className="section-heading"><h2>Recent latency</h2><span className="muted secondary-text">Last 50 requests</span></div>
          {recent.isPending && <SkeletonRows rows={4} />}
          {recent.isError && <InlineError message="Could not load recent latency." retry={() => { void recent.refetch() }} />}
          {recent.isSuccess && <LatencyChart rows={recent.data} />}
        </section>
        <section className="insight-panel">
          <div className="section-heading"><h2>Providers</h2></div>
          {metrics.isPending ? <SkeletonRows rows={2} /> : <Providers counts={data?.provider_counts ?? {}} />}
        </section>
      </div>
    </div>
  )
}
