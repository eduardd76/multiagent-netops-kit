# kit/tests/test_golden.py
"""Pins every kit output the speaker script quotes (default configuration, MockLLM). A refactor must not change any of
it. Regenerate ONLY on purpose: NETOPS_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_golden.py"""
import json
import os
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden" / "default_run.json"
KEEP = ("version", "device", "playbook_entry", "commands", "rollback", "expected_post_state", "diagnosis",
        "rationale", "blast_radius", "blast_radius_evidence_ids")


def snapshot() -> dict:
    from netops.llm import MockLLM
    from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, run_lab1, team
    from netops.scoring import measure_single, measure_team

    lab1 = run_lab1(new_incident(llm=MockLLM(), verbose=False))
    inc = new_incident(llm=MockLLM(), verbose=False)
    g1 = team(inc).run_to_gate(ALERT)
    g2 = g1.reject(ONCALL_REJECT)
    res = g2.approve("on-call")
    # the one deliberate change: the validation post-check summary line becomes generic in Task 4
    trace = [[w, t] for w, t in inc.trace.lines if not (w == "validation" and t.startswith("after "))]

    def cost(m):
        return {k: v for k, v in m["cost"].items() if k != "wall time (s)"}

    return {"lab1": lab1, "trace": trace,
            "transcript": [[m.from_, m.to, m.intent, m.status, m.task] for m in inc.bus.transcript],
            "evidence": [[e.id, e.tool, e.args] for e in inc.evidence.all()],
            "proposals": [{k: g.proposal[k] for k in KEEP} for g in (g1, g2)],
            "pre_checks": [g1.pre_checks, g2.pre_checks],
            "post_checks": [[c["check"], c["ok"], c["detail"]] for c in res["post_checks"]],
            "reachability": res["reachability"], "audit": inc.network.fabric.audit,
            "approval_log": [{k: v for k, v in e.items() if k != "digest"} for e in inc.approvals.log],
            "cost_single": cost(measure_single(MockLLM())), "cost_team": cost(measure_team(MockLLM()))}


def test_default_outputs_unchanged():
    got = json.loads(json.dumps(snapshot(), default=str))
    if os.environ.get("NETOPS_UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True))
    assert got == json.loads(GOLDEN.read_text())
