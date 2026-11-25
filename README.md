# PolicyDesk RAG

## Overview

PolicyDesk RAG is a retrieval-augmented generation (RAG) service for the fictional Tarnwick Consulting.  
Upload policy documents and ask questions in English or Urdu.  
Open a citation to read the original passage, or see a refusal when the available evidence cannot support an answer.

## Features

- Upload, list, inspect, and delete PDF, DOCX, PPTX, Markdown, and plain-text documents. Ingestion preserves source locations and extracts tables as Markdown where supported.
- Retrieve passages with pgvector cosine search and optional PostgreSQL keyword search. Answers include validated source IDs, ranked passages, scores, timings, and token counts. Streaming reports live stages and releases answer text after validation.
- Create an account with JWT authentication. Document access, retrieval, deletion, and metrics are scoped to the signed-in owner.
- Ask in Urdu. The prompt requests the question's language and the golden set reports Urdu results separately.
- Use the React frontend to queue uploads, inspect citation passages, search the document list, and check workspace health and Insights. Insights uses `ask_logs` through `/metrics` and `/metrics/recent`.
- Detect tiny or white Word text and surface a warning. Extracted text is treated as untrusted data. Upload checks reject unsupported types, mismatched binary signatures, corrupt files, and textless scans.
- Handle empty libraries with a refusal, exact duplicates with `409`, and competing versions with version and date context. The LLM client can fall back to local Ollama. A database constraint prevents duplicate records during concurrent uploads.

## Tech stack

| Layer | Technology |
| --- | --- |
| API and data contracts | Python 3.12, FastAPI, Uvicorn, Pydantic and pydantic-settings |
| Question workflow and model clients | LangGraph, HTTPX, Tenacity, Groq `openai/gpt-oss-20b`, Ollama `qwen2.5:3b` fallback |
| Embeddings | Ollama `bge-m3`, 1,024 dimensions |
| Storage and retrieval | PostgreSQL 16, pgvector, SQLAlchemy async, asyncpg, PostgreSQL full-text search |
| Extraction | PyMuPDF, pymupdf4llm, python-docx, python-pptx, Python text decoding |
| Auth and limits | PyJWT, bcrypt, SlowAPI |
| Web client | React, Vite, TypeScript, Tailwind CSS, TanStack Query, Motion, IBM Plex |
| Verification | pytest, Jupyter, repository evaluation runner and Groq `qwen/qwen3.8-27b` judge |

## Architecture

```mermaid
flowchart LR
    browser["Browser"] --> web["React web client"]
    web -->|"JWT + HTTP / SSE"| api["FastAPI"]
    api -->|"Uploads"| ingest["Extract, chunk, embed"]
    ingest -->|"Embed chunks"| embed["Ollama · bge-m3"]
    ingest -->|"Write document and chunks"| db["PostgreSQL · pgvector + full-text index"]
    api -->|Questions| graph["LangGraph"]
    api -->|"Accounts, documents, metrics"| db
    graph -->|"Embed question"| embed
    graph -->|"Retrieve owned passages"| db
    graph -->|"Guard and generate"| groq["Groq · Prompt Guard + gpt-oss-20b"]
    graph -.->|"Generation fallback"| ollama["Ollama · qwen2.5:3b"]
```

See [DESIGN.md](DESIGN.md) for the upload and question flows and the reasons behind the defaults.

## Prerequisites

- Windows with PowerShell, Git for cloning, and Python 3.12.
- Node.js 20.19+, 22.13+, or 24+ with npm.
- Docker Desktop with Docker Compose running.
- Ollama running locally. Download the embedding and fallback models with the commands below.
- A free Groq API key for the default guard, generator, and evaluation judge.

```powershell
ollama pull bge-m3
ollama pull qwen2.5:3b
```

## Setup

1. Clone the repository and start in its root.

   ```powershell
   git clone https://github.com/gullsnobar/valumatix-rag.git
   Set-Location valumatix-rag
   Copy-Item .env.example .env
   ```

