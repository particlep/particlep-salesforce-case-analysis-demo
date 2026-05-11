from __future__ import annotations

from datetime import date, datetime, time, timezone

from .base import (
    Account,
    CaseComment,
    CaseHistoryEvent,
    CaseRecord,
    Contact,
)


# Fields the Service Cloud Entitlements feature adds to Case. Not present on
# orgs without Entitlements turned on (most Developer Edition orgs).
_ENTITLEMENT_FIELDS = ("EntitlementId", "SlaStartDate", "SlaExitDate", "MilestoneStatus")

# Always-present fields on standard Case.
_REQUIRED_CASE_FIELDS = (
    "Id", "CaseNumber", "Subject", "Description", "Status", "Priority",
    "Origin", "Reason", "Type", "CreatedDate", "ClosedDate", "IsEscalated",
    "ContactId", "AccountId",
)

# Relationship traversals — depend on the parent FK actually existing on Case.
# Owner is always present; Contact/Account are too (the FKs above) but a
# nil FK means the join returns null, which we already handle.
_RELATIONSHIP_FIELDS = (
    "Owner.Name",
    "Contact.Name", "Contact.Email", "Contact.Phone",
    "Account.Name", "Account.Type",
)


def _soql_datetime(dt: datetime) -> str:
    """SOQL datetime literal: YYYY-MM-DDTHH:mm:ssZ. No fractional seconds,
    no `+00:00` with colon."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SalesforceSource:
    """Live Salesforce REST source.

    Pulls Cases created OR last-modified on the run date, plus their comments,
    history, related Contact and Account. Pre-flights an SObject describe so
    optional fields (Entitlements/SLA) and optional child relationships
    (CaseComments, Histories) are only requested if the target org actually
    has them — Developer Edition orgs without Service Cloud Entitlements still
    work, the SLA bucket will just be empty for them.
    """

    def __init__(
        self,
        username: str | None,
        password: str | None,
        security_token: str | None,
        domain: str = "login",
    ) -> None:
        from simple_salesforce import Salesforce  # imported here to keep the import optional

        if not (username and password and security_token):
            raise ValueError("SalesforceSource requires username, password, security_token")

        self.sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain,
        )
        self._capabilities = self._discover_capabilities()

    def _discover_capabilities(self) -> dict:
        """Describe Case once to find out which optional fields and child
        relationships this org actually has."""
        desc = self.sf.Case.describe()
        field_names = {f["name"] for f in desc["fields"]}
        relationship_names = {
            r["relationshipName"]
            for r in desc.get("childRelationships", [])
            if r.get("relationshipName")
        }
        caps = {
            "has_entitlements": all(f in field_names for f in _ENTITLEMENT_FIELDS),
            "has_case_comments": "CaseComments" in relationship_names,
            "has_histories": "Histories" in relationship_names,
        }
        print(f"Salesforce capabilities: {caps}")
        return caps

    def fetch_cases(self, run_date: date) -> list[CaseRecord]:
        start = datetime.combine(run_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(run_date, time(23, 59, 59), tzinfo=timezone.utc)

        select_fields = list(_REQUIRED_CASE_FIELDS) + list(_RELATIONSHIP_FIELDS)
        if self._capabilities["has_entitlements"]:
            select_fields.extend(_ENTITLEMENT_FIELDS)

        subqueries: list[str] = []
        if self._capabilities["has_case_comments"]:
            subqueries.append(
                "(SELECT Id, CommentBody, CreatedBy.Name, CreatedDate "
                "FROM CaseComments ORDER BY CreatedDate ASC)"
            )
        if self._capabilities["has_histories"]:
            subqueries.append(
                "(SELECT Id, Field, OldValue, NewValue, CreatedDate, CreatedBy.Name "
                "FROM Histories ORDER BY CreatedDate ASC)"
            )

        select_clause = ", ".join(select_fields + subqueries)
        case_soql = (
            f"SELECT {select_clause} "
            f"FROM Case "
            f"WHERE (CreatedDate >= {_soql_datetime(start)} "
            f"AND CreatedDate <= {_soql_datetime(end)}) "
            f"OR (LastModifiedDate >= {_soql_datetime(start)} "
            f"AND LastModifiedDate <= {_soql_datetime(end)}) "
            f"ORDER BY CreatedDate ASC "
            f"LIMIT 1000"
        )

        result = self.sf.query_all(case_soql)
        return [self._to_record(row) for row in result["records"]]

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        # Salesforce datetimes look like 2026-05-10T14:33:00.000+0000
        return datetime.fromisoformat(value.replace("Z", "+00:00").replace(".000+0000", "+00:00"))

    def _to_record(self, row: dict) -> CaseRecord:
        contact = None
        if row.get("Contact"):
            contact = Contact(
                id=row["ContactId"],
                name=row["Contact"]["Name"],
                email=row["Contact"].get("Email"),
                phone=row["Contact"].get("Phone"),
            )

        account = None
        if row.get("Account"):
            account = Account(
                id=row["AccountId"],
                name=row["Account"]["Name"],
                type=row["Account"].get("Type"),
            )

        comments: list[CaseComment] = []
        if row.get("CaseComments") and row["CaseComments"].get("records"):
            for c in row["CaseComments"]["records"]:
                comments.append(
                    CaseComment(
                        id=c["Id"],
                        body=c.get("CommentBody") or "",
                        author=(c.get("CreatedBy") or {}).get("Name") or "Unknown",
                        created_at=self._parse_dt(c["CreatedDate"]) or datetime.now(timezone.utc),
                    )
                )

        history: list[CaseHistoryEvent] = []
        owner_changes = 0
        if row.get("Histories") and row["Histories"].get("records"):
            for h in row["Histories"]["records"]:
                field = h.get("Field") or ""
                if field == "Owner":
                    owner_changes += 1
                history.append(
                    CaseHistoryEvent(
                        field=field,
                        old_value=str(h.get("OldValue")) if h.get("OldValue") is not None else None,
                        new_value=str(h.get("NewValue")) if h.get("NewValue") is not None else None,
                        created_at=self._parse_dt(h["CreatedDate"]) or datetime.now(timezone.utc),
                        changed_by=(h.get("CreatedBy") or {}).get("Name") or "Unknown",
                    )
                )

        sla_target = self._parse_dt(row.get("SlaExitDate"))
        sla_breached = (
            (row.get("MilestoneStatus") or "").lower() == "violation"
            or (
                sla_target is not None
                and row.get("Status") not in ("Closed", "Resolved")
                and sla_target < datetime.now(timezone.utc)
            )
        )

        return CaseRecord(
            id=row["Id"],
            case_number=row["CaseNumber"],
            subject=row.get("Subject") or "",
            description=row.get("Description") or "",
            status=row.get("Status") or "",
            priority=row.get("Priority") or "",
            origin=row.get("Origin") or "",
            reason=row.get("Reason"),
            type=row.get("Type"),
            created_at=self._parse_dt(row["CreatedDate"]) or datetime.now(timezone.utc),
            closed_at=self._parse_dt(row.get("ClosedDate")),
            is_escalated=bool(row.get("IsEscalated")),
            owner_name=(row.get("Owner") or {}).get("Name") or "Unassigned",
            owner_changes=owner_changes,
            sla_target_at=sla_target,
            sla_breached=sla_breached,
            contact=contact,
            account=account,
            comments=comments,
            history=sorted(history, key=lambda h: h.created_at),
        )
