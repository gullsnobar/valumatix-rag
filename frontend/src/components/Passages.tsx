import { useEffect, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { RetrievedChunkOut } from '../api/types.ts'
import { SlideOver } from './SlideOver.tsx'
import { MatchBar, SourceTerm } from './SourcesUI.tsx'

interface SourceSelection {
  chunkId: string
  chunks: RetrievedChunkOut[]
}

function Passage({ chunk, full = false, highlighted = false }: {
  chunk: RetrievedChunkOut
  full?: boolean
  highlighted?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const article = useRef<HTMLElement>(null)
  useEffect(() => {
    if (highlighted) article.current?.scrollIntoView({ block: 'nearest' })
  }, [highlighted])
  return (
    <article ref={article} className={highlighted ? 'passage passage-highlighted' : 'passage'}>
      <div className="passage-head">
        <span className="source-number mono" aria-label={`Citation ${chunk.citation_id.slice(1)}`}>
          {chunk.citation_id.slice(1)}
        </span>
        <div className="passage-filename">
          <p>{chunk.filename}</p>
          <p className="muted secondary-text">
            {chunk.page === null && !chunk.section && 'Document'}
            {chunk.page !== null && <>Page <span className="mono">{chunk.page}</span></>}
            {chunk.page !== null && chunk.section && ' · '}
            {chunk.section}
          </p>
        </div>
        {chunk.cited && <span className="cited-label">Cited</span>}
      </div>
      <MatchBar value={chunk.similarity} />
      <details className="source-details secondary-text">
        <summary>Details</summary>
        <dl className="source-scores">
          <div><dt><SourceTerm term="Keyword rank" /></dt><dd className="mono">{chunk.keyword_rank ?? '—'}</dd></div>
          <div><dt><SourceTerm term="Combined score" /></dt><dd className="mono">{chunk.rrf_score.toFixed(4)}</dd></div>
        </dl>
      </details>
      <p className={'passage-text' + (full || expanded ? '' : ' passage-clamped')} dir="auto">{chunk.text}</p>
      {!full && <button type="button" className="button ghost compact passage-expand"
        aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? 'Show less' : 'Read full passage'}</button>}
    </article>
  )
}

export function RetrievedPassages({ count, chunks }: { count: number; chunks: RetrievedChunkOut[] }) {
  return (
    <details className="retrieved-passages">
      <summary>
        <span>Sources found (<span className="mono">{count}</span>)</span>
        <ChevronRight aria-hidden="true" />
      </summary>
      {chunks.length > 0
        ? <div className="passage-list">{chunks.map((chunk) => <Passage key={chunk.chunk_id} chunk={chunk} />)}</div>
        : <p className="muted secondary-text no-passages">No sources found.</p>}
    </details>
  )
}

export function SourcesDrawer({ selection, close }: { selection: SourceSelection | null; close: () => void }) {
  return (
    <SlideOver open={selection !== null} title="Sources" onClose={close}>
      <div className="passage-list drawer-passages">
        {selection?.chunks.map((chunk) => <Passage key={chunk.chunk_id} chunk={chunk}
          full highlighted={selection.chunkId === chunk.chunk_id} />)}
      </div>
    </SlideOver>
  )
}
