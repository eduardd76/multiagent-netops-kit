"""Parsers on REAL captured cEOS output, and Network reads/reachability on the simulator."""
import json
from pathlib import Path

from netops.network import Network
from netops.parsers import parse_interface, parse_logging, parse_ospf_interface, parse_ospf_neighbors, parse_ping, parse_route

FIX = Path(__file__).parent / "fixtures" / "ceos"


def load(state, node, name):
    p = FIX / state / node / name
    return json.loads(p.read_text()) if name.endswith(".json") else p.read_text()


def test_parsers_on_real_ceos_broken_state():
    assert parse_ospf_neighbors("BRANCH-7", load("broken", "branch7", "show_ip_ospf_neighbor.json")) == []
    oi = parse_ospf_interface("BRANCH-7", "Ethernet1", load("broken", "branch7", "show_ip_ospf_interface_Ethernet1.json"))
    assert oi.area == "0.0.0.1" and oi.neighbor_count == 0 and oi.hello == 10
    hub = parse_ospf_interface("HUB-1", "Ethernet1", load("broken", "hub1", "show_ip_ospf_interface_Ethernet1.json"))
    assert hub.area == "0.0.0.0"
    intf = parse_interface("BRANCH-7", "Ethernet1", load("broken", "branch7", "show_interfaces_Ethernet1.json"))
    assert intf.line_protocol == "up" and intf.link_status_changes == 38
    assert not parse_route("BRANCH-7", "10.100.10.0/24", load("broken", "branch7", "show_ip_route_10.100.10.0_24.json")).present
    assert not parse_ping("BRANCH-7", "10.100.10.10", "10.20.20.1", load("broken", "branch7", "ping.txt")).success
    logs = parse_logging("BRANCH-7", load("broken", "branch7", "show_logging.txt"), 2026)
    assert sum(l.category == "LINK" for l in logs) >= 20


def test_parsers_on_real_ceos_healthy_and_converging():
    n = parse_ospf_neighbors("BRANCH-7", load("healthy", "branch7", "show_ip_ospf_neighbor.json"))
    assert [(x.neighbor_id, x.state, x.area) for x in n] == [("1.1.1.1", "full", "0.0.0.0")]
    r = parse_route("BRANCH-7", "10.100.10.0/24", load("healthy", "branch7", "show_ip_route_10.100.10.0_24.json"))
    assert r.present and r.route_type == "OSPF" and r.next_hops == ["10.0.12.1"]
    assert parse_ping("BRANCH-7", "10.100.10.10", "10.20.20.1", load("healthy", "branch7", "ping.txt")).success
    # the real "FULL but no route yet" window, captured 6 s after the fix
    assert parse_ospf_neighbors("BRANCH-7", load("converging", "branch7", "show_ip_ospf_neighbor.json"))[0].state == "full"
    assert not parse_route("BRANCH-7", "10.100.10.0/24", load("converging", "branch7", "show_ip_route_10.100.10.0_24.json")).present


def test_network_reads_and_reachability():
    net = Network.simulated()
    assert net.reachability() == "FAIL"
    assert net.ospf_neighbors("BRANCH-7") == []
    assert net.ospf_interface("BRANCH-7", "Et1").area == "0.0.0.1"
    assert net.ospf_interface("HUB-1", "Ethernet1").area == "0.0.0.0"
    assert net.uplink("BRANCH-7") == {"interface": "Ethernet1", "peer": "HUB-1", "peer_interface": "Ethernet1"}
    s = net.log_summary("BRANCH-7")
    assert s.total >= 400 and s.counts["LINK"] > 0.9 * s.total and any("CONFIG_I" in n for n in s.notable)
    assert net.reachability("BRANCH-8") == "PASS"


def test_reachability_after_fix_needs_time():
    net = Network.simulated()
    net.configure("BRANCH-7", ["interface Ethernet1", "ip ospf area 0.0.0.0"], by="test")
    assert net.reachability() == "FAIL"          # not yet: FULL in ~9 s, route ~6.5 s later
    net.wait(16)
    assert net.reachability() == "PASS"
