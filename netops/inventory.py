# kit/netops/inventory.py
"""Where the topology and the intent come from. Default: the incident file. Customer demos: a file in NetBox's
export shape, so moving to the customer's real NetBox later changes one line of the pack, not the agents."""
from __future__ import annotations

import json
from pathlib import Path

from netops.ports import DeviceInfo, Link, Service, Uplink

# NetBox platform slugs -> our nos names (real NetBox installs use the long slugs)
PLATFORM_TO_NOS = {"eos": "eos", "arista-eos": "eos", "srl": "srl", "nokia-srlinux": "srl", "frr": "frr",
                   "iosxe": "iosxe", "cisco-iosxe": "iosxe", "junos": "junos", "juniper-junos": "junos"}
NOS_TO_PLATFORM = {"eos": "arista-eos", "srl": "nokia-srlinux", "frr": "frr", "iosxe": "cisco-iosxe",
                   "junos": "juniper-junos"}


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


class NetBoxExportInventory(_Topology):
    """Reads the subset of a NetBox export we need: devices (role, platform, config_context), cables with both
    terminations, the ospf_area custom field on the cable, and the service in the top-level config_context."""

    def __init__(self, data: dict | str | Path):
        self.data = data if isinstance(data, dict) else json.loads(Path(data).read_text())

    def devices(self) -> dict[str, DeviceInfo]:
        out = {}
        for d in self.data["devices"]:
            ctx = d.get("config_context") or {}
            ip = (d.get("primary_ip4") or {}).get("address", "")
            out[d["name"]] = DeviceInfo(name=d["name"], role=d["role"]["slug"],
                                        nos=PLATFORM_TO_NOS[d["platform"]["slug"]], mgmt=ip.split("/")[0],
                                        lan_gateway=ctx.get("lan_gateway", ""), router_id=ctx.get("router_id", ""))
        return out

    def links(self) -> list[Link]:
        out = []
        for c in self.data["cables"]:
            a, b = c["a_terminations"][0]["object"], c["b_terminations"][0]["object"]
            out.append(Link(a["device"]["name"], a["name"], b["device"]["name"], b["name"],
                            str((c.get("custom_fields") or {}).get("ospf_area", ""))))
        return out

    def service(self) -> Service:
        return Service(**self.data["config_context"]["service"])


def to_netbox_export(inv) -> dict:
    """Render any inventory in NetBox's export shape (what `make customize` writes for a customer pack)."""
    def term(dev, ifname):
        return [{"object_type": "dcim.interface", "object": {"device": {"name": dev}, "name": ifname}}]

    devices = [{"name": d.name, "role": {"slug": d.role}, "platform": {"slug": NOS_TO_PLATFORM[d.nos]},
                "primary_ip4": {"address": f"{d.mgmt}/24"} if d.mgmt else None,
                "config_context": {k: v for k, v in (("lan_gateway", d.lan_gateway), ("router_id", d.router_id)) if v}}
               for d in inv.devices().values()]
    cables = [{"id": n, "a_terminations": term(l.a_dev, l.a_if), "b_terminations": term(l.b_dev, l.b_if),
               "custom_fields": {"ospf_area": l.area}} for n, l in enumerate(inv.links(), 1)]
    s = inv.service()
    return {"devices": devices, "cables": cables, "config_context": {"service": {"prefix": s.prefix, "address": s.address}}}
