"""Wire everything for a lab: a fresh incident, Lab 1's single agent, the full team, and the contrast."""
from __future__ import annotations

from dataclasses import dataclass, field

from netops.agents.coordinator import Coordinator, GateRequest
from netops.agents.single import SingleAgent
from netops.approval import Approvals, GateError
from netops.evidence import EvidenceStore
from netops.llm import LLM, make_llm
from netops.network import Network
from netops.protocol import Bus
from netops.scoring import claims_resolved
from netops.trace import Trace

ALERT = ("P1 -- users at BRANCH-7 cannot reach the core service 10.100.10.10. The dashboard is green: "
         "no alarm, no threshold, nothing red.")

ONCALL_REJECT = ("No. You're telling me what to type. You're not telling me what breaks if you're wrong -- "
                "show me the neighbor tables on both ends. Rejected. Give me a change I'd actually approve.")


@dataclass
class Incident:
    network: Network
    llm: LLM
    trace: Trace
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    bus: Bus = field(default_factory=Bus)
    approvals: Approvals = field(default_factory=Approvals)
    pack: object = None              # a pack object in hardened mode (None = the workshop)
    skin: object = None
    channel: object = None           # an ApprovalChannel
    audit: object = None             # an AuditSink (Fanout)
    sources: tuple = ()


def new_incident(variant: str | None = None, llm: LLM | None = None, network: Network | None = None,
                 verbose: bool = True) -> Incident:
    """A fresh, isolated world: new network state, new evidence, new approvals (old tokens can't be reused)."""
    from netops import render                   # a display mapping set earlier must not skin the workshop
    render.configure(None)
    return Incident(network=network or Network.simulated(variant), llm=llm or make_llm(), trace=Trace(verbose))


def run_lab1(inc: Incident) -> dict:
    if inc.pack is not None:                    # its tools write with no playbook, no gate, no human
        raise GateError("Lab 1's ungated agent is not available in hardened mode")
    run = SingleAgent(inc.llm, inc.network, inc.evidence).run(ALERT, trace=inc.trace)
    writes = [c for c in run.calls if c["tool"] in ("bounce_interface", "clear_counters") and c["ok"]]
    last = max((i for i, c in enumerate(run.calls) if c in writes), default=-1)
    verified = any(c["tool"] in ("ping", "route") and c["ok"] for c in run.calls[last + 1:]) if writes else False
    return {"agent_says": run.final_text, "claimed_resolved": claims_resolved(run.final_text),
            "reachability": inc.network.reachability(), "writes": [c["tool"] for c in writes],
            "verified_outcome_after_its_change": verified, "human_approved": False,
            "independent_check": False, "model": sorted(set(run.sources))}


def team(inc: Incident, approver: str = "on-call") -> Coordinator:
    pack = inc.pack
    if pack is None:
        return Coordinator(inc.network, inc.llm, bus=inc.bus, evidence=inc.evidence, approvals=inc.approvals,
                           trace=inc.trace, approver=approver)
    return Coordinator(inc.network, inc.llm, bus=inc.bus, evidence=inc.evidence, approvals=inc.approvals,
                       trace=inc.trace, approver=pack.approval.get("approver", approver),
                       requester=pack.requester, demo=True, audit=inc.audit, sources=inc.sources)


def run_team(inc: Incident, approver: str = "on-call", reject_first: bool = True) -> dict:
    gate: GateRequest = team(inc, approver).run_to_gate(ALERT)
    if reject_first or not gate.ready:
        gate = gate.reject(ONCALL_REJECT)
    return gate.approve(approver)


def contrast(lab1: dict, lab4: dict) -> str:
    rows = [("Says 'resolved'", lab1["claimed_resolved"], lab4["resolved"]),
            ("reachability()", lab1["reachability"], lab4["reachability"]),
            ("Change came from a vetted playbook", False, True),
            ("A human approved the change", lab1["human_approved"], True),
            ("Independent validation after the change", lab1["independent_check"], True)]
    out = [f"{'':42} {'Lab 1 (one agent)':>18} {'Lab 4 (team)':>14}"]
    out += [f"{q:42} {str(a):>18} {str(b):>14}" for q, a, b in rows]
    return "\n".join(out)
