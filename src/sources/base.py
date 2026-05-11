from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass
class CaseComment:
    id: str
    body: str
    author: str
    created_at: datetime


@dataclass
class CaseHistoryEvent:
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime
    changed_by: str


@dataclass
class Contact:
    id: str
    name: str
    email: str | None
    phone: str | None


@dataclass
class Account:
    id: str
    name: str
    type: str | None


@dataclass
class CaseRecord:
    """Normalized case shape used by every analysis module.

    Both SalesforceSource and SyntheticSource emit this exact shape so the
    analysis layer never knows where the data came from.
    """

    id: str
    case_number: str
    subject: str
    description: str
    status: str
    priority: str
    origin: str
    reason: str | None
    type: str | None
    created_at: datetime
    closed_at: datetime | None
    is_escalated: bool
    owner_name: str
    owner_changes: int  # derived from history
    sla_target_at: datetime | None
    sla_breached: bool
    contact: Contact | None
    account: Account | None
    comments: list[CaseComment] = field(default_factory=list)
    history: list[CaseHistoryEvent] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        """Compact dict used inside Claude prompts. Trim verbose fields."""
        return {
            "id": self.id,
            "case_number": self.case_number,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "origin": self.origin,
            "reason": self.reason,
            "type": self.type,
            "created_at": self.created_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "is_escalated": self.is_escalated,
            "owner_name": self.owner_name,
            "owner_changes": self.owner_changes,
            "sla_target_at": self.sla_target_at.isoformat() if self.sla_target_at else None,
            "sla_breached": self.sla_breached,
            "contact_name": self.contact.name if self.contact else None,
            "account_name": self.account.name if self.account else None,
            "account_type": self.account.type if self.account else None,
            "comments": [
                {"author": c.author, "body": c.body, "at": c.created_at.isoformat()}
                for c in self.comments
            ],
            "history": [
                {
                    "field": h.field,
                    "from": h.old_value,
                    "to": h.new_value,
                    "by": h.changed_by,
                    "at": h.created_at.isoformat(),
                }
                for h in self.history
            ],
        }


class CaseSource(Protocol):
    def fetch_cases(self, run_date: date) -> list[CaseRecord]:
        """Return all cases created OR updated on run_date (member's local timezone)."""
        ...
