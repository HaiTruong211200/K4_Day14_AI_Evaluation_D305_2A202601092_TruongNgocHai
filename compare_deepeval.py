"""Run DeepEval answer-side metrics on the recorded Lab 14 artifacts."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path

# DeepEval's default adaptive timeout was too short for this lab's five-context
# judge prompts. Set this before importing DeepEval so retries use the override.
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "180")

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase
from dotenv import load_dotenv

try:
    # New DeepEval releases expose OpenAIModel.
    from deepeval.models import OpenAIModel as DeepEvalOpenAIModel
except ImportError:
    # Compatibility with DeepEval 3.9.x, where the same adapter is GPTModel.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from deepeval.models import GPTModel as DeepEvalOpenAIModel


ROOT = Path(__file__).resolve().parent
ACTUAL_PATH = ROOT / "artifacts" / "actual_answers.json"
GOLDEN_PATH = ROOT / "golden_dataset.json"
OUTPUT_PATH = ROOT / "artifacts" / "deepeval_results.json"
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "contextual_recall",
    "contextual_precision",
    "contextual_relevancy",
)


def _write_checkpoint(model: str, results: list[dict]) -> None:
    payload = {
        "framework": "deepeval",
        "framework_version": importlib.metadata.version("deepeval"),
        "judge_model": model,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": [
            "FaithfulnessMetric",
            "AnswerRelevancyMetric",
            "ContextualRecallMetric",
            "ContextualPrecisionMetric",
            "ContextualRelevancyMetric",
        ],
        "results": results,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    answer_model = os.getenv("OPENAI_MODEL", "").strip()
    judge_model_name = os.getenv("DEEPEVAL_MODEL", "gpt-4.1-mini").strip()
    if not os.getenv("OPENAI_API_KEY", "").strip() or not answer_model:
        raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL must be configured in .env")

    actual = json.loads(ACTUAL_PATH.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    golden_by_id = {row["id"]: row for row in golden["qa_pairs"]}
    answers = actual["answers"][: args.limit]
    judge_model = DeepEvalOpenAIModel(
        model=judge_model_name,
        temperature=0,
        generation_kwargs={"max_completion_tokens": 3000},
    )
    completed: dict[str, dict] = {}
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        completed = {
            row["id"]: row
            for row in previous.get("results", [])
            if all(metric in row for metric in METRIC_NAMES)
        }

    results: list[dict] = []
    for index, answer in enumerate(answers, start=1):
        case_id = answer["id"]
        if case_id in completed:
            results.append(completed[case_id])
            print(f"[{index:02d}/{len(answers):02d}] {case_id} cached", flush=True)
            continue

        print(
            f"[{index:02d}/{len(answers):02d}] {case_id} starting "
            f"with judge={judge_model_name}",
            flush=True,
        )

        test_case = LLMTestCase(
            input=answer["question"],
            actual_output=answer["actual_answer"],
            expected_output=golden_by_id[case_id]["expected_answer"],
            retrieval_context=[chunk["text"] for chunk in answer["retrieved_contexts"]],
        )
        metrics = {
            "faithfulness": FaithfulnessMetric,
            "answer_relevancy": AnswerRelevancyMetric,
            "contextual_recall": ContextualRecallMetric,
            "contextual_precision": ContextualPrecisionMetric,
            "contextual_relevancy": ContextualRelevancyMetric,
        }
        row: dict = {"id": case_id}
        for metric_name, metric_class in metrics.items():
            print(f"  measuring {metric_name}...", flush=True)
            metric = metric_class(
                threshold=0.5,
                model=judge_model,
                include_reason=True,
                async_mode=False,
            )
            metric.measure(test_case, _show_indicator=False)
            row[metric_name] = metric.score
            row[f"{metric_name}_passed"] = metric.is_successful()
            row[f"{metric_name}_reason"] = metric.reason

        results.append(row)
        _write_checkpoint(judge_model_name, results)
        print(
            f"[{index:02d}/{len(answers):02d}] {case_id} "
            + " ".join(
                f"{metric}={row[metric]:.4f}" for metric in METRIC_NAMES
            ),
            flush=True,
        )

    _write_checkpoint(judge_model_name, results)
    print("Averages:")
    for metric_name in METRIC_NAMES:
        average = sum(row[metric_name] for row in results) / len(results)
        print(f"  {metric_name}: {average:.4f}")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
