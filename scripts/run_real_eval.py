from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_index import main as rebuild_knowledge_index
from src.api.app import create_app
from src.bootstrap.container import get_service_container
from src.config import get_settings
from src.contracts.core import RunStatus
from src.evaluation import RuleBasedResponseQualityBaseline
from src.workers.ticket_worker import TicketWorker


DEFAULT_SAMPLES_PATH = PROJECT_ROOT / "evals" / "samples" / "customer_support_eval_zh.jsonl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / ".artifacts" / "evals" / "real_eval_report.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    route_hits = sum(
        1 for item in records if item["primary_route"] == item["expected_primary_route"]
    )
    escalation_hits = sum(
        1
        for item in records
        if item["needs_escalation"] == item["expected_escalation"]
    )
    quality_scores = [
        item["response_quality"]["overall_score"]
        for item in records
        if _get_nested_number(item.get("response_quality"), "overall_score") is not None
    ]
    trajectory_scores = [
        item["trajectory_evaluation"]["score"]
        for item in records
        if _get_nested_number(item.get("trajectory_evaluation"), "score") is not None
    ]
    judge_statuses = [_get_response_quality_status(item) for item in records]
    failures = [
        {
            "sample_id": item["sample_id"],
            "route_mismatch": item["primary_route"] != item["expected_primary_route"],
            "escalation_mismatch": item["needs_escalation"] != item["expected_escalation"],
            "trajectory_score": _get_nested_number(item.get("trajectory_evaluation"), "score"),
            "http_status": item["http_status"],
            "response_quality_status": _get_response_quality_status(item),
        }
        for item in records
        if item["primary_route"] != item["expected_primary_route"]
        or item["needs_escalation"] != item["expected_escalation"]
        or (_get_nested_number(item.get("trajectory_evaluation"), "score") or 0.0) < 5.0
        or item["http_status"] not in {202, 502}
        or _get_response_quality_status(item) != "succeeded"
    ]

    return {
        "total_samples": len(records),
        "route_accuracy": round(route_hits / len(records), 3) if records else 0.0,
        "escalation_accuracy": round(escalation_hits / len(records), 3) if records else 0.0,
        "avg_response_quality_score": round(sum(quality_scores) / len(quality_scores), 3)
        if quality_scores
        else 0.0,
        "avg_trajectory_score": round(sum(trajectory_scores) / len(trajectory_scores), 3)
        if trajectory_scores
        else 0.0,
        "response_quality_judge": {
            "succeeded_count": sum(1 for status in judge_statuses if status == "succeeded"),
            "failed_count": sum(1 for status in judge_statuses if status == "failed"),
            "unavailable_count": sum(1 for status in judge_statuses if status == "unavailable"),
        },
        "failed_samples": failures,
    }


def _build_payload(
    *,
    settings,
    records: list[dict[str, Any]],
    api_base_url: str | None,
    host: str,
    port: int,
    disable_gmail: bool,
    active_knowledge_source_path: Path,
    active_knowledge_db_path: Path,
    rebuild_index: bool,
    backup_path: Path | None,
    eval_run_id: str,
    in_progress: bool,
) -> dict[str, Any]:
    return {
        "mode": {
            "use_real_llm": True,
            "gmail": "disabled" if disable_gmail else "enabled",
            "knowledge_provider": "local_real",
            "policy_provider": "static_real",
            "database": "configured_runtime",
            "transport": "http",
            "api_base_url": api_base_url or f"http://{host}:{port}",
            "knowledge_source_path": str(active_knowledge_source_path),
            "knowledge_db_path": str(active_knowledge_db_path),
            "knowledge_index_rebuilt": rebuild_index,
            "knowledge_index_backup_path": str(backup_path) if backup_path else None,
            "llm_model": settings.llm.chat_model,
            "embedding_model": settings.embedding.model,
            "eval_run_id": eval_run_id,
            "in_progress": in_progress,
        },
        "records": records,
        "summary": build_report(records),
    }


def _write_report(
    *,
    report_path: Path,
    settings,
    records: list[dict[str, Any]],
    api_base_url: str | None,
    host: str,
    port: int,
    disable_gmail: bool,
    active_knowledge_source_path: Path,
    active_knowledge_db_path: Path,
    rebuild_index: bool,
    backup_path: Path | None,
    eval_run_id: str,
    in_progress: bool,
) -> dict[str, Any]:
    payload = _build_payload(
        settings=settings,
        records=records,
        api_base_url=api_base_url,
        host=host,
        port=port,
        disable_gmail=disable_gmail,
        active_knowledge_source_path=active_knowledge_source_path,
        active_knowledge_db_path=active_knowledge_db_path,
        rebuild_index=rebuild_index,
        backup_path=backup_path,
        eval_run_id=eval_run_id,
        in_progress=in_progress,
    )
    _ensure_parent(report_path)
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return payload


