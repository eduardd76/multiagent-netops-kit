"""Where the human decides. Each channel writes the change into its system's own record format and reads the
decision back from that record -- the pattern a real integration uses (never trust the callback body alone).
A channel returns a DECISION. Only netops.approval.Approvals mints the token, inside the gate."""
from __future__ import annotations

import itertools

from netops.approval import digest_of
from netops.ports import ApprovalTicket, Decision

MOCK_LABEL = "mock {system} - real formats, no connection"
AI_LABEL = "AI-generated, unverified"


def _identity(text: str) -> str:
    return text


class _Channel:
    name = "base"
    prefix = "REQ"

    def __init__(self, skin=None):
        self.show = skin.display if skin is not None else _identity
        self._n = itertools.count(1)

    def request(self, proposal: dict, pre_checks: list[dict]) -> ApprovalTicket:
        tid = f"{self.prefix}{next(self._n) + 30000:07d}"
        return ApprovalTicket(id=tid, channel=self.name, digest=digest_of(proposal), version=proposal["version"],
                              record=self._record(tid, proposal, pre_checks))

    def _summary(self, p: dict, pre: list[dict]) -> dict:
        s = self.show
        return {"title": s(f"{p['diagnosis']} on {p['device']} (v{p['version']})"),
                "narrative": s(f"[{AI_LABEL}] {p['rationale']} Blast radius: {p['blast_radius']}"),
                "commands": "\n".join(p["commands"]), "rollback": "\n".join(p["rollback"]),
                "tests": "\n".join(p["expected_post_state"]), "device": s(p["device"]),
                "checks": [f"{'PASS' if c['ok'] else 'FAIL'} {c['check']}: {s(str(c['detail']))}" for c in pre]}


class NotebookApproval(_Channel):
    """Today's behaviour: the person in front of the notebook decides."""
    name, prefix = "notebook", "NB"

    def _record(self, tid, p, pre):
        return {"id": tid, **self._summary(p, pre), "decision": None}

    def decide(self, ticket, *, approve, by, reason=""):
        ticket.record["decision"] = {"approve": approve, "by": by, "reason": reason}

    def decision(self, ticket) -> Decision:
        d = ticket.record["decision"]
        if d is None:
            return Decision("pending")
        return Decision("approved" if d["approve"] else "rejected", d["by"], d["reason"])


class MockServiceNowCR(_Channel):
    """A ServiceNow change_request record (sn_chg_rest field names); approvals as sysapproval_approver rows."""
    name, prefix = "servicenow", "CHG"

    def _record(self, tid, p, pre):
        s = self._summary(p, pre)
        return {"number": tid, "type": "normal", "state": "assess", "short_description": s["title"],
                "description": s["narrative"], "justification": s["title"], "implementation_plan": s["commands"],
                "backout_plan": s["rollback"], "test_plan": s["tests"], "cmdb_ci": s["device"],
                "risk": "moderate", "impact": "3 - Low", "u_proposal_digest": digest_of(p),
                "u_pre_checks": s["checks"], "approval": "requested", "sysapproval_approver": [],
                "u_source": MOCK_LABEL.format(system="ServiceNow")}

    def decide(self, ticket, *, approve, by, reason=""):
        r = ticket.record
        r["sysapproval_approver"].append({"approver": by, "state": "approved" if approve else "rejected",
                                          "comments": reason})
        r["approval"] = "approved" if approve else "rejected"

    def decision(self, ticket) -> Decision:
        rows = ticket.record["sysapproval_approver"]          # re-read the system of record
        if not rows:
            return Decision("pending")
        last = rows[-1]
        return Decision(last["state"], last["approver"], last["comments"])


class MockJiraApproval(_Channel):
    """A Jira Service Management request with one approval (servicedeskapi shapes)."""
    name, prefix = "jira", "NOC-"

    def _record(self, tid, p, pre):
        s = self._summary(p, pre)
        return {"issueKey": tid, "requestTypeId": "change",
                "requestFieldValues": {"summary": s["title"], "description": s["narrative"],
                                       "implementation": s["commands"], "backout": s["rollback"],
                                       "u_proposal_digest": digest_of(p)},
                "approvals": [{"id": "1", "name": "Change approval", "finalDecision": "pending", "approvers": []}],
                "u_source": MOCK_LABEL.format(system="Jira Service Management")}

    def decide(self, ticket, *, approve, by, reason=""):
        a = ticket.record["approvals"][0]
        a["approvers"].append({"approver": {"displayName": by}, "approverDecision": "approved" if approve else "declined",
                               "comment": reason})
        a["finalDecision"] = "approved" if approve else "declined"

    def decision(self, ticket) -> Decision:
        a = ticket.record["approvals"][0]
        if a["finalDecision"] == "pending":
            return Decision("pending")
        last = a["approvers"][-1]
        return Decision("approved" if a["finalDecision"] == "approved" else "rejected",
                        last["approver"]["displayName"], last["comment"])
