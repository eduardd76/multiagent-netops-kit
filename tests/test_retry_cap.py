"""The retry cap: a human can reject a change three times; the third rejection stops the team and escalates."""
import pytest

from netops.agents.coordinator import Escalation
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team


def test_third_rejection_escalates_and_nothing_is_applied():
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = team(inc).run_to_gate(ALERT)
    g = g.reject(ONCALL_REJECT)                      # v1 rejected -> v2
    g = g.reject("Still not convinced.")            # v2 rejected -> v3
    assert g.proposal["version"] == 3
    with pytest.raises(Escalation, match="3 rejections"):
        g.reject("No.")                             # v3 rejected -> stop
    last = inc.bus.transcript[-1]
    assert last.status == "needs_human" and last.task.startswith("escalated:")
    assert inc.network.reachability() == "FAIL"     # the team stopped; the fault is still there
    assert not [a for a in inc.network.fabric.audit if a.get("by") not in (None, "fault")]


def test_the_cap_is_configurable():
    inc = new_incident(llm=MockLLM(), verbose=False)
    c = team(inc)
    c.max_rejections = 1
    with pytest.raises(Escalation):
        c.run_to_gate(ALERT).reject(ONCALL_REJECT)
