"""The on-call engineer's nine questions before ANY change to a production router.

These are the questions a senior network engineer asks out loud before typing `configure`. The gate panel
(`render.gate`) prints them next to the proposal. Some the kit can answer from evidence (a pre-check, a field of the
proposal, a property of the executor). The rest stay with the human -- and the panel says so, instead of pretending.

    status "kit"   -> answered by code: a validation pre-check, the proposal itself, or the executor
    status "human" -> only the approver can answer it (change window, business context, judgement)
"""
from __future__ import annotations

# (key, question). Order matters: it is the order an engineer walks through a change.
QUESTIONS: list[tuple[str, str]] = [
    ("evidence", "Does the evidence support the diagnosis? (area 0.0.0.1 on BRANCH-7 vs 0.0.0.0 on HUB-1, in actual output)"),
    ("target", "Is the target value verified against the neighbor -- confirmed, not remembered?"),
    ("scope", "Scoped to only the affected interface?"),
    ("blast_radius", "Blast radius: what else rides on this link?"),
    ("rollback", "Tested rollback in hand before we commit?"),
    ("window", "Are we allowed to touch routing right now (window / approval context)?"),
    ("pass_fail", "Pass/fail defined before commit: FULL, route back, 5/5 ping?"),
    ("backout", "Back-out trigger set: not FULL in ~60 s -> revert?"),
    ("save", "Save only after validation passes -- write memory is the last step."),
]

# Plan 3 contract name: the nine questions as plain strings (guide, approver sheet, cheat sheet, deck).
NOC_CHECKLIST: list[str] = [q for _, q in QUESTIONS]

SAVE_COMMANDS = ("write memory", "copy running-config startup-config", "wr mem")


def answer(gate) -> list[dict]:
    """[{n, question, status: kit|human, ok: bool|None, detail}] for a GateRequest (or anything with
    .proposal and .pre_checks). `ok is None` means: the human must answer this one."""
    p = gate.proposal
    pre = {c["check"]: c for c in gate.pre_checks}

    def from_check(name: str) -> tuple[str, bool | None, str]:
        c = pre.get(name)
        return ("kit", c["ok"], f"pre-check {name}: {c['detail']}") if c else ("human", None, "no pre-check ran")

    interfaces = [c for c in p["commands"] if c.startswith("interface ")]
    saves = [c for c in p["commands"] if c.startswith(SAVE_COMMANDS)]
    rows = {
        "evidence": from_check("fault_still_present"),
        "target": from_check("target_matches_neighbor"),
        "scope": ("kit", len(interfaces) == 1, f"interfaces touched: {', '.join(interfaces) or 'none'}"),
        "blast_radius": from_check("blast_radius_evidenced"),
        "rollback": ("kit", bool(p.get("rollback")), " / ".join(p.get("rollback", [])) or "no rollback"),
        "window": ("human", None, "the kit cannot know your change calendar -- you answer this"),
        "pass_fail": from_check("expected_post_state_matches"),
        "backout": ("kit", True, "executor backs out automatically if OSPF is not FULL before its timer"),
        "save": ("kit", not saves, "no save command in the change; save after post-validation"
                 if not saves else f"save inside the change: {saves}"),
    }
    out = []
    for n, (key, question) in enumerate(QUESTIONS, 1):
        status, ok, detail = rows[key]
        out.append({"n": n, "key": key, "question": question, "status": status, "ok": ok, "detail": detail})
    return out
