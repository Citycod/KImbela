import logging
import socket
import time
from dataclasses import dataclass, field

import resend
from flask import current_app
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout


logger = logging.getLogger(__name__)


@dataclass
class Message:
    subject: str = ""
    recipients: list[str] | None = None
    sender: str | None = None
    body: str | None = None
    html: str | None = None
    charset: str | None = "utf-8"
    extra_headers: dict | None = field(default_factory=dict)

    def __post_init__(self):
        if self.recipients is None:
            self.recipients = []


class ResendMail:
    def __init__(self):
        self.app = None

    def init_app(self, app):
        self.app = app
        api_key = app.config.get("RESEND_API_KEY", "")
        resend.api_key = api_key
        app.extensions["mail"] = self

    def send(self, message):
        app = current_app._get_current_object()
        api_key = app.config.get("RESEND_API_KEY", "")
        resend.api_key = api_key

        if not api_key:
            raise RuntimeError("RESEND_API_KEY is not configured")

        recipients = message.recipients or []
        if not recipients:
            raise ValueError("Email recipients are required")

        sender = message.sender or app.config.get(
            "MAIL_DEFAULT_SENDER", "Kimbela <onboarding@resend.dev>"
        )

        payload = {
            "from": sender,
            "to": recipients,
            "subject": message.subject,
        }

        if message.html:
            payload["html"] = message.html
        if message.body:
            payload["text"] = message.body
        if not message.html and not message.body:
            payload["text"] = ""
        if message.extra_headers:
            payload["headers"] = message.extra_headers

        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = resend.Emails.send(payload)
                logger.info(
                    "Email sent via Resend to %s: %s",
                    ", ".join(recipients),
                    response.get("id", "no-id"),
                )
                return response
            except Exception as exc:
                if not self._is_transient_error(exc):
                    raise
                last_error = exc
                logger.warning(
                    "Resend send failed for %s (attempt %s/%s): %s",
                    ", ".join(recipients),
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt == max_attempts:
                    break
                time.sleep(min(0.75 * attempt, 2.5))

        raise last_error

    @staticmethod
    def _is_transient_error(exc):
        message = str(exc).lower()
        transient_markers = (
            "failed to establish a new connection",
            "failed to resolve",
            "lookup timed out",
            "name resolution",
            "dns",
            "timed out",
            "timeout",
            "enetunreach",
            "network is unreachable",
            "ehostunreach",
            "host is unreachable",
            "503",
            "502",
            "504",
            "429",
        )
        return isinstance(
            exc, (RequestsConnectionError, Timeout, socket.gaierror)
        ) or any(marker in message for marker in transient_markers)
