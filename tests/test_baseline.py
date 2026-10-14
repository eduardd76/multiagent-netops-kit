import pytest

from netops.approval import Approvals, GateError, digest_of
from netops.llm import FallbackLLM, MockLLM
from netops.network import Network
from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team
from netops.ports import ApprovalTicket, Decision


class StubChannel:
    """A minimal ApprovalChannel: the decision lives in the ticket record and is read back from it."""
    name = "stub"

    def request(self, proposal, pre_checks):
        return ApprovalTicket(id="REQ0001", channel=self.name, digest=digest_of(proposal),
                              version=proposal["version"], record={"decision": None})

    def decide(self, ticket, *, approve, by, reason=""):
        ticket.record["decision"] = {"approve": approve, "by": by, "reason": reason}

    def decision(self, ticket):
        d = ticket.record["decision"]
        if d is None:
            return Decision("pending")
        return Decision("approved" if d["approve"] else "rejected", d["by"], d["reason"])


def via_channel(g, who):
    """Hardened mode: the approval comes through the channel, never a direct gate.approve()."""
    ch = StubChannel()
    t = g.submit(ch)
    ch.decide(t, approve=True, by=who)
    return g.resolve(ch, t)


def demo_team(inc, **kw):
    from netops.agents.coordinator import Coordinator
    return Coordinator(inc.network, inc.llm, bus=inc.bus, evidence=inc.evidence, approvals=inc.approvals,
                       trace=inc.trace, approver="Camille", requester="presenter", demo=True, **kw)


def test_specialists_get_a_read_only_network():
    ro = Network.simulated().read_only()
    assert ro.reachability() == "FAIL"
    assert ro.affected and ro.service["address"] and ro.inventory is not None
    with pytest.raises(PermissionError):
        ro.configure("BRANCH-7", ["interface Ethernet1"], by="x")
    with pytest.raises(PermissionError):
        ro.clear_counters("BRANCH-7")
    c = team(new_incident(llm=MockLLM(), verbose=False))
    with pytest.raises(PermissionError):
        c.config.net.configure("BRANCH-7", [], by="x")


def test_writes_only_to_lab_devices():
    inc = new_incident(llm=MockLLM(), verbose=False)
    c = demo_team(inc)
    c.executor.allowed_devices = {"HUB-1"}
    g = c.run_to_gate(ALERT).reject(ONCALL_REJECT)
    with pytest.raises(GateError, match="lab allowlist"):
        via_channel(g, "Camille")
    assert inc.network.fabric.audit == []


def test_executor_refuses_a_proposal_that_differs_from_the_playbook():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    g.proposal["commands"] = ["interface Ethernet1", "ip ospf area 0.0.0.2"]
    with pytest.raises(GateError, match="re-rendered"):
        via_channel(g, "Camille")
    assert inc.network.fabric.audit == []


def test_executor_refuses_tampered_post_checks():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    g.proposal["post_checks"] = [{**c, "backout": False} for c in g.proposal["post_checks"]]
    with pytest.raises(GateError, match="playbook|re-rendered"):
        via_channel(g, "Camille")
    assert inc.network.fabric.audit == []


def test_separation_of_duties():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    with pytest.raises(GateError, match="separation of duties"):
        via_channel(g, "presenter")
    with pytest.raises(GateError, match="separation of duties"):
        via_channel(g, " Presenter ")
    assert via_channel(g, "Camille")["resolved"]


def test_demo_mode_refuses_a_direct_approve():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    with pytest.raises(GateError, match="in demo mode approvals come through the approval channel"):
        g.approve("Camille")
    with pytest.raises(GateError, match="approval channel"):
        g.approve("Camille", change_id="CHG0030001")
    assert inc.network.fabric.audit == [] and inc.approvals.log == []


def test_default_mode_still_approves_directly():
    inc = new_incident(llm=MockLLM(), verbose=False)
    assert team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT).approve("on-call")["resolved"]


def test_resolve_refuses_an_unknown_decision_state():
    class Odd(StubChannel):
        def decision(self, ticket):
            return Decision("cancelled", "Camille", "")

    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    ch = Odd()
    with pytest.raises(GateError, match="cancelled"):
        g.resolve(ch, g.submit(ch))
    assert inc.network.fabric.audit == []


def test_token_binds_device_and_change_id():
    a = Approvals()
    p = {"device": "BRANCH-7", "commands": ["x"]}
    t = a.approve(p, "Camille", change_id="CHG0030001")
    assert (t.device, t.change_id) == ("BRANCH-7", "CHG0030001")
    forged = type(t)(t.digest, t.approver, t.run_id, t.expiry, t.mac, t.tenant, "HUB-1", t.change_id)
    with pytest.raises(GateError, match="invalid approval signature"):
        a.consume(forged, p)
    a.consume(t, p)


def test_fallback_can_be_forbidden():
    class Down:
        def chat(self, **kw):
            raise ConnectionError("endpoint down")
    with pytest.raises(RuntimeError, match="not allowed"):
        FallbackLLM(Down(), allow_fallback=False).chat(role="config", messages=[], tools=[])
    assert FallbackLLM(Down()).chat(role="config", messages=[{"role": "user", "content": "x"}], tools=[]).source.startswith("mock")


@pytest.mark.parametrize("tamper", [
    lambda p: p["rollback"].append("router ospf 1"),
    lambda p: p.__setitem__("rollback", ["interface Ethernet1", "ip ospf area 0.0.0.5"]),
    lambda p: p["rollback_params"].__setitem__("uplink", "Ethernet2"),
    lambda p: p.pop("rollback_params"),
])
def test_executor_refuses_a_tampered_rollback(tamper):
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    tamper(g.proposal)
    with pytest.raises(GateError, match="rollback"):
        via_channel(g, "Camille")
    assert inc.network.fabric.audit == [] and not [e for e in inc.approvals.log if e["event"] == "consumed"]


@pytest.mark.parametrize("by", ["", "   ", None])
def test_a_channel_approval_must_name_an_approver(by):
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    with pytest.raises(GateError, match="names no approver"):
        via_channel(g, by)
    assert inc.network.fabric.audit == [] and not [e for e in inc.approvals.log if e["event"] == "consumed"]


def test_a_named_channel_approval_still_resolves_and_records_the_stripped_name():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = demo_team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    assert via_channel(g, "  Camille ")["resolved"]
    assert [e for e in inc.approvals.log if e["event"] == "approved"][0]["approver"] == "Camille"
