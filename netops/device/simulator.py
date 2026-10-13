"""SimulatedDevice — a fake Arista cEOS that answers like the real one.

Every JSON document below copies the key layout captured from ceos:4.34.8M on 2026-10-12
(see tests/fixtures/ceos/). The parsers in netops/parsers.py read real and simulated output with
the same code; tests/test_simulator.py checks the layouts match.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Literal

from netops.device.driver import CommandError, ConfigResult
from netops.device.fabric import Fabric, Port
from netops.readers.eos import normalize_interface  # noqa: F401  (EOS interface names; re-exported)

_LOG_HEADER = """Syslog logging: enabled
Buffer logging: level debugging
Console logging: level informational
Persistent logging: disabled
Monitor logging: level informational
Synchronous logging: disabled
Trap logging: level informational
Sequence numbers: disabled
Syslog facility: local4
Hostname format: Hostname only
Repeat logging interval: disabled
Repeat messages: disabled

Log Buffer:"""

_OPTIONS = {"multitopologyCapability": False, "externalRoutingCapability": True, "multicastCapability": False,
            "nssaCapability": False, "linkLocalSignaling": False, "demandCircuitsSupport": False,
            "opaqueLsaSupport": False, "doNotUseInRouteCalc": False}

_TEXT_ONLY = ("show logging", "ping", "show running-config")


class SimulatedDevice:
    nos = "eos"

    def __init__(self, fabric: Fabric, hostname: str):
        if hostname not in fabric.spec["devices"]:
            raise ValueError(f"unknown device {hostname}")
        self.fabric, self.hostname = fabric, hostname

    # ------------------------------------------------------------------ DeviceDriver API
    def run(self, cmds: list[str], fmt: Literal["json", "text"] = "json") -> list[dict]:
        out = []
        for raw in cmds:
            cmd = " ".join(raw.split())
            if fmt == "json" and cmd.startswith(_TEXT_ONLY):
                raise CommandError(f"'{cmd}' has no JSON output on EOS; request it with fmt='text'")
            out.append(self._dispatch(cmd, fmt))
        return out

    def configure(self, cmds: list[str], *, by: str = "operator") -> ConfigResult:
        """Validate EVERY line first, then apply (atomic, like a cEOS configure session)."""
        plan, ctx = [], None
        for raw in cmds:
            line = " ".join(raw.split())
            if line in ("", "!", "configure", "configure terminal", "end", "exit", "commit") \
                    or line.startswith("configure session"):
                continue
            m = re.fullmatch(r"interface (\S+)", line)
            if m:
                ctx = self._port(normalize_interface(m.group(1)))
                continue
            if ctx is None:
                raise CommandError(f"% Invalid input (at '{line}')")
            if m := re.fullmatch(r"ip ospf area (\d+\.\d+\.\d+\.\d+)", line):
                ipaddress.IPv4Address(m.group(1))
                plan.append((ctx, "area", m.group(1)))
            elif line == "no ip ospf area":
                plan.append((ctx, "area", None))
            elif line in ("shutdown", "no shutdown"):
                plan.append((ctx, "admin", line == "no shutdown"))
            elif m := re.fullmatch(r"mtu (\d+)", line):
                plan.append((ctx, "mtu", int(m.group(1))))
            elif m := re.fullmatch(r"description (.+)", line):
                plan.append((ctx, "description", m.group(1)))
            elif line == "ip ospf network point-to-point":
                continue
            else:
                raise CommandError(f"% Invalid input (at '{line}')")
        for port, attr, value in plan:
            if attr == "admin":
                self.fabric.set_admin(port, value, by)
            else:
                self.fabric.configure_port(port, attr, value, by)
        return ConfigResult(device=self.hostname, applied=[l for l in cmds if l.strip()], by=by)

    def wait(self, seconds: float) -> None:
        self.fabric.advance(seconds)

    # ------------------------------------------------------------------ helpers
    def _port(self, name: str) -> Port:
        try:
            return self.fabric.port(self.hostname, name)
        except KeyError:
            raise CommandError(f"% Interface {name} does not exist") from None

    def _epoch(self, dt) -> float:
        return dt.timestamp() if dt else 0.0

    def _dispatch(self, cmd: str, fmt: str) -> dict:
        if cmd == "show ip ospf neighbor":
            return self._ospf_neighbor()
        if m := re.fullmatch(r"show ip ospf interface (\S+)", cmd):
            return self._ospf_interface(normalize_interface(m.group(1)))
        if m := re.fullmatch(r"show interfaces (\S+)", cmd):
            return self._interfaces(normalize_interface(m.group(1)))
        if m := re.fullmatch(r"show ip route (\S+)", cmd):
            return self._route(m.group(1))
        if m := re.fullmatch(r"clear counters(?: (\S+))?", cmd):
            self.fabric.clear_counters(self.hostname, normalize_interface(m.group(1)) if m.group(1) else None,
                                       by="cli")
            return {} if fmt == "json" else {"output": ""}
        if cmd == "show logging":
            return {"output": self._logging()}
        if m := re.fullmatch(r"ping (\S+)(?: source (\S+))?(?: repeat (\d+))?", cmd):
            return {"output": self._ping(m.group(1), m.group(2), int(m.group(3) or 5))}
        if m := re.fullmatch(r"show running-config interfaces (\S+)", cmd):
            return {"output": self._running(normalize_interface(m.group(1)))}
        raise CommandError(f"% Invalid input (at '{cmd}')")

    # ------------------------------------------------------------------ eAPI JSON (captured layouts)
    def _ospf_neighbor(self) -> dict:
        entries = []
        for p in self.fabric.ports_of(self.hostname):
            state = self.fabric.adjacency_state(p)
            if state is None:
                continue                                    # area mismatch: no entry at all
            q = self.fabric.peer(p)
            entries.append({
                "routerId": self.fabric.spec["devices"][q.device]["router_id"], "interfaceAddress": q.ip,
                "interfaceName": p.name, "priority": 0, "adjacencyState": state, "drState": None,
                "options": dict(_OPTIONS), "inactivity": self._epoch(self.fabric.clock) + p.dead,
                "details": {"areaId": p.area, "designatedRouter": "0.0.0.0", "backupDesignatedRouter": "0.0.0.0",
                            "numberOfStateChanges": 6, "stateTime": self._epoch(p.last_change),
                            "inactivityDefers": 0, "retransmissionCount": 0, "bfdState": "adminDown",
                            "bfdRequestSent": False, "grHelperTimer": None, "grNumAttempts": 0,
                            "grLastRestartTime": None}})
        return {"vrfs": {"default": {"instList": {"1": {"ospfNeighborEntries": entries}}}}}

    def _ospf_interface(self, name: str) -> dict:
        p = self._port(name)
        n = 1 if self.fabric.adjacency_state(p) == "full" else 0
        body = {"state": "p2p" if p.oper_up else "down", "cost": 10, "neighborCount": n,
                "helloInterval": p.hello, "deadInterval": p.dead, "retransmitInterval": 5, "transmitDelay": 1,
                "options": dict(_OPTIONS, externalRoutingCapability=False), "area": p.area,
                "interfaceAddress": p.ip, "interfaceMask": 31, "interfaceType": "p2p", "bfdState": "default",
                "passive": p.passive, "teEnabled": False, "interfaceSpeed": 1000, "tilfaProtection": "disabled"}
        return {"vrfs": {"default": {"instList": {"1": {"interfaces": {name: body}}}}}}

    def _interfaces(self, name: str) -> dict:
        p = self._port(name)
        up = p.oper_up
        return {"interfaces": {name: {
            "name": name, "forwardingModel": "routed", "lineProtocolStatus": "up" if up else "down",
            "interfaceStatus": "connected" if up else ("disabled" if not p.admin_up else "notconnect"),
            "hardware": "ethernet", "interfaceAddress": [{"primaryIp": {"address": p.ip, "maskLen": 31}}],
            "description": p.description, "bandwidth": 1000000000, "mtu": p.mtu, "l3MtuConfigured": True,
            "lastStatusChangeTimestamp": self._epoch(p.last_change),
            "interfaceCounters": {"inOctets": 0, "inDiscards": 0, "linkStatusChanges": p.link_status_changes,
                                  "totalInErrors": p.in_errors, "totalOutErrors": 0,
                                  "counterRefreshTime": self._epoch(self.fabric.clock)},
            "duplex": "duplexFull", "autoNegotiate": "unknown", "loopbackMode": "loopbackNone", "lanes": 0}}}

    def _route(self, arg: str) -> dict:
        prefix = arg if "/" in arg else self.fabric.prefix_for(arg)
        routes = {}
        if prefix:
            present, via = self.fabric.has_route(self.hostname, prefix)
            if present and via is None:
                routes[prefix] = {"hardwareProgrammed": True, "routeType": "connected", "routeLeaked": False,
                                  "kernelProgrammed": True, "routeAction": "forward", "directlyConnected": True,
                                  "vias": [{"interface": "Loopback100"}]}
            elif present:
                routes[prefix] = {"hardwareProgrammed": True, "routeType": "OSPF", "routeLeaked": False,
                                  "kernelProgrammed": True, "preference": 110, "metric": 20, "routeAction": "forward",
                                  "directlyConnected": False,
                                  "vias": [{"nexthopAddr": via.peer_ip, "interface": via.name}]}
        return {"vrfs": {"default": {"routingDisabled": False, "allRoutesProgrammedHardware": True,
                                     "allRoutesProgrammedKernel": True, "defaultRouteState": "notSet",
                                     "routes": routes}}}

    # ------------------------------------------------------------------ text commands
    def _logging(self) -> str:
        lines = [f"{e.ts.strftime('%b %d %H:%M:%S')} {e.device} {e.process}: {e.text}"
                 for e in self.fabric.logs[self.hostname]]
        return _LOG_HEADER + "\n" + "\n".join(lines) + "\n"

    def _ping(self, dst: str, src: str | None, repeat: int) -> str:
        ok = self.fabric.can_ping(self.hostname, dst, src)
        head = f"PING {dst} ({dst}) from {src or self.fabric.ports_of(self.hostname)[0].ip} : 72(100) bytes of data."
        if not ok:
            return (f"{head}\n\n--- {dst} ping statistics ---\n"
                    f"{repeat} packets transmitted, 0 received, 100% packet loss, time 47ms\n\n")
        replies = "\n".join(f"80 bytes from {dst}: icmp_seq={i} ttl=64 time=0.{140 + i} ms" for i in range(1, repeat + 1))
        return (f"{head}\n{replies}\n\n--- {dst} ping statistics ---\n"
                f"{repeat} packets transmitted, {repeat} received, 0% packet loss, time 21ms\n"
                f"rtt min/avg/max/mdev = 0.141/0.143/0.145/0.002 ms, ipg/ewma 5.198/3.590 ms\n")

    def _running(self, name: str) -> str:
        p = self._port(name)
        lines = [f"interface {name}", f"   description {p.description}", f"   mtu {p.mtu}", "   no switchport",
                 f"   ip address {p.ip}/31", "   ip ospf network point-to-point"]
        if p.area:
            lines.append(f"   ip ospf area {p.area}")
        if not p.admin_up:
            lines.append("   shutdown")
        return "\n".join(lines) + "\n"
