"""The network as agents see it: a set of DeviceDrivers + the topology, exposed as READ tools.

Agents never touch a DeviceDriver directly. They call these methods (through an allowlisted
ToolBox), get typed models back, and every result becomes citable evidence.
"""
from __future__ import annotations

import time
from datetime import datetime

from netops.device.driver import ConfigResult, DeviceDriver
from netops.device.fabric import Fabric, load_incident
from netops.device.simulator import SimulatedDevice
from netops.inventory import YamlInventory
from netops.models import InterfaceStatus, LogLine, LogSummary, OspfInterface, OspfNeighbor, PingResult, Route
from netops.parsers import summarize_logs
from netops.readers import get_reader


class Network:
    def __init__(self, devices: dict[str, DeviceDriver], spec: dict, fabric: Fabric | None = None, inventory=None):
        self.devices, self.spec, self.fabric = devices, spec, fabric
        self.inventory = inventory or YamlInventory(spec)
        self.year = datetime.fromisoformat(spec["start_time"]).year
        self.affected: str = spec.get("affected") or next(iter(spec["devices"]))

    @classmethod
    def simulated(cls, variant: str | None = None) -> "Network":
        fabric = Fabric(variant)
        return cls({h: SimulatedDevice(fabric, h) for h in fabric.spec["devices"]}, fabric.spec, fabric)

    @classmethod
    def ceos(cls, hosts: dict[str, str], username: str = "admin", password: str = "admin",
             transport_for=None) -> "Network":
        """Real cEOS devices over eAPI. `hosts` maps hostname -> management address.
        Same topology file, same read tools, same agents -- only the driver changes."""
        from netops.device.ceos import CeosDevice
        spec = load_incident()
        devices = {h: CeosDevice(h, addr, username, password,
                                 transport=transport_for(h) if transport_for else None) for h, addr in hosts.items()}
        return cls(devices, spec)

    # ---------------------------------------------------------------- topology (from the inventory port)
    def _dev(self, device: str) -> DeviceDriver:
        if device not in self.devices:
            raise ValueError(f"unknown device {device!r}; devices: {', '.join(self.devices)}")
        return self.devices[device]

    def uplink(self, device: str) -> dict:
        """The device's uplink: its interface, the peer device and the peer's interface."""
        return self.inventory.uplink(device).as_dict()

    @property
    def service(self) -> dict:
        s = self.inventory.service()
        return {"prefix": s.prefix, "address": s.address}

    def lan_gateway(self, device: str) -> str:
        return self.inventory.devices()[device].lan_gateway

    def context(self, device: str | None = None) -> dict:
        """Everything a runbook, a template or a check may refer to, for the incident device."""
        device = device or self.affected
        up, devs = self.uplink(device), self.inventory.devices()
        control = next(n for n, d in devs.items() if d.role == devs[device].role and n != device)
        return {"device": device, "uplink": up["interface"], "peer": up["peer"], "peer_interface": up["peer_interface"],
                "service": self.service["address"], "service_prefix": self.service["prefix"],
                "lan_gateway": self.lan_gateway(device), "control": control}

    # ---------------------------------------------------------------- vendor: which reader speaks this device
    def nos(self, device: str) -> str:
        return getattr(self._dev(device), "nos", "eos")

    def reader(self, device: str):
        return get_reader(self.nos(device))

    # ---------------------------------------------------------------- READ tools
    def ospf_neighbors(self, device: str) -> list[OspfNeighbor]:
        return self.reader(device).ospf_neighbors(self._dev(device))

    def ospf_interface(self, device: str, interface: str) -> OspfInterface:
        r = self.reader(device)
        return r.ospf_interface(self._dev(device), r.normalize_interface(interface))

    def interface(self, device: str, interface: str) -> InterfaceStatus:
        r = self.reader(device)
        return r.interface(self._dev(device), r.normalize_interface(interface))

    def route(self, device: str, prefix: str) -> Route:
        return self.reader(device).route(self._dev(device), prefix)

    def ping(self, device: str, destination: str, source: str | None = None, repeat: int = 5) -> PingResult:
        return self.reader(device).ping(self._dev(device), destination, source, repeat)

    def logs(self, device: str) -> list[LogLine]:
        return self.reader(device).logs(self._dev(device), self.year)

    def log_summary(self, device: str) -> LogSummary:
        return summarize_logs(device, self.logs(device))

    # ---------------------------------------------------------------- ground truth + time
    def reachability(self, device: str | None = None) -> str:
        """The question that matters: can the branch's users reach the core service? PASS / FAIL."""
        device = device or self.affected
        ok = self.ping(device, self.service["address"], self.lan_gateway(device)).success
        return "PASS" if ok else "FAIL"

    def wait(self, seconds: float) -> None:
        """Let the network converge. All simulated devices share one clock; real devices just sleep."""
        if self.fabric is not None:
            self.fabric.advance(seconds)
        else:
            time.sleep(seconds)

    def read_only(self) -> "ReadOnlyNetwork":
        return ReadOnlyNetwork(self)

    # ---------------------------------------------------------------- WRITE (never given to team agents)
    def configure(self, device: str, cmds: list[str], *, by: str) -> ConfigResult:
        return self._dev(device).configure(cmds, by=by)

    def clear_counters(self, device: str, interface: str | None = None) -> None:
        self.reader(device).clear_counters(self._dev(device), interface)


class ReadOnlyNetwork:
    """The network as a specialist agent gets it: every read, no write. Only the Executor holds the real one."""
    _WRITES = frozenset({"configure", "clear_counters"})

    def __init__(self, net: Network):
        object.__setattr__(self, "_net", net)

    def __getattr__(self, name: str):
        if name in ReadOnlyNetwork._WRITES:
            raise PermissionError(f"read-only network: agents can't call {name}()")
        return getattr(self._net, name)
