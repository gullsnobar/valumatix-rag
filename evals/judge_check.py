"""Export judge decisions for human review and measure agreement after labeling."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REVIEW_PATH = RESULTS_DIR / "judge_review.csv"
AGREEMENT_PATH = RESULTS_DIR / "judge_agreement.json"
_REVIEW_COLUMNS = (
    "id", "question", "reference_answer", "system_answer", "judge_correctness",
    "judge_reason", "human_correctness",
)
_REVIEW_SIZE = 12


def _select_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [
        item for item in items
        if item.get("outcome") == "answered"
        and item.get("correctness", {}).get("score") in (0, 1)
    ]
    selected = [
        item
        for score in (1, 0)
        for item in [row for row in eligible if row["correctness"]["score"] == score][:_REVIEW_SIZE // 2]
    ]
    selected_ids = {item["id"] for item in selected}
    selected.extend(item for item in eligible if item["id"] not in selected_ids)
    return selected[:_REVIEW_SIZE]


def export_review() -> int:
    """Export a balanced sample of answered items from the latest answer report."""

    latest = max(RESULTS_DIR.glob("answers_*.json"), default=None)
    if latest is None:
        raise ValueError("No answer reports found. Run the full evaluation first.")
    report = json.loads(latest.read_text(encoding="utf-8"))
    selected = _select_review_items(report["items"])
    with REVIEW_PATH.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=_REVIEW_COLUMNS)
        writer.writeheader()
        for item in selected:
            rating = item["correctness"]
            writer.writerow({
                "id": item["id"], "question": item["question"],
                "reference_answer": item["reference_answer"],
                "system_answer": item["answer"],
                "judge_correctness": rating["score"], "judge_reason": rating["reason"],
                "human_correctness": "",
            })
    return len(selected)


def agreement(pairs: list[tuple[int, int]]) -> dict[str, int | float | None]:
    """Compute observed agreement and Cohen's kappa for binary rating pairs."""

    if not pairs:
        raise ValueError("No human labels are filled in. Enter 0 or 1 in human_correctness.")
    count = len(pairs)
    judge = Counter(first for first, _ in pairs)
    human = Counter(second for _, second in pairs)
    observed = sum(first == second for first, second in pairs) / count
    expected = sum(judge[value] * human[value] for value in (0, 1)) / count**2
    return {
        "labeled_items": count,
        "agreement_rate": observed,
        "cohens_kappa": (observed - expected) / (1 - expected) if expected != 1 else None,
    }


def score_review() -> dict[str, int | float | None]:
    """Read the labeled CSV and save the resulting agreement statistics."""

    pairs = []
    with REVIEW_PATH.open(encoding="utf-8-sig", newline="") as source:
        for line, row in enumerate(csv.DictReader(source), 2):
            human = row["human_correctness"].strip()
            if not human:
                continue
            judge = row["judge_correctness"].strip()
            if human not in {"0", "1"} or judge not in {"0", "1"}:
                raise ValueError(f"Row {line}: judge and human scores must be 0 or 1.")
            pairs.append((int(judge), int(human)))
    result = agreement(pairs)
    AGREEMENT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    """Export the review worksheet or score completed human labels."""

    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--export", action="store_true")
    action.add_argument("--score", action="store_true")
    args = parser.parse_args()
    try:
        if args.export:
            count = export_review()
            print(f"Exported {count} of {_REVIEW_SIZE} requested review items to {REVIEW_PATH}.")
        else:
            result = score_review()
            kappa = result["cohens_kappa"]
            print(f"Agreement: {result['agreement_rate']:.1%} ({result['labeled_items']} labeled items)")
            print("Cohen's kappa:", f"{kappa:.4f}" if kappa is not None else "undefined")
            print(f"Saved {AGREEMENT_PATH}")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
