"""Compare retrieval configurations and score answers from the production graph."""

import argparse
import asyncio
import hashlib
import json
import logging
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import quantiles
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.asking import AskService
from app.config import Settings, get_settings
from app.db import AskLog, Document, SessionFactory, engine, init_db
from app.errors import NoExtractableTextError, RagServiceError, RateLimitedError
from app.ingestion.extractors import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import ingest_document
from app.llm_client import ChatClient, EmbeddingClient
from app.retrieval import retrieve
from app.schemas import AskRequest
from evals.judge import MAX_RATE_RETRIES, JudgeClient, summarize_judgements
from evals.metrics import GoldenItem, aggregate, hit_at_k, matches_source, recall_at_k, reciprocal_rank

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"
GOLDEN_SET = ROOT / "evals" / "golden_set.json"
CONFIGS = ("fixed+dense", "fixed+hybrid", "structure+dense", "structure+hybrid")
_ITEM_PAUSE_SECONDS = 8
_EVAL_LOCK_ID = 1625130855
_CACHE_VERSION = 2
logger = logging.getLogger(__name__)

type Payload = dict[str, Any]


def write_json(path: Path, payload: object) -> None:
    """Atomically save a UTF-8 JSON artifact."""

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class ResultCache:
    """Cache completed provider responses separately from temporary failures."""

    def __init__(self, path: Path, *, enabled: bool) -> None:
        """Load the on-disk cache, or keep it disabled for a fresh run."""

        self._path = path
        self._enabled = enabled
        self._records: Payload = (
            json.loads(path.read_text(encoding="utf-8")) if enabled and path.exists() else {}
        )

    def get(self, category: str, key: str) -> Payload | None:
        """Look up a result for this task and input fingerprint."""

        return self._records.get(category, {}).get(key)

    def put(self, category: str, key: str, value: Payload) -> None:
        """Persist a completed result immediately for resumability."""

        if self._enabled:
            self._records.setdefault(category, {})[key] = value
            write_json(self._path, self._records)


class _QuestionEmbeddings(EmbeddingClient):
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


@asynccontextmanager
async def _exclusive_run() -> AsyncIterator[None]:
    # The two benchmark owners are reserved and reused across runs.
    async with engine.connect() as connection:
        locked = await connection.scalar(select(func.pg_try_advisory_lock(_EVAL_LOCK_ID)))
        if not locked:
            raise RuntimeError("Another evaluation is using the reserved eval owners.")
        await connection.commit()
        try:
            yield
        finally:
            await connection.execute(select(func.pg_advisory_unlock(_EVAL_LOCK_ID)))


async def _clear_documents(owners: set[str]) -> None:
    async with SessionFactory.begin() as session:
        await session.execute(delete(Document).where(Document.owner_id.in_(owners)))


async def _index_corpus(
    strategy: str, files: list[Path], embedder: EmbeddingClient, settings: Settings
) -> Payload:
    owner = f"eval-{strategy}"
    scoped_settings = settings.model_copy(update={"chunk_strategy": strategy})
    skipped = []
    indexed = []
    async with SessionFactory() as session:
        for path in files:
            data = await asyncio.to_thread(path.read_bytes)
            try:
                document = await ingest_document(data, path.name, owner, session, embedder, scoped_settings)
                indexed.append({"file": path.name, "chunks": document.num_chunks})
            except NoExtractableTextError as exc:
                skipped.append({"file": path.name, "reason": exc.error_code})
    logger.info("Indexed %d files for %s. Skipped %d.", len(indexed), owner, len(skipped))
    return {"indexed": indexed, "skipped": skipped}


def _retrieval_report(rows: list[Payload]) -> Payload:
    return {"count": len(rows), **aggregate([row["metrics"] for row in rows])}


