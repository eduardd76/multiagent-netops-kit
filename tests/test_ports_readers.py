import pytest

from netops.device.driver import CommandError, ConfigResult
from netops.models import OspfNeighbor
from netops.network import Network
from netops.readers import get_reader, register_reader


def test_eos_reader_is_registered_and_drivers_say_eos():
    net = Network.simulated()
    assert net.nos("BRANCH-7") == "eos" and get_reader("eos").nos == "eos"
    assert net.reader("BRANCH-7") is get_reader("eos")


def test_unknown_nos_lists_the_known_ones():
    with pytest.raises(ValueError, match="known: eos"):
        get_reader("vyos")


def test_eos_interface_rules_live_in_the_reader():
    r = get_reader("eos")
    assert r.normalize_interface("et1") == "Ethernet1"
    with pytest.raises(CommandError):
        r.normalize_interface("ge-0/0/0")
    assert r.interface_pattern == r"Ethernet\d+"


class ToyDriver:
    nos, hostname = "toy", "T1"

    def run(self, cmds, fmt="json"):
        return [{"neighbors": [{"id": "9.9.9.9", "if": "port1", "st": "FULL"}]}]

    def configure(self, cmds, *, by="operator"):
        return ConfigResult("T1", cmds, by)

    def wait(self, seconds):
        pass


class ToyReader:
    nos, interface_pattern = "toy", r"port\d+"

    def normalize_interface(self, name):
        return name

    def ospf_neighbors(self, d):
        return [OspfNeighbor(device=d.hostname, neighbor_id=n["id"], interface=n["if"], state=n["st"].lower(),
                             area="", raw_command="toy-show") for n in d.run(["toy-show"])[0]["neighbors"]]


def test_a_new_nos_plugs_in_without_touching_network():
    register_reader(ToyReader())
    spec = Network.simulated().spec
    net = Network({"T1": ToyDriver()}, spec)
    assert net.ospf_neighbors("T1")[0].state == "full"
