"""ContainerLab: the presenter's read-only window onto the routers' own CLI."""
import pytest

from netops.clab import ContainerLab


def test_container_names_follow_containerlab():
    assert ContainerLab("netops").container("BRANCH-7") == "clab-netops-branch7"
    assert ContainerLab("netops").container("HUB-1") == "clab-netops-hub1"


def test_only_show_and_ping(monkeypatch):
    lab = ContainerLab("netops")
    monkeypatch.setattr(lab, "_sh", lambda cmd: pytest.fail("must not run"))
    for bad in ("configure", "clear counters", "reload", "bash rm -rf /"):
        with pytest.raises(ValueError, match="read-only"):
            lab.cli("BRANCH-7", bad)


def test_route_legend_and_ping_noise_are_dropped(monkeypatch, capsys):
    lab = ContainerLab("netops", vm="clab")
    seen = []
    outputs = {"route": "VRF: default\nSource Codes:\n  C - connected\n\n O  10.100.10.0/24 [110/20]\n   via 10.0.22.1",
               "ping": "PING 10.100.10.10\n64 bytes from...\n--- stats ---\n2 packets transmitted, 2 received, 0% packet loss"}
    monkeypatch.setattr(lab, "_sh", lambda cmd: seen.append(cmd) or outputs["route" if "route" in cmd else "ping"])
    lab.cli("BRANCH-8", "show ip route 10.100.10.0/24")
    lab.cli("BRANCH-8", "ping 10.100.10.10 source 10.30.30.1 repeat 2")
    out = capsys.readouterr().out
    assert "Source Codes" not in out and "O  10.100.10.0/24" in out
    assert "64 bytes" not in out and "2 packets transmitted, 2 received" in out
    assert seen[0].startswith("docker exec clab-netops-branch8 Cli -p 15 -c ")
