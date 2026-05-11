# Synthetic case data

`cases_sample.json` is a deterministic snapshot of 150 cases produced by
`src/sources/synthetic.py`, anchored to **2026-05-10**.

The orchestrator does **not** read this file. The `SyntheticSource`
regenerates the same set of cases anchored to whichever `RUN_DATE` is in
effect. The JSON is here for two reasons:

1. **Inspection** — eyeball the shape and content variety without running Python.
2. **Eval fixtures** — `evals/` references stable case IDs from this snapshot.

## Regenerating

```bash
python -m src.sources.synthetic synthetic_data/cases_sample.json 2026-05-10
```

The first positional arg is the output path, the second is the anchor date
(ISO format).

## Content shape

A healthcare member-services org. 19 categories across pharmacy, clinical,
claims, billing, prior auth, appeals, enrollment, technical, and benefits
inquiries. Mix is intentionally messy: terse one-liners alongside verbose
multi-paragraph complaints; agents that write fluently next to ones who paste
codes. ~12% of SLA-tracked cases breach. ~15% of cases bounce between owners.
Clinical-content cases include adverse drug reactions, mental health crises,
and symptom inquiries — these are the ones the clinical-flag analysis should
catch.
