"""Render the briefing HTML from analysis outputs.

Pure data-in / HTML-out. No I/O except reading the template. Sending is in
`send.py`; the orchestrator writes a copy to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import REPO_ROOT
from src.sources.base import CaseRecord


@dataclass
class Briefing:
    subject: str
    html: str
    run_date: date


# Colors used in chips / bucket headers
_RED = ("#fde8e8", "#b32424")
_AMBER = ("#fef3c7", "#92400e")
_BLUE = ("#dbeafe", "#1e40af")
_GRAY = ("#e5e7eb", "#374151")


_CLINICAL_URGENCY_TAG = {
    "immediate": ("Clinical · immediate", _RED),
    "same_day": ("Clinical · same-day", _AMBER),
    "routine": ("Clinical · routine", _BLUE),
}


def _case_url(instance_url: str | None, case_id: str) -> str:
    if not instance_url:
        return "#"
    base = instance_url.rstrip("/")
    return f"{base}/lightning/r/Case/{case_id}/view"


def _list_view_url(instance_url: str | None, run_date: date) -> str | None:
    if not instance_url:
        return None
    base = instance_url.rstrip("/")
    return (
        f"{base}/lightning/o/Case/list"
        f"?filterName=Recent&t={run_date.isoformat()}"
    )


def compose(
    *,
    run_date: date,
    cases: list[CaseRecord],
    narrative: str,
    topics: dict,
    escalation: dict,
    clinical: dict,
    sla: dict,
    instance_url: str | None,
    source_label: str,
    dry_run: bool,
) -> Briefing:
    cases_by_id = {c.id: c for c in cases}

    # ---- Critical items (clinical + high-risk escalations) ----------
    critical_items: list[dict] = []

    # Clinical flags first, ordered by urgency
    urgency_order = {"immediate": 0, "same_day": 1, "routine": 2}
    clinical_flags = sorted(
        clinical.get("flags", []),
        key=lambda f: urgency_order.get(f.get("urgency", "routine"), 3),
    )
    for flag in clinical_flags:
        case = cases_by_id.get(flag["case_id"])
        tag, (tag_bg, tag_fg) = _CLINICAL_URGENCY_TAG.get(
            flag.get("urgency", "routine"), ("Clinical", _BLUE)
        )
        critical_items.append(
            {
                "tag": tag,
                "tag_bg": tag_bg,
                "tag_fg": tag_fg,
                "case_number": case.case_number if case else flag["case_id"],
                "case_subject": case.subject if case else "(case not found)",
                "summary": flag["summary"],
                "url": _case_url(instance_url, flag["case_id"]),
            }
        )

    # Then high-risk escalations (>= 0.6), dedup against any case already shown
    shown_ids = {f["case_id"] for f in clinical_flags}
    high_escalations = sorted(
        [s for s in escalation.get("scores", []) if s.get("score", 0) >= 0.6],
        key=lambda s: -s.get("score", 0),
    )
    for esc in high_escalations:
        if esc["case_id"] in shown_ids:
            continue
        case = cases_by_id.get(esc["case_id"])
        critical_items.append(
            {
                "tag": f"Escalation risk · {esc['score']:.2f}",
                "tag_bg": _RED[0],
                "tag_fg": _RED[1],
                "case_number": case.case_number if case else esc["case_id"],
                "case_subject": case.subject if case else "(case not found)",
                "summary": esc.get("reason", ""),
                "url": _case_url(instance_url, esc["case_id"]),
            }
        )

    # ---- Topic clusters (top 8, ordered by share) ----------
    topic_clusters = sorted(
        topics.get("clusters", []),
        key=lambda c: (-c.get("case_count", 0), c.get("label", "")),
    )[:8]

    # ---- SLA buckets ----------
    sla_bucket_defs = [
        ("approaching_breach", "Approaching SLA breach", _AMBER[1]),
        ("already_breached", "SLA breached", _RED[1]),
        ("bouncing", "Bouncing owners", _AMBER[1]),
        ("stalled", "Stalled", _AMBER[1]),
        ("unusual_handle_time", "Unusual handle time", _GRAY[1]),
    ]
    sla_buckets: list[dict] = []
    for key, label, color in sla_bucket_defs:
        items = sla.get(key, [])
        if not items:
            continue
        rendered_items = []
        for item in items:
            case = cases_by_id.get(item["case_id"])
            rendered_items.append(
                {
                    "case_number": case.case_number if case else item["case_id"],
                    "summary": item["summary"],
                    "url": _case_url(instance_url, item["case_id"]),
                }
            )
        sla_buckets.append({"label": label, "color": color, "rows": rendered_items})

    # ---- Counts ----------
    case_count = len(cases)
    open_count = sum(1 for c in cases if c.closed_at is None)
    closed_count = case_count - open_count
    escalated_count = sum(1 for c in cases if c.is_escalated)

    # ---- Alert chips ----------
    alert_chips: list[dict] = []
    immediate_clinical = sum(1 for f in clinical_flags if f.get("urgency") == "immediate")
    same_day_clinical = sum(1 for f in clinical_flags if f.get("urgency") == "same_day")
    breached = len(sla.get("already_breached", []))
    approaching = len(sla.get("approaching_breach", []))
    n_escalations = len(high_escalations)

    if immediate_clinical:
        alert_chips.append(
            {"text": f"{immediate_clinical} immediate clinical", "bg": _RED[0], "fg": _RED[1]}
        )
    if same_day_clinical:
        alert_chips.append(
            {"text": f"{same_day_clinical} same-day clinical", "bg": _AMBER[0], "fg": _AMBER[1]}
        )
    if breached:
        alert_chips.append(
            {"text": f"{breached} SLA breach{'es' if breached != 1 else ''}", "bg": _RED[0], "fg": _RED[1]}
        )
    if approaching:
        alert_chips.append(
            {"text": f"{approaching} approaching SLA", "bg": _AMBER[0], "fg": _AMBER[1]}
        )
    if n_escalations:
        alert_chips.append(
            {"text": f"{n_escalations} escalation risk{'s' if n_escalations != 1 else ''}", "bg": _AMBER[0], "fg": _AMBER[1]}
        )

    # ---- Subject ----------
    subject_parts = [f"Daily Support Brief — {run_date.strftime('%b %-d')}"]
    if immediate_clinical:
        subject_parts.append(f"{immediate_clinical} immediate clinical")
    elif same_day_clinical:
        subject_parts.append(f"{same_day_clinical} same-day clinical")
    if breached:
        subject_parts.append(f"{breached} SLA breach{'es' if breached != 1 else ''}")
    elif approaching:
        subject_parts.append(f"{approaching} approaching SLA")
    if n_escalations and not (immediate_clinical or same_day_clinical):
        subject_parts.append(f"{n_escalations} escalation risk{'s' if n_escalations != 1 else ''}")
    subject = " — ".join(subject_parts) if len(subject_parts) > 1 else subject_parts[0]

    # ---- Render ----------
    env = Environment(
        loader=FileSystemLoader(str(REPO_ROOT / "src" / "email_brief")),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("template.html")
    html = template.render(
        subject=subject,
        run_date_display=run_date.strftime("%A, %B %-d, %Y"),
        run_date_iso=run_date.isoformat(),
        narrative=narrative,
        alert_chips=alert_chips,
        critical_items=critical_items,
        topic_clusters=topic_clusters,
        sla_buckets=sla_buckets,
        case_count=case_count,
        open_count=open_count,
        closed_count=closed_count,
        escalated_count=escalated_count,
        list_view_url=_list_view_url(instance_url, run_date),
        source_label=source_label,
        dry_run=dry_run,
    )

    return Briefing(subject=subject, html=html, run_date=run_date)


def save_to_disk(briefing: Briefing, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{briefing.run_date.isoformat()}.html"
    path.write_text(briefing.html)
    return path
