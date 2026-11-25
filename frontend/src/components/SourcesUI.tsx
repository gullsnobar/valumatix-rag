import { useId, useRef } from 'react'

export function CitationChip({ number, source, open }: {
  number: string
  source?: string
  open?: () => void
}) {
  const id = useId()
  const tooltip = useRef<HTMLSpanElement>(null)
  function fitTooltip() {
    const element = tooltip.current
    const chip = element?.parentElement
    if (!element || !chip) return
    const origin = chip.getBoundingClientRect().left
    const viewport = chip.closest('.conversation-scroll')?.getBoundingClientRect()
    const left = (viewport?.left ?? 0) + 6
    const right = (viewport?.right ?? window.innerWidth) - 6
    element.style.left = Math.max(left, Math.min(origin, right - element.offsetWidth)) - origin + 'px'
  }

  if (!open) return <sup><span className="citation mono" aria-label={'Citation ' + number}>{number}</span></sup>
  return (
    <sup className="citation-anchor" onPointerEnter={fitTooltip} onFocus={fitTooltip}>
      <button type="button" className="citation mono" aria-label={'Open citation ' + number}
        aria-describedby={source ? id : undefined} onClick={open}>{number}</button>
      {source && <span className="citation-tooltip" ref={tooltip} id={id} role="tooltip">{source}</span>}
    </sup>
  )
}

const sourceTerms = {
  Match: 'How closely this passage matches your question (0 to 1).',
  'Keyword rank': 'Position in the keyword search results.',
  'Combined score': 'Final ranking after combining meaning-based and keyword search.',
}

export function SourceTerm({ term }: { term: keyof typeof sourceTerms }) {
  const id = useId()
  return <span className="source-term" tabIndex={0} aria-describedby={id}>
    {term}
    <span className="source-term-tooltip" role="tooltip" id={id}>{sourceTerms[term]}</span>
  </span>
}

export function MatchBar({ value, digits = 3 }: { value: number; digits?: number }) {
  const fraction = Math.max(0, Math.min(1, value))
  return <div className="match-row">
    <SourceTerm term="Match" />
    <div className="match-track" aria-hidden="true"><span style={{ width: fraction * 100 + '%' }} /></div>
    <span className="mono">{fraction.toFixed(digits)}</span>
  </div>
}
