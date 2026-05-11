# Evals

The eval harness exists to catch regressions when the prompts or tool
schemas change. It's not a benchmark.

## Running

```bash
# Eval runner pins to synthetic source.
CASE_SOURCE=synthetic python -m evals.run_eval evals/fixtures/baseline.json
```

The runner generates the synthetic case set anchored to the fixture's
`run_date`, runs all four analysis modules, and checks the fixture's
expectations:

- `must_flag` — case IDs that should appear in clinical flags **or** in
  escalation scores ≥ 0.5
- `must_not_flag` — case IDs that should not appear as critical
- `required_topic_keywords` — substrings that must appear in at least one
  cluster label (cluster-coherence smoke test)

Results land in `evals/results/eval_<date>_<ts>.json` and a summary prints
to stdout.

## Adding fixtures

Each fixture targets a known synthetic case set (date + seed). The default
seed `4242` and date `2026-05-10` produce a stable case set; tweaking the
seed produces a different one.

To add a fixture exercising a different distribution:

```bash
# Generate a case set with a new seed
python -c "
from datetime import date
from src.sources.synthetic import save_sample_json
from pathlib import Path
save_sample_json(Path('synthetic_data/seed_99.json'), date(2026, 6, 1), seed=99)
"
# Eyeball the JSON, pick IDs that should and shouldn't flag, write a fixture.
```

## Why this design

The synthetic data is deterministic, so eval runs are reproducible. A model
non-determinism that *would* fail a fixture is exactly the kind of
regression we want to catch — the prompt is brittle or the schema isn't
constraining the model enough.

Run the eval after any prompt change, before merging.
