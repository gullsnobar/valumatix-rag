import { useLayoutEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Link } from 'react-router'
import type { RetrievedChunkOut } from '../api/types.ts'
import { useShell } from '../hooks/shell.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { exampleQuestions } from '../questions.ts'
import { Answer, AnswerText } from './Answer.tsx'
import { Composer } from './Composer.tsx'
import { Monogram } from './Brand.tsx'
import { SourcesDrawer } from './Passages.tsx'
import { PipelineProgress } from './PipelineProgress.tsx'
import { InlineError, SkeletonRows } from './Notice.tsx'
import { SampleProgress, UploadRows } from './UploadZone.tsx'

export function AskPage() {
  const { ownerId, uploads, conversation, notify, pickFiles, draft, setDraft, addingSamples, loadSamples } = useShell()
  const [source, setSource] = useState<{ chunks: RetrievedChunkOut[]; chunkId: string } | null>(null)
  const scroller = useRef<HTMLElement>(null)
  const pinned = useRef(true)
  const documents = useDocuments(ownerId)
  const count = documents.data?.total
  const hasDocuments = (count ?? 0) > 0
  const busy = conversation.activeId !== null
  const reduced = useReducedMotion()

  useLayoutEffect(() => {
    const element = scroller.current
    if (element && pinned.current) element.scrollTop = element.scrollHeight
  }, [conversation.turns, uploads.rows.length])

  function send(question: string) {
    if (!question.trim() || busy) return
    pinned.current = true
    setDraft('')
    void conversation.ask(question)
  }

  return (
    <>
      <section className="page-scroll conversation-scroll" aria-label="Ask PolicyDesk RAG" ref={scroller} onScroll={() => {
        const element = scroller.current
        if (element) pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 56
      }}>
        <div className="page-container ask-column">
          <div className="ask-content">
            {conversation.turns.length === 0
              ? <div className="ask-empty">
                {documents.isPending && <div className="intro-panel"><SkeletonRows rows={4} /></div>}
                {documents.isError && !hasDocuments && <InlineError message="Could not load documents."
                  retry={() => { void documents.refetch() }} />}
                {documents.isSuccess && !hasDocuments && <div className="intro-panel">
                  <h2>Start by adding your documents</h2>
                  <ol className="numbered-steps">
                    <li>Upload documents</li>
                    <li>Ask a question in plain language</li>
                    <li>Check the source shown under every answer</li>
                  </ol>
                  <div className="intro-actions">
                    <button className="button primary" type="button" disabled={addingSamples} onClick={loadSamples}>
                      Load sample documents
                    </button>
                    <button className="button secondary" type="button" onClick={pickFiles}>Upload my own</button>
                  </div>
                </div>}
                {hasDocuments && <>
                  <h2>What would you like to know?</h2>
                  <ul className="example-questions" aria-label="Example questions">
                    {exampleQuestions.map((example) => <li key={example}>
                      <button type="button" disabled={busy} onClick={() => send(example)}>{example}</button>
                    </li>)}
                  </ul>
                </>}
              </div>
              : <div className="conversation">
                {conversation.turns.map((turn) => <article className="conversation-turn" key={turn.id}>
                  <motion.p className="asked-question" dir="auto" initial={!reduced && turn.status === 'running'
                    ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}>{turn.question}</motion.p>
                  <div className="assistant-message">
                    <Monogram answer />
                    {turn.status === 'running' && <div className="answer-card draft-answer">
                      <PipelineProgress completed={turn.stages} />
                      {turn.draft && <AnswerText text={turn.draft} />}
                    </div>}
                    {turn.status === 'complete' && turn.result && <Answer
                      result={turn.result} duration={turn.duration} notify={notify}
                      openSource={(chunk) => setSource({ chunks: turn.result?.chunks ?? [], chunkId: chunk.chunk_id })}
                    />}
                    {(turn.status === 'stopped' || turn.status === 'error') && <div className="answer-card turn-retry">
                      <p className="muted">{turn.status === 'stopped' ? 'Question stopped.' : 'The answer could not be completed.'}</p>
                      <button type="button" className="button ghost compact" disabled={busy} onClick={() => {
                        pinned.current = true
                        void conversation.ask(turn.question, turn.id)
                      }}>Retry</button>
                    </div>}
                  </div>
                </article>)}
              </div>}
            {addingSamples && <SampleProgress />}
            <UploadRows queue={uploads} />
          </div>
          <div className="composer-dock">
            <p className="composer-context muted secondary-text">
              {count === 0 ? <>No documents yet · <button className="text-link" type="button" onClick={pickFiles}>Upload</button></>
                : count === undefined ? documents.isError
                  ? <>Documents unavailable · <Link className="text-link" to="/documents">Manage</Link></>
                  : 'Checking your documents…'
                  : <>Searching <span className="mono">{count}</span> {count === 1 ? 'document' : 'documents'}
                    {' · '}<Link className="text-link" to="/documents">Manage</Link></>}
            </p>
            <Composer value={draft} change={setDraft} busy={busy}
              onSend={() => send(draft)} onStop={conversation.stop} onAttach={pickFiles} />
          </div>
        </div>
      </section>
      <SourcesDrawer selection={source} close={() => setSource(null)} />
    </>
  )
}
