"""The incident state machine — the physics every lab depends on."""
from netops.device.fabric import Fabric


def test_healthy_fabric_without_faults():
    f = Fabric(inject=False)
    p = f.port("BRANCH-7", "Ethernet1")
    assert f.adjacency_state(p) == "full"
    assert f.can_ping("BRANCH-7", "10.100.10.10", "10.20.20.1")


def test_incident_symptoms_at_314():
    f = Fabric()
    p = f.port("BRANCH-7", "Ethernet1")
    assert f.clock.isoformat() == "2026-10-12T03:14:00"
    assert p.oper_up and p.area == "0.0.0.1" and f.peer(p).area == "0.0.0.0"
    assert f.adjacency_state(p) is None                       # area mismatch: neighbor ABSENT (as on cEOS)
    assert not f.can_ping("BRANCH-7", "10.100.10.10", "10.20.20.1")
    assert f.adjacency_state(f.port("BRANCH-8", "Ethernet1")) == "full"   # control site healthy


def test_logs_are_loud_and_recovery_stops_after_the_change():
    f = Fabric()
    logs = f.logs["BRANCH-7"]
    assert len(logs) >= 400
    assert sum(e.category == "LINK" for e in logs) / len(logs) > 0.9
    change = next(e for e in logs if e.category == "CONFIG")
    established = [e for e in logs if "ESTABLISHED" in e.text]
    assert established and all(e.ts < change.ts for e in established)    # recovered before, never after
    assert logs[0].ts.isoformat().startswith("2026-10-12T02:14")         # flapping started an hour earlier
    assert not any("area" in e.text.lower() for e in logs)               # cEOS says nothing about the area


def test_fix_converges_with_real_timing():
    f = Fabric()
    p = f.port("BRANCH-7", "Ethernet1")
    f.configure_port(p, "area", "0.0.0.0", by="on-call")
    assert f.adjacency_state(p) == "init"
    f.advance(9)
    assert f.adjacency_state(p) == "full"
    assert not f.has_route("BRANCH-7", "10.100.10.0/24")[0]   # FULL but no route yet (SPF hold)
    f.advance(7)
    assert f.can_ping("BRANCH-7", "10.100.10.10", "10.20.20.1")


def test_flap_does_not_fix_area_mismatch():
    f = Fabric()
    p = f.port("BRANCH-7", "Ethernet1")
    f.flap(p, 1)
    f.advance(60)
    assert f.adjacency_state(p) is None and not f.can_ping("BRANCH-7", "10.100.10.10", "10.20.20.1")


def test_variants():
    m = Fabric(variant="mtu_mismatch")
    assert m.adjacency_state(m.port("BRANCH-7", "Ethernet1")) == "exchStart"
    r = Fabric(variant="full_no_route")
    assert r.adjacency_state(r.port("BRANCH-7", "Ethernet1")) == "full"
    assert not r.has_route("BRANCH-7", "10.100.10.0/24")[0]


def test_deterministic():
    a, b = Fabric(), Fabric()
    assert [(e.ts, e.text) for e in a.logs["BRANCH-7"]] == [(e.ts, e.text) for e in b.logs["BRANCH-7"]]


def test_audit_records_changes_but_not_the_fault_history():
    f = Fabric()
    assert f.audit == []
    f.configure_port(f.port("BRANCH-7", "Ethernet1"), "area", "0.0.0.0", by="on-call")
    assert f.audit[0]["by"] == "on-call" and not f.saved["BRANCH-7"]
