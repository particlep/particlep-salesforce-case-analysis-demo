from __future__ import annotations

from datetime import date

from src.config import Config

from .base import CaseRecord, CaseSource
from .salesforce import SalesforceSource
from .synthetic import SyntheticSource


def get_source(cfg: Config) -> CaseSource:
    if cfg.case_source == "synthetic":
        return SyntheticSource()
    return SalesforceSource(
        username=cfg.sf_username,
        password=cfg.sf_password,
        security_token=cfg.sf_security_token,
        domain=cfg.sf_domain,
    )


__all__ = ["CaseRecord", "CaseSource", "get_source", "date"]
