"""The brief's acceptance criteria. Deterministic: MockLLM, seeded simulator."""
import pytest

from netops.agents.config import ConfigAgent
from netops.agents.coordinator import Coordinator, Escalation
from netops.approval import GateError
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, contrast, new_incident, run_lab1, run_team, team


def inc(**kw):
    return new_incident(llm=kw.pop("llm", MockLLM()), verbose=False, **kw)


def test_lab1_trap_single_agent_says_resolved_but_reachability_fails():
    r = run_lab1(inc())
    assert r["claimed_resolved"] and r["reachability"] == "FAIL"
    assert r["writes"] == ["bounce_interface", "clear_counters"] and not r["verified_outcome_after_its_change"]


def test_lab1_is_deterministic():
    assert run_lab1(inc()) == run_lab1(inc())


def test_lab2_coordinator_emits_diagnose_and_finds_both_faults():
    i = inc()
    c = team(i)
    findings = c.diagnose(ALERT)
    first = i.bus.transcript[0]
    assert (first.from_, first.to, first.intent, first.status) == ("coordinator", "troubleshooting", "diagnose", "requested")
    assert {f.id for f in findings} == {"interface_flap", "ospf_area_mismatch"}
    assert findings[0].id == "ospf_area_mismatch"                    # ranked: the one that explains the outage
    assert c.decide().id == "ospf_area_mismatch"
    assert i.network.fabric.audit == []                              # diagnosis touched nothing


def test_lab3_config_proposes_only_playbook_commands_and_blocks_off_playbook():
    i = inc(llm=MockLLM(tempt=True))                                 # the "model" also suggests clear ip ospf process
    c = team(i)
    c.diagnose(ALERT)
    c.decide()
    prop = c.propose()
    reply = i.bus.transcript[-1]
    assert reply.status == "needs_human" and reply.intent == "propose"
    assert prop["commands"] == ["interface Ethernet1", "ip ospf area 0.0.0.0"]
    assert [b["command"] for b in prop["blocked"]] == ["clear ip ospf process"]
    pre = c.validate(prop, "pre")
    checks = {x["check"]: x["ok"] for x in pre["checks"]}
    assert checks["commands_in_allowed_commands"] and checks["commands_equal_playbook_render"]
    assert not checks["blast_radius_evidenced"]                     # v1 can't cite HUB-1's neighbor table
    assert i.network.fabric.audit == [] and i.network.reachability() == "FAIL"   # nothing applied


def test_lab3_tampered_proposal_fails_validation():
    i = inc()
    c = team(i)
    c.diagnose(ALERT); c.decide()
    prop = c.propose()
    prop["commands"] = prop["commands"] + ["router ospf 1"]
    checks = {x["check"]: x["ok"] for x in c.validate(prop, "pre")["checks"]}
    assert not checks["commands_in_allowed_commands"] and not checks["commands_equal_playbook_render"]


def test_lab4_full_team_human_approves_and_validation_confirms():
    i = inc()
    gate = team(i).run_to_gate(ALERT)
    assert not gate.ready
    with pytest.raises(GateError, match="reject with your reasons"):
        gate.approve("on-call")
    assert i.network.fabric.audit == []
    v2 = gate.reject(ONCALL_REJECT)
    assert v2.ready and v2.proposal["version"] == 2
    result = v2.approve("on-call")
    assert result["resolved"] and result["reachability"] == "PASS"
    assert {c["check"]: c["ok"] for c in result["post_checks"]} == {"ospf neighbor state = FULL": True,
                                                                  "branch l3 reachable = true": True}
    assert [a["by"] for a in i.network.fabric.audit] == ["executor:on-call"]
    statuses = [m.status for m in i.bus.transcript if m.to.startswith("human:")]
    assert statuses.count("needs_human") == 2


def test_lab1_vs_lab4_contrast():
    table = contrast(run_lab1(inc()), run_team(inc()))
    assert "FAIL" in table and "PASS" in table


def test_no_playbook_fix_escalates_instead_of_improvising():
    with pytest.raises(Escalation):
        team(inc(variant="mtu_mismatch")).run_to_gate(ALERT)


def test_weak_model_still_reaches_the_right_outcome():
    """A 'model' that answers garbage: the outcome is guaranteed by tools + playbook, not model luck."""
    from netops.llm import LLMReply

    class Weak:
        def chat(self, *, role, messages, tools):
            return LLMReply(text="I think it might be DNS.", source="live:weak")

    result = run_team(inc(llm=Weak()))
    assert result["resolved"]
