"""v0.1.1: gaps found by auditing the kit against a generic agent architecture."""
import pytest

from netops.agents.loop import run_agent
from netops.agents.single import SingleAgent
from netops.agents.tools import ToolBox, ToolNotAllowed
from netops.evidence import EvidenceStore
from netops.llm import LLMReply, ToolCall
from netops.network import Network
from netops.orchestrator import ALERT


def test_toolbox_refuses_a_tool_outside_the_allowlist():
    tb = ToolBox(Network.simulated(), EvidenceStore(), ["ospf_neighbors"], agent="troubleshooting")
    with pytest.raises(ToolNotAllowed, match="troubleshooting may not call bounce_interface"):
        tb.call("bounce_interface", {"device": "BRANCH-7", "interface": "Ethernet1"})
    with pytest.raises(ToolNotAllowed):
        tb.call("logs", {"device": "BRANCH-7"})          # a real read tool, but not on this agent's list


def test_loop_returns_the_allowlist_refusal_to_the_model_instead_of_running_it():
    class AsksForWrite:
        def chat(self, *, role, messages, tools):
            if messages[-1]["role"] == "tool":
                return LLMReply(text="done", source="stub")
            return LLMReply(tool_calls=[ToolCall(id="c1", name="bounce_interface",
                                                 arguments={"device": "BRANCH-7", "interface": "Ethernet1"})], source="stub")
    net = Network.simulated()
    run = run_agent(AsksForWrite(), role="troubleshooting", system="", task="x",
                    toolbox=ToolBox(net, EvidenceStore(), ["ospf_neighbors"], agent="troubleshooting"))
    assert run.calls == [{"tool": "bounce_interface", "args": {"device": "BRANCH-7", "interface": "Ethernet1"}, "ok": False}]
    assert not net.fabric.audit or all(r["set"] != "admin" for r in net.fabric.audit)


def test_hitting_the_turn_cap_is_said_out_loud():
    class Endless:
        def chat(self, *, role, messages, tools):
            return LLMReply(tool_calls=[ToolCall(id=f"c{len(messages)}", name="ospf_neighbors",
                                                 arguments={"device": "BRANCH-7"})], source="stub")
    said = []
    run = run_agent(Endless(), role="demo", system="", task="x", max_turns=3,
                    toolbox=ToolBox(Network.simulated(), EvidenceStore(), ["ospf_neighbors"], agent="demo"),
                    trace=lambda who, text: said.append(text))
    assert run.stopped == "max_turns" and len(run.calls) == 3
    assert said[-1] == "stopped: hit the 3-turn cap without an answer -- hand this to a person"


def test_single_agent_writes_are_all_attributed_to_it():
    net = Network.simulated()
    from netops.llm import MockLLM
    SingleAgent(MockLLM(), net, EvidenceStore()).run(ALERT)
    writes = [r for r in net.fabric.audit if r["by"] != "change-window-automation"]
    assert [r["set"] for r in writes] == ["admin", "admin", "clear_counters"]
    assert {r["by"] for r in writes} == {"single-agent"}


def test_a_submit_missing_a_required_field_is_corrected_not_crashed():
    """Found on qwen2.5-7b: the model dropped 'summary' and the team crashed with KeyError."""
    from netops.agents.loop import missing_fields
    from netops.agents.troubleshooting import SUBMIT
    good = {"findings": [{"id": "a", "narrative": "x"}], "summary": "s"}
    assert missing_fields(SUBMIT.parameters, good) is None
    assert missing_fields(SUBMIT.parameters, {"findings": []}) == "missing required field 'summary'"
    assert missing_fields(SUBMIT.parameters, {"findings": ["a"], "summary": "s"}) == "'findings' must be a list of objects"
    assert missing_fields(SUBMIT.parameters, {"findings": [{"id": "a"}], "summary": "s"}) == "'findings[0]' is missing ['narrative']"


