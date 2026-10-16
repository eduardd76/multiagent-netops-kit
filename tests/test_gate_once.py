"""One approval, one write: a gate that has been approved refuses a second approve() and any reject()."""
import pytest

from netops.approval import GateError
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team


def _approved_once():
    inc = new_incident(llm=MockLLM(), verbose=False)
    gate = team(inc, "on-call").run_to_gate(ALERT).reject(ONCALL_REJECT)
    assert gate.approve("on-call")["resolved"]
    return inc, gate


def test_approving_the_same_gate_twice_is_refused():
    inc, gate = _approved_once()
    with pytest.raises(GateError, match="already approved and applied by executor:on-call -- one write per approval"):
        gate.approve("on-call")
    writes = [r for r in inc.network.audit if str(r.get("by", "")).startswith("executor:on-call")]
    assert len(writes) == 1, inc.network.audit
    approved = [m for m in inc.bus.transcript if m.task.startswith("Approved")]
    assert [m.task for m in approved] == ["Approved v2."]


def test_rejecting_an_approved_gate_is_refused():
    inc, gate = _approved_once()
    n = len(inc.bus.transcript)
    with pytest.raises(GateError, match="already approved"):
        gate.reject("changed my mind")
    assert len(inc.bus.transcript) == n
