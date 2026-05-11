# Daily support briefing — Salesforce + Claude

A single-script pipeline that pulls yesterday's Salesforce Cases, runs four
parallelized Claude analyses (topic clustering, escalation risk, clinical
flags, SLA/ownership), composes a 60-second-read HTML brief with an
Opus-written narrative summary at the top, and emails it at 7am.

Built to demonstrate Service Cloud Case fluency, Claude API design (prompt
caching across analyses, tool-use for structured output, Sonnet/Opus split),
and PHI-aware data handling. Lives in one GitHub Actions cron + one Python
package — no persistent infrastructure.

## About this version

This code is a variation of a project originally built for a client to
analyze their Salesforce Case data. The original ran against a live
Salesforce org.

This public version preserves the architecture and prompt design 
but swaps the live Salesforce source for a synthetic-case generator so the
repo runs end-to-end without a Salesforce org, an API user, or any real
member data. The 150 mock cases in `synthetic_data/` are deterministic and
intentionally messy — adverse drug events, bouncing owners, near-SLA-breach
cases, terse one-liners next to multi-paragraph complaints — so the
analysis modules have realistic signal to find. The `SalesforceSource`
implementation is still here and still works against a real org if you wire
up credentials; the `CaseSource` Protocol means the analysis layer can't
tell the difference.

## Quick start (no Salesforce, no email account)

```bash
git clone <this repo>
cd salesforce-case-analysis

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Minimal env — just an Anthropic API key.
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY. Leave everything else default
# (CASE_SOURCE=synthetic, EMAIL_PROVIDER=console).

python -m src.orchestrator
```

This runs against 150 deterministic-but-realistically-messy synthetic
healthcare member-services cases anchored to `RUN_DATE`. The rendered HTML
lands in `sample_outputs/briefing_<date>.html`.

## What runs

```
┌────────────────────────┐
│ GitHub Actions cron    │  7am daily
│ (.github/workflows/    │
│  daily-briefing.yml)   │
└──────────┬─────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Python orchestrator                  │
│                                       │
│ 1. Pull cases                        │
│    (sources/{salesforce,synthetic})  │
│ 2. Build cached case context         │
│ 3. 4 Sonnet analyses                 │
│    (sharing one cache breakpoint)    │
│ 4. 1 Opus narrative                  │
│ 5. Compose HTML + send               │
└──┬──────────────┬──────────────┬─────┘
   ▼              ▼              ▼
┌────────┐  ┌─────────┐  ┌──────────────┐
│ SFDC   │  │ Claude  │  │ SendGrid OR  │
│ REST   │  │ API     │  │ console      │
└────────┘  └─────────┘  └──────────────┘
```

## Project structure

```
salesforce-case-analysis/
├── README.md
├── .github/workflows/daily-briefing.yml
├── src/
│   ├── orchestrator.py             # entry point
│   ├── config.py                   # env-driven config
│   ├── sources/
│   │   ├── base.py                 # CaseRecord protocol
│   │   ├── salesforce.py           # simple-salesforce + SOQL
│   │   └── synthetic.py            # deterministic 150-case generator
│   ├── analysis/
│   │   ├── client.py               # shared Anthropic client + 4 tools + cached context
│   │   ├── topics.py               # Sonnet — topic clustering
│   │   ├── escalation.py           # Sonnet — escalation risk scoring
│   │   ├── clinical.py             # Sonnet — clinical red flags (PHI-aware)
│   │   ├── sla.py                  # Sonnet — SLA/ownership analysis
│   │   └── narrative.py            # Opus — 60-second narrative
│   ├── email_brief/
│   │   ├── compose.py              # Jinja2 HTML render
│   │   ├── template.html
│   │   └── send.py                 # sendgrid | console
│   └── prompts/
│       ├── topic_clustering.md
│       ├── escalation_scoring.md
│       ├── clinical_flags.md
│       ├── sla_analysis.md
│       └── daily_narrative.md
├── synthetic_data/cases_sample.json
├── evals/
│   ├── run_eval.py
│   ├── fixtures/baseline.json
│   └── results/
├── docs/
│   ├── soql-queries.md
│   ├── phi-handling.md
│   └── extending-to-write-back.md
└── sample_outputs/
```

## How the Claude calls are structured

The four Sonnet analyses share an expensive piece of context — the full set
of yesterday's cases serialized as JSON (~130KB → ~35K input tokens). Without
prompt caching, that context would be re-billed four times.

Instead, every Sonnet call uses identical bytes for `tools` and `system`,
with a `cache_control: {type: "ephemeral"}` breakpoint at the end of the
case-data block. The first call (topics) writes the cache; the next three
calls read it at ~0.1× cost. Only the `messages` payload and `tool_choice`
differ per call — and `tool_choice` doesn't invalidate the tools or system
cache.

```
                  ┌─ tools (identical, sorted) ──┐
                  │  • submit_clinical_flags     │ cached
                  │  • submit_escalation_scores  │
                  │  • submit_sla_analysis       │
                  │  • submit_topic_clusters     │
                  └──────────────────────────────┘
                  ┌─ system (identical) ──────────┐
                  │  • generic role               │ cached
                  │  • case data JSON  ← breakpoint
                  └──────────────────────────────┘
                  ┌─ messages (varies) ───────────┐
                  │  • the specific analysis ask  │ not cached
                  └──────────────────────────────┘
                  + tool_choice (varies — does NOT invalidate cache above)
```

The `[cache_write_input_tokens]` / `[cache_read_input_tokens]` numbers print
in the orchestrator log so you can verify caching is working. Expected
pattern on a fresh run:

```
[topics] in=240 cache_write=35200 cache_read=0    out=1500
[escalation] in=240 cache_write=0   cache_read=35200 out=900
[clinical] in=240 cache_write=0   cache_read=35200 out=600
[sla] in=240 cache_write=0   cache_read=35200 out=750
```

For the architectural detail on why this works (prefix-match caching,
silent invalidators, tool-order stability), see Anthropic's
[prompt-caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

## Models

| Call           | Model              | Why                                              |
| -------------- | ------------------ | ------------------------------------------------ |
| 4× analyses    | `claude-sonnet-4-6`| Best speed/intelligence for structured extraction with tool use. |
| Narrative      | `claude-opus-4-7`  | The 60-second narrative is the highest-leverage prose in the email; pay Opus for it. |

## Source: live Salesforce vs. synthetic

Two `CaseSource` implementations behind a Protocol — the analysis layer is
source-agnostic.

- **`SyntheticSource`** generates 150 deterministic cases anchored to the run
  date. Run-to-run stable, full of the messy real-world signals the
  analysis modules need to detect: adverse drug events, mental-health
  crises, bouncing owners, near-SLA-breach cases, terse one-liners
  alongside multi-paragraph complaints. Default for the portfolio demo.
- **`SalesforceSource`** issues a single `simple-salesforce` `query_all`
  against `Case` with the SOQL in `docs/soql-queries.md`. Pulls Cases
  created or last-modified yesterday, plus Comments, History, related
  Contact and Account in subqueries.

Pick via `CASE_SOURCE=synthetic|salesforce`.

## PHI handling

This is healthcare-adjacent data by design. Two-line summary:

- Full case descriptions go to Anthropic over TLS, never to disk and never
  to the email reader.
- The clinical-flag prompt and tool schema explicitly forbid PHI in the
  analyst summary fields. The output that lands in the email is case IDs
  + categorization + sanitized one-liners; reviewers follow the Salesforce
  link for full context.

Full detail and threat model in `docs/phi-handling.md`.

## What's intentionally not here

- **Day-over-day topic deltas.** Mentioned in the spec but require
  persistence; "no persistent infrastructure" wins. Adding a 7-day rolling
  history file in `sample_outputs/` would be ~30 lines.
- **Salesforce write-back.** v2 territory — design sketch in
  `docs/extending-to-write-back.md`.
- **A dashboard.** This is an email pipeline; the dashboard is the email.

## Why this exists

A Salesforce-fluent RevOps builder reading this should see:

1. **Service Cloud Case fidelity** — the SOQL uses real fields (SLA
   milestones, IsEscalated, owner history) not just `Status` + `Subject`.
2. **PHI-aware prompt design** — the clinical-flag contract is explicit in
   both prompt and tool schema, not bolted on.
3. **Claude API patterns at a non-trivial scale** — prompt caching across
   sibling calls, Sonnet/Opus tier choice, tool-use for structured output.
4. **Honest synthetic data** — the messy realism is the point; clean toy
   data would defeat the analysis.

## License

MIT.
