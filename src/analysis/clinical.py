from __future__ import annotations

import anthropic

from .client import CaseContext, load_prompt, log_usage, run_sonnet_analysis


def run_clinical(
    client: anthropic.Anthropic,
    model: str,
    context: CaseContext,
) -> dict:
    user_prompt = (
        load_prompt("clinical_flags")
        + "\n\nNow produce the flags via the submit_clinical_flags tool. "
        "Remember: no PHI in summaries — clinical-team operators will look up "
        "the full case in Salesforce."
    )
    result, usage = run_sonnet_analysis(
        client,
        model=model,
        context=context,
        user_prompt=user_prompt,
        tool_name="submit_clinical_flags",
    )
    log_usage("clinical", usage)
    return result
