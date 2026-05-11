"""Evaluation harness for the analysis modules.

Loads a fixture (a JSON file pinning a small case set + expected outcomes),
runs the four analyses, and scores them against the fixture's expectations.

The point of evals here isn't precision-recall on a benchmark dataset — it's
catching regressions when prompts or tool schemas change. A fixture pins:

  - **Must-flag** case IDs (cases that should appear in escalation OR clinical
    output)
  - **Must-not-flag** case IDs (routine cases that shouldn't appear as
    critical)
  - **Required topic** labels (cases of a known type should cluster
    coherently)

Run with:

    python -m evals.run_eval evals/fixtures/baseline.json
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from src.analysis.client import CaseContext, make_client
from src.analysis.clinical import run_clinical
from src.analysis.escalation import run_escalation
from src.analysis.sla import run_sla
from src.analysis.topics import run_topics
from src.config import REPO_ROOT, load_config
from src.sources import get_source


def main(fixture_path: Path) -> int:
    fixture = json.loads(fixture_path.read_text())
    run_date = date.fromisoformat(fixture["run_date"])

    cfg = load_config()
    # Eval pins the source to synthetic — fixtures reference synthetic case IDs.
    if cfg.case_source != "synthetic":
        print("Eval runner pins case_source=synthetic. Set CASE_SOURCE=synthetic.", file=sys.stderr)
        return 2

    source = get_source(cfg)
    cases = source.fetch_cases(run_date)
    context = CaseContext.build(cases, run_date.isoformat())

    client = make_client(cfg.anthropic_api_key)
    topics = run_topics(client, cfg.sonnet_model, context)
    escalation = run_escalation(client, cfg.sonnet_model, context)
    clinical = run_clinical(client, cfg.sonnet_model, context)
    sla = run_sla(client, cfg.sonnet_model, context)

    results = {
        "fixture": str(fixture_path),
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "checks": [],
        "raw": {"topics": topics, "escalation": escalation, "clinical": clinical, "sla": sla},
    }

    flagged_ids = set()
    flagged_ids.update(s["case_id"] for s in escalation.get("scores", []) if s.get("score", 0) >= 0.5)
    flagged_ids.update(f["case_id"] for f in clinical.get("flags", []))

    for case_id in fixture.get("must_flag", []):
        ok = case_id in flagged_ids
        results["checks"].append({
            "name": f"must_flag:{case_id}",
            "passed": ok,
            "expected": "appears in escalation>=0.5 OR clinical flags",
            "actual": "present" if ok else "absent",
        })

    for case_id in fixture.get("must_not_flag", []):
        ok = case_id not in flagged_ids
        results["checks"].append({
            "name": f"must_not_flag:{case_id}",
            "passed": ok,
            "expected": "not flagged",
            "actual": "absent" if ok else "present",
        })

    # Topic-coherence: at least one cluster label must contain each required keyword
    cluster_labels = " ".join(c.get("label", "").lower() for c in topics.get("clusters", []))
    for kw in fixture.get("required_topic_keywords", []):
        ok = kw.lower() in cluster_labels
        results["checks"].append({
            "name": f"topic_keyword:{kw}",
            "passed": ok,
            "expected": f"keyword '{kw}' appears in any cluster label",
            "actual": "present" if ok else "absent",
        })

    passed = sum(1 for c in results["checks"] if c["passed"])
    total = len(results["checks"])
    results["score"] = f"{passed}/{total}"

    out_dir = REPO_ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_{run_date.isoformat()}_{int(datetime.now().timestamp())}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nEval: {passed}/{total} passed ({out_path})")
    for c in results["checks"]:
        marker = "PASS" if c["passed"] else "FAIL"
        print(f"  [{marker}] {c['name']}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m evals.run_eval <fixture_path>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
