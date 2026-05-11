"""Shared Claude client + caching helper for the four Sonnet analysis calls.

The four Sonnet analyses (topics, escalation, clinical, SLA) all run against
the same day's case data. We exploit that by structuring every Sonnet call
identically up to a single `cache_control` breakpoint on the case-data system
block:

    tools:     [stable list of all four analysis tools, sorted by name]
    system:    [generic role,
                case data JSON ← cache_control here]
    messages:  [per-analysis user prompt, varies]
    tool_choice: forces the relevant tool

`tool_choice` changes do not invalidate the tools or system cache, so the four
Sonnet calls share a single cached prefix. The first call writes the cache;
the remaining three read it at ~0.1x cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic

from src.config import REPO_ROOT
from src.sources.base import CaseRecord


# ---------- Tools (defined here, used identically across all 4 Sonnet calls) -

TOPIC_TOOL = {
    "name": "submit_topic_clusters",
    "description": (
        "Submit a clustering of yesterday's cases by underlying member need. "
        "Use this tool to return your final analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "array",
                "description": "5-10 clusters, ordered by case_count descending.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "Short specific label (5-10 words).",
                        },
                        "description": {
                            "type": "string",
                            "description": "1-2 sentence description of the pattern.",
                        },
                        "case_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Case IDs in this cluster.",
                        },
                        "case_count": {"type": "integer"},
                        "share_pct": {
                            "type": "number",
                            "description": "Percentage 0-100.",
                        },
                        "notable": {
                            "type": "boolean",
                            "description": "True if cluster is unusually large or strange.",
                        },
                    },
                    "required": [
                        "label",
                        "description",
                        "case_ids",
                        "case_count",
                        "share_pct",
                        "notable",
                    ],
                },
            }
        },
        "required": ["clusters"],
    },
}


ESCALATION_TOOL = {
    "name": "submit_escalation_scores",
    "description": (
        "Submit per-case escalation-risk scores. Only return cases scoring "
        "0.4 or higher. Use this tool to return your final analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string"},
                        "score": {
                            "type": "number",
                            "description": "0.0 to 1.0, 1.0 = imminent escalation.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence naming a specific signal.",
                        },
                    },
                    "required": ["case_id", "score", "reason"],
                },
            }
        },
        "required": ["scores"],
    },
}


CLINICAL_TOOL = {
    "name": "submit_clinical_flags",
    "description": (
        "Submit cases warranting clinical-team review. Do NOT echo PHI in "
        "summaries — reference cases by ID; clinical team will look up the "
        "full record in Salesforce."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string"},
                        "flag_type": {
                            "type": "string",
                            "enum": [
                                "adverse_event",
                                "urgent_symptom",
                                "medication",
                                "behavioral_health",
                                "maternity",
                                "other_clinical",
                            ],
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["routine", "same_day", "immediate"],
                        },
                        "summary": {
                            "type": "string",
                            "description": (
                                "One sentence in clinical terms. No member "
                                "names, no direct quotes, no specific identifiers."
                            ),
                        },
                    },
                    "required": ["case_id", "flag_type", "urgency", "summary"],
                },
            }
        },
        "required": ["flags"],
    },
}


def _sla_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "summary": {
                "type": "string",
                "description": (
                    "One sentence naming the specific issue with a number "
                    "if possible (e.g. '3 owner changes since 9am')."
                ),
            },
        },
        "required": ["case_id", "summary"],
    }


SLA_TOOL = {
    "name": "submit_sla_analysis",
    "description": (
        "Submit operational issues bucketed by type. Return empty lists for "
        "buckets with no entries — do not invent."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "approaching_breach": {"type": "array", "items": _sla_item_schema()},
            "already_breached": {"type": "array", "items": _sla_item_schema()},
            "bouncing": {"type": "array", "items": _sla_item_schema()},
            "stalled": {"type": "array", "items": _sla_item_schema()},
            "unusual_handle_time": {"type": "array", "items": _sla_item_schema()},
        },
        "required": [
            "approaching_breach",
            "already_breached",
            "bouncing",
            "stalled",
            "unusual_handle_time",
        ],
    },
}


# All four tools, sorted by name so the rendered tool list is byte-identical
# across calls. This is what makes prompt caching work — see `shared/prompt-
# caching.md`: changing tool order invalidates the entire prefix.
ALL_ANALYSIS_TOOLS = sorted(
    [TOPIC_TOOL, ESCALATION_TOOL, CLINICAL_TOOL, SLA_TOOL],
    key=lambda t: t["name"],
)


# ---------- Prompt loading ---------------------------------------------------


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (REPO_ROOT / "src" / "prompts" / f"{name}.md").read_text()


# ---------- Case context payload (the cached part) ---------------------------


@dataclass(frozen=True)
class CaseContext:
    """The case-data payload shared across the four Sonnet calls.

    Stored as a deterministic JSON string with sorted keys so byte-identical
    serialization is guaranteed run-to-run.
    """

    cases_json: str
    case_count: int
    run_date_iso: str

    @classmethod
    def build(cls, cases: list[CaseRecord], run_date_iso: str) -> "CaseContext":
        payload = {
            "run_date": run_date_iso,
            "case_count": len(cases),
            "cases": [c.to_prompt_dict() for c in cases],
        }
        return cls(
            cases_json=json.dumps(payload, sort_keys=True, ensure_ascii=False),
            case_count=len(cases),
            run_date_iso=run_date_iso,
        )


GENERIC_SYSTEM = (
    "You analyze daily support cases for a healthcare member-services org. "
    "You receive the full case data once and answer follow-up analyses via "
    "tool calls. Be specific and concrete. Reference case IDs verbatim from "
    "the data."
)


# ---------- Client / call helper ---------------------------------------------


def make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def run_sonnet_analysis(
    client: anthropic.Anthropic,
    *,
    model: str,
    context: CaseContext,
    user_prompt: str,
    tool_name: str,
) -> tuple[dict, anthropic.types.Usage]:
    """Run one Sonnet analysis call against the shared cached case context.

    Returns the tool-use input dict and the usage object so the caller can
    log cache-hit metrics.
    """
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        tools=ALL_ANALYSIS_TOOLS,
        tool_choice={"type": "tool", "name": tool_name},
        system=[
            {"type": "text", "text": GENERIC_SYSTEM},
            {
                "type": "text",
                "text": (
                    f"=== Yesterday's cases ({context.case_count} total, "
                    f"run date {context.run_date_iso}) ===\n\n"
                    f"{context.cases_json}"
                ),
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # tool_choice forces the model to call exactly the requested tool. The
    # response content will start with a tool_use block; find it.
    tool_use = next(
        (b for b in response.content if b.type == "tool_use" and b.name == tool_name),
        None,
    )
    if tool_use is None:
        raise RuntimeError(
            f"Expected tool_use block for {tool_name}, got: "
            f"{[b.type for b in response.content]}"
        )
    return tool_use.input, response.usage


def log_usage(label: str, usage: anthropic.types.Usage) -> None:
    """Print a one-line cache/usage report. Useful for verifying caching."""
    print(
        f"[{label}] in={usage.input_tokens} "
        f"cache_write={getattr(usage, 'cache_creation_input_tokens', 0) or 0} "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0) or 0} "
        f"out={usage.output_tokens}"
    )
