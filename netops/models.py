"""Small, vendor-neutral models. Agents reason over THESE, never over raw CLI.

Every model keeps `raw_command` (what was run on the device) so a network engineer can always
see the real command behind an observation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# OSPF neighbor states as the protocol defines them (lower-case, as cEOS eAPI reports them).
AdjState = Literal["full", "2ways", "init", "exchStart", "exchange", "loading", "down"]
LogCategory = Literal["LINK", "OSPF", "CONFIG", "OTHER"]


class Obs(BaseModel):
    """Base for every observation: which command produced it."""
    raw_command: str = ""

    def for_llm(self) -> dict:
        """What a model is allowed to see (JSON-safe)."""
        return self.model_dump(mode="json")


class OspfNeighbor(Obs):
    device: str
    neighbor_id: str
    interface: str
    state: str          # "full" when the adjacency is up
    area: str


class OspfInterface(Obs):
    device: str
    interface: str
    area: str
    hello: int
    dead: int
    neighbor_count: int
    passive: bool = False


class InterfaceStatus(Obs):
    device: str
    interface: str
    line_protocol: str              # "up" / "down"
    link_status_changes: int        # how many times the link went up/down (the flap counter)
    in_errors: int = 0
    description: str = ""
    mtu: int | None = None


class Route(Obs):
    device: str
    prefix: str
    present: bool
    route_type: str | None = None
    next_hops: list[str] = Field(default_factory=list)


class PingResult(Obs):
    device: str
    destination: str
    source: str | None
    sent: int
    received: int

    @property
    def success(self) -> bool:
        return self.sent > 0 and self.received == self.sent


class LogLine(Obs):
    device: str
    ts: datetime
    category: LogCategory
    text: str


class LogSummary(Obs):
    """Event-filtered syslog: counts per category plus the non-link lines (for specialists)."""
    device: str
    total: int
    counts: dict[str, int]
    notable: list[str] = Field(default_factory=list)
