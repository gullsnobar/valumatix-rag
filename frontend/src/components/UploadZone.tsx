import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { LoaderCircle, Upload } from 'lucide-react'
import type { UploadQueue } from '../hooks/useUploadQueue.ts'

export function UploadZone({ queue, compact }: { queue: UploadQueue; compact: boolean }) {
  const dragCount = useRef(0)
  const [dragging, setDragging] = useState(false)

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragCount.current = 0
    setDragging(false)
    queue.enqueue(Array.from(event.dataTransfer.files))
  }

  const className = 'drop-zone' + (compact ? ' drop-zone-compact' : '') + (dragging ? ' drop-active' : '')
  return <div className={className}
    onDragOver={(event) => {
      if (!event.dataTransfer.types.includes('Files')) return
      event.preventDefault()
      event.dataTransfer.dropEffect = 'copy'
    }}
    onDragEnter={(event) => {
      if (!event.dataTransfer.types.includes('Files')) return
      event.preventDefault()
      dragCount.current++
      setDragging(true)
    }}
    onDragLeave={() => {
      dragCount.current = Math.max(0, dragCount.current - 1)
      if (!dragCount.current) setDragging(false)
    }}
    onDrop={drop}>
    <p><Upload aria-hidden="true" /> Drop files here</p>
    <p className="muted secondary-text">PDF, DOCX, PPTX, MD, TXT · Up to 10 MB per file</p>
  </div>
}

export function SampleProgress() {
  return <div className="sample-progress" role="status">
    <LoaderCircle className="busy-spinner" aria-hidden="true" />
    <div><p>Adding sample documents…</p>
      <p className="muted secondary-text">This takes a moment while PolicyDesk RAG prepares each file for search.</p></div>
  </div>
}

export function UploadRows({ queue }: { queue: UploadQueue }) {
  return queue.rows.length > 0
    ? <ul className="upload-rows" aria-label="Uploads" aria-live="polite">
        {queue.rows.map((row) => <li key={row.id} className="upload-row">
          <p className="upload-name" title={row.name}>{row.name}</p>
          {row.status === 'queued' && <p className="muted secondary-text">Queued</p>}
          {row.status === 'uploading' && <>
            <progress max={100} value={row.progress} aria-label={`Upload progress for ${row.name}`} />
            <p className="muted secondary-text">{row.progress === 100
              ? 'Processing file…' : <span className="mono">{row.progress}%</span>}</p>
          </>}
          {row.status === 'uploaded' && <p className="success secondary-text">Uploaded · {row.chunks} chunks</p>}
          {row.status === 'error' && <>
            <p className="danger secondary-text">{row.error}</p>
            {row.requestId && <p className="muted secondary-text break-words">Request <span className="mono">{row.requestId}</span></p>}
          </>}
        </li>)}
      </ul>
    : null
}
