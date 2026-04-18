from __future__ import annotations

from colorama import Fore, Style

from src.api.services import TicketApiService
from src.bootstrap.container import get_service_container
from src.config import (
    RUNTIME_REQUIRED_SETTINGS,
    SettingsError,
    get_settings,
    validate_required_settings,
)


def main() -> None:
    settings = get_settings()
    if not settings.gmail.enabled:
        raise SettingsError(
            "Gmail polling is disabled. Set `GMAIL_ENABLED=true` and configure Gmail OAuth to use `run_poller.py`."
        )

    validate_required_settings(RUNTIME_REQUIRED_SETTINGS)
    container = get_service_container()
    api_service = TicketApiService(container.ticket_store, container=container)

    print(Fore.GREEN + "Starting Gmail poller batch..." + Style.RESET_ALL)
    result = api_service.scan_gmail(max_results=None, enqueue=True)
    if result.ingested_tickets == 0 and result.errors == 0:
        print(Fore.YELLOW + "No new emails to ingest." + Style.RESET_ALL)
        return

    for item in result.items:
        if item.ticket_id is None:
            print(
                Fore.RED
                + f"Failed to process Gmail thread {item.source_thread_id}"
                + Style.RESET_ALL
            )
            continue
        print(
            Fore.CYAN
            + (
                f"Enqueued run {item.queued_run_id} for "
                f"{'new' if item.created_ticket else 'existing'} ticket {item.ticket_id}"
            )
            + Style.RESET_ALL
        )


if __name__ == "__main__":
    main()
