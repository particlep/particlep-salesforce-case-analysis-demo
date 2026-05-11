from __future__ import annotations

import anthropic

from .client import CaseContext, load_prompt, log_usage, run_sonnet_analysis


def run_sla(
    client: anthropic.Anthropic,
    model: str,
    context: CaseContext,
) -> dict:
    user_prompt = (
        load_prompt("sla_analysis")
        + "\n\nNow produce the analysis via the submit_sla_analysis tool."
    )
    result, usage = run_sonnet_analysis(
        client,
        model=model,
        context=context,
        user_prompt=user_prompt,
        tool_name="submit_sla_analysis",
    )
    log_usage("sla", usage)
    return result
