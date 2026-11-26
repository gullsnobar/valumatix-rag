import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { Search, Upload } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useShell } from '../hooks/shell.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { DeleteDocument } from './DeleteDocument.tsx'
import { InlineError } from './Notice.tsx'
import { SampleProgress, UploadRows, UploadZone } from './UploadZone.tsx'

const uploadDayFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })
const uploadTimeFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' })
const uploadTitleFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'long' })
const rowVariants = { visible: { opacity: 1 }, removed: { opacity: 0 } }
const cellVariants = { visible: { height: 'auto' }, removed: { height: 0, overflow: 'clip' } }

function DocumentCell({ className, children }: {
  className?: string
  children: ReactNode
}) {
  const reduced = useReducedMotion()
  return <td className={className}>
    <motion.div variants={cellVariants} transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}>
      <div className="table-cell-value">{children}</div>
    </motion.div>
  </td>
}

function UploadedAt({ value }: { value: string }) {
  const date = new Date(value)
  return <time dateTime={value} title={uploadTitleFormat.format(date)}>
    {uploadDayFormat.format(date)}, {uploadTimeFormat.format(date)}
  </time>
}

function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}

function Warnings({ warnings }: { warnings: string[] }) {
  const id = useId()
  if (!warnings.length) return null
  const hidden = warnings.some((warning) => warning.toLowerCase().includes('hidden text'))
  const label = hidden ? 'Hidden text detected' : warnings.length + (warnings.length === 1 ? ' warning' : ' warnings')
  return <span className="warning-anchor" tabIndex={0} aria-describedby={id}>
    <span className="warning-label">{label}</span>
    <span className="warning-tooltip" role="tooltip" id={id}>{warnings.join('\n')}</span>
  </span>
}

export function DocumentsPage() {
  const { ownerId, uploads, notify, pickFiles, addingSamples, loadSamples } = useShell()
  const [search, setSearch] = useState('')
  const query = useDocuments(ownerId)
  const documents = query.data?.documents ?? []
  const term = search.trim().toLowerCase()
  const visible = documents.filter((document) => document.filename.toLowerCase().includes(term))
  const reduced = useReducedMotion()

  return (
    <div className="page-container standard-page">
      <div className="documents-toolbar">
        <label className="document-search">
          <Search aria-hidden="true" />
          <span className="sr-only">Search documents</span>
          <input className="input" type="search" placeholder="Search documents" value={search}
            onChange={(event) => setSearch(event.currentTarget.value)} />
        </label>
        <div className="document-actions">
          <button className="button secondary" type="button" disabled={addingSamples} onClick={loadSamples}>Load samples</button>
          <button className="button primary" type="button" onClick={pickFiles}><Upload /> Upload</button>
        </div>
      </div>
      <UploadZone queue={uploads} compact={!query.isSuccess || documents.length > 0} />
      {addingSamples && <SampleProgress />}
      <UploadRows queue={uploads} />
      {query.isError && <InlineError message="Could not load documents." retry={() => { void query.refetch() }} />}
      {(query.isPending || query.isSuccess || documents.length > 0) && <div className="document-table-wrap">
        <table className="document-table">
          <caption className="sr-only">Uploaded documents</caption>
          <thead><tr>
            <th scope="col">Filename</th>
            <th scope="col" className="table-type">Type</th>
            <th scope="col" className="table-size table-number">Size</th>
            <th scope="col" className="table-chunks table-number">Chunks</th>
            <th scope="col" className="table-uploaded">Uploaded at</th>
            <th scope="col" className="table-warnings">Warnings</th>
            <th scope="col" className="table-actions"><span className="sr-only">Actions</span></th>
          </tr></thead>
          <tbody>
            {query.isPending && Array.from({ length: 4 }, (_, index) => (
              <tr key={index} className="table-skeleton">
                <td colSpan={7}><span className="skeleton-bar" aria-hidden="true" />
                  <span className="sr-only">Loading documents</span></td>
              </tr>
            ))}
            <AnimatePresence key={term} initial={false}>
              {visible.map((document) => <motion.tr key={document.id}
                className="document-row" initial={false} animate="visible" exit="removed" variants={rowVariants}
                transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}>
                <DocumentCell>
                  <span className="table-filename" title={document.filename}>{document.filename}</span>
                </DocumentCell>
                <DocumentCell><span className="type-label">{document.file_type.toUpperCase()}</span></DocumentCell>
                <DocumentCell className="table-number mono muted">{fileSize(document.size_bytes)}</DocumentCell>
                <DocumentCell className="table-number mono">{document.num_chunks}</DocumentCell>
                <DocumentCell className="table-uploaded mono muted"><UploadedAt value={document.created_at} /></DocumentCell>
                <DocumentCell className="muted"><Warnings warnings={document.warnings} /></DocumentCell>
                <DocumentCell className="table-actions"><DeleteDocument document={document} ownerId={ownerId} notify={notify} /></DocumentCell>
              </motion.tr>)}
            </AnimatePresence>
            {query.isSuccess && visible.length === 0 && <tr className="empty-table">
              <td colSpan={7}>
                <h2>{documents.length ? 'No documents match your search' : 'No documents uploaded'}</h2>
                {!documents.length && <p className="muted">Upload your own files or load the samples to get started.</p>}
              </td>
            </tr>}
          </tbody>
        </table>
      </div>}
    </div>
  )
}
