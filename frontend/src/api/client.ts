import { expireSession, getAccessToken } from './session.ts'
import type {
  AuthResponse, Credentials, DocumentListOut, DocumentOut, ErrorResponse,
  HealthOut, MetricsOut, RecentMetricOut, SampleDocumentsOut, UserOut,
} from './types.ts'

const configuredUrl: unknown = import.meta.env?.VITE_API_URL
export const API_URL = (
  (typeof configuredUrl === 'string' && configuredUrl.trim()) || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')
export const API_DOCS_URL = API_URL + '/docs'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object'
}

export function isErrorResponse(value: unknown): value is ErrorResponse {
  if (!isRecord(value) || !isRecord(value.error)) return false
  const { code, message, request_id } = value.error
  return typeof code === 'string' && typeof message === 'string' && typeof request_id === 'string'
}

export function errorFromPayload(status: number, payload: unknown, requestId: string | null): ApiError {
  if (isErrorResponse(payload)) {
    const { code, message, request_id } = payload.error
    return new ApiError(status, code, message, request_id || requestId)
  }
  return new ApiError(status, 'http_error', `The request failed (HTTP ${status}).`, requestId)
}

interface ApiOptions extends RequestInit {
  authenticated?: boolean
  acceptedStatuses?: number[]
}

export async function openApi(
  path: string,
  options: ApiOptions = {},
): Promise<{ response: Response; token: string | null }> {
  const { authenticated = true, acceptedStatuses = [], ...init } = options
  const token = authenticated ? getAccessToken() : null
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new ApiError(0, 'network_error', 'Could not reach the service. Check your connection.')
  }
  if (response.status === 401) expireSession(token)
  if (!response.ok && !acceptedStatuses.includes(response.status)) {
    const payload: unknown = await response.json().catch(() => null)
    throw errorFromPayload(response.status, payload, response.headers.get('X-Request-ID'))
  }
  return { response, token }
}

export async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { response } = await openApi(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  authenticate(mode: 'login' | 'signup', credentials: Credentials, signal?: AbortSignal) {
    return request<AuthResponse>(`/auth/${mode}`, {
      authenticated: false,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
      signal,
    })
  },
  me: (signal?: AbortSignal) => request<UserOut>('/auth/me', { signal }),
  documents: (signal?: AbortSignal) => request<DocumentListOut>('/documents', { signal }),
  loadSamples: () => request<SampleDocumentsOut>('/documents/samples', { method: 'POST' }),
  deleteDocument: (id: string) =>
    request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  metrics: (signal?: AbortSignal) => request<MetricsOut>('/metrics', { signal }),
  recentMetrics: (signal?: AbortSignal) => request<RecentMetricOut[]>('/metrics/recent?limit=50', { signal }),
  health: (signal?: AbortSignal) =>
    request<HealthOut>('/health', { signal, acceptedStatuses: [503], authenticated: false }),
}

export function uploadDocument(
  file: File,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
): Promise<DocumentOut> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Upload cancelled.', 'AbortError'))
      return
    }
    const xhr = new XMLHttpRequest()
    const token = getAccessToken()
    const cancel = () => xhr.abort()
    xhr.open('POST', `${API_URL}/documents`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.responseType = 'json'
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(100, Math.round(event.loaded / event.total * 100)))
    }
    xhr.onload = () => {
      const payload: unknown = xhr.response
      if (xhr.status === 401) expireSession(token)
      if (xhr.status === 201 && isRecord(payload)) resolve(payload as unknown as DocumentOut)
      else reject(errorFromPayload(xhr.status, payload, xhr.getResponseHeader('X-Request-ID')))
    }
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'The upload could not reach the service.'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled.', 'AbortError'))
    xhr.onloadend = () => signal.removeEventListener('abort', cancel)
    signal.addEventListener('abort', cancel, { once: true })
    const form = new FormData()
    form.set('file', file)
    xhr.send(form)
  })
}
