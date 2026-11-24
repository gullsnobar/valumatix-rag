# Plan: Production RAG Service (Portfolio 01)

Deadline: Wednesday 25 November 2026
Budget: about 20 hours
Machine: Windows, CPU only, 16 GB RAM

## Phases

### Phase 0: Environment and repo (1h)
Verified when: Ollama answers in the terminal, pgvector accepts `CREATE EXTENSION vector`, and the repo is on GitHub with `main` and a first feature branch merged.
- Install Python 3.12, Node 20 LTS, Git, Docker Desktop and Ollama.
- Pull `qwen2.5:3b`, `bge-m3` and `llama3.2:3b`.
- Run PostgreSQL 16 with pgvector in Docker (`docker-compose.yml`).
- Create the repo with `.gitignore`, `.env.example`, the folder skeleton and this plan.

### Phase 1: Corpus (1h)
Verified when: 10 documents exist in `corpus/` across PDF, DOCX, PPTX, MD and TXT, and Ghalib has read them.
- Valumatix handbook: Leave v1 (DOCX), Leave v2 (PDF, contradicts v1), Expense Policy with table (PDF), Remote Work (DOCX), Service Catalogue and Pricing (PDF), Onboarding (DOCX), Security & IT (MD), Company Overview (PPTX), FAQ (TXT), Code of Conduct with a hidden injection line (DOCX), and a scanned image-only PDF.

### Phase 2: Notebooks (2.5h), branch `feature/notebooks`
Verified when: each notebook runs top to bottom.
- `01_extraction`, `02_chunking` (fixed window vs heading-aware), `03_embedding_retrieval`, `04_answering`.

### Phase 3: Ingestion API (2h), branch `feature/ingestion`
Verified when: in Swagger, upload returns 201, a duplicate returns 409, an unsupported type returns 415, an empty or scanned PDF returns 400, list returns 200, delete returns 204, and the deleted document's chunks are gone from the DB.
- Files: `config.py`, `schemas.py`, `db.py`, `ingestion/`, `main.py`.

### Phase 4: Ask API (2h), branch `feature/ask-endpoint`
Verified when: the answer cites only retrieved chunk ids, an unanswerable question is refused, and the response includes chunk scores. The streaming endpoint emits the stages, then the tokens, then a final event.
- Files: `retrieval.py`, `generation.py`, `llm_client.py`.

### Phase 5: Evaluation (3h), branch `feature/evals`
Verified when: `python -m evals.run` writes `evals/results/*.json` and EVAL.md reports the numbers.
- Golden set of at least 30 questions: at least 5 unanswerable, plus reworded, multi-part and contradiction questions.
- Retrieval comparison (no LLM): chunking A vs B, then reranking on vs off. Metrics are hit@k, recall@k and MRR.
- Answer eval on the winning configuration: faithfulness, correctness and refusal accuracy, scored by the llama3.2:3b judge.
- Judge reliability: 10 hand labels and the agreement rate between judge and hand labels.

### Phase 6: Guardrails, errors and tests (2h), branch `feature/guardrails`
Verified when: `pytest` passes and each guardrail has a test.
- Input guardrails: empty or too long, off-topic, injection and jailbreak.
- Output guardrails: citations must be a subset of the retrieved chunks, no leak of the prompt or keys.
- Documents: chunk text is treated as data, and corrupt files are rejected.
- Errors: 429 via slowapi, 503 on Ollama or DB timeout.

### Phase 7: Frontend (2h), branch `feature/frontend`
Verified when: the full demo flow works in the browser.
- React + Vite + TypeScript + Tailwind + Motion.
- Upload with progress, document list, streaming chat, citations, and the chunks panel with scores.

### Phase 8: Stretch bonuses (3h+), in this order
- A: JWT auth (`feature/auth`).
- C: Langfuse tracing, p50/p95 latency and tokens (`feature/observability`).
- H: deploy to the Dokploy VPS (`feature/deploy`).
- B: Urdu questions and a separate eval section (`feature/multilingual`).

### Phase 9: Submission (2h)
- README, DESIGN.md, EVAL.md, Swagger screenshots, AI-usage file (prompts and this chat), and the demo video.

## Decision log
| Decision | Chosen | Why |
| --- | --- | --- |
| Corpus | Invented Valumatix handbook | Full control of facts; contradiction and injection cases planted deliberately |
| LLM | qwen2.5:3b via Ollama | Free, private, usable on CPU, follows instructions well |
| Embeddings | bge-m3 via Ollama | Multilingual, 1024 dimensions, runs locally |
| Vector DB | PostgreSQL + pgvector | One DB for users, docs and chunks; cascading deletes; full-text search for hybrid |
| Judge | llama3.2:3b | Different model family from the answerer; validated against hand labels |
| Comparisons | Chunking A vs B, reranking on vs off | Retrieval-only metrics, so fast on CPU |
| RAG framework | Own code, no LangChain | Every line explainable |
| Frontend | React + Vite + Tailwind + Motion | Bonus D; streaming keeps the CPU wait feeling smooth |

## Not yet specified
- Phase 4: final chunk size and top-k, decided from the Phase 0 speed test and the Phase 2 notebooks.
- Phase 8 H: whether the VPS has enough RAM for Ollama. Checked when we reach that phase.

## Always / Never
- Always: secrets in `.env` only; timeouts and retries on every Ollama and DB call; work on feature branches merged into `main`.
- Never: commit `.env`; use no-code RAG builders; log secrets.

## Progress
| Phase | Status |
| --- | --- |
| 0 | in progress |
| 1–9 | pending |