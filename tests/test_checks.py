from netops.checks import evaluate, poll
from netops.evidence import EvidenceStore
from netops.network import Network

FULL = {"name": "adj", "tool": "ospf_neighbors", "expect": {"interface": "{uplink}", "state": "full"}, "backout": True}
PING = {"name": "reach", "tool": "ping", "args": {"destination": "{service}", "source": "{lan_gateway}"},
        "expect": {"success": True}}


def test_checks_read_the_fault_as_it_is():
    net = Network.simulated()
    ctx = net.context()
    assert evaluate(net, FULL, ctx)[0] is False and evaluate(net, PING, ctx)[0] is False
    assert evaluate(net, {**FULL, "on": "control", "expect": {"state": "full"}}, ctx)[0] is True


def test_poll_waits_for_convergence_and_records_evidence():
    net = Network.simulated()
    net.configure("BRANCH-7", ["interface Ethernet1", "ip ospf area 0.0.0.0"], by="test")
    ev = EvidenceStore()
    rows, waited = poll(net, [FULL, PING], net.context(), deadline_s=60, poll_s=3, evidence=ev)
    assert all(r["ok"] for r in rows) and 9 <= waited <= 30
    assert [e.tool for e in ev.all()][:2] == ["ospf_neighbors", "ping"]


def test_poll_gives_up_at_the_deadline():
    net = Network.simulated()
    rows, waited = poll(net, [FULL], net.context(), deadline_s=6, poll_s=3)
    assert rows == [{"check": "adj", "ok": False, "detail": "BRANCH-7 Ethernet1"}] and waited == 6


def test_post_check_details_are_the_strings_the_script_quotes():
    net = Network.simulated()
    net.configure("BRANCH-7", ["interface Ethernet1", "ip ospf area 0.0.0.0"], by="test")
    rows, waited = poll(net, [FULL, PING], net.context(), deadline_s=60, poll_s=3)
    assert rows[0]["detail"] == "BRANCH-7 Ethernet1"
    assert rows[1]["detail"] == f"5/5 after {waited:.0f}s"
    route = {"name": "rt", "tool": "route", "args": {"prefix": "{service}/32"}, "expect": {"protocol": "ospf"}}
    assert poll(net, [route], net.context(), deadline_s=0, poll_s=3)[0][0]["detail"] == "BRANCH-7 route"
