"""SimulatedDevice must answer like a real cEOS (layouts from tests/fixtures/ceos, captured live)."""
import json
from pathlib import Path

import pytest

from netops.device.driver import CommandError
from netops.device.fabric import Fabric
from netops.device.simulator import SimulatedDevice

FIX = Path(__file__).parent / "fixtures" / "ceos"


def real(state, node, name):
    return json.loads((FIX / state / node / name).read_text())


def keys(d):
    return set(d.keys())


@pytest.fixture
def br7():
    return SimulatedDevice(Fabric(), "BRANCH-7")


def test_neighbor_json_layout_matches_real_ceos():
    sim = SimulatedDevice(Fabric(inject=False), "BRANCH-7").run(["show ip ospf neighbor"])[0]
    ref = real("healthy", "branch7", "show_ip_ospf_neighbor.json")
    s = sim["vrfs"]["default"]["instList"]["1"]["ospfNeighborEntries"][0]
    r = ref["vrfs"]["default"]["instList"]["1"]["ospfNeighborEntries"][0]
    assert keys(s) == keys(r) and keys(s["details"]) == keys(r["details"])


def test_area_mismatch_neighbor_list_is_empty_like_real_ceos(br7):
    sim = br7.run(["show ip ospf neighbor"])[0]
    ref = real("broken", "branch7", "show_ip_ospf_neighbor.json")
    assert sim == ref == {"vrfs": {"default": {"instList": {"1": {"ospfNeighborEntries": []}}}}}


def test_ospf_interface_and_interfaces_layouts(br7):
    s = br7.run(["show ip ospf interface Ethernet1"])[0]["vrfs"]["default"]["instList"]["1"]["interfaces"]["Ethernet1"]
    r = real("broken", "branch7", "show_ip_ospf_interface_Ethernet1.json")["vrfs"]["default"]["instList"]["1"]["interfaces"]["Ethernet1"]
    assert keys(s) == keys(r) and s["area"] == r["area"] == "0.0.0.1"
    si = br7.run(["show interfaces Et1"])[0]["interfaces"]["Ethernet1"]
    ri = real("broken", "branch7", "show_interfaces_Ethernet1.json")["interfaces"]["Ethernet1"]
    assert keys(si) <= keys(ri)
    assert {"linkStatusChanges", "totalInErrors"} <= keys(si["interfaceCounters"])
    assert si["lineProtocolStatus"] == ri["lineProtocolStatus"] == "up"


def test_route_absent_layout_identical(br7):
    assert br7.run(["show ip route 10.100.10.0/24"])[0] == real("broken", "branch7", "show_ip_route_10.100.10.0_24.json")


def test_text_commands_and_json_refusal(br7):
    with pytest.raises(CommandError, match="fmt='text'"):
        br7.run(["show logging"])
    log = br7.run(["show logging"], fmt="text")[0]["output"]
    assert "Log Buffer:" in log and "(uplink to HUB-1), changed state to down" in log
    ping = br7.run(["ping 10.100.10.10 source 10.20.20.1 repeat 5"], fmt="text")[0]["output"]
    assert "5 packets transmitted, 0 received, 100% packet loss" in ping


def test_config_grammar_fix_and_invalid_input(br7):
    with pytest.raises(CommandError, match="Invalid input"):
        br7.configure(["interface Ethernet1", "router ospf 1"])
    assert br7.fabric.audit == []                       # atomic: nothing applied
    br7.configure(["interface Ethernet1", "ip ospf area 0.0.0.0"], by="on-call")
    br7.wait(16)
    ping = br7.run(["ping 10.100.10.10 source 10.20.20.1 repeat 5"], fmt="text")[0]["output"]
    assert "5 received, 0% packet loss" in ping
    assert "ip ospf area 0.0.0.0" in br7.run(["show running-config interfaces Ethernet1"], fmt="text")[0]["output"]


def test_the_trap_shut_noshut_and_clear_counters(br7):
    br7.configure(["interface Ethernet1", "shutdown"], by="agent")
    br7.configure(["interface Ethernet1", "no shutdown"], by="agent")
    br7.run(["clear counters Ethernet1"])
    br7.wait(30)
    intf = br7.run(["show interfaces Ethernet1"])[0]["interfaces"]["Ethernet1"]
    assert intf["lineProtocolStatus"] == "up" and intf["interfaceCounters"]["linkStatusChanges"] == 0
    assert "100% packet loss" in br7.run(["ping 10.100.10.10 source 10.20.20.1"], fmt="text")[0]["output"]
