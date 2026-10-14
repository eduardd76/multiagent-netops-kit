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
