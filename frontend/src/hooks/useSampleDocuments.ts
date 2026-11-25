import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import type { SampleDocumentsOut } from '../api/types.ts'
import { errorNotice } from './notices.ts'
import type { Notify } from './notices.ts'
import { documentKey } from './useDocuments.ts'

function sampleNotice(result: SampleDocumentsOut) {
  const scan = result.rejected.find((file) => file.filename === 'scanned_office_notice.pdf' && file.code === 'no_extractable_text')
  const other = result.rejected.filter((file) => file !== scan)
  const sentences = [`Added ${result.added} ${result.added === 1 ? 'document' : 'documents'}.`]
  if (scan) sentences.push('1 was skipped because it has no readable text (scanned image).')
  if (result.skipped_duplicates) {
    const count = result.skipped_duplicates
    sentences.push(`${count} ${count === 1 ? 'was' : 'were'} already in your documents.`)
  }
  if (other.length) sentences.push(`${other.length} could not be added. ${other[0].filename}: ${other[0].message}`)
  return { kind: other.length ? 'error' as const : 'success' as const, message: sentences.join(' ') }
}

export function useSampleDocuments(ownerId: string, notify: Notify) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.loadSamples,
    onSuccess: (result) => notify(sampleNotice(result)),
    onError: (error) => notify(errorNotice(error)),
    onSettled: () => client.invalidateQueries({ queryKey: documentKey(ownerId) }),
  })
}
