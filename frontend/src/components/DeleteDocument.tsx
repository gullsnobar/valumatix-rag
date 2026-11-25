import { useId, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { api } from '../api/client.ts'
import type { DocumentListOut, DocumentOut } from '../api/types.ts'
import { errorNotice } from '../hooks/notices.ts'
import type { Notify } from '../hooks/notices.ts'
import { documentKey } from '../hooks/useDocuments.ts'
import { Popover } from './Popover.tsx'

export function DeleteDocument({
  document, ownerId, notify,
}: { document: DocumentOut; ownerId: string; notify: Notify }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => api.deleteDocument(document.id),
    onSuccess: () => {
      setOpen(false)
      client.setQueryData<DocumentListOut>(documentKey(ownerId), (data) => {
        if (!data) return data
        const documents = data.documents.filter((record) => record.id !== document.id)
        return { documents, total: documents.length }
      })
      void client.invalidateQueries({ queryKey: documentKey(ownerId) })
      notify({ kind: 'success', message: 'Document deleted.' })
    },
    onError: (error) => notify(errorNotice(error)),
  })
  return (
    <div className="popover-anchor">
      <button
        type="button" className="icon-button delete-trigger" aria-label={`Delete ${document.filename}`}
        title="Delete document" aria-expanded={open} aria-controls={open ? id : undefined}
        disabled={mutation.isPending} onClick={() => setOpen(!open)}
      ><Trash2 /></button>
      {open && <Popover id={id} label="Confirm document deletion" busy={mutation.isPending} onClose={() => setOpen(false)}>
        <p className="popover-title">Delete document?</p>
        <p className="muted secondary-text">{document.filename}</p>
        {mutation.isError && <p className="danger secondary-text">Deletion failed. You can try again.</p>}
        <div className="popover-actions">
          <button className="button secondary compact" type="button" disabled={mutation.isPending}
            onClick={() => setOpen(false)}>Cancel</button>
          <button className="button secondary destructive compact" type="button" disabled={mutation.isPending}
            onClick={() => mutation.mutate()}>{mutation.isPending ? 'Deleting…' : 'Delete'}</button>
        </div>
      </Popover>}
    </div>
  )
}
