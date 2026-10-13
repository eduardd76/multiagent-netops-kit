"""Plain-text views for the notebooks (they read the same in Colab, a terminal and a test log)."""
from __future__ import annotations

from netops.protocol import Bus

_SKIN = None


def configure(skin=None) -> None:
    """Customer mode: every panel prints the customer's names."""
    global _SKIN
    _SKIN = skin


def _p(*parts) -> None:
    text = " ".join(str(p) for p in parts)
    print(_SKIN.display(text) if _SKIN is not None else text)


def banner(text: str) -> None:
    line = "=" * min(len(text) + 4, 100)
    _p(f"{line}\n  {text}\n{line}")


def dashboard(reachability: str | None) -> None:
    _p("  CPU: OK   Memory: OK   Interfaces up: OK   Alarms: 0      No alarm, no threshold, nothing red.")
    _p("  >>> RESOLVED. <<<" if reachability == "PASS" else "  >>> RESOLVED? <<<   (reachability() = "
          f"{reachability or '?'})")


def llm_label(llm) -> str:
    if hasattr(llm, "inner"):
        return llm_label(llm.inner) + " -- customer names, secrets redacted"
    name = type(llm).__name__
    if name == "MockLLM":
        return "MockLLM (deterministic stand-in -- not a model)"
    if name == "FallbackLLM":
        return f"live endpoint ({llm.primary.model}) with MockLLM fallback"
    return name


def transcript(bus: Bus, width: int = 70) -> None:
    _p(f"{'from':>16}    {'to':<16} {'intent':<9} {'status':<12} task")
    for m in bus.transcript:
        _p(f"{m.from_:>16} -> {m.to:<16} {m.intent:<9} {m.status:<12} {m.task[:width]}")


def findings(items) -> None:
    for f in items:
        _p(f"* {f.title}\n    explains the outage: {f.explains_outage}   evidence: {', '.join(f.evidence_ids)}\n"
              f"    {f.narrative}")


def gate(g) -> None:
    """What the human sees before deciding: diagnosis, exact commands, expected result, checks."""
    p = g.proposal
    _p(f"CHANGE REQUEST v{p['version']}  --  playbook entry: {p['playbook_entry']}")
    _p(f"  diagnosis : {p['diagnosis']}\n  rationale : {p['rationale']}")
    _p("  commands  :\n" + "\n".join(f"      {c}" for c in p["commands"]))
    _p("  rollback  :\n" + "\n".join(f"      {c}" for c in p["rollback"]))
    _p(f"  expected  : {'; '.join(p['expected_post_state'])}")
    _p(f"  blast radius: {p['blast_radius']}  [evidence: {', '.join(p['blast_radius_evidence_ids']) or 'none'}]")
    for b in p.get("blocked", []):
        _p(f"  BLOCKED before proposal: {b['command']}  ({b['reason']})")
    _p("  pre-checks:")
    for c in g.pre_checks:
        _p(f"      {'PASS' if c['ok'] else 'FAIL'}  {c['check']}: {c['detail']}")
    checklist(g)
    _p(f"  ready for approval: {g.ready}")


def checklist(g) -> None:
    """The on-call engineer's nine questions. 'kit' rows are answered by code; 'human' rows are yours."""
    from netops.checklist import answer
    _p("  ON-CALL CHECKLIST (9 questions before any change):")
    for r in answer(g):
        mark = {True: "yes ", False: "NO  ", None: "you "}[r["ok"]]
        _p(f"      {r['n']}. [{mark}] {r['question']}\n             ({r['status']}: {r['detail']})")


def artifacts(gate, approvals) -> None:
    """The three artifacts every change leaves behind: proposal, validation report, approval record.
    In a regulated network the audit trail is the product -- this is what you hand the auditor."""
    p, r = gate.proposal, gate.result
    _p("THREE ARTIFACTS PER ACTION")
    _p(f"1) PROPOSAL v{p['version']}  ({p['playbook_entry']}, device {p['device']})")
    _p("     commands : " + " / ".join(p["commands"]))
    _p("     rollback : " + " / ".join(p["rollback"]))
    _p(f"     evidence : blast radius {', '.join(p['blast_radius_evidence_ids']) or 'none'}")
    _p("2) VALIDATION REPORT")
    for phase, checks in (("pre ", gate.pre_checks), ("post", r.get("post_checks", []))):
        for c in checks:
            _p(f"     {phase} {'PASS' if c['ok'] else 'FAIL'}  {c['check']}: {c['detail']}")
    _p(f"     ground truth: reachability() = {r.get('reachability', '?')}")
    _p("3) APPROVAL RECORD")
    for e in approvals.log:
        _p("     " + "  ".join(f"{k}={v}" for k, v in e.items()))
    ex = r.get("execution", {})
    _p(f"     executor applied {len(ex.get('applied', []))} commands, rolled back: {ex.get('rolled_back')}, "
          f"waited {ex.get('waited_s', 0):.0f}s for FULL")


def audit(network) -> None:
    rows = network.fabric.audit if network.fabric else []
    _p("DEVICE CHANGE AUDIT")
    for a in rows or [{"ts": "-", "device": "-", "interface": "-", "set": "no changes", "to": "", "by": "-"}]:
        _p(f"  {a['ts']}  {a['device']} {a['interface']}  {a['set']} -> {a['to']}   by {a['by']}")