async def _measure_retrieval(
    config: str, items: list[GoldenItem], embedder: EmbeddingClient, settings: Settings
) -> Payload:
    strategy, mode = config.split("+")
    configuration = settings.model_copy(update={"chunk_strategy": strategy, "retrieval_mode": mode})
    rows = []
    async with SessionFactory() as session:
        for item in items:
            # Changing top_k only truncates the same ranking, so prefixes are identical.
            chunks = await retrieve(
                session, f"eval-{strategy}", item["question"], embedder, configuration, top_k=8
            )
            scores = {
                "hit@1": hit_at_k(chunks, item, 1),
                "hit@4": hit_at_k(chunks, item, 4),
                "recall@4": recall_at_k(chunks, item, 4),
                "recall@8": recall_at_k(chunks, item, 8),
                "mrr": reciprocal_rank(chunks, item),
            }
            rows.append({
                **item, "metrics": scores,
                "retrieved": [
                    {**asdict(chunk), "matched_sources": [
                        source["file"] for source in item["expected_sources"]
                        if matches_source(chunk, source)
                    ]}
                    for chunk in chunks
                ],
            })
    overall = _retrieval_report(rows)
    logger.info("%s MRR %.4f, recall@4 %.4f", config, overall["mrr"], overall["recall@4"])
    return {
        "overall": overall,
        "languages": {
            language: _retrieval_report([row for row in rows if row["language"] == language])
            for language in ("en", "ur")
        },
        "items": rows,
    }


async def _ask(
    item: GoldenItem, owner: str, embedder: EmbeddingClient, chat: ChatClient, settings: Settings
) -> Payload:
    for retries in range(MAX_RATE_RETRIES + 1):
        request_id = f"eval-{item['id']}-{uuid4()}"
        try:
            async with SessionFactory() as session:
                service = AskService(session, embedder, chat, settings, owner, request_id)
                result = await service.answer(AskRequest(question=item["question"], top_k=4))
                latency = await session.scalar(
                    select(AskLog.latency_ms)
                    .where(AskLog.owner_id == owner, AskLog.request_id == request_id)
                )
            answer = result.model_dump(mode="json")
            return {
                **answer,
                "latency_ms": latency,
                "retrieved_filenames": [chunk.filename for chunk in result.chunks],
                "rate_retries": retries,
            }
        except RateLimitedError as exc:
            if retries == MAX_RATE_RETRIES:
                return {"error": exc.error_code, "rate_retries": retries}
            logger.info("%s rate-limited. Retrying in %.1f s.", item["id"], exc.retry_after_seconds)
            await asyncio.sleep(exc.retry_after_seconds)
        except RagServiceError as exc:
            logger.warning("%s answer failed (%s).", item["id"], exc.error_code)
            return {"error": exc.error_code, "rate_retries": retries}
    raise AssertionError("Rate limit retry loop ended without a result")


def _config_signature(config: str, settings: Settings, corpus_digest: str) -> Payload:
    fields = (
        "chunk_size_words", "chunk_overlap_words", "chunk_max_words", "embed_model",
        "candidate_k", "rrf_k", "min_similarity", "llm_max_tokens", "llm_temperature", "guard_model",
    )
    return {
        "version": _CACHE_VERSION,
        "configuration": config,
        "corpus_digest": corpus_digest,
        **{field: getattr(settings, field) for field in fields},
    }


async def _measure_answers(
    winner: str, items: list[GoldenItem], embedder: EmbeddingClient,
    settings: Settings, cache: ResultCache, corpus_digest: str,
) -> list[Payload]:
    strategy, mode = winner.split("+")
    configuration = settings.model_copy(update={
        "chunk_strategy": strategy, "retrieval_mode": mode, "llm_fallback_enabled": False,
    })
    signature = _config_signature(winner, configuration, corpus_digest)
    chat = ChatClient(configuration)
    rows = []
    try:
        async with JudgeClient(configuration) as judge:
            for index, item in enumerate(items, 1):
                if index > 1:
                    await asyncio.sleep(_ITEM_PAUSE_SECONDS)
                logger.info("Evaluating %s (%d/%d).", item["id"], index, len(items))
                key = _digest([signature, item["id"], item["question"], configuration.llm_model])
                answer = cache.get("answer", key)
                from_cache = answer is not None
                if answer is None:
                    answer = await _ask(item, f"eval-{strategy}", embedder, chat, configuration)
                    if "error" not in answer:
                        cache.put("answer", key, answer)
                row = {**item, **answer, "cached": from_cache}
                if "error" in answer:
                    row["outcome"] = "error"
                elif item["answerable"]:
                    row["outcome"] = "false_refusal" if answer["refused"] else "answered"
                    await _judge_answer(row, signature, judge, cache, configuration)
                else:
                    row["outcome"] = "correct_refusal" if answer["refused"] else "hallucination"
                rows.append(row)
                logger.info("%s: %s", item["id"], row["outcome"])
    finally:
        await chat.aclose()
    return rows


