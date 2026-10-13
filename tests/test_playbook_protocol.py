from pathlib import Path

import pytest

from netops.approval import Approvals, GateError
from netops.playbook import CommandGate, PlaybookError, load_playbook, render
from netops.protocol import Bus, Message, TokenLeak


def test_root_playbook_is_the_packaged_one():
    assert Path("playbook.yaml").read_text() == Path("netops/playbook.yaml").read_text()


def test_gate_allows_only_playbook_prefixes():
    gate = CommandGate(load_playbook()["ospf_area_mismatch"].allowed_commands)
    assert gate.check("interface Ethernet1").allowed
    assert gate.check("ip ospf area 0.0.0.0").allowed
    for bad in ("router ospf 1", "no ip ospf area", "clear ip ospf process", "ip ospf area 0.0.0.0; reload",
                "interfaces Ethernet1", "shutdown", "ip ospf area0.0.0.0x"):
        assert not gate.check(bad).allowed, bad


def test_render_fix_and_rollback():
    e = load_playbook()["ospf_area_mismatch"]
    assert render(e, {"uplink": "Ethernet1", "expected_area": "0.0.0.0"}) == ["interface Ethernet1", "ip ospf area 0.0.0.0"]
    assert render(e, {"uplink": "Ethernet1", "current_area": "0.0.0.1"}, "rollback")[1] == "ip ospf area 0.0.0.1"


def test_params_cannot_smuggle_commands():
    e = load_playbook()["ospf_area_mismatch"]
    with pytest.raises(PlaybookError, match="uplink"):
        render(e, {"uplink": "Ethernet1\nrouter ospf 1", "expected_area": "0.0.0.0"})
    with pytest.raises(PlaybookError, match="expected_area"):
        render(e, {"uplink": "Ethernet1"})


def test_message_uses_from_alias_and_bus_dispatches():
    bus = Bus()
    bus.register("troubleshooting", lambda m: Message(**{"from": "troubleshooting"}, to=m.from_, intent="diagnose",
                                                         task=m.task, payload={"findings": []}, status="done"))
    reply = bus.send(Message(**{"from": "coordinator"}, to="troubleshooting", intent="diagnose",
                             task="why is BRANCH-7 down?", status="requested"))
    assert reply.status == "done" and reply.reply_to == bus.transcript[0].id
    assert bus.transcript[0].dump()["from"] == "coordinator"


def test_tokens_never_travel_and_are_single_use_and_bound():
    a = Approvals()
    prop = {"commands": ["interface Ethernet1", "ip ospf area 0.0.0.0"]}
    tok = a.approve(prop, "on-call")
    with pytest.raises(TokenLeak):
        Bus().send(Message(**{"from": "coordinator"}, to="executor", intent="propose", task="x",
                           payload={"approval": tok}, status="done"))
    with pytest.raises(GateError, match="changed after"):
        a.consume(tok, {"commands": ["interface Ethernet1", "ip ospf area 0.0.0.9"]})
    a.consume(tok, prop)
    with pytest.raises(GateError, match="already used"):
        a.consume(tok, prop)
    assert tok.mac not in repr(tok)
