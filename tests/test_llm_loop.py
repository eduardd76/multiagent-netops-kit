from types import SimpleNamespace as NS

from netops.agents.loop import run_agent
from netops.agents.tools import ToolBox
from netops.evidence import EvidenceStore
from netops.llm import FallbackLLM, LLMReply, MockLLM, OpenAICompatLLM, ToolCall, ToolSpec, make_llm
from netops.network import Network


class Scripted:
    def __init__(self, replies): self.replies = list(replies)
    def chat(self, *, role, messages, tools):
        r = self.replies.pop(0); r.source = "scripted"; return r


def test_make_llm_defaults_to_mock_without_endpoint(monkeypatch):
    for v in ("NETOPS_LLM", "NETOPS_BASE_URL", "NETOPS_MODEL"):
        monkeypatch.delenv(v, raising=False)
    assert isinstance(make_llm(), MockLLM)


def test_make_llm_uses_shared_endpoint_with_fallback(monkeypatch):
    monkeypatch.setenv("NETOPS_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("NETOPS_MODEL", "some-model")
    llm = make_llm()
    assert isinstance(llm, FallbackLLM) and isinstance(llm.primary, OpenAICompatLLM)


def test_fallback_announces_itself():
    class Down:
        def chat(self, **kw): raise ConnectionError("endpoint unreachable")
    llm = FallbackLLM(Down())
    reply = llm.chat(role="single-agent", messages=[{"role": "system", "content": ""}, {"role": "user", "content": "x"}], tools=[])
    assert "fallback" in reply.source and llm.events[0]["reason"].startswith("ConnectionError")


def test_openai_compat_parses_tool_calls_and_bad_json():
    msg = NS(content=None, tool_calls=[NS(id="c1", function=NS(name="route", arguments='{"device": "BRANCH-7"}')),
                                       NS(id="c2", function=NS(name="route", arguments="{oops"))])
    fake = NS(chat=NS(completions=NS(create=lambda **kw: NS(choices=[NS(message=msg)]))))
    r = OpenAICompatLLM("u", "m", client=fake).chat(role="x", messages=[], tools=[])
    assert r.tool_calls[0].arguments == {"device": "BRANCH-7"} and "_unparseable" in r.tool_calls[1].arguments


def test_loop_runs_tools_records_evidence_and_survives_errors():
    net, ev = Network.simulated(), EvidenceStore()
    llm = Scripted([LLMReply(tool_calls=[ToolCall(id="1", name="route", arguments={"device": "BRANCH-7", "prefix": "10.100.10.0/24"}),
                                         ToolCall(id="2", name="bounce_interface", arguments={"device": "BRANCH-7", "interface": "Ethernet1"}),
                                         ToolCall(id="3", name="ospf_interface", arguments={"device": "BRANCH-7"})]),
                    LLMReply(text="done")])
    run = run_agent(llm, role="r", system="s", task="t", toolbox=ToolBox(net, ev, ["route", "ospf_interface"], agent="r"))
    assert run.stopped == "end_turn" and [c["ok"] for c in run.calls] == [True, False, False]
    assert len(ev) == 1 and net.fabric.audit == []           # the disallowed write never happened


def test_loop_validates_structured_output_with_one_correction():
    submit = ToolSpec(name="submit_x", description="", parameters={"type": "object"})
    llm = Scripted([LLMReply(tool_calls=[ToolCall(id="1", name="submit_x", arguments={"v": -1})]),
                    LLMReply(tool_calls=[ToolCall(id="2", name="submit_x", arguments={"v": 3})])])
    run = run_agent(llm, role="r", system="s", task="t", submit=submit,
                    validate=lambda a: None if a.get("v", -1) >= 0 else "v must be >= 0")
    assert run.submitted == {"v": 3} and run.invalid_outputs == ["v must be >= 0"]


def test_loop_gives_up_after_two_invalid_outputs():
    submit = ToolSpec(name="submit_x", description="", parameters={"type": "object"})
    llm = Scripted([LLMReply(text="prose"), LLMReply(text="more prose")])
    run = run_agent(llm, role="r", system="s", task="t", submit=submit)
    assert run.submitted is None and len(run.invalid_outputs) == 2
