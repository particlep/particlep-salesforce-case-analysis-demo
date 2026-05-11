from __future__ import annotations

import anthropic

from .client import CaseContext, load_prompt, log_usage, run_sonnet_analysis


def run_topics(
    client: anthropic.Anthropic,
    model: str,
    context: CaseContext,
) -> dict:
    user_prompt = (
        load_prompt("topic_clustering")
        + "\n\nNow produce the clustering via the submit_topic_clusters tool."
    )
    result, usage = run_sonnet_analysis(
        client,
        model=model,
        context=context,
        user_prompt=user_prompt,
        tool_name="submit_topic_clusters",
    )
    log_usage("topics", usage)
    return result
