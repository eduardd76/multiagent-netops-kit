# kit/netops/inventory.py
"""Where the topology and the intent come from. Default: the incident file. Any other source implements the
Inventory port (netops/ports.py) and subclasses _Topology for uplink()."""
from __future__ import annotations

from netops.ports import DeviceInfo, Link, Service, Uplink


class _Topology:
    """uplink() from links(): shared by every inventory."""

    def uplink(self, device: str) -> Uplink:
        for l in self.links():
            if l.a_dev == device:
                return Uplink(l.a_if, l.b_dev, l.b_if)
            if l.b_dev == device:
                return Uplink(l.b_if, l.a_dev, l.a_if)
        raise ValueError(f"{device} has no uplink in the topology")


class YamlInventory(_Topology):
    def __init__(self, spec: dict):
        self.spec = spec

    def devices(self) -> dict[str, DeviceInfo]:
        return {n: DeviceInfo(name=n, role=d["role"], nos=d.get("nos", "eos"), mgmt=d.get("mgmt", ""),
                              lan_gateway=d.get("lan_gateway", ""), router_id=d.get("router_id", ""))
                for n, d in self.spec["devices"].items()}

    def links(self) -> list[Link]:
        out = []
        for l in self.spec["links"]:
            (ad, ai), (bd, bi) = l["a"].split(":"), l["b"].split(":")
            out.append(Link(ad, ai, bd, bi, str(l.get("area", ""))))
        return out

    def service(self) -> Service:
        return Service(**self.spec["service"])
