"""Opus 4.7 daily narrative.

Receives a compact summary of yesterday plus the four Sonnet analyses, and
writes the 3-4 sentence opening of the email. Different model than the Sonnet
calls so we don't try to share cache — single call anyway.
"""

from __future__ import annotations

import json

import anthropic

from .client import load_prompt, log_usage


def run_narrative(
    client: anthropic.Anthropic,
    model: str,
    *,
    run_date_iso: str,
    case_count: int,
    topics: dict,
    escalation: dict,
    clinical: dict,
    sla: dict,
) -> str:
    system = load_prompt("daily_narrative")

    # Build a compact context — just what the narrative needs, not the full
    # case data. The sub-analyses already extracted the signal.
    context = {
        "run_date": run_date_iso,
        "case_count": case_count,
        "topic_clusters": topics.get("clusters", []),
        "high_risk_escalations": [
            s for s in escalation.get("scores", []) if s.get("score", 0) >= 0.6
        ],
        "escalation_count_total": len(escalation.get("scores", [])),
        "clinical_flags": clinical.get("flags", []),
        "sla_summary": {
            bucket: len(sla.get(bucket, []))
            for bucket in (
                "approaching_breach",
                "already_breached",
                "bouncing",
                "stalled",
                "unusual_handle_time",
            )
        },
        "sla_detail": sla,
    }

    response = client.messages.create(
        model=model,
        max_tokens=600,
        thinking={"type": "adaptive"},
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    "Write the opening narrative for today's email. Here is "
                    "the upstream analysis to draw from:\n\n"
                    + json.dumps(context, indent=2)
                ),
            }
        ],
    )
    log_usage("narrative", response.usage)

    text_blocks = [b.text for b in response.content if b.type == "text"]
    return "\n".join(text_blocks).strip()
