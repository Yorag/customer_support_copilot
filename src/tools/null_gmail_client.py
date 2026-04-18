from __future__ import annotations

from typing import Any


class NullGmailClient:
    """Local placeholder for environments that disable Gmail integration."""

    def scan_inbox(
        self,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        return {
            "requested_max_results": max_results,
            "candidate_threads": 0,
            "skipped_existing_draft_threads": 0,
            "skipped_self_sent_threads": 0,
            "items": [],
        }

    def fetch_unanswered_emails(
        self,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def create_draft_reply(self, initial_email: Any, reply_text: str) -> dict[str, str]:
        message_id = getattr(initial_email, "messageId", None) or "local"
        return {"id": f"local-draft:{message_id}"}

    def send_reply(self, initial_email: Any, reply_text: str) -> dict[str, str]:
        message_id = getattr(initial_email, "messageId", None) or "local"
        return {"id": f"local-message:{message_id}"}