async def _judge_answer(
    row: Payload, signature: Payload, judge: JudgeClient, cache: ResultCache, settings: Settings
) -> None:
    cited = [chunk["text"] for chunk in row["chunks"] if chunk["cited"]]
    # Include the judged input so a regenerated answer cannot reuse an unrelated score.
    judge_signature = {
        **signature,
        "judged_input": _digest([row["answer"], row["reference_answer"], row["key_facts"], cited]),
    }
    key = _digest([judge_signature, row["id"], row["question"], settings.judge_model])
    kinds = ("correctness",) if row["refused"] else ("faithfulness", "correctness")
    for kind in kinds:
        rating = cache.get(kind, key)
        if rating is None:
            if kind == "faithfulness":
                rating = await judge.faithfulness(row["answer"], cited)
            else:
                rating = await judge.correctness(
                    row["question"], row["reference_answer"], row["answer"],
                    key_facts=row["key_facts"],
                )
            if rating["score"] is not None or rating["reason"] == "judge_parse_error":
                cache.put(kind, key, rating)
        row[kind] = rating


def _answer_summary(rows: list[Payload], settings: Settings) -> Payload:
    outcomes = Counter(row["outcome"] for row in rows)
    answerable = sum(row["answerable"] for row in rows)
    unanswerable = len(rows) - answerable
    latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
    percentiles = quantiles(latencies, n=100, method="inclusive") if len(latencies) > 1 else latencies * 99
    result = {
        "items": len(rows), "answerable": answerable, "unanswerable": unanswerable,
        "answered": outcomes["answered"],
        "correct_refusals": outcomes["correct_refusal"],
        "hallucinations": outcomes["hallucination"],
        "false_refusals": outcomes["false_refusal"],
        "errors": outcomes["error"],
        "refusal_accuracy": outcomes["correct_refusal"] / unanswerable if unanswerable else None,
        "hallucination_rate": outcomes["hallucination"] / unanswerable if unanswerable else None,
        "latency_samples": len(latencies),
        "p50_latency_ms": round(percentiles[49], 2) if percentiles else None,
        "p95_latency_ms": round(percentiles[94], 2) if percentiles else None,
        "provider_counts": dict(Counter(row["provider"] for row in rows if row.get("provider"))),
        "prompt_tokens": sum(row.get("prompt_tokens", 0) for row in rows),
        "completion_tokens": sum(row.get("completion_tokens", 0) for row in rows),
        "cached": sum(row["cached"] for row in rows),
    }
    result["estimated_cost_usd"] = (
        result["prompt_tokens"] * settings.cost_per_million_input_tokens
        + result["completion_tokens"] * settings.cost_per_million_output_tokens
    ) / 1_000_000
    for kind in ("faithfulness", "correctness"):
        result[kind] = summarize_judgements([row[kind] for row in rows if kind in row])
    return result


