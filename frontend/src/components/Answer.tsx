import { useState } from 'react'
import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import type { AskResponse, RetrievedChunkOut } from '../api/types.ts'
import type { Notify } from '../hooks/notices.ts'
import { RetrievedPassages } from './Passages.tsx'
import { CitationChip } from './SourcesUI.tsx'

type SourceClick = (chunk: RetrievedChunkOut) => void

const refusalLabels: Record<string, string> = {
  no_documents: 'No documents yet',
  low_relevance: 'Not found in your documents',
  not_in_documents: 'Not found in your documents',
  prompt_injection: 'Request to override instructions',
  output_blocked: 'Answer blocked by a safety check',
  ungrounded: 'No source supports this answer',
  empty_question: 'No question entered',
  question_too_long: 'Question too long',
}

function inline(text: string, chunks: RetrievedChunkOut[], open: SourceClick): ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*|\[C\d+\])/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{inline(part.slice(2, -2), chunks, open)}</strong>
    }
    if (/^\[C\d+\]$/.test(part)) {
      const chunk = chunks.find((candidate) => candidate.citation_id === part.slice(1, -1))
      if (chunk) {
        const source = [chunk.filename, chunk.page === null ? chunk.section : 'page ' + chunk.page].filter(Boolean).join(' · ')
        return <CitationChip key={index} number={chunk.citation_id.slice(1)} source={source} open={() => open(chunk)} />
      }
    }
    return part
  })
}

interface TextBlock { kind: 'paragraph' | 'list'; lines: string[] }

function groupLines(text: string): TextBlock[] {
  const blocks: TextBlock[] = []
  let current: TextBlock | undefined
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) {
      current = undefined
      continue
    }
    const bullet = /^\s*[-*]\s+(.+)$/.exec(line)
    const kind = bullet ? 'list' : 'paragraph'
    if (!current || current.kind !== kind) {
      current = { kind, lines: [] }
      blocks.push(current)
    }
    current.lines.push(bullet ? bullet[1] : line)
  }
  return blocks
}

export function AnswerText({
  text, chunks = [], openSource = () => undefined,
}: { text: string; chunks?: RetrievedChunkOut[]; openSource?: SourceClick }) {
  return <div className="answer-text" dir="auto">
    {groupLines(text).map((block, index) => block.kind === 'list'
      ? <ul key={index}>{block.lines.map((line, number) => <li key={number}>{inline(line, chunks, openSource)}</li>)}</ul>
      : <p key={index}>{inline(block.lines.join('\n'), chunks, openSource)}</p>)}
  </div>
}

export function Answer({
  result, duration, openSource, notify,
}: { result: AskResponse; duration?: number; openSource: SourceClick; notify: Notify }) {
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied'>('idle')
  const reduced = useReducedMotion()
  const totalTokens = result.prompt_tokens + result.completion_tokens
  const model = [result.model?.split('/').at(-1), result.provider].filter(Boolean).join(' · ')

  async function copy() {
    setCopyState('copying')
    try {
      await navigator.clipboard.writeText(result.answer)
      setCopyState('copied')
    } catch {
      setCopyState('idle')
      notify({ kind: 'error', message: 'Could not copy to the clipboard.' })
    }
  }

  return (
    <motion.section className="answer-block answer-card"
      initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0 : 0.19, ease: 'easeOut' }} aria-label="Answer">
      {result.refused
        ? <div className="refusal"><AnswerText text={result.answer} chunks={result.chunks} openSource={openSource} />
          {result.refusal_reason && <p className="secondary-text">
            {refusalLabels[result.refusal_reason] ?? 'Unable to answer'} (<span className="mono">{result.refusal_reason}</span>)
          </p>}</div>
        : <AnswerText text={result.answer} chunks={result.chunks} openSource={openSource} />}
      <div className="answer-footer">
        <p className="muted secondary-text">
          {model && <>{model} · </>}
          {duration !== undefined && <><span className="mono">{Math.round(duration)} ms</span> · </>}
          <span className="mono">{totalTokens.toLocaleString()}</span> tokens
        </p>
        <button type="button" className="button ghost compact" disabled={copyState === 'copying'}
          onClick={() => { void copy() }}>
          {copyState === 'copied' ? 'Copied' : copyState === 'copying' ? 'Copying…' : 'Copy'}
        </button>
      </div>
      <RetrievedPassages count={result.retrieved_count} chunks={result.chunks} />
    </motion.section>
  )
}
