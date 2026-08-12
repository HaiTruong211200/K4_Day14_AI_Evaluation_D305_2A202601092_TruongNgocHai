"""Local dashboard server for the Lab 14 RAG evaluation pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from domain_assistant import DomainAssistant
from template import RAGASEvaluator


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "dashboard"
GOLDEN = json.loads((ROOT / "golden_dataset.json").read_text(encoding="utf-8"))
GOLDEN_BY_QUESTION = {row["question"]: row for row in GOLDEN["qa_pairs"]}


class DashboardHandler(SimpleHTTPRequestHandler):
    assistant: DomainAssistant | None = None
    evaluator = RAGASEvaluator()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/benchmark":
            path = ROOT / "artifacts" / "benchmark_results.json"
            if not path.exists():
                self._json({"error": "benchmark_results.json not found"}, 404)
                return
            self._json(json.loads(path.read_text(encoding="utf-8")))
            return
        if route == "/api/golden-questions":
            self._json(
                [
                    {"id": row["id"], "question": row["question"]}
                    for row in GOLDEN["qa_pairs"]
                ]
            )
            return
        if route == "/api/deepeval":
            path = ROOT / "artifacts" / "deepeval_results.json"
            if not path.exists():
                self._json(
                    {
                        "available": False,
                        "message": "DeepEval LLM results are not available yet.",
                        "results": [],
                    }
                )
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            required = {
                "faithfulness",
                "answer_relevancy",
                "contextual_recall",
                "contextual_precision",
                "contextual_relevancy",
            }
            valid_results = [
                row
                for row in payload.get("results", [])
                if required.issubset(row)
            ]
            self._json(
                {
                    "available": bool(valid_results),
                    "message": (
                        None
                        if valid_results
                        else "DeepEval file exists but has no complete five-metric cases."
                    ),
                    "judge_model": payload.get("judge_model"),
                    "results": valid_results,
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/ask":
            self._json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(body.get("question", "")).strip()
            if not question:
                raise ValueError("Question must not be empty")

            if self.assistant is None:
                self.__class__.assistant = DomainAssistant.from_corpus(
                    ROOT / "data" / "technology_store", top_k=5
                )
            response = self.assistant.answer_with_trace(question)
            contexts = [chunk.text for chunk in response.retrieved_chunks]
            joined_context = "\n\n".join(contexts)
            gold = GOLDEN_BY_QUESTION.get(question)

            faithfulness = self.evaluator.evaluate_faithfulness(
                response.actual_answer, joined_context
            )
            relevance = self.evaluator.evaluate_relevance(
                response.actual_answer, question
            )
            metrics: dict[str, float | None] = {
                "faithfulness": faithfulness,
                "relevance": relevance,
                "completeness": None,
                "context_recall": None,
                "context_precision": None,
                "overall": None,
            }
            if gold is not None:
                result = self.evaluator.run_full_eval(
                    answer=response.actual_answer,
                    question=question,
                    context=joined_context,
                    expected=gold["expected_answer"],
                    contexts=contexts,
                )
                metrics.update(
                    {
                        "faithfulness": result.faithfulness,
                        "relevance": result.relevance,
                        "completeness": result.completeness,
                        "context_recall": result.context_recall,
                        "context_precision": result.context_precision,
                        "overall": result.overall_score(),
                    }
                )

            self._json(
                {
                    "question": question,
                    "answer": response.actual_answer,
                    "matched_golden": gold["id"] if gold else None,
                    "expected_answer": gold["expected_answer"] if gold else None,
                    "metrics": metrics,
                    "chunks": [asdict(chunk) for chunk in response.retrieved_chunks],
                }
            )
        except Exception as exc:
            self._json({"error": str(exc)}, 400)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    print("RAG Evaluation Studio: http://127.0.0.1:8765", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
