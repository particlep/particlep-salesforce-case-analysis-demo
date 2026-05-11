from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    case_source: str  # "synthetic" | "salesforce"
    email_provider: str  # "sendgrid" | "console"
    run_date: date  # the "yesterday" we analyze
    output_dir: Path

    sf_username: str | None
    sf_password: str | None
    sf_security_token: str | None
    sf_domain: str
    sf_instance_url: str | None

    sendgrid_api_key: str | None
    email_from: str | None
    email_to: tuple[str, ...]

    sonnet_model: str = "claude-sonnet-4-6"
    opus_model: str = "claude-opus-4-7"


def load_config() -> Config:
    run_date_str = os.getenv("RUN_DATE", "").strip()
    if run_date_str:
        run_date = datetime.strptime(run_date_str, "%Y-%m-%d").date()
    else:
        run_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    email_to_raw = os.getenv("EMAIL_TO", "")
    email_to = tuple(addr.strip() for addr in email_to_raw.split(",") if addr.strip())

    output_dir = REPO_ROOT / os.getenv("OUTPUT_DIR", "sample_outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        case_source=os.getenv("CASE_SOURCE", "synthetic").lower(),
        email_provider=os.getenv("EMAIL_PROVIDER", "console").lower(),
        run_date=run_date,
        output_dir=output_dir,
        sf_username=os.getenv("SF_USERNAME") or None,
        sf_password=os.getenv("SF_PASSWORD") or None,
        sf_security_token=os.getenv("SF_SECURITY_TOKEN") or None,
        sf_domain=os.getenv("SF_DOMAIN") or "login",
        sf_instance_url=os.getenv("SF_INSTANCE_URL") or None,
        sendgrid_api_key=os.getenv("SENDGRID_API_KEY") or None,
        email_from=os.getenv("EMAIL_FROM") or None,
        email_to=email_to,
    )

    if cfg.case_source not in {"synthetic", "salesforce"}:
        raise ValueError(f"CASE_SOURCE must be synthetic|salesforce, got {cfg.case_source}")
    if cfg.email_provider not in {"sendgrid", "console"}:
        raise ValueError(f"EMAIL_PROVIDER must be sendgrid|console, got {cfg.email_provider}")
    if cfg.case_source == "salesforce" and not (cfg.sf_username and cfg.sf_password and cfg.sf_security_token):
        raise ValueError("Salesforce source requires SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN")
    if cfg.email_provider == "sendgrid" and not (cfg.sendgrid_api_key and cfg.email_from and cfg.email_to):
        raise ValueError("SendGrid provider requires SENDGRID_API_KEY, EMAIL_FROM, EMAIL_TO")

    return cfg
