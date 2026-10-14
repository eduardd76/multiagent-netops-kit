"""The only way an agent touches the network. Allowlists are enforced HERE, in code."""
from __future__ import annotations

from typing import Callable, Iterable

from netops.evidence import EvidenceStore
from netops.llm import ToolSpec
from netops.network import Network


class ToolNotAllowed(PermissionError):
    pass


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_D = {"type": "string", "description": "device hostname, e.g. BRANCH-7"}
_I = {"type": "string", "description": "interface, e.g. Ethernet1"}

READ_TOOLS: dict[str, tuple[str, dict, Callable]] = {
    "ospf_neighbors": ("OSPF neighbor table (show ip ospf neighbor). Empty list = no adjacency.",
                       _schema({"device": _D}, ["device"]), lambda n, a: n.ospf_neighbors(a["device"])),
    "ospf_interface": ("OSPF settings of an interface: area, hello/dead timers (show ip ospf interface).",
                       _schema({"device": _D, "interface": _I}, ["device", "interface"]),
                       lambda n, a: n.ospf_interface(a["device"], a["interface"])),
    "interface": ("Interface status and link-status-change counter (show interfaces).",
                  _schema({"device": _D, "interface": _I}, ["device", "interface"]),
                  lambda n, a: n.interface(a["device"], a["interface"])),
    "route": ("Look up a prefix in the routing table (show ip route).",
              _schema({"device": _D, "prefix": {"type": "string"}}, ["device", "prefix"]),
              lambda n, a: n.route(a["device"], a["prefix"])),
    "ping": ("Ping from a device, optionally from a source address.",
             _schema({"device": _D, "destination": {"type": "string"}, "source": {"type": "string"}},
                     ["device", "destination"]),
             lambda n, a: n.ping(a["device"], a["destination"], a.get("source"))),
    "logs": ("The full syslog buffer (show logging). Can be hundreds of lines.",
             _schema({"device": _D}, ["device"]), lambda n, a: n.logs(a["device"])),
    "log_summary": ("Syslog summarised: counts per category plus the OSPF/CONFIG lines verbatim.",
                    _schema({"device": _D}, ["device"]), lambda n, a: n.log_summary(a["device"])),
}

# Lab 1 ONLY. These change the network with no playbook, no gate, no human. That is the point of Lab 1.
UNGATED_TOOLS: dict[str, tuple[str, dict, Callable]] = {
    "bounce_interface": ("shutdown / no shutdown an interface. Applies immediately.",
                         _schema({"device": _D, "interface": _I}, ["device", "interface"]),
                         lambda n, a: (n.configure(a["device"], [f"interface {a['interface']}", "shutdown"], by="single-agent"),
                                       n.configure(a["device"], [f"interface {a['interface']}", "no shutdown"],
                                                   by="single-agent"))[-1].applied),
    "clear_counters": ("clear counters on an interface. Applies immediately.",
                       _schema({"device": _D, "interface": _I}, ["device", "interface"]),
                       lambda n, a: n.clear_counters(a["device"], a["interface"], by="single-agent") or "counters cleared"),
}


class ToolBox:
    def __init__(self, network: Network, evidence: EvidenceStore, allow: Iterable[str], *, agent: str,
                 ungated: bool = False, extra_tools: dict | None = None):
        self.net, self.evidence, self.agent = network, evidence, agent
        self.table = dict(READ_TOOLS) | (dict(UNGATED_TOOLS) if ungated else {}) \
            | dict(extra_tools or {})
        self.allow = list(dict.fromkeys(allow))
        unknown = [t for t in self.allow if t not in self.table]
        if unknown:
            raise ValueError(f"{agent}: unknown or ungated tools without ungated=True: {unknown}")
        self.calls: list[dict] = []

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec(name=t, description=self.table[t][0], parameters=self.table[t][1]) for t in self.allow]

    def call(self, name: str, args: dict) -> str:
        if name not in self.allow:
            raise ToolNotAllowed(f"{self.agent} may not call {name}")
        try:
            result = self.table[name][2](self.net, args)
        except KeyError as e:
            return f"ERROR: missing argument {e}"
        except Exception as e:                          # device errors, bad interface names...
            return f"ERROR: {e}"
        ev = self.evidence.add(name, args, result)
        self.calls.append({"tool": name, "args": args, "ev": ev.id})
        return self.evidence.text(ev)
