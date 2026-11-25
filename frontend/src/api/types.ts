export interface Credentials {
  email: string
  password: string
}

export interface UserOut {
  id: string
  email: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  user: UserOut
}

export interface ErrorBody {
  code: string
  message: string
  request_id: string
}

export interface ErrorResponse {
  error: ErrorBody
}

export interface DocumentOut {
  id: string
  filename: string
  file_type: string
  size_bytes: number
  num_chunks: number
  warnings: string[]
  created_at: string
}

export interface DocumentListOut {
  documents: DocumentOut[]
  total: number
}

export interface SampleDocumentsOut {
  added: number
  skipped_duplicates: number
  rejected: { filename: string; code: string; message: string }[]
}

export interface AskRequest {
  question: string
  top_k?: number | null
}

export interface CitationOut {
  id: string
  chunk_id: string
  document_id: string
  filename: string
  page: number | null
  section: string | null
}

export interface RetrievedChunkOut {
  citation_id: string
  chunk_id: string
  document_id: string
  filename: string
  page: number | null
  section: string | null
  text: string
  similarity: number
  keyword_rank: number | null
  rrf_score: number
  cited: boolean
}

export interface AskResponse {
  answer: string
  refused: boolean
  refusal_reason: string | null
  citations: CitationOut[]
  chunks: RetrievedChunkOut[]
  retrieved_count: number
  provider: string | null
  model: string | null
  timings_ms: Record<string, number>
  prompt_tokens: number
  completion_tokens: number
  request_id: string
}

export interface MetricsOut {
  total_requests: number
  error_rate: number
  refusal_rate: number
  p50_latency_ms: number
  p95_latency_ms: number
  avg_latency_ms: number
  total_prompt_tokens: number
  total_completion_tokens: number
  estimated_cost_usd: number
  provider_counts: Record<string, number>
  window: string
}

export interface RecentMetricOut {
  created_at: string
  latency_ms: number
  provider: string | null
  refused: boolean
  refusal_reason: string | null
}

type ServiceStatus = 'ok' | 'unavailable'

export interface HealthOut {
  status: ServiceStatus
  database: ServiceStatus
  embedding_service: ServiceStatus
}

export type AskStreamEvent =
  | { type: 'stage'; data: { stage: string } }
  | { type: 'token'; data: { text: string } }
  | { type: 'done'; data: AskResponse }
  | { type: 'error'; data: ErrorResponse }
