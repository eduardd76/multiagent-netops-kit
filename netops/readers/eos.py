# kit/netops/readers/eos.py
"""Arista EOS: the commands to run and how to read their JSON. The simulator answers the same commands with the
same JSON, so this one reader serves SimulatedDevice and CeosDevice."""
from __future__ import annotations

import re

from netops.device.driver import CommandError, DeviceDriver
from netops.models import InterfaceStatus, LogLine, OspfInterface, OspfNeighbor, PingResult, Route
from netops.parsers import (parse_interface, parse_logging, parse_ospf_interface, parse_ospf_neighbors, parse_ping,
                            parse_route)


def normalize_interface(name: str) -> str:
    """EOS accepts Et1 / eth1 / ethernet1 / Ethernet1 -- so do we."""
    m = re.fullmatch(r"(?i)(et|eth|ethernet)\s*(\d+)", name.strip())
    if not m:
        raise CommandError(f"% Invalid input (interface '{name}')")
    return f"Ethernet{m.group(2)}"


class EosReader:
    nos = "eos"
    interface_pattern = r"Ethernet\d+"

    def normalize_interface(self, name: str) -> str:
        return normalize_interface(name)

    def ospf_neighbors(self, d: DeviceDriver) -> list[OspfNeighbor]:
        return parse_ospf_neighbors(d.hostname, d.run(["show ip ospf neighbor"])[0])

    def ospf_interface(self, d: DeviceDriver, ifname: str) -> OspfInterface:
        return parse_ospf_interface(d.hostname, ifname, d.run([f"show ip ospf interface {ifname}"])[0])

    def interface(self, d: DeviceDriver, ifname: str) -> InterfaceStatus:
        return parse_interface(d.hostname, ifname, d.run([f"show interfaces {ifname}"])[0])

    def route(self, d: DeviceDriver, prefix: str) -> Route:
        return parse_route(d.hostname, prefix, d.run([f"show ip route {prefix}"])[0])

    def ping(self, d: DeviceDriver, dst: str, src: str | None, repeat: int) -> PingResult:
        cmd = f"ping {dst}" + (f" source {src}" if src else "") + f" repeat {repeat}"
        return parse_ping(d.hostname, dst, src, d.run([cmd], fmt="text")[0]["output"])

    def logs(self, d: DeviceDriver, year: int) -> list[LogLine]:
        return parse_logging(d.hostname, d.run(["show logging"], fmt="text")[0]["output"], year)

    def clear_counters(self, d: DeviceDriver, ifname: str | None) -> None:
        d.run([f"clear counters {ifname}" if ifname else "clear counters"])
