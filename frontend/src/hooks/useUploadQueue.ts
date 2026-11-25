import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, uploadDocument } from '../api/client.ts'
import type { DocumentListOut } from '../api/types.ts'
import { documentKey } from './useDocuments.ts'

const MAX_FILE_SIZE = 10 * 1024 * 1024

export interface UploadRow {
  id: string
  name: string
  status: 'queued' | 'uploading' | 'uploaded' | 'error'
  progress: number
  chunks?: number
  error?: string
  requestId?: string | null
}

interface Task {
  id: string
  file: File
}

function uploadError(error: unknown): { error: string; requestId?: string | null } {
  if (!(error instanceof ApiError)) return { error: 'Upload failed. Please try again.' }
  const messages: Record<number, string> = {
    409: 'Already uploaded.',
    415: 'Unsupported file type.',
    413: 'File exceeds the 10 MB limit.',
  }
  return {
    error: error.status
      ? `${error.status} · ${messages[error.status] ?? error.message}`
      : error.message,
    requestId: error.requestId,
  }
}

export function useUploadQueue(ownerId: string) {
  const client = useQueryClient()
  const [rows, setRows] = useState<UploadRow[]>([])
  const tasks = useRef<Task[]>([])
  const active = useRef<AbortController | null>(null)

  useEffect(() => () => {
    tasks.current = []
    active.current?.abort()
  }, [])

  function update(id: string, changes: Partial<UploadRow>) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...changes } : row))
  }

  async function drain() {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    try {
      while (tasks.current.length && !controller.signal.aborted) {
        const task = tasks.current.shift()
        if (!task) break
        update(task.id, { status: 'uploading' })
        try {
          if (task.file.size > MAX_FILE_SIZE) throw new ApiError(413, 'file_too_large', 'File is too large.')
          const document = await uploadDocument(task.file, (progress) => update(task.id, { progress }), controller.signal)
          if (controller.signal.aborted) return
          update(task.id, { chunks: document.num_chunks, progress: 100, status: 'uploaded' })
          await client.cancelQueries({ queryKey: documentKey(ownerId) })
          client.setQueryData<DocumentListOut>(documentKey(ownerId), (current) => {
            const documents = [document, ...(current?.documents ?? []).filter((entry) => entry.id !== document.id)]
            return { documents, total: documents.length }
          })
          void client.invalidateQueries({ queryKey: documentKey(ownerId) })
        } catch (error) {
          if (controller.signal.aborted) return
          update(task.id, { ...uploadError(error), status: 'error' })
          if (error instanceof ApiError && error.status === 401) return
        }
      }
    } finally {
      active.current = null
    }
  }

  function enqueue(files: File[]) {
    if (!files.length) return
    const next = files.map((file) => ({ id: crypto.randomUUID(), file }))
    tasks.current.push(...next)
    setRows((current) => [
      ...current.filter((row) => row.status === 'queued' || row.status === 'uploading'),
      ...next.map<UploadRow>(({ id, file }) => ({ id, name: file.name, progress: 0, status: 'queued' })),
    ])
    void drain()
  }

  return { rows, enqueue }
}

export type UploadQueue = ReturnType<typeof useUploadQueue>
