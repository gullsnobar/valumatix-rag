import { useOutletContext } from 'react-router'
import type { Notify } from './notices.ts'
import type { Conversation } from './useConversation.ts'
import type { UploadQueue } from './useUploadQueue.ts'

export interface ShellContext {
  ownerId: string
  uploads: UploadQueue
  conversation: Conversation
  notify: Notify
  draft: string
  setDraft: (value: string) => void
  addingSamples: boolean
  loadSamples: () => void
  pickFiles: () => void
}

export function useShell() {
  return useOutletContext<ShellContext>()
}
