"""Report delivery channels. Credentials always come from environment variables."""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import requests


class NotifyError(Exception):
    pass


@dataclass
class RenderedReport:
    subject: str
    markdown: str
    html: str
    telegram: list[str]
    has_alerts: bool = False


class Notifier:
    type = "base"

    def __init__(self, **options: Any):
        self.options = options
        # only_on_alert: send only when there is a price drop, new low or target hit.
        self.only_on_alert = bool(options.get("only_on_alert", False))

    def env(self, key: str, default_env: str) -> str:
        name = self.options.get(key, default_env)
        value = os.environ.get(name, "")
        if not value:
            raise NotifyError(f"{self.type}: environment variable {name} is not set")
        return value

    def send(self, report: RenderedReport) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    type = "console"

    def send(self, report: RenderedReport) -> None:
        sys.stdout.write(report.markdown)


class GitHubSummaryNotifier(Notifier):
    """Appends the report to the GitHub Actions job summary page."""

    type = "github_summary"

    def send(self, report: RenderedReport) -> None:
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not path:
            return  # not running in Actions: nothing to do
        with open(path, "a") as fh:
            fh.write(report.markdown)


class TelegramNotifier(Notifier):
    type = "telegram"

    def send(self, report: RenderedReport) -> None:
        token = self.env("bot_token_env", "TELEGRAM_BOT_TOKEN")
        chat_id = self.env("chat_id_env", "TELEGRAM_CHAT_ID")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for text in report.telegram:
            r = requests.post(url, json={
                "chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True,
            }, timeout=30)
            if r.status_code != 200:
                raise NotifyError(f"telegram: HTTP {r.status_code}: {r.text[:200]}")


class EmailNotifier(Notifier):
    """SMTP email. For Gmail use smtp.gmail.com:465 and an App Password."""

    type = "email"

    def send(self, report: RenderedReport) -> None:
        host = self.options.get("smtp_host", "smtp.gmail.com")
        port = int(self.options.get("smtp_port", 465))
        user = self.env("username_env", "SMTP_USERNAME")
        password = self.env("password_env", "SMTP_PASSWORD")
        to = self.options.get("to") or os.environ.get(self.options.get("to_env", "REPORT_EMAIL_TO"), "") or user
        msg = EmailMessage()
        msg["Subject"] = report.subject
        msg["From"] = self.options.get("from", user)
        msg["To"] = to if isinstance(to, str) else ", ".join(to)
        msg.set_content(report.markdown)
        msg.add_alternative(report.html, subtype="html")
        ctx = ssl.create_default_context()
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                    s.login(user, password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as s:
                    s.starttls(context=ctx)
                    s.login(user, password)
                    s.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise NotifyError(f"email: {e}") from e


REGISTRY: dict[str, type[Notifier]] = {
    n.type: n for n in (ConsoleNotifier, GitHubSummaryNotifier, TelegramNotifier, EmailNotifier)
}


def create_notifier(type_: str, **options: Any) -> Notifier:
    try:
        return REGISTRY[type_](**options)
    except KeyError:
        raise NotifyError(f"unknown notifier {type_!r}; available: {sorted(REGISTRY)}") from None
