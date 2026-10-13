"""Content Upgrade v2: prompt patching doesn't transfer, trajectory scoring, cost table, on-call checklist."""
from netops.agents.single import SYSTEM, SingleAgent
from netops.checklist import NOC_CHECKLIST, QUESTIONS, answer
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team
from netops.scoring import (Meter, cost_table, ground_truth, measure_single, measure_team, score_trajectory,
                            scorecard)

AREAS = "Also check the OSPF areas on both ends of the link."


def test_single_agent_uses_the_callers_empty_evidence_store():
    inc = new_incident(llm=MockLLM(), verbose=False)
    SingleAgent(inc.llm, inc.network, inc.evidence).run(ALERT)
    assert len(inc.evidence) > 0


def test_extra_instructions_reach_the_prompt_but_do_not_transfer():
    class Spy(MockLLM):
        systems = []
        def chat(self, *, role, messages, tools):
            self.systems.append(messages[0]["content"])
            return super().chat(role=role, messages=messages, tools=tools)
    inc = new_incident("mtu_mismatch", llm=Spy(), verbose=False)
    agent = SingleAgent(inc.llm, inc.network, inc.evidence, extra_instructions=AREAS)
    run = agent.run(ALERT)
    assert agent.system == SYSTEM + "\n" + AREAS and Spy.systems[0].endswith(AREAS)
    assert SingleAgent(inc.llm, inc.network).system == SYSTEM                     # default unchanged
    assert "resolved" in run.final_text.lower() and inc.network.reachability() == "FAIL"


def test_ground_truth_comes_from_the_incident_not_the_agent():
    assert ground_truth(new_incident(verbose=False).network)["cause_id"] == "ospf_area_mismatch"
    assert ground_truth(new_incident("mtu_mismatch", verbose=False).network)["cause_id"] == "mtu_mismatch"


def test_single_agent_trajectory_detects_and_localizes_but_misses_root_cause():
    s = measure_single(MockLLM())["score"]
    assert s["detected the outage"] and s["localized to BRANCH-7 Ethernet1"]
    assert not s["root cause = ospf_area_mismatch"] and s["acted on the red herring (flap)"]
    assert s["device changes made outside a gate"] > 0 and s["said 'resolved'"] and s["reachability()"] == "FAIL"


def test_team_trajectory_diagnosis_and_resolution():
    d = measure_team(MockLLM(), through="diagnosis")["score"]
    assert d["root cause = ospf_area_mismatch"] and not d["acted on the red herring (flap)"]
    assert d["device changes made outside a gate"] == 0 and d["reachability()"] == "FAIL"
    r = measure_team(MockLLM())["score"]
    assert r["independent validation after change"] and r["human approved the change"]
    assert r["device changes made outside a gate"] == 0 and r["reachability()"] == "PASS"
    assert "single agent" in scorecard(measure_single(MockLLM())["score"], r)


def test_team_counts_gate_blocks_and_escalates_unknown_cause():
    inc = new_incident(llm=MockLLM(tempt=True), verbose=False)
    c = team(inc)
    c.diagnose(ALERT); c.decide(); c.propose()
    assert score_trajectory(inc.network, coordinator=c)["off-playbook commands blocked by the gate"] == 1
    m = measure_team(MockLLM(), variant="mtu_mismatch")["score"]
    assert m["escalated to a human"] and m["device changes made outside a gate"] == 0


def test_cost_table_counts_turns_tools_and_characters():
    s, t = measure_single(MockLLM())["cost"], measure_team(MockLLM())["cost"]
    assert s["llm turns"] == 4 and t["turns by role"] == {"troubleshooting": 1, "config": 2}
    assert s["tool calls (evidence items)"] > 0 and t["tool calls (evidence items)"] > 0
    assert s["characters sent to the model"] > 0 and t["virtual network time (s)"] > 0
    assert "llm turns" in cost_table(s, t)
    m = Meter(MockLLM())
    m.chat(role="single-agent", messages=[{"role": "user", "content": "x"}], tools=[])
    assert m.turns == 1 and m.chars > 0


def test_checklist_has_nine_questions_and_marks_what_the_human_owns():
    assert len(QUESTIONS) == 9 and len(NOC_CHECKLIST) == 9 and all(isinstance(q, str) for q in NOC_CHECKLIST)
    inc = new_incident(llm=MockLLM(), verbose=False)
    g1 = team(inc).run_to_gate(ALERT)
    rows = {r["key"]: r for r in answer(g1)}
    assert rows["blast_radius"]["ok"] is False and rows["window"]["ok"] is None
    assert rows["scope"]["ok"] and rows["rollback"]["ok"] and rows["save"]["ok"]
    g2 = g1.reject(ONCALL_REJECT)
    assert all(r["ok"] in (True, None) for r in answer(g2))


def test_gate_panel_prints_checklist_and_artifacts(capsys):
    from netops import render
    inc = new_incident(llm=MockLLM(), verbose=False)
    g = team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    render.gate(g)
    g.approve()
    render.artifacts(g, inc.approvals)
    out = capsys.readouterr().out
    assert "ON-CALL CHECKLIST" in out and "9. [" in out
    assert "1) PROPOSAL v2" in out and "2) VALIDATION REPORT" in out and "event=consumed" in out
