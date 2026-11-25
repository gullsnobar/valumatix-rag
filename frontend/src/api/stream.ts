import { ApiError, errorFromPayload, isErrorResponse, isRecord, openApi } from './client.ts'
import { expireSession } from './session.ts'
import type { AskRequest, AskResponse, AskStreamEvent } from './types.ts'

const errorStatuses: Readonly<Record<string, number>> = {
  service_unavailable: 503,
  rate_limited: 429,
  unauthorized: 401,
  validation_error: 422,
}
const frameBoundary = /\r\n\r\n|\n\n|\r\r/

function parseFrame(frame: string): AskStreamEvent | null {
  let name = ''
  const dataLines: string[] = []
  for (const line of frame.split(/\r\n|\n|\r/)) {
    if (line.startsWith('event:')) name = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }
  if (!name || dataLines.length === 0) return null
  const data: unknown = JSON.parse(dataLines.join('\n'))
  if (name === 'stage' && isRecord(data) && typeof data.stage === 'string') {
    return { type: 'stage', data: { stage: data.stage } }
  }
  if (name === 'token' && isRecord(data) && typeof data.text === 'string') {
    return { type: 'token', data: { text: data.text } }
  }
  if (name === 'error' && isErrorResponse(data)) return { type: 'error', data }
  if (name === 'done' && isRecord(data) && typeof data.answer === 'string' && Array.isArray(data.chunks)) {
    return { type: 'done', data: data as unknown as AskResponse }
  }
  return null
}

interface StreamCallbacks {
  onStage: (stage: string) => void
  onToken: (text: string) => void
}

export async function streamAsk(
  question: AskRequest,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): Promise<AskResponse> {
  const { response, token } = await openApi('/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(question),
    signal,
  })
  const requestId = response.headers.get('X-Request-ID')
  if (!response.body?.getReader) {
    throw new ApiError(0, 'missing_stream', 'The service did not return an answer stream.', requestId)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  function processFrame(frame: string): AskResponse | undefined {
    const event = parseFrame(frame)
    if (event?.type === 'stage') callbacks.onStage(event.data.stage)
    if (event?.type === 'token') callbacks.onToken(event.data.text)
    if (event?.type === 'done') return event.data
    if (event?.type === 'error') {
      const status = errorStatuses[event.data.error.code] ?? 500
      if (status === 401) expireSession(token)
      throw errorFromPayload(status, event.data, requestId)
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      for (let boundary = frameBoundary.exec(buffer); boundary; boundary = frameBoundary.exec(buffer)) {
        const result = processFrame(buffer.slice(0, boundary.index))
        if (result) return result
        buffer = buffer.slice(boundary.index + boundary[0].length)
      }
      if (done) {
        const result = processFrame(buffer)
        if (result) return result
        throw new ApiError(0, 'incomplete_stream', 'The answer stream ended before verification.', requestId)
      }
    }
  } catch (error) {
    if (error instanceof ApiError || signal.aborted) throw error
    throw new ApiError(0, 'stream_error', 'The answer stream was interrupted. Please retry.', requestId)
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
