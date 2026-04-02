from datetime import datetime, timezone

from colorama import Fore, Style

from src.api.services import TicketApiService
from src.config import RUNTIME_REQUIRED_SETTINGS, SettingsError, get_settings, validate_required_settings
from src.message_log import IngestEmailPayload
from src.tools.service_container import get_service_container


def main() -> None:
    settings = get_settings()
    if not settings.gmail.enabled:
        raise SettingsError(
            "Gmail polling is disabled. Set `GMAIL_ENABLED=true` and configure Gmail OAuth to use `main.py`."
        )

    validate_required_settings(RUNTIME_REQUIRED_SETTINGS)
    container = get_service_container()
    gmail_client = container.gmail_client
    api_service = TicketApiService(container.ticket_store, container=container)

    print(Fore.GREEN + "Starting ticket execution batch..." + Style.RESET_ALL)
    emails = gmail_client.fetch_unanswered_emails()
    if not emails:
        print(Fore.YELLOW + "No new emails to process." + Style.RESET_ALL)
        return

    for email in emails:
        ingest_payload = IngestEmailPayload(
            source_channel="gmail",
            source_thread_id=email["threadId"],
            source_message_id=email["messageId"] or email["id"],
            sender_email_raw=email["sender"],
            subject=email["subject"],
            body_text=email["body"],
            message_timestamp=datetime.now(timezone.utc),
            references=email.get("references"),
            attachments=[],
        )
        ticket, _ = api_service.ingest_email(payload=ingest_payload, idempotency_key=None)
        result = api_service.run_ticket(
            ticket_id=ticket.ticket_id,
            ticket_version=ticket.version,
            trigger_type="poller",
            force_retry=False,
            actor_id="system:poller",
            request_id=f"poller:{ticket.ticket_id}",
            idempotency_key=None,
        )
        print(
            Fore.CYAN
            + f"Finished ticket {result.ticket.ticket_id} with run {result.run.run_id}"
            + Style.RESET_ALL
        )


if __name__ == "__main__":
    main()
