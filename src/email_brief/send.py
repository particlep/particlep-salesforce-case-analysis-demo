"""Pluggable senders. EMAIL_PROVIDER env var picks the backend."""

from __future__ import annotations

from src.config import Config

from .compose import Briefing


def send(briefing: Briefing, cfg: Config) -> None:
    if cfg.email_provider == "console":
        _send_console(briefing)
    elif cfg.email_provider == "sendgrid":
        _send_sendgrid(briefing, cfg)
    else:
        raise ValueError(f"unknown EMAIL_PROVIDER: {cfg.email_provider}")


def _send_console(briefing: Briefing) -> None:
    print("\n" + "=" * 70)
    print(f"SUBJECT: {briefing.subject}")
    print("=" * 70)
    print(f"(dry-run — HTML written to disk, not sent. {len(briefing.html):,} bytes.)")
    print("=" * 70)


def _send_sendgrid(briefing: Briefing, cfg: Config) -> None:
    # Imported here so a console-only run doesn't require the sendgrid package.
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=cfg.email_from,
        to_emails=list(cfg.email_to),
        subject=briefing.subject,
        html_content=briefing.html,
    )

    client = SendGridAPIClient(cfg.sendgrid_api_key)
    response = client.send(message)

    if response.status_code >= 300:
        raise RuntimeError(
            f"SendGrid returned {response.status_code}: {response.body!r}"
        )
    print(f"Sent via SendGrid (status {response.status_code}) to {', '.join(cfg.email_to)}")
