"""Run DeepEval's deterministic ExactMatchMetric on all recorded answers."""

from __future__ import annotations

import json
from pathlib import Path

from deepeval.metrics import ExactMatchMetric
from deepeval.test_case import LLMTestCase


ROOT = Path(__file__).resolve().parent


def main() -> None:
    golden = json.loads((ROOT / "golden_dataset.json").read_text(encoding="utf-8"))
    actual = json.loads(
        (ROOT / "artifacts" / "actual_answers.json").read_text(encoding="utf-8")
    )
    expected_by_id = {row["id"]: row for row in golden["qa_pairs"]}
    results = []
    for answer in actual["answers"]:
        metric = ExactMatchMetric()
        test_case = LLMTestCase(
            input=answer["question"],
            actual_output=answer["actual_answer"],
            expected_output=expected_by_id[answer["id"]]["expected_answer"],
        )
        metric.measure(test_case, _show_indicator=False)
        results.append(
            {"id": answer["id"], "score": metric.score, "passed": metric.is_successful()}
        )

    output = {
        "framework": "deepeval",
        "framework_version": "3.9.9",
        "metric": "ExactMatchMetric",
        "total": len(results),
        "passed": sum(row["passed"] for row in results),
        "average": sum(row["score"] for row in results) / len(results),
        "results": results,
    }
    output_path = ROOT / "artifacts" / "deepeval_exact_match_results.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"DeepEval ExactMatch: {output['passed']}/{output['total']} passed")
    print(f"Average: {output['average']:.4f}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
