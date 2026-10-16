"""Coordinator: orchestrates diagnose -> propose -> validate(pre) -> HUMAN -> apply -> validate(post).
It routes on message status and holds the incident state. It NEVER runs a device command itself."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from netops.agents.config import ConfigAgent
from netops.agents.troubleshooting import Finding, TroubleshootingAgent
from netops.agents.validation import ValidationAgent
from netops.approval import Approvals, GateError, digest_of
from netops.evidence import EvidenceStore
from netops.executor import Executor, default_backout_triggered
from netops.llm import LLM
from netops.network import Network
from netops.playbook import load_playbook
from netops.ports import ApprovalTicket
from netops.protocol import Bus, Message


class Escalation(RuntimeError):
    """Stop and hand the incident to a person: no playbook fix for the diagnosed cause, or the
    on-call engineer rejected the change too many times. Never improvise CLI to get unstuck."""


def is_near_copy(previous: dict, revised: dict) -> bool:
    """True if the revised proposal adds nothing the reviewer could weigh: a near-copy gets refused
    instead of being sent back to the human for another look.
    TODO(user): decide what counts as "nothing new" -- see the hand-off note."""
    return False


def choose_root_cause(findings: list[Finding]) -> Finding | None:
    """Act on the finding that explains the OUTAGE and has a playbook fix -- not on the loudest one."""
    playbook = load_playbook()
    for f in findings:
        if f.explains_outage and f.id in playbook and playbook[f.id].root_cause:
            return f
    return None


class Coordinator:
    name = "coordinator"

    def __init__(self, network: Network, llm: LLM, *, bus: Bus | None = None, evidence: EvidenceStore | None = None,
                 approvals: Approvals | None = None, trace=None, approver: str = "on-call",
                 choose: Callable[[list[Finding]], Finding | None] = choose_root_cause,
                 backout_triggered: Callable = default_backout_triggered, max_rejections: int = 3,
                 requester: str | None = None, demo: bool = False, audit=None, sources=()):
        self.net, self.bus = network, bus or Bus()
        self.ev, self.approvals = evidence if evidence is not None else EvidenceStore(), approvals or Approvals()
        self.trace, self.approver, self.choose = trace or (lambda *a: None), approver, choose
        self.max_rejections = max_rejections        # after this many human rejections: stop and escalate
        ro = network.read_only()                    # specialists read; only the Executor holds the writer
        self.requester, self.sources, self.demo = requester, tuple(sources), demo
        self.troubleshooting = TroubleshootingAgent(llm, ro, self.ev, self.trace, sources=self.sources)
        self.config = ConfigAgent(llm, ro, self.ev, self.trace)
        self.validation = ValidationAgent(ro, self.ev, self.trace)
        self.executor = Executor(network, self.approvals, backout_triggered=backout_triggered, audit=audit,
                                 allowed_devices=set(network.devices) if demo else None,
                                 playbook=load_playbook() if demo else None,
                                 recheck=self.validation.pre_check if demo else None)
        for agent in (self.troubleshooting, self.config, self.validation):
            self.bus.register(agent.name, agent.handle)
        self.findings: list[Finding] = []
        self.root_cause: Finding | None = None

    def _send(self, to: str, intent: str, task: str, payload: dict) -> Message:
        return self.bus.send(Message(**{"from": self.name}, to=to, intent=intent, task=task, payload=payload,
                                     status="requested"))

    def diagnose(self, alert: str) -> list[Finding]:
        reply = self._send("troubleshooting", "diagnose", alert, {})
        self.findings = [Finding(**f) for f in reply.payload["findings"]]
        for f in self.findings:
            self.trace(self.name, f"finding: {f.title} | explains the outage: {f.explains_outage} | "
                                  f"evidence {', '.join(f.evidence_ids)}\n  {f.narrative}")
        return self.findings

    def decide(self) -> Finding | None:
        self.root_cause = self.choose(self.findings)
        self.trace(self.name, f"acting on: {self.root_cause.title}" if self.root_cause else
                   "no finding with a playbook fix -> escalate to the human")
        return self.root_cause

    def propose(self, version: int = 1, revision_note: str = "", neighbor_ids: list[str] | None = None) -> dict:
        reply = self._send("config", "propose", f"fix: {self.root_cause.title}",
                           {"finding": self.root_cause.model_dump(), "version": version,
                            "revision_note": revision_note, "neighbor_evidence_ids": neighbor_ids or [],
                            "device": self.net.affected})
        p = reply.payload["proposal"]
        self.trace(self.name, f"proposal v{p['version']} ({p['playbook_entry']}): {' / '.join(p['commands'])}\n"
                              f"  expected: {'; '.join(p['expected_post_state'])}\n"
                              f"  blast radius: {p['blast_radius']} [evidence: {', '.join(p['blast_radius_evidence_ids']) or 'none'}]")
        return p

    def validate(self, proposal: dict, phase: str) -> dict:
        return self._send("validation", "validate", f"{phase}-check v{proposal['version']}",
                          {"proposal": proposal, "phase": phase}).payload

    def run_to_gate(self, alert: str) -> "GateRequest":
        self.diagnose(alert)
        if self.decide() is None:
            raise Escalation("no playbook fix for the diagnosed cause -- escalate to the on-call engineer")
        return self._gate(self.propose())

    def request_approval(self, proposal: dict) -> "GateRequest":
        """Validation pre-checks, then pause for the human (status needs_human)."""
        return self._gate(proposal)

    def _gate(self, proposal: dict) -> "GateRequest":
        pre = self.validate(proposal, "pre")
        for chk in pre["checks"]:
            self.trace("validation", f"{'PASS' if chk['ok'] else 'FAIL'}  {chk['check']}: {chk['detail']}")
        self.trace(self.name, f"waiting for {self.approver} to approve or reject v{proposal['version']} (status: needs_human)")
        self.bus.send(Message(**{"from": self.name}, to=f"human:{self.approver}", intent="propose",
                              task=f"approve change v{proposal['version']}?",
                              payload={"proposal": proposal, "pre_checks": pre["checks"]}, status="needs_human"))
        return GateRequest(self, proposal, pre["checks"])


@dataclass
class GateRequest:
    """What the human sees: the diagnosis, the exact commands, the expected result, the checks."""
    coordinator: Coordinator
    proposal: dict
    pre_checks: list[dict]
    result: dict = field(default_factory=dict)
    approved_by: str = ""                  # set on the first approval: one approval, one write

    def _refuse_if_spent(self) -> None:
        """An approved gate is spent (applied, or in flight): a second approve() or a reject() is refused."""
        if self.approved_by:
            raise GateError(f"v{self.proposal['version']} was already approved and applied by executor:{self.approved_by} "
                            f"-- one write per approval; nothing was applied")

    @property
    def ready(self) -> bool:
        return all(c["ok"] for c in self.pre_checks)

    def _human(self, text: str, decision: dict) -> None:
        c = self.coordinator
        c.trace(f"human:{c.approver}", text)
        c.bus.send(Message(**{"from": f"human:{c.approver}"}, to=c.name, intent="propose", task=text,
                           payload=decision, status="done"))

    def reject(self, reasons: str) -> "GateRequest":
        self._refuse_if_spent()
        c = self.coordinator
        self._human(reasons, {"decision": "reject", "version": self.proposal["version"]})
        if self.proposal["version"] >= c.max_rejections:
            self._escalate(f"{self.proposal['version']} rejections (cap {c.max_rejections})")
        up = c.net.uplink(self.proposal["device"])
        reply = c._send("troubleshooting", "diagnose", "blast radius: neighbor tables on both ends",
                        {"want": "neighbor_evidence", "device": self.proposal["device"], "peer": up["peer"]})
        v2 = c.propose(version=self.proposal["version"] + 1, revision_note=reasons,
                       neighbor_ids=reply.payload["evidence_ids"])
        if is_near_copy(self.proposal, v2):
            self._escalate(f"v{v2['version']} adds nothing new to v{self.proposal['version']}")
        return c._gate(v2)

    def _escalate(self, why: str) -> None:
        """The retry cap: the team stops proposing and a person takes the incident. Nothing is applied."""
        c = self.coordinator
        c.trace(c.name, f"ESCALATE: {why} -- stopping; nothing was applied")
        c.bus.send(Message(**{"from": c.name}, to=f"human:{c.approver}", intent="propose",
                           task=f"escalated: {why}", payload={"last_proposal": self.proposal},
                           status="needs_human"))
        raise Escalation(f"escalated to a person: {why}")

    def submit(self, channel) -> "ApprovalTicket":
        """Put this exact proposal in front of the human, in their tool."""
        ticket = channel.request(self.proposal, self.pre_checks)
        self.coordinator.trace(self.coordinator.name, f"submitted v{self.proposal['version']} as {ticket.id} "
                                                      f"({channel.name}); waiting for the approver")
        return ticket

    def resolve(self, channel, ticket):
        """Read the decision back from the channel and act on it. Rejected -> the next gate. Approved -> applied."""
        if ticket.digest != digest_of(self.proposal):
            raise GateError("this decision is for a different version of the change")
        d = channel.decision(ticket)
        if d.state == "pending":
            raise GateError(f"still waiting for the approver on {ticket.id}")
        if d.state == "rejected":
            return self.reject(d.reason)
        if d.state != "approved":
            raise GateError(f"unknown decision state {d.state!r} on {ticket.id} -- refusing to act on it")
        named = (d.by or "").strip()
        if not named:                      # a channel decision is never approved in someone else's name
            raise GateError("the approval channel names no approver -- refusing")
        return self._approve(named, change_id=ticket.id)

    def approve(self, approver: str | None = None, *, change_id: str = "") -> dict:
        """The workshop's notebook approval. In demo mode the decision must come from the channel (resolve)."""
        if self.coordinator.demo:
            raise GateError("in demo mode approvals come through the approval channel -- submit(), then resolve()")
        return self._approve(approver, change_id=change_id)

    def _approve(self, approver: str | None, *, change_id: str) -> dict:
        self._refuse_if_spent()
        c = self.coordinator
        who = approver or c.approver
        if c.requester and who.strip().casefold() == c.requester.strip().casefold():
            raise GateError("separation of duties: the requester can't approve their own change")
        if not self.ready:
            failing = "; ".join(x["detail"] for x in self.pre_checks if not x["ok"])
            raise GateError(f"pre-checks are failing ({failing}) -- reject with your reasons instead")
        self.approved_by = who                                                     # spent from here on, even if apply raises
        self._human(f"Approved v{self.proposal['version']}.", {"decision": "approve"})
        token = c.approvals.approve(self.proposal, who, change_id=change_id)      # minted on the human's action, handed to the Executor
        execution = c.executor.apply(self.proposal, token)
        post = c.validate(self.proposal, "post") if not execution["rolled_back"] else {"checks": [], "passed": False}
        reach = c.net.reachability(self.proposal["device"])
        resolved = post["passed"] and reach == "PASS"
        c.bus.send(Message(**{"from": c.name}, to=f"human:{who}", intent="validate",
                           task="RESOLVED." if resolved else "NOT resolved",
                           payload={"post_checks": post["checks"], "reachability": reach}, status="done"))
        c.trace(c.name, ("RESOLVED. " if resolved else "NOT resolved. ") + f"reachability() = {reach}")
        self.result = {"execution": execution, "post_checks": post["checks"], "reachability": reach,
                       "resolved": resolved}
        return self.result
