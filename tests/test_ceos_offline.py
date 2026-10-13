"""The SAME agent code against CeosDevice, served by JSON captured from a real cEOS 4.34.8M (no lab needed)."""
import json
from pathlib import Path

import pytest

from netops.agents.troubleshooting import TroubleshootingAgent
from netops.device.ceos import CeosDevice
from netops.device.driver import CommandError
from netops.evidence import EvidenceStore
from netops.llm import MockLLM
from netops.network import Network
from netops.orchestrator import ALERT

FIX = Path(__file__).parent / "fixtures" / "ceos"
FILES = {"show ip ospf neighbor": "show_ip_ospf_neighbor.json",
         "show ip ospf interface Ethernet1": "show_ip_ospf_interface_Ethernet1.json",
         "show interfaces Ethernet1": "show_interfaces_Ethernet1.json",
         "show ip route 10.100.10.0/24": "show_ip_route_10.100.10.0_24.json",
         "show logging": "show_logging.txt",
         "ping 10.100.10.10 source 10.20.20.1 repeat 5": "ping.txt"}


def recorded_eapi(state: str, node: str):
    """A fake eAPI endpoint answering from the real captures (BRANCH-8 = the healthy capture, as the control)."""
    def transport(request: dict) -> dict:
        out = []
        for cmd in request["params"]["cmds"]:
            if cmd == "enable":
                out.append({})
                continue
            f = FIX / state / node / FILES[cmd]
            body = f.read_text()
            out.append(json.loads(body) if f.suffix == ".json" else {"output": body})
        return {"jsonrpc": "2.0", "id": request["id"], "result": out}
    return transport


def test_same_troubleshooting_code_finds_both_faults_on_real_ceos_output():
    nodes = {"BRANCH-7": ("broken", "branch7"), "HUB-1": ("broken", "hub1"), "BRANCH-8": ("healthy", "branch7"),
             "HUB-2": ("healthy", "hub1")}
    net = Network.ceos({h: "192.0.2.1" for h in nodes}, transport_for=lambda h: recorded_eapi(*nodes[h]))
    findings, _ = TroubleshootingAgent(MockLLM(), net, EvidenceStore()).diagnose(ALERT)
    ids = {f.id for f in findings}
    assert ids == {"interface_flap", "ospf_area_mismatch"}
    area = next(f for f in findings if f.id == "ospf_area_mismatch")
    assert area.observed["local_area"] == "0.0.0.1" and area.observed["peer_area"] == "0.0.0.0"
    assert net.reachability() == "FAIL"


def test_ceos_configure_uses_a_session_and_reports_errors():
    sent = []

    def transport(req):
        sent.append(req["params"]["cmds"])
        if "router ospf 1" in req["params"]["cmds"]:
            return {"jsonrpc": "2.0", "id": req["id"],
                    "error": {"code": 1002, "message": "CLI command 2 of 3 'router ospf 1' failed: invalid command",
                              "data": [{}, {"errors": ["Invalid input"]}]}}
        return {"jsonrpc": "2.0", "id": req["id"], "result": [{} for _ in req["params"]["cmds"]]}


    dev = CeosDevice("BRANCH-7", "192.0.2.1", transport=transport)
    dev.configure(["interface Ethernet1", "ip ospf area 0.0.0.0"], by="executor:on-call")
    assert sent[0][0] == "enable" and sent[0][1].startswith("configure session netops-")
    assert sent[0][2:] == ["interface Ethernet1", "ip ospf area 0.0.0.0", "commit"]
    with pytest.raises(CommandError, match="invalid command"):
        dev.configure(["router ospf 1"])
