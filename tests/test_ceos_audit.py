"""On real devices the change audit comes from Network itself (the simulator keeps its own in the fabric)."""
from netops.network import Network, audit_rows


class FakeDevice:
    def __init__(self):
        self.pushed = []

    def configure(self, cmds, *, by="operator"):
        self.pushed.append(cmds)


def test_audit_rows_match_the_simulator_format():
    rows = audit_rows("BRANCH-7", ["interface Ethernet1", "ip ospf area 0.0.0.0"], "executor:alice")
    assert [(r["device"], r["interface"], r["set"], r["to"], r["by"]) for r in rows] == \
        [("BRANCH-7", "Ethernet1", "area", "0.0.0.0", "executor:alice")]
    assert [r["set"] + "=" + str(r["to"]) for r in audit_rows("X", ["interface Et1", "shutdown", "no shutdown"], "a")] \
        == ["admin=down", "admin=up"]


def test_real_network_records_its_changes():
    net = Network({"BRANCH-7": FakeDevice()}, Network.simulated().spec)
    assert net.audit == []
    net.configure("BRANCH-7", ["interface Ethernet1", "ip ospf area 0.0.0.0"], by="executor:alice")
    assert [(a["set"], a["to"], a["by"]) for a in net.audit] == [("area", "0.0.0.0", "executor:alice")]
    assert net.read_only().audit == net.audit


def test_simulated_network_audit_is_the_fabric_audit():
    net = Network.simulated()
    assert net.audit is net.fabric.audit
