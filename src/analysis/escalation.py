from __future__ import annotations

import anthropic

from .client import CaseContext, load_prompt, log_usage, run_sonnet_analysis


def run_escalation(
    client: anthropic.Anthropic,
    model: str,
    context: CaseContext,
) -> dict:
    user_prompt = (
        load_prompt("escalation_scoring")
        + "\n\nNow produce the scores via the submit_escalation_scores tool."
    )
    result, usage = run_sonnet_analysis(
        client,
        model=model,
        context=context,
        user_prompt=user_prompt,
        tool_name="submit_escalation_scores",
    )
    log_usage("escalation", usage)
    return result