def _clear_runtime_caches() -> None:
    from src.config import get_settings

    get_settings.cache_clear()
    get_service_container.cache_clear()


def _apply_runtime_overrides(
    *,
    disable_gmail: bool,
    knowledge_source_path: Path | None,
    knowledge_db_path: Path | None,
) -> None:
    if disable_gmail:
        os.environ["GMAIL_ENABLED"] = "false"
    if knowledge_source_path is not None:
        os.environ["KNOWLEDGE_SOURCE_PATH"] = str(knowledge_source_path)
    if knowledge_db_path is not None:
        os.environ["KNOWLEDGE_DB_PATH"] = str(knowledge_db_path)
    _clear_runtime_caches()


def _backup_existing_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = index_path.parent / f"{index_path.name}_backup_{timestamp}"
    shutil.move(str(index_path), str(backup_path))
    return backup_path


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


class LocalApiServer:
    def __init__(self, *, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> str:
        app = create_app()
        config = uvicorn.Config(app, host=self._host, port=self._port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        base_url = f"http://{self._host}:{self._port}"
        for _ in range(120):
            try:
                response = requests.get(f"{base_url}/docs", timeout=2)
                if response.status_code == 200:
                    return base_url
            except Exception:
                time.sleep(0.5)

        raise RuntimeError(f"API server did not become ready at {base_url}.")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)


class LocalWorkerRunner:
    def __init__(self, *, worker_id: str = "real-eval-worker") -> None:
        self._container = get_service_container()
        self._worker = TicketWorker(
            store=self._container.ticket_store,
            container=self._container,
            worker_id=worker_id,
        )

    def run_once(self) -> Any:
        return self._worker.run_once()


def _build_trace_fallback(
    *,
    expected_route_template: str,
    actual_route: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "score": 0.0,
        "expected_route": expected_route_template,
        "actual_route": actual_route,
        "violations": [{"type": "run_failed", "message": reason}],
    }


def _get_nested_number(payload: dict[str, Any] | None, key: str) -> float | int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if isinstance(value, (int, float)):
        return value
    return None


def _get_response_quality_status(item: dict[str, Any]) -> str:
    status = str(item.get("response_quality_status") or "").strip().lower()
    if status in {"succeeded", "failed", "unavailable"}:
        return status
    return "succeeded" if item.get("response_quality") is not None else "failed"


def _extract_response_quality_status(trace_payload: dict[str, Any]) -> str:
    for event in trace_payload.get("events", []):
        if event.get("event_name") != "response_quality_judge":
            continue
        metadata = event.get("metadata") or {}
        status = str(metadata.get("judge_status") or "").strip().lower()
        if status in {"succeeded", "failed"}:
            return status
        event_status = str(event.get("status") or "").strip().lower()
        if event_status in {"succeeded", "failed"}:
            return event_status
    return "succeeded" if trace_payload.get("response_quality") is not None else "unavailable"


def _build_response_quality_baseline(
    *,
    sample: dict[str, Any],
    trace_payload: dict[str, Any],
    snapshot_payload: dict[str, Any],
) -> dict[str, Any] | None:
    latest_run = snapshot_payload.get("latest_run") or {}
    draft_text = _extract_draft_text(trace_payload)
    if not draft_text:
        return None
    final_action = latest_run.get("final_action")
    baseline = RuleBasedResponseQualityBaseline()
    return baseline.evaluate(
        email_subject=sample.get("email_subject"),
        email_body=sample.get("email_body"),
        draft_text=draft_text,
        evidence_summary=_extract_latest_draft_evidence_summary(trace_payload),
        policy_summary=None,
        primary_route=snapshot_payload["ticket"].get("primary_route"),
        final_action=final_action,
    )


def _extract_draft_text(trace_payload: dict[str, Any]) -> str | None:
    for event in reversed(trace_payload.get("events", [])):
        if event.get("event_name") not in {"create_gmail_draft", "clarify_request", "close_ticket"}:
            continue
        outputs = event.get("outputs") or {}
        if isinstance(outputs, dict):
            draft_versions = outputs.get("draft_versions")
            if isinstance(draft_versions, list) and draft_versions:
                latest = draft_versions[-1]
                if isinstance(latest, dict):
                    content_text = latest.get("content_text")
                    if isinstance(content_text, str) and content_text.strip():
                        return content_text
    return None


def _extract_latest_draft_evidence_summary(trace_payload: dict[str, Any]) -> str | None:
    for event in reversed(trace_payload.get("events", [])):
        if event.get("event_name") != "draft_reply":
            continue
        outputs = event.get("outputs") or {}
        if isinstance(outputs, dict):
            knowledge_summary = outputs.get("knowledge_summary")
            if isinstance(knowledge_summary, str) and knowledge_summary.strip():
                return knowledge_summary
    return None


def _wait_for_run_completion(
    *,
    session: requests.Session,
    base_url: str,
    ticket_id: str,
    run_id: str,
    request_timeout_seconds: int,
    local_worker_runner: LocalWorkerRunner | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + request_timeout_seconds

    while time.monotonic() < deadline:
        if local_worker_runner is not None:
            local_worker_runner.run_once()

        snapshot_response = session.get(
            f"{base_url}/tickets/{ticket_id}",
            timeout=request_timeout_seconds,
        )
        snapshot_response.raise_for_status()
        snapshot_payload = snapshot_response.json()
        latest_run = snapshot_payload.get("latest_run") or {}

        if latest_run.get("run_id") == run_id and latest_run.get("status") in {
            RunStatus.SUCCEEDED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
            RunStatus.TIMED_OUT.value,
        }:
            trace_response = session.get(
                f"{base_url}/tickets/{ticket_id}/trace",
                params={"run_id": run_id},
                timeout=request_timeout_seconds,
            )
            trace_response.raise_for_status()
            return snapshot_payload, trace_response.json()

        time.sleep(0.1)

    raise TimeoutError(
        f"Timed out waiting for run `{run_id}` on ticket `{ticket_id}` to finish."
    )


def run_real_eval(
    *,
    samples_path: Path,
    report_path: Path,
    api_base_url: str | None,
    host: str,
    port: int,
    request_timeout_seconds: int,
    disable_gmail: bool,
    knowledge_source_path: Path | None,
    knowledge_db_path: Path | None,
    rebuild_index: bool,
) -> dict[str, Any]:
    _apply_runtime_overrides(
        disable_gmail=disable_gmail,
        knowledge_source_path=knowledge_source_path,
        knowledge_db_path=knowledge_db_path,
    )

    settings = get_settings()
    active_knowledge_db_path = settings.knowledge.chroma_persist_directory
    active_knowledge_source_path = settings.knowledge.source_document_path

    backup_path: Path | None = None
    if rebuild_index:
        backup_path = _backup_existing_index(active_knowledge_db_path)
        rebuild_knowledge_index()
        _clear_runtime_caches()
        settings = get_settings()
        active_knowledge_db_path = settings.knowledge.chroma_persist_directory
        active_knowledge_source_path = settings.knowledge.source_document_path

    records: list[dict[str, Any]] = []
    samples = load_jsonl(samples_path)
    total_samples = len(samples)
    eval_run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:8]

    def _execute(base_url: str, *, local_worker_runner: LocalWorkerRunner | None = None) -> None:
        session = requests.Session()

        for index, sample in enumerate(samples, start=1):
            print(f"[real-eval] {index}/{total_samples} {sample['sample_id']} ingest")
            ingest_response = session.post(
                f"{base_url}/tickets/ingest-email",
                json={
                    "source_channel": "gmail",
                    "source_thread_id": f"real-eval-thread-{eval_run_id}-{sample['sample_id']}",
                    "source_message_id": f"<{sample['sample_id']}.{eval_run_id}@real-eval.local>",
                    "sender_email_raw": '"Real Eval User" <real-eval@example.com>',
                    "subject": sample["email_subject"],
                    "body_text": sample["email_body"],
                    "message_timestamp": f"2026-04-02T10:{index:02d}:00+08:00",
                    "attachments": [],
                },
                timeout=request_timeout_seconds,
            )
            ingest_response.raise_for_status()
            ingest_payload = ingest_response.json()

            print(f"[real-eval] {index}/{total_samples} {sample['sample_id']} run")
            run_response = session.post(
                f"{base_url}/tickets/{ingest_payload['ticket_id']}/run",
                json={
                    "ticket_version": ingest_payload["version"],
                    "trigger_type": "offline_eval",
                    "force_retry": False,
                },
                headers={
                    "X-Actor-Id": "real-eval",
                    "X-Request-Id": f"{sample['sample_id']}-{eval_run_id}",
                },
                timeout=request_timeout_seconds,
            )

            run_payload = run_response.json()
            if run_response.status_code == 202:
                snapshot_payload, trace_payload = _wait_for_run_completion(
                    session=session,
                    base_url=base_url,
                    ticket_id=ingest_payload["ticket_id"],
                    run_id=run_payload["run_id"],
                    request_timeout_seconds=request_timeout_seconds,
                    local_worker_runner=local_worker_runner,
                )
            else:
                snapshot_response = session.get(
                    f"{base_url}/tickets/{ingest_payload['ticket_id']}",
                    timeout=request_timeout_seconds,
                )
                snapshot_response.raise_for_status()
                snapshot_payload = snapshot_response.json()
                trace_payload = {
                    "trace_id": run_payload.get("trace_id"),
                    "events": [],
                    "latency_metrics": {},
                    "resource_metrics": {},
                    "trajectory_evaluation": _build_trace_fallback(
                        expected_route_template=sample["expected_route_template"],
                        actual_route=snapshot_payload["ticket"].get("primary_route"),
                        reason=run_payload.get("message")
                        or "Run request did not enqueue successfully.",
                    ),
                }

            actual_route = snapshot_payload["ticket"].get("primary_route")
            escalation_flag = any(
                event["event_name"] == "escalation_decision"
                and bool((event.get("metadata") or {}).get("needs_escalation"))
                for event in trace_payload.get("events", [])
            )

            records.append(
                {
                    "sample_id": sample["sample_id"],
                    "scenario_type": sample["scenario_type"],
                    "trace_id": trace_payload.get("trace_id"),
                    "primary_route": actual_route,
                    "expected_primary_route": sample["expected_primary_route"],
                    "needs_escalation": escalation_flag,
                    "expected_escalation": sample["expected_escalation"],
                    "final_action": (
                        (snapshot_payload.get("latest_run") or {}).get("final_action")
                        or (run_payload.get("error", {}).get("details") or {}).get("final_action")
                    ),
                    "http_status": run_response.status_code,
                    "response_quality": trace_payload.get("response_quality"),
                    "response_quality_status": _extract_response_quality_status(trace_payload),
                    "response_quality_baseline": _build_response_quality_baseline(
                        sample=sample,
                        trace_payload=trace_payload,
                        snapshot_payload=snapshot_payload,
                    ),
                    "trajectory_evaluation": trace_payload.get("trajectory_evaluation")
                    or _build_trace_fallback(
                        expected_route_template=sample["expected_route_template"],
                        actual_route=actual_route,
                        reason="Trace response did not include trajectory_evaluation.",
                    ),
                    "latency_metrics": trace_payload.get("latency_metrics") or {},
                    "resource_metrics": trace_payload.get("resource_metrics") or {},
                }
            )
            print(
                "[real-eval] "
                f"{index}/{total_samples} {sample['sample_id']} "
                f"status={run_response.status_code} "
                f"route={actual_route} "
                f"escalation={escalation_flag}"
            )
            _write_report(
                report_path=report_path,
                settings=settings,
                records=records,
                api_base_url=api_base_url,
                host=host,
                port=port,
                disable_gmail=disable_gmail,
                active_knowledge_source_path=active_knowledge_source_path,
                active_knowledge_db_path=active_knowledge_db_path,
                rebuild_index=rebuild_index,
                backup_path=backup_path,
                eval_run_id=eval_run_id,
                in_progress=True,
            )

    if api_base_url:
        _execute(api_base_url.rstrip("/"))
    else:
        with LocalApiServer(host=host, port=port) as base_url:
            _execute(base_url, local_worker_runner=LocalWorkerRunner())

    payload = _write_report(
        report_path=report_path,
        settings=settings,
        records=records,
        api_base_url=api_base_url,
        host=host,
        port=port,
        disable_gmail=disable_gmail,
        active_knowledge_source_path=active_knowledge_source_path,
        active_knowledge_db_path=active_knowledge_db_path,
        rebuild_index=rebuild_index,
        backup_path=backup_path,
        eval_run_id=eval_run_id,
        in_progress=False,
    )
    return payload


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Run real-environment evaluation against the ticket workflow over HTTP."
    )
    parser.add_argument(
        "--samples-path",
        type=Path,
        default=DEFAULT_SAMPLES_PATH,
        help="Path to the JSONL sample set.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path to write the evaluation report JSON.",
    )
    parser.add_argument(
        "--api-base-url",
        type=str,
        default=None,
        help="Use an already running API instead of starting a local server.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host used when starting a local API server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port used when starting a local API server.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=180,
        help="Timeout for each HTTP request.",
    )
    parser.add_argument(
        "--knowledge-source-path",
        type=Path,
        default=None,
        help="Override KNOWLEDGE_SOURCE_PATH for this run.",
    )
    parser.add_argument(
        "--knowledge-db-path",
        type=Path,
        default=None,
        help="Override KNOWLEDGE_DB_PATH for this run.",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Backup the current knowledge index and rebuild it before evaluation.",
    )
    parser.add_argument(
        "--keep-gmail-enabled",
        action="store_true",
        help="Do not force GMAIL_ENABLED=false for the evaluation run.",
    )
    args = parser.parse_args()
    return run_real_eval(
        samples_path=args.samples_path,
        report_path=args.report_path,
        api_base_url=args.api_base_url,
        host=args.host,
        port=args.port,
        request_timeout_seconds=args.request_timeout_seconds,
        disable_gmail=not args.keep_gmail_enabled,
        knowledge_source_path=args.knowledge_source_path,
        knowledge_db_path=args.knowledge_db_path,
        rebuild_index=args.rebuild_index,
    )


if __name__ == "__main__":
    main()
