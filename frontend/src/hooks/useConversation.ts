import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { streamAsk } from '../api/stream.ts'
import type { AskResponse } from '../api/types.ts'
import { errorNotice } from './notices.ts'
import type { Notify } from './notices.ts'

export const QUESTION_LIMIT = 1000

export interface Turn {
  id: string
  question: string
  status: 'running' | 'complete' | 'stopped' | 'error'
  stages: string[]
  draft: string
  result?: AskResponse
  duration?: number
}

export function useConversation(ownerId: string, notify: Notify) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const active = useRef<AbortController | null>(null)
  const client = useQueryClient()

  useEffect(() => () => active.current?.abort(), [])

  function change(id: string, update: (turn: Turn) => Turn) {
    setTurns((current) => current.map((turn) => turn.id === id ? update(turn) : turn))
  }

  async function ask(question: string, retryId?: string) {
    const clean = question.trim()
    if (!clean || clean.length > QUESTION_LIMIT || active.current) return
    const controller = new AbortController()
    active.current = controller
    const id = retryId ?? crypto.randomUUID()
    const turn: Turn = { id, question: clean, status: 'running', stages: [], draft: '' }
    if (retryId) change(id, () => turn)
    else setTurns((current) => [...current, turn])
    setActiveId(id)
    const started = performance.now()
    try {
      const result = await streamAsk({ question: clean }, {
        onStage: (stage) => change(id, (current) => ({ ...current, stages: [...current.stages, stage] })),
        onToken: (text) => change(id, (current) => ({ ...current, draft: current.draft + text })),
      }, controller.signal)
      controller.signal.throwIfAborted()
      change(id, (current) => ({
        ...current, status: 'complete', result, draft: '', duration: performance.now() - started,
      }))
      void client.invalidateQueries({ queryKey: ['metrics', ownerId] })
      void client.invalidateQueries({ queryKey: ['metrics-recent', ownerId] })
    } catch (error) {
      if (controller.signal.aborted) {
        change(id, (current) => ({ ...current, status: 'stopped', draft: '' }))
      } else {
        change(id, (current) => ({ ...current, status: 'error', draft: '' }))
        notify(errorNotice(error, () => { void ask(clean, id) }))
      }
    } finally {
      active.current = null
      setActiveId(null)
    }
  }

  return { turns, activeId, ask, stop: () => active.current?.abort() }
}

export type Conversation = ReturnType<typeof useConversation>
