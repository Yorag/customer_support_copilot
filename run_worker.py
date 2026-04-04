from __future__ import annotations

import argparse
import socket
import time

from src.bootstrap.container import get_service_container
from src.config import RUNTIME_REQUIRED_SETTINGS, validate_required_settings
from src.workers.ticket_worker import (
    DEFAULT_WORKER_POLL_INTERVAL_SECONDS,
    TicketWorker,
)


def build_worker_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ticket worker loop.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and execute at most one queued ticket run, then exit.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=DEFAULT_WORKER_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds when running in loop mode.",
    )
    parser.add_argument(
        "--worker-id",
        default=_default_worker_id(),
        help="Stable worker identity used for lease ownership and trace events.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    validate_required_settings(RUNTIME_REQUIRED_SETTINGS)
    args = build_worker_arg_parser().parse_args(argv)
    if args.poll_interval_seconds <= 0:
        raise SystemExit("--poll-interval-seconds must be greater than 0.")

    container = get_service_container()
    worker = TicketWorker(
        store=container.ticket_store,
        container=container,
        worker_id=args.worker_id,
    )
    if args.once:
        worker.run_once()
        return 0

    while True:
        worker.run_once()
        time.sleep(args.poll_interval_seconds)


def _default_worker_id() -> str:
    return f"worker-{socket.gethostname()}"


if __name__ == "__main__":
    raise SystemExit(main())