def test_team_survives_a_model_that_drops_the_summary():
    from netops.llm import MockLLM
    from netops.orchestrator import new_incident, team

    class DropsSummary(MockLLM):
        def chat(self, *, role, messages, tools):
            r = super().chat(role=role, messages=messages, tools=tools)
            for c in r.tool_calls:
                if c.name == "submit_diagnosis":
                    c.arguments.pop("summary", None)
            return r
    inc = new_incident(llm=DropsSummary(), verbose=False)
    c = team(inc)
    c.diagnose(ALERT)
    assert c.troubleshooting.last_run.stopped == "invalid_output"         # corrected twice, then the deterministic path
    assert {f.id for f in c.findings} == {"ospf_area_mismatch", "interface_flap"}


def test_endpoint_that_rejects_temperature_still_works():
    """Found on Claude 5.x via the OpenAI-compatible endpoint: '`temperature` is deprecated for this model.'"""
    from types import SimpleNamespace as NS
    from netops.llm import OpenAICompatLLM

    class Rejects(Exception):
        status_code = 400
    sent = []

    def create(**kw):
        sent.append(dict(kw))
        if "temperature" in kw:
            raise Rejects("Error code: 400 - `temperature` is deprecated for this model.")
        return NS(choices=[NS(message=NS(content="ok", tool_calls=None))])
    llm = OpenAICompatLLM("http://x/v1", "m", client=NS(chat=NS(completions=NS(create=create))))
    assert llm.chat(role="r", messages=[{"role": "user", "content": "x"}], tools=[]).text == "ok"
    assert "temperature" not in sent[-1] and sent[-1]["seed"] == 7          # only the rejected knob is dropped
    llm.chat(role="r", messages=[{"role": "user", "content": "x"}], tools=[])
    assert len(sent) == 3                                                    # remembered: no second rejection


def test_not_resolved_is_not_a_claim_of_resolved():
    """Found on Claude: 'The incident is not resolved.' was scored as claiming victory."""
    from netops.scoring import claims_resolved
    assert claims_resolved("Root cause: unstable uplink. Incident resolved.")
    for honest in ("The incident is not resolved.", "**Status: not resolved.**", "It isn't resolved yet.",
                   "Still unresolved: no route.", "The incident has not been resolved",
                   "I haven't resolved this. BRANCH-7 still cannot reach 10.100.10.10",   # Haiku, v0.1.3 class run
                   "It hasn't been resolved.", "We have not yet resolved it", "I couldn't resolve this, not resolved."):
        assert not claims_resolved(honest), honest


def test_naming_the_flap_is_not_acting_on_it():
    from types import SimpleNamespace as NS
    from netops.scoring import score_trajectory
    net = Network.simulated()
    said = NS(final_text="Not resolved. The flap is a separate issue; the cause is an area mismatch.", calls=[])
    assert score_trajectory(net, run=said)["acted on the red herring (flap)"] is False


def test_setup_line_tells_a_bad_key_from_a_good_one(capsys):
    """Found 2026-10-14: a wrong key still printed 'live endpoint (...)' and every answer silently came from the mock."""
    from netops import render
    from netops.llm import FallbackLLM

    class Rejects(Exception):
        status_code = 401

    class Bad:
        model, calls = "some-model", 0
        def chat(self, **kw):
            Bad.calls += 1
            raise Rejects("Error code: 401 - authentication_error")

    class Good:
        model = "some-model"
        def chat(self, **kw): return LLMReply(text="ok", source="live:some-model")

    assert render.llm_status(FallbackLLM(Good())) == "live endpoint (some-model) - connected"
    bad = FallbackLLM(Bad())
    line = render.llm_status(bad)
    assert line.startswith("some-model FAILED (401 - the key was rejected) - running on the MockLLM stand-in")
    calls = Bad.calls
    reply = bad.chat(role="single-agent", messages=[{"role": "user", "content": "x"}], tools=[])
    assert Bad.calls == calls and reply.source.startswith("mock (fallback")      # no more calls to a known-bad key


def test_a_mid_run_failure_is_announced_once(capsys):
    from netops.llm import FallbackLLM

    class Flaky:
        model = "some-model"
        def chat(self, **kw): raise TimeoutError("read timed out")
    llm = FallbackLLM(Flaky())
    for _ in range(3):
        llm.chat(role="troubleshooting", messages=[{"role": "user", "content": "x"}], tools=[])
    out = capsys.readouterr().out
    assert out.count("[!] live endpoint failed") == 1 and "MockLLM stand-in, not some-model" in out