def _show_summary(summary: Payload) -> None:
    scores = summary["retrieval"]
    print(f"{'Configuration':<18} {'Hit@1':>7} {'Hit@4':>7} {'Recall@4':>9} {'Recall@8':>9} {'MRR':>7}")
    for name, report in scores.items():
        print(f"{name:<18} " + " ".join(
            f"{report['overall'][metric]:>{width}.3f}"
            for metric, width in (("hit@1", 7), ("hit@4", 7), ("recall@4", 9), ("recall@8", 9), ("mrr", 7))
        ))
    print(f"Winner: {summary['winner']}")
    if summary["answers"] is not None:
        print(f"\n{'Language':<9} {'Correctness':>12} {'Faithfulness':>12} {'Refusals':>9} {'Hallucinations':>14} {'Errors':>7}")
        for name, group in summary["answers"].items():
            correctness = f"{group['correctness']['passed']}/{group['correctness']['scored']}"
            faithfulness = f"{group['faithfulness']['passed']}/{group['faithfulness']['scored']}"
            refusals = f"{group['correct_refusals']}/{group['unanswerable']}"
            print(f"{name:<9} {correctness:>12} {faithfulness:>12} {refusals:>9} {group['hallucinations']:>14} {group['errors']:>7}")


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    items: list[GoldenItem] = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    answerable = [item for item in items if item["answerable"]]
    files = sorted(
        path for path in (ROOT / "corpus").rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    corpus_digest = _digest([[str(path.relative_to(ROOT)), hashlib.sha256(path.read_bytes()).hexdigest()] for path in files])
    configurations = list(dict.fromkeys(args.configs))
    strategies = list(dict.fromkeys(name.split("+")[0] for name in configurations))
    owners = {f"eval-{strategy}" for strategy in strategies}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%fZ")
    retrieval_path = RESULTS_DIR / f"retrieval_{timestamp}.json"
    answers_path = RESULTS_DIR / f"answers_{timestamp}.json"
    embedder = EmbeddingClient(settings)
    try:
        async with _exclusive_run():
            await init_db()
            await _clear_documents(owners)
            try:
                index = {strategy: await _index_corpus(strategy, files, embedder, settings) for strategy in strategies}
                questions = [item["question"] for item in answerable]
                vectors = _QuestionEmbeddings(dict(zip(questions, await embedder.embed(questions), strict=True)))
                retrieval = {
                    name: await _measure_retrieval(name, answerable, vectors, settings)
                    for name in configurations
                }
                winner = max(configurations, key=lambda name: (
                    retrieval[name]["overall"]["mrr"], retrieval[name]["overall"]["recall@4"],
                ))
                write_json(retrieval_path, {
                    "timestamp": timestamp, "index": index, "winner": winner,
                    "mrr_depth": 8, "configurations": retrieval,
                })
                summary = {
                    "timestamp": timestamp, "winner": winner, "retrieval_file": retrieval_path.name,
                    "answers_file": None, "answers": None,
                    "retrieval": {
                        name: {key: report[key] for key in ("overall", "languages")}
                        for name, report in retrieval.items()
                    },
                }
                if not args.retrieval_only:
                    cache = ResultCache(RESULTS_DIR / "cache.json", enabled=not args.no_cache)
                    rows = await _measure_answers(winner, items, embedder, settings, cache, corpus_digest)
                    answer_summary = {
                        "overall": _answer_summary(rows, settings),
                        **{
                            language: _answer_summary([row for row in rows if row["language"] == language], settings)
                            for language in ("en", "ur")
                        },
                    }
                    write_json(answers_path, {
                        "timestamp": timestamp, "configuration": winner,
                        "answer_model": settings.llm_model, "judge_model": settings.judge_model,
                        "summary": answer_summary, "items": rows,
                    })
                    summary.update(answers_file=answers_path.name, answers=answer_summary)
                write_json(RESULTS_DIR / "latest_summary.json", summary)
                _show_summary(summary)
            finally:
                await _clear_documents(owners)
                logger.info("Removed documents owned by %s.", ", ".join(sorted(owners)))
    finally:
        await embedder.aclose()
        await engine.dispose()


def main() -> None:
    """Read CLI options and execute the requested evaluation stages."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-only", action="store_true", help="Skip generation and judging.")
    parser.add_argument("--configs", nargs="+", choices=CONFIGS, default=CONFIGS)
    parser.add_argument("--no-cache", action="store_true", help="Avoid reading or writing model results.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logger.setLevel(logging.INFO)
    logging.getLogger("evals.judge").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
