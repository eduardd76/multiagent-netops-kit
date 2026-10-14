# kit/netops/ports.py
"""The six ports. Read this file to extend the kit: implement one of these protocols and pass the adapter in
(Incident / Coordinator take sources, audit and an approval channel). Agents never import an adapter -- only
these shapes.

  Inventory       devices, links and intent              (default: incident.yaml, netops/inventory.py)
  DeviceDriver    how to talk to a device                 (netops/device/driver.py)
  Reader          how to interpret what a device says     (netops/readers/)
  EvidenceSource  observations from outside the device    (as_tool() makes one an agent tool)
  ChangeExecutor  the only writer                         (netops/executor.py)
  ApprovalChannel where the human decides                 (Coordinator gate: submit() / resolve())
  AuditSink       where the record of every action goes   (netops/audit_emit.py dispatches to it)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from netops.device.driver import DeviceDriver
from netops.models import InterfaceStatus, LogLine, OspfInterface, OspfNeighbor, PingResult, Route


# ---------------------------------------------------------------- inventory
@dataclass(frozen=True)
class DeviceInfo:
    name: str
    role: str
    nos: str = "eos"
    mgmt: str = ""
    lan_gateway: str = ""
    router_id: str = ""


@dataclass(frozen=True)
class Link:
    a_dev: str
    a_if: str
    b_dev: str
    b_if: str
    area: str = ""                       # intent: the area both ends should run


@dataclass(frozen=True)
class Uplink:
    interface: str
    peer: str
    peer_interface: str

    def as_dict(self) -> dict:
        return {"interface": self.interface, "peer": self.peer, "peer_interface": self.peer_interface}


@dataclass(frozen=True)
class Service:
    prefix: str
    address: str


class Inventory(Protocol):
    def devices(self) -> dict[str, DeviceInfo]: ...
    def links(self) -> list[Link]: ...
    def service(self) -> Service: ...
    def uplink(self, device: str) -> Uplink: ...


# ---------------------------------------------------------------- reading devices
class Reader(Protocol):
    nos: str
    interface_pattern: str

    def normalize_interface(self, name: str) -> str: ...
    def ospf_neighbors(self, d: DeviceDriver) -> list[OspfNeighbor]: ...
    def ospf_interface(self, d: DeviceDriver, ifname: str) -> OspfInterface: ...
    def interface(self, d: DeviceDriver, ifname: str) -> InterfaceStatus: ...
    def route(self, d: DeviceDriver, prefix: str) -> Route: ...
    def ping(self, d: DeviceDriver, dst: str, src: str | None, repeat: int) -> PingResult: ...
    def logs(self, d: DeviceDriver, year: int) -> list[LogLine]: ...
    def clear_counters(self, d: DeviceDriver, ifname: str | None) -> None: ...


# ---------------------------------------------------------------- evidence beyond the device
class EvidenceItem(BaseModel):
    ts: str
    device: str
    source: str
    text: str


class EvidenceSource(Protocol):
    name: str
    description: str

    def query(self, device: str, *, limit: int = 400) -> list[EvidenceItem]: ...


_SOURCE_SCHEMA = {"type": "object", "properties": {"device": {"type": "string"}, "limit": {"type": "integer"}},
                  "required": ["device"], "additionalProperties": False}


def as_tool(source: EvidenceSource) -> tuple[str, tuple]:
    """Any EvidenceSource as one more read tool for an agent: (name, (description, schema, handler))."""
    return source.name, (source.description, _SOURCE_SCHEMA,
                         lambda n, a: source.query(a["device"], limit=int(a.get("limit", 400))))


# ---------------------------------------------------------------- the writer
class ChangeExecutor(Protocol):
    def apply(self, proposal: dict, token: Any) -> dict: ...


# ---------------------------------------------------------------- the human gate
@dataclass
class ApprovalTicket:
    id: str
    channel: str
    digest: str
    version: int
    record: dict = field(default_factory=dict)      # what the external system holds, in its own format


@dataclass
class Decision:
    state: Literal["pending", "approved", "rejected"]
    by: str = ""
    reason: str = ""


class ApprovalChannel(Protocol):
    """Returns a DECISION, never a token. Only netops.approval.Approvals mints tokens."""
    name: str

    def request(self, proposal: dict, pre_checks: list[dict]) -> ApprovalTicket: ...
    def decide(self, ticket: ApprovalTicket, *, approve: bool, by: str, reason: str = "") -> None: ...
    def decision(self, ticket: ApprovalTicket) -> Decision: ...


# ---------------------------------------------------------------- the record
@dataclass
class AuditEvent:
    kind: str                       # message | approved | consumed | change_applied | change_rolled_back
    actor: str
    device: str = ""
    detail: dict = field(default_factory=dict)


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...
