"""Daily briefing orchestrator.

Pull cases → 4 Sonnet analyses (sharing one cached case context) → 1 Opus
narrative → compose HTML → send. Entry point for the GitHub Actions workflow
and for local runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from src.analysis.client import CaseContext, make_client
from src.analysis.clinical import run_clinical
from src.analysis.escalation import run_escalation
from src.analysis.narrative import run_narrative
from src.analysis.sla import run_sla
from src.analysis.topics import run_topics
from src.config import Config, load_config
from src.email_brief.compose import compose, save_to_disk
from src.email_brief.send import send
from src.sources import get_source


def run(cfg: Config) -> int:
    started = time.monotonic()

    # 1. Pull cases
    source = get_source(cfg)
    cases = source.fetch_cases(cfg.run_date)
    print(f"Fetched {len(cases)} cases for {cfg.run_date.isoformat()} from {cfg.case_source}")

    if not cases:
        print("No cases — nothing to brief on. Exiting clean.")
        return 0

    # 2. Build shared cached context
    context = CaseContext.build(cases, cfg.run_date.isoformat())
    print(f"Built case context: {len(context.cases_json):,} chars JSON")

    # 3. Analyses (run sequentially so cache reads accumulate on calls 2-4)
    client = make_client(cfg.anthropic_api_key)
    topics = run_topics(client, cfg.sonnet_model, context)
    escalation = run_escalation(client, cfg.sonnet_model, context)
    clinical = run_clinical(client, cfg.sonnet_model, context)
    sla = run_sla(client, cfg.sonnet_model, context)

    # 4. Narrative (Opus, different model — own cache scope)
    narrative = run_narrative(
        client,
        cfg.opus_model,
        run_date_iso=cfg.run_date.isoformat(),
        case_count=len(cases),
        topics=topics,
        escalation=escalation,
        clinical=clinical,
        sla=sla,
    )

    # 5. Compose HTML
    briefing = compose(
        run_date=cfg.run_date,
        cases=cases,
        narrative=narrative,
        topics=topics,
        escalation=escalation,
        clinical=clinical,
        sla=sla,
        instance_url=cfg.sf_instance_url,
        source_label=cfg.case_source,
        dry_run=(cfg.email_provider == "console"),
    )

    saved_path = save_to_disk(briefing, cfg.output_dir)
    print(f"Wrote {saved_path}")

    # Also dump raw analysis outputs for evals / debugging
    _dump_raw(cfg.output_dir / f"raw_{cfg.run_date.isoformat()}.json", {
        "run_date": cfg.run_date.isoformat(),
        "case_count": len(cases),
        "narrative": narrative,
        "topics": topics,
        "escalation": escalation,
        "clinical": clinical,
        "sla": sla,
    })

    # 6. Send
    send(briefing, cfg)

    elapsed = time.monotonic() - started
    print(f"Done in {elapsed:.1f}s.")
    return 0


def _dump_raw(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.orchestrator",
        description="Generate the daily Salesforce case briefing.",
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="Closed-case date to analyze (YYYY-MM-DD). Defaults to RUN_DATE env var or yesterday UTC.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(2)
        os.environ["RUN_DATE"] = args.date

    try:
        cfg = load_config()
    except Exception as exc:  # configuration error — fail fast with a clean message
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(cfg))
