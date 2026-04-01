from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import get_settings
from src.tools.types import GmailClientProtocol


class GmailApiClient(GmailClientProtocol):
    def __init__(self) -> None:
        self.settings = get_settings()
        self.service = self._get_gmail_service()

    def fetch_unanswered_emails(
        self,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        try:
            recent_emails = self.fetch_recent_emails(max_results)
            if not recent_emails:
                return []

            drafts = self.fetch_draft_replies()
            threads_with_drafts = {draft["threadId"] for draft in drafts}

            seen_threads = set()
            unanswered_emails = []
            for email in recent_emails:
                thread_id = email["threadId"]
                if thread_id in seen_threads or thread_id in threads_with_drafts:
                    continue

                seen_threads.add(thread_id)
                email_info = self._get_email_info(email["id"])
                if self._should_skip_email(email_info):
                    continue
                unanswered_emails.append(email_info)

            return unanswered_emails
        except Exception as error:
            print(f"An error occurred: {error}")
            return []

    def fetch_recent_emails(
        self,
        max_results: int | None = None,
    ) -> list[dict[str, str]]:
        try:
            if max_results is None:
                max_results = self.settings.gmail.default_fetch_limit

            now = datetime.now()
            delay = now - timedelta(hours=self.settings.gmail.inbox_lookback_hours)

            after_timestamp = int(delay.timestamp())
            before_timestamp = int(now.timestamp())

            query = f"after:{after_timestamp} before:{before_timestamp}"
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
            return results.get("messages", [])
        except Exception as error:
            print(f"An error occurred while fetching emails: {error}")
            return []

    def fetch_draft_replies(self) -> list[dict[str, str]]:
        try:
            drafts = self.service.users().drafts().list(userId="me").execute()
            draft_list = drafts.get("drafts", [])
            return [
                {
                    "draft_id": draft["id"],
                    "threadId": draft["message"]["threadId"],
                    "id": draft["message"]["id"],
                }
                for draft in draft_list
            ]
        except Exception as error:
            print(f"An error occurred while fetching drafts: {error}")
            return []

    def create_draft_reply(self, initial_email: Any, reply_text: str) -> Any:
        try:
            message = self._create_reply_message(initial_email, reply_text)
            return self.service.users().drafts().create(
                userId="me",
                body={"message": message},
            ).execute()
        except Exception as error:
            print(f"An error occurred while creating draft: {error}")
            return None

    def send_reply(self, initial_email: Any, reply_text: str) -> Any:
        try:
            message = self._create_reply_message(
                initial_email,
                reply_text,
                send=True,
            )
            return self.service.users().messages().send(
                userId="me",
                body=message,
            ).execute()
        except Exception as error:
            print(f"An error occurred while sending reply: {error}")
            return None

    def _create_reply_message(
        self,
        email: Any,
        reply_text: str,
        *,
        send: bool = False,
    ) -> dict[str, str]:
        message = self._create_html_email_message(
            recipient=email.sender,
            subject=email.subject,
            reply_text=reply_text,
        )

        if email.messageId:
            message["In-Reply-To"] = email.messageId
            message["References"] = f"{email.references} {email.messageId}".strip()
            if send:
                message["Message-ID"] = f"<{uuid.uuid4()}@gmail.com>"

        return {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode(),
            "threadId": email.threadId,
        }

    def _get_gmail_service(self):
        creds = None
        token_path = self.settings.gmail.token_path
        credentials_path = self.settings.gmail.credentials_path

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_path),
                self.settings.gmail.scopes,
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path),
                    self.settings.gmail.scopes,
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=creds)

    def _should_skip_email(self, email_info: dict[str, str]) -> bool:
        my_email = self.settings.gmail.my_email
        return bool(my_email and my_email in email_info["sender"])

    def _get_email_info(self, msg_id: str) -> dict[str, str]:
        message = self.service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()

        payload = message.get("payload", {})
        headers = {
            header["name"].lower(): header["value"]
            for header in payload.get("headers", [])
        }

        return {
            "id": msg_id,
            "threadId": message.get("threadId"),
            "messageId": headers.get("message-id"),
            "references": headers.get("references", ""),
            "sender": headers.get("from", "Unknown"),
            "subject": headers.get("subject", "No Subject"),
            "body": self._get_email_body(payload),
        }

    def _get_email_body(self, payload: dict[str, Any]) -> str:
        def decode_data(data: str) -> str:
            return base64.urlsafe_b64decode(data).decode("utf-8").strip() if data else ""

        def extract_body(parts: list[dict[str, Any]]) -> str:
            for part in parts:
                mime_type = part.get("mimeType", "")
                data = part["body"].get("data", "")
                if mime_type == "text/plain":
                    return decode_data(data)
                if mime_type == "text/html":
                    html_content = decode_data(data)
                    return self._extract_main_content_from_html(html_content)
                if "parts" in part:
                    result = extract_body(part["parts"])
                    if result:
                        return result
            return ""

        if "parts" in payload:
            body = extract_body(payload["parts"])
        else:
            data = payload["body"].get("data", "")
            body = decode_data(data)
            if payload.get("mimeType") == "text/html":
                body = self._extract_main_content_from_html(body)

        return self._clean_body_text(body)

    def _extract_main_content_from_html(self, html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "head", "meta", "title"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    def _clean_body_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\r", "").replace("\n", "")).strip()

    def _create_html_email_message(
        self,
        recipient: str,
        subject: str,
        reply_text: str,
    ) -> MIMEMultipart:
        message = MIMEMultipart("alternative")
        message["to"] = recipient
        message["subject"] = (
            f"Re: {subject}" if not subject.startswith("Re: ") else subject
        )

        html_text = reply_text.replace("\n", "<br>").replace("\\n", "<br>")
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body>{html_text}</body>
        </html>
        """

        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        return message