2. Put your Groq key in `GROQ_API_KEY` in `.env`. Generate a private JWT key and put the output in `JWT_SECRET`. Set a local PostgreSQL password and match it in `DATABASE_URL`.

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Start PostgreSQL, create the Python environment, and install the pinned dependencies.

   ```powershell
   docker compose up -d
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

4. Install the frontend dependencies.

   ```powershell
   Set-Location frontend
   npm install
   Set-Location ..
   ```

## Configuration

Backend settings load from the repository-root `.env` or the process environment. The example contains placeholders. Keep values marked **Secret** in the private configuration. For a different API origin, set `VITE_API_URL` in `frontend/.env.local`.

| Environment variable | Default or requirement | Meaning |
| --- | --- | --- |
| `POSTGRES_USER` | Required, example `rag` | Docker database user |
| `POSTGRES_PASSWORD` | Required, **Secret** | Docker database password |
| `POSTGRES_DB` | Required, example `rag` | Docker database name |
| `DATABASE_URL` | Required, **Secret** | SQLAlchemy async connection URL. The local example uses `postgresql+asyncpg` and host port `5433` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local embedding and fallback chat origin |
| `EMBED_MODEL` | `bge-m3` | Ollama embedding model |
| `EMBED_DIMENSIONS` | `1024` | Expected vector length and stored column dimension |
| `EMBEDDING_BATCH_SIZE` | `16` | Texts per embedding request |
| `FALLBACK_LLM_MODEL` | `qwen2.5:3b` | Ollama chat model |
| `LLM_FALLBACK_ENABLED` | `true` | Enables Ollama generation fallback |
| `LLM_PROVIDER` | `groq` | Compatibility setting. Provider order is defined by `ChatClient` |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible API base |
| `GROQ_API_KEY` | Required, **Secret** | Groq credential for generation, Prompt Guard, and judging |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Primary generation model |
| `JUDGE_MODEL` | `qwen/qwen3.8-27b` | Evaluation judge |
| `GUARD_MODEL` | `meta-llama/llama-prompt-guard-2-86m` | Optional model-based injection check |
| `LLM_MAX_TOKENS` | `400` | Answer generation output cap |
| `LLM_TEMPERATURE` | `0.1` | Answer generation sampling temperature |
| `JWT_SECRET` | Required, **Secret** | Private JWT signing key of at least 32 UTF-8 bytes. The example key is rejected |
| `JWT_ALGORITHM` | `HS256` | Supported signing algorithm |
| `JWT_EXPIRE_MINUTES` | `720` | Access token lifetime in minutes |
| `CHUNK_STRATEGY` | `structure` | Upload splitting mode, `structure` or `fixed` |
| `CHUNK_SIZE_WORDS` | `120` | Fixed window size and structure target |
| `CHUNK_OVERLAP_WORDS` | `25` | Fixed window overlap |
| `CHUNK_MAX_WORDS` | `200` | Structure split and merge cap, with an exception for an intact oversized table row |
| `TOP_K` | `4` | Default number of passages returned per question |
| `RETRIEVAL_MODE` | `hybrid` | Dense-only or dense plus keyword search |
| `CANDIDATE_K` | `20` | Candidate limit per search before truncation or fusion |
| `RRF_K` | `60` | Reciprocal rank fusion constant |
| `MIN_SIMILARITY` | `0.45` | Minimum best cosine similarity across returned passages |
| `MAX_QUESTION_CHARS` | `1000` | Maximum trimmed question length |
| `RATE_LIMIT_ASK` | `20/minute` | Per-client limit shared by both ask routes |
| `RATE_LIMIT_UPLOAD` | `30/minute` | Per-client document upload limit |
| `RATE_LIMIT_LOGIN` | `10/minute` | Per-client login limit |
| `COST_PER_MILLION_INPUT_TOKENS` | `0.0` | USD rate used to estimate prompt cost |
| `COST_PER_MILLION_OUTPUT_TOKENS` | `0.0` | USD rate used to estimate completion cost |
| `MAX_UPLOAD_MB` | `10` | Upload size limit in 1,024 × 1,024-byte units |
| `HTTP_TIMEOUT_SECONDS` | `30.0` | Timeout passed to provider HTTP clients |
| `HTTP_MAX_RETRIES` | `3` | Total attempts under the transient-error retry policy |
| `DATABASE_TIMEOUT_SECONDS` | `30.0` | Pool, connection, and command timeout |
| `CORS_ALLOWED_ORIGIN` | `http://localhost:5173` | Single permitted browser origin |
| `VITE_API_URL` | `http://127.0.0.1:8000` | Frontend API origin |

## Running the service

With PostgreSQL and Ollama running, launch FastAPI from the repository root.

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

In a second PowerShell terminal, run Vite.

```powershell
Set-Location frontend
npm run dev
```

