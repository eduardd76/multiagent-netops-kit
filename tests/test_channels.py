import json

import pytest

from netops.approval import GateError
from netops.channels import MockJiraApproval, MockServiceNowCR, NotebookApproval
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team


@pytest.mark.parametrize("channel_cls", [NotebookApproval, MockServiceNowCR, MockJiraApproval])
def test_reject_then_approve_through_a_channel(channel_cls):
    inc = new_incident(llm=MockLLM(), verbose=False)
    ch = channel_cls()
    g1 = team(inc).run_to_gate(ALERT)
    t1 = g1.submit(ch)
    assert ch.decision(t1).state == "pending"
    with pytest.raises(GateError, match="still waiting"):
        g1.resolve(ch, t1)
    ch.decide(t1, approve=False, by="Camille", reason=ONCALL_REJECT)
    g2 = g1.resolve(ch, t1)
    t2 = g2.submit(ch)
    ch.decide(t2, approve=True, by="Camille")
    assert g2.resolve(ch, t2)["resolved"]


def test_a_decision_on_v1_cannot_approve_v2():
    inc = new_incident(llm=MockLLM(), verbose=False)
    ch = MockServiceNowCR()
    g1 = team(inc).run_to_gate(ALERT)
    t1 = g1.submit(ch)
    ch.decide(t1, approve=False, by="Camille", reason=ONCALL_REJECT)
    g2 = g1.resolve(ch, t1)
    ch.decide(t1, approve=True, by="Camille")          # someone approves the OLD ticket
    with pytest.raises(GateError, match="different version"):
        g2.resolve(ch, t1)


def test_servicenow_record_has_real_fields_and_labels_itself():
    inc = new_incident(llm=MockLLM(), verbose=False)
    t = team(inc).run_to_gate(ALERT).submit(MockServiceNowCR())
    r = t.record
    assert r["number"].startswith("CHG") and r["u_source"] == "mock ServiceNow - real formats, no connection"
    assert r["implementation_plan"] == "interface Ethernet1\nip ospf area 0.0.0.0"
    assert r["u_proposal_digest"] == t.digest and "AI-generated, unverified" in r["description"]
    assert {"short_description", "backout_plan", "test_plan", "cmdb_ci", "risk", "approval"} <= set(r)
    json.dumps(r)                                        # the leave-behind is plain JSON
