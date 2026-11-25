import { useLayoutEffect, useRef } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Paperclip, Send } from 'lucide-react'
import { QUESTION_LIMIT } from '../hooks/useConversation.ts'

export function Composer({
  value, change, onSend, onStop, onAttach, busy,
}: {
  value: string
  change: (value: string) => void
  onSend: () => void
  onStop: () => void
  onAttach: () => void
  busy: boolean
}) {
  const box = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const element = box.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = Math.min(element.scrollHeight, 150) + 'px'
  }, [value])

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!busy && value.trim()) onSend()
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (!busy && value.trim()) onSend()
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="policy-question">Question</label>
      <textarea id="policy-question" ref={box} rows={1} dir="auto"
        maxLength={QUESTION_LIMIT} value={value} onChange={(event) => change(event.currentTarget.value)}
        onKeyDown={onKeyDown} placeholder="Ask about a policy…" aria-describedby="question-length" />
      <div className="composer-controls">
        <button type="button" className="icon-button composer-attach" aria-label="Upload a document"
          title="Upload a document" onClick={onAttach}><Paperclip /></button>
        <span className="mono muted secondary-text" id="question-length">{value.length} / {QUESTION_LIMIT}</span>
        {busy
          ? <button type="button" className="button secondary" onClick={onStop}>Stop</button>
          : <button type="submit" className="button primary" disabled={!value.trim()}><Send /> Send</button>}
      </div>
    </form>
  )
}