Open [PolicyDesk RAG](http://localhost:5173) to sign up. The workspace starts empty for each account. Use **Load sample documents** to add the readable [corpus files](corpus/), or upload your own. Open **Help** for the guide and example questions. The API is at [127.0.0.1:8000](http://127.0.0.1:8000/docs) and readiness is at [/health](http://127.0.0.1:8000/health).

## API documentation

Open [Swagger UI](http://127.0.0.1:8000/docs). Run `POST /auth/signup` or `POST /auth/login`, copy the returned `access_token`, and paste the token into **Authorize**. API clients send `Authorization: Bearer <token>`.

| Method | Path | Auth | Success | Documented error codes |
| --- | --- | --- | ---: | --- |
| POST | `/auth/signup` | Public | 201 | 409, 422, 503, 500 |
| POST | `/auth/login` | Public | 200 | 401, 422, 429, 503, 500 |
| GET | `/auth/me` | Bearer | 200 | 401, 422, 503, 500 |
| POST | `/documents` | Bearer | 201 | 400, 401, 409, 413, 415, 422, 429, 503, 500 |
| POST | `/documents/samples` | Bearer | 200 | 401, 422, 503, 500 |
| GET | `/documents` | Bearer | 200 | 401, 422, 503, 500 |
| GET | `/documents/{document_id}` | Bearer | 200 | 401, 404, 422, 503, 500 |
| DELETE | `/documents/{document_id}` | Bearer | 204 | 401, 404, 422, 503, 500 |
| POST | `/ask` | Bearer | 200 | 401, 422, 429, 503, 500 |
| POST | `/ask/stream` | Bearer | 200 | 401, 422, 429, 503, 500 |
| GET | `/metrics` | Bearer | 200 | 401, 422, 503, 500 |
| GET | `/metrics/recent` | Bearer | 200 | 401, 422, 503, 500 |
| GET | `/health` | Public | 200 | 503, 500 |

Uploads use multipart field `file`. Sample loading takes no request body and returns `added`, `skipped_duplicates`, and per-file `rejected` entries for the authenticated owner. Ask requests use JSON with `question` and an optional `top_k` from 1 through 10. Refusals are successful responses with `refused: true` and a `refusal_reason`. The stream sends `stage`, validated `token`, and terminal `done` or `error` events. Once streaming starts, the HTTP status stays 200 and a later failure is sent as an `error` event.

Errors generally use `{"error":{"code":"…","message":"…","request_id":"…"}}`. Look for the same request ID in `X-Request-ID`. A dependency failure on `/health` returns its regular readiness body with HTTP 503.

## Running tests

From the activated Python environment with PostgreSQL running, run:

```powershell
python -m pytest -q
```

The current suite passed **117 cases**, including 78 unit cases and 39 API cases. It covers extraction, chunking, retrieval, guardrails, evaluation metrics, uploads and sample loading, cascading deletes, JWT and ownership, SSE, rate limits, fallback, and telemetry. API tests use real PostgreSQL with fake embedding and generation clients, so they avoid live model calls.

Run `npm run lint` and `npm run build` from `frontend/` for the web client.

## Running the evaluation

Run from the repository root with the Python environment active, PostgreSQL and Ollama running, and `GROQ_API_KEY` configured.

```powershell
python -m evals.run
python -m evals.run --retrieval-only
python -m evals.judge_check --export
# Fill human_correctness in evals/results/judge_review.csv with independent 0 or 1 labels.
python -m evals.judge_check --score
```

Use `--no-cache` for a fresh answer and judge run. Retrieval-only mode skips generation and judging. Either run updates `evals/results/latest_summary.json`, and the timestamped artifacts preserve the full runs. For the golden set, ranking comparison, before/after results, and remaining failures, see [EVAL.md](EVAL.md).

## Screenshots

The [screenshots folder](docs/screenshots/) currently contains no images. Expected captures are `login.png`, `signup.png`, `ask-citations.png`, `documents.png`, `insights.png`, `swagger-upload.png`, and `swagger-ask.png`.

## Project structure

```text
app/                   FastAPI, auth, database, retrieval, generation, and LangGraph
  ingestion/           Upload validation, extraction, chunking, and embedding
corpus/                19 fictional demo documents
frontend/              React and TypeScript UI
  src/api/             Typed HTTP, SSE, and session clients
  src/components/      Auth, navigation, Ask, Documents, and Insights
evals/                 Golden set, runner, metrics, judge, and saved results
notebooks/             Extraction, chunking, retrieval, and answering experiments
tests/
  unit/                Component and evaluation tests
  api/                 FastAPI integration tests
plans/                 Original development plan
docs/                  Demo script, graph, screenshots, and AI disclosure
DESIGN.md              Design decisions and trade-offs
EVAL.md                Recorded evaluation results
docker-compose.yml     Local PostgreSQL and pgvector
```

## AI usage

See the [AI usage disclosure](docs/ai-usage/README.md) for tools, model details, and the prompt and conversation records.

## Deployment

Not deployed.
