import { useEffect } from 'react'
import type { Notice as NoticeData } from '../hooks/notices.ts'

export function Notice({ notice, dismiss }: { notice: NoticeData; dismiss: () => void }) {
  useEffect(() => {
    if (!notice.durationMs) return
    const deadline = window.setTimeout(dismiss, notice.durationMs)
    return () => window.clearTimeout(deadline)
  }, [dismiss, notice])

  return (
    <div className={'notice notice-' + notice.kind} role={notice.kind === 'error' ? 'alert' : 'status'}>
      <div>
        <p>{notice.message}</p>
        {notice.requestId && <p className="muted notice-id">Request <span className="mono">{notice.requestId}</span></p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {notice.retry && <button type="button" className="button secondary compact" onClick={() => {
          dismiss()
          notice.retry?.()
        }}>Retry</button>}
        <button type="button" className="button ghost compact" onClick={dismiss}>Dismiss</button>
      </div>
    </div>
  )
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-list" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div className="skeleton-row" key={index} aria-hidden="true">
          <span className="skeleton-bar" /><span className="skeleton-bar short" />
        </div>
      ))}
    </div>
  )
}

export function InlineError({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="inline-error" role="alert">
      <p>{message}</p>
      <button className="button secondary compact" type="button" onClick={retry}>Retry</button>
    </div>
  )
}
