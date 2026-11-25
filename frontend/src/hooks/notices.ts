import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ApiError, isRecord } from '../api/client.ts'

export interface Notice {
  message: string
  kind: 'error' | 'success'
  requestId?: string | null
  retry?: () => void
  durationMs?: number
}

export function useRouteNotice() {
  const location = useLocation()
  const navigate = useNavigate()
  const state: unknown = location.state
  const message = isRecord(state) && typeof state.message === 'string' ? state.message : undefined
  const [notice, setNotice] = useState<Notice | null>(() => message
    ? { message, kind: 'success', durationMs: 4500 }
    : null)

  useEffect(() => {
    if (message) void navigate(location.pathname, { replace: true, state: null })
  }, [location.pathname, message, navigate])

  return [notice, setNotice] as const
}

export function errorNotice(error: unknown, retry?: () => void): Notice {
  return {
    kind: 'error',
    message: error instanceof ApiError ? error.message : 'Something went wrong. Please try again.',
    requestId: error instanceof ApiError ? error.requestId : null,
    retry,
  }
}

export type Notify = (notice: Notice) => void
