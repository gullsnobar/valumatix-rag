"""Re-score saved baseline answers using the current key-facts correctness rule."""

import asyncio
import json
import logging

from app.config import get_settings
from evals.judge import JudgeClient, summarize_judgements
from evals.metrics import GoldenItem
from evals.run import GOLDEN_SET, RESULTS_DIR, write_json

logger = logging.getLogger(__name__)
_JUDGE_PAUSE_SECONDS = 2


async def _rejudge_baseline() -> None:
    source = RESULTS_DIR / "baseline_answers.json"
    destination = RESULTS_DIR / "baseline_rejudged.json"
    baseline = json.loads(source.read_text(encoding="utf-8"))
    golden: list[GoldenItem] = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in golden}
    for row in baseline["items"]:
        item = by_id[row["id"]]
        if any(row[field] != item[field] for field in ("question", "answerable", "language")):
            raise ValueError(f"Golden item {item['id']} does not match the saved baseline.")

    settings = get_settings()
    requests = 0
    async with JudgeClient(settings) as judge:
        for row in baseline["items"]:
            item = by_id[row["id"]]
            row["key_facts"] = item["key_facts"]
            if not item["answerable"] or "error" in row:
                continue
            if requests:
                await asyncio.sleep(_JUDGE_PAUSE_SECONDS)
            row["correctness"] = await judge.correctness(
                item["question"], item["reference_answer"], row["answer"],
                key_facts=item["key_facts"],
            )
            requests += 1
            logger.info("Re-judged %s (%d).", item["id"], requests)

    for group in ("overall", "en", "ur"):
        ratings = [
            row["correctness"] for row in baseline["items"]
            if "correctness" in row and (group == "overall" or row["language"] == group)
        ]
        baseline["summary"][group]["correctness"] = summarize_judgements(ratings)
    baseline["judge_model"] = settings.judge_model
    baseline["correctness_rule"] = "all_key_facts_no_reference_contradictions"
    write_json(destination, baseline)
    logger.info("Saved %s.", destination.name)


def main() -> None:
    """Re-judge the baseline without regenerating answers or timing new asks."""

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logger.setLevel(logging.INFO)
    logging.getLogger("evals.judge").setLevel(logging.INFO)
    asyncio.run(_rejudge_baseline())


if __name__ == "__main__":
    main()
