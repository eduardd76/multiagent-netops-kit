from netops.inventory import YamlInventory
from netops.network import Network


def test_yaml_inventory_matches_the_incident_file():
    net = Network.simulated()
    inv = net.inventory
    assert isinstance(inv, YamlInventory)
    assert inv.uplink("BRANCH-7").as_dict() == {"interface": "Ethernet1", "peer": "HUB-1", "peer_interface": "Ethernet1"}
    assert inv.devices()["BRANCH-7"].lan_gateway == "10.20.20.1" and inv.devices()["HUB-1"].nos == "eos"
    assert inv.service().address == "10.100.10.10"


def test_context_and_affected_replace_the_literals():
    net = Network.simulated()
    assert net.affected == "BRANCH-7"
    assert net.context() == {"device": "BRANCH-7", "uplink": "Ethernet1", "peer": "HUB-1",
                             "peer_interface": "Ethernet1", "service": "10.100.10.10",
                             "service_prefix": "10.100.10.0/24", "lan_gateway": "10.20.20.1", "control": "BRANCH-8"}
    assert net.reachability() == net.reachability("BRANCH-7") == "FAIL"


def test_no_hard_coded_branch_in_agent_code():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "netops"
    offenders = [str(p.relative_to(root)) for p in list(root.glob("agents/*.py")) + [root / "network.py"]
                 if '"BRANCH-7"' in p.read_text()]
    assert offenders == [], offenders
