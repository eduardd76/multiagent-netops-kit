"""render.lab: the read-only 'state of the lab' view the presenter shows; the area stays hidden until the reveal."""
from netops import render
from netops.network import Network


def test_lab_view_shows_the_incident_without_the_answer(capsys):
    assert render.lab(Network.simulated()) == {"BRANCH-7": "FAIL", "BRANCH-8": "PASS"}
    out = capsys.readouterr().out
    assert "BRANCH-7 ---- no OSPF" in out and "BRANCH-8 ==== OSPF FULL" in out
    assert "0.0.0.1" not in out and "AREA" not in out
    assert max(len(line) for line in out.splitlines()) <= 100


def test_lab_view_reveals_the_areas_on_request(capsys):
    render.lab(Network.simulated(), show_area=True)
    assert "BRANCH-7 0.0.0.1 ---- no OSPF ------ 0.0.0.0 HUB-1" in capsys.readouterr().out


def test_lab_view_survives_an_unreachable_device(capsys, monkeypatch):
    net = Network.simulated()
    real = net.ospf_neighbors

    def neighbors(device):
        if device == "HUB-2":
            raise ConnectionRefusedError
        return real(device)
    monkeypatch.setattr(net, "ospf_neighbors", neighbors)
    render.lab(net)
    assert "HUB-2     UNREACHABLE (ConnectionRefusedError)" in capsys.readouterr().out


def test_lab_view_brief_is_one_line(capsys):
    assert render.lab(Network.simulated(), brief=True) == {"BRANCH-7": "FAIL", "BRANCH-8": "PASS"}
    assert capsys.readouterr().out == "THE LAB -- the simulator: BRANCH-7 FAIL, BRANCH-8 PASS\n"
