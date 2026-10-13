import pytest

from netops.llm import LLMReply, ToolCall
from netops.skin import BoundaryLLM, Skin, redact

S = Skin({"BRANCH-7": "LYON-BR07", "HUB-1": "PAR-HUB01"})


def test_display_and_canonical_are_inverse_and_respect_boundaries():
    t = "BRANCH-7 Ethernet1 -> HUB-1:Ethernet1; BRANCH-77 and HUB-10 untouched"
    shown = S.display(t)
    assert shown == "LYON-BR07 Ethernet1 -> PAR-HUB01:Ethernet1; BRANCH-77 and HUB-10 untouched"
    assert S.canonical(shown) == t


def test_ambiguous_mapping_is_refused():
    with pytest.raises(ValueError, match="ambiguous"):
        Skin({"BRANCH-7": "HUB-1", "HUB-1": "X"})


def test_redaction():
    t = "snmp-server community s3cr3t ro\nusername admin secret 0 hunter2\nenable password p4ss\nkey finding: area"
    r = redact(t)
    assert "s3cr3t" not in r and "hunter2" not in r and "p4ss" not in r and "key finding: area" in r


def test_boundary_shows_customer_names_and_maps_tool_calls_back():
    seen = {}

    class Echo:
        def chat(self, *, role, messages, tools):
            seen["user"] = messages[-1]["content"]
            return LLMReply(text="checking LYON-BR07", tool_calls=[ToolCall(id="1", name="logs",
                                                                            arguments={"device": "LYON-BR07"})])

    reply = BoundaryLLM(Echo(), S).chat(role="x", messages=[{"role": "user", "content": "BRANCH-7 is down"}], tools=[])
    assert seen["user"] == "LYON-BR07 is down"
    assert reply.tool_calls[0].arguments == {"device": "BRANCH-7"}


def test_trace_prints_customer_names(capsys):
    from netops.trace import Trace
    Trace(True, skin=S)("coordinator", "acting on BRANCH-7")
    assert "LYON-BR07" in capsys.readouterr().out
