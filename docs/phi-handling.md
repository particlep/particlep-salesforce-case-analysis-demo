# PHI handling

This pipeline operates on Case content that — in a real healthcare member-
services org — contains Protected Health Information. The design treats PHI
as in-flight data, never persisted in any output the email reader sees.

## What's in-scope as PHI

- Full case `Description` and `CaseComment.body` (clinical content)
- `Contact.Name`, `Contact.Email`, `Contact.Phone`
- Anything in `EmailMessage.TextBody` if email-to-case is enabled

## Where PHI flows

1. **Salesforce → in-memory `CaseRecord`.** The `simple-salesforce` client
   pulls the raw rows over TLS. They live as Python objects in process memory
   for the duration of the run.
2. **In-memory → Anthropic API call.** The full case payload is sent in the
   `system` field of the four Sonnet calls. Anthropic's API is a BAA-
   eligible Trust Center surface; if you're processing actual PHI, you need
   to (a) sign a BAA with Anthropic and (b) confirm your org's privacy review
   has cleared LLM analysis of this data.
3. **Anthropic response → analysis output.** Tool-use outputs contain case
   IDs, scores, and *short* analyst summaries. The clinical-flag prompt
   explicitly forbids echoing PHI in summaries — see
   `src/prompts/clinical_flags.md`.
4. **Analysis output → HTML email.** Only case IDs, case numbers, subjects,
   priority/origin, and the analyst summaries make it into the email. The
   full case `Description` and comment bodies are **never** rendered into
   HTML.

## The PHI-free output contract

The clinical analysis prompt specifies:

> Critical: do NOT echo back personally identifying details. Reference the
> case by ID and category only. The clinical team will look up the full case
> in Salesforce.

And the tool's `summary` field documents:

> One sentence in clinical terms. No member names, no direct quotes, no
> specific identifiers.

This is two layers of belt-and-suspenders: the prompt, and the tool schema
description.

### What if the model violates the contract?

This is a real concern. The current pipeline has no automated PHI scrubber on
the analysis output. Three mitigations to consider before production use:

1. **Output-side filter.** Run the analyst summaries through a NER + regex
   pass (names, dates, phone, email, MRN-shaped IDs) before composing the
   email. Reject and re-prompt if PII is detected.
2. **Manual review for the first N runs.** Before fully automating, route
   the email to a reviewer for the first ~10 runs and spot-check.
3. **Reduce the surface.** If reviewer fatigue is a concern, drop the
   `summary` field from clinical flags entirely and ship only category +
   urgency + Salesforce link. Reviewer opens the case to see context.

## What's stored on disk

- `sample_outputs/briefing_YYYY-MM-DD.html` — the rendered email
- `sample_outputs/raw_YYYY-MM-DD.json` — the full analysis output (the
  same content that's in the email, plus raw tool outputs for evals)

**The raw case data is not written anywhere.** No CSV dumps, no caching to
disk, no log files containing case bodies.

## Logging

Print statements in the orchestrator log token counts and case counts only —
no case content. Don't add logging that writes case bodies to stdout or
stderr; the GitHub Actions runner exports stdout as an artifact, which would
inadvertently persist PHI.

## In short

PHI lives in three places during a run: the Python process, the TLS
connection to Anthropic, and the Anthropic API processing. After the run:
the rendered email (PHI-free by contract) and the raw analysis JSON
(PHI-free by contract). The original case bodies stay in Salesforce.
