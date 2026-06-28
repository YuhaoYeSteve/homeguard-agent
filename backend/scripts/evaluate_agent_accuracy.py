import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from app.agent.schemas import ChatResponse, ToolEvent
from app.evaluation.agent_accuracy import (
    EvaluationCase,
    evaluate_cases,
    load_cases,
    render_markdown_report,
    summarize_results,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = BACKEND_ROOT / "evals" / "agent_accuracy_cases.jsonl"
DEFAULT_OUTPUT = BACKEND_ROOT / "evals" / "agent_accuracy_report.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run non-video accuracy evaluation cases against the local Agent API.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help="JSONL case file. Default: {}".format(DEFAULT_CASES),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend base URL. Default: http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Markdown report output path. Default: {}".format(DEFAULT_OUTPUT),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-case total and HTTP read timeout in seconds. Default: 60",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit with code 2 when overall accuracy is below this ratio, for example 0.8.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases. Useful for smoke checks.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=None,
        help="Run only cases in this category. Can be repeated.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Run only the specified case id. Can be repeated.",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if args.category:
        wanted_categories = set(args.category)
        cases = [case for case in cases if case.category in wanted_categories]
    if args.case_id:
        wanted_case_ids = set(args.case_id)
        cases = [case for case in cases if case.id in wanted_case_ids]
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]

    def response_provider(case: EvaluationCase) -> ChatResponse:
        return call_stream_api(
            case=case,
            base_url=args.base_url,
            timeout=args.timeout,
        )

    def progress(index: int, total: int, case: EvaluationCase) -> None:
        print("[{}/{}] {}".format(index, total, case.id), flush=True)

    results = evaluate_cases(cases, response_provider, progress_callback=progress)
    report = render_markdown_report(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    summary = summarize_results(results)
    print("Report written to {}".format(args.output))
    print("total_cases={}".format(summary["total_cases"]))
    print("passed_cases={}".format(summary["passed_cases"]))
    print("overall_accuracy={:.2%}".format(summary["overall_accuracy"]))
    print("route_accuracy={:.2%}".format(summary["route_accuracy"]))
    print("unsafe_tool_block_rate={:.2%}".format(summary["unsafe_tool_block_rate"]))

    if args.fail_under is not None and summary["overall_accuracy"] < args.fail_under:
        print(
            "overall_accuracy below threshold: {:.2%} < {:.2%}".format(
                summary["overall_accuracy"],
                args.fail_under,
            ),
            file=sys.stderr,
        )
        return 2
    return 0


def call_stream_api(
    case: EvaluationCase,
    base_url: str,
    timeout: float,
) -> ChatResponse:
    url = "{}/api/chat/stream".format(base_url.rstrip("/"))
    payload = {
        "conversation_id": "eval_{}".format(case.id),
        "message": case.user_message,
        "client_history": [_model_to_dict(message) for message in case.history],
    }
    last_error = None
    deadline = time.monotonic() + timeout
    answer_chunks = []
    tool_events = []
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    if time.monotonic() > deadline:
                        return _partial_stream_response(
                            case=case,
                            answer_chunks=answer_chunks,
                            tool_events=tool_events,
                            code="EVAL_TIMEOUT",
                            message="case {} exceeded {} seconds without final response".format(
                                case.id,
                                timeout,
                            ),
                        )
                    event = _parse_sse_line(raw_line)
                    if event is None:
                        continue
                    if event.get("type") == "error":
                        last_error = event
                    elif event.get("type") == "answer_delta":
                        delta = event.get("delta")
                        if delta:
                            answer_chunks.append(str(delta))
                    elif event.get("type") == "tool_result" and isinstance(
                        event.get("event"),
                        dict,
                    ):
                        tool_events.append(ToolEvent(**event["event"]))
                    if event.get("type") == "final" and isinstance(event.get("response"), dict):
                        return ChatResponse(**event["response"])
    except httpx.TimeoutException as exc:
        return _partial_stream_response(
            case=case,
            answer_chunks=answer_chunks,
            tool_events=tool_events,
            code="EVAL_TIMEOUT",
            message=str(exc),
        )
    if last_error:
        return _partial_stream_response(
            case=case,
            answer_chunks=answer_chunks,
            tool_events=tool_events,
            code=str(last_error.get("code") or "STREAM_ERROR"),
            message=str(last_error.get("message") or ""),
        )
    return _partial_stream_response(
        case=case,
        answer_chunks=answer_chunks,
        tool_events=tool_events,
        code="STREAM_MISSING_FINAL",
        message="stream finished without final response for {}".format(case.id),
    )


def _parse_sse_line(raw_line: str) -> Any:
    line = raw_line.strip()
    if not line.startswith("data: "):
        return None
    return json.loads(line[len("data: ") :])


def _partial_stream_response(
    case: EvaluationCase,
    answer_chunks: Any,
    tool_events: Any,
    code: str,
    message: str,
) -> ChatResponse:
    return ChatResponse(
        conversation_id="eval_{}".format(case.id),
        assistant_message="".join(answer_chunks),
        tool_events=tool_events,
        error={"code": code, "message": message},
    )


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


if __name__ == "__main__":
    raise SystemExit(main())
