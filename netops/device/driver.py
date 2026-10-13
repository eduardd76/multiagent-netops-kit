"""The DeviceDriver interface — how to talk to a device. Reading its output is a Reader's job (netops/readers/).
The seam that lets the SAME agent code run on a simulated switch
(for students) and on a real Arista cEOS over eAPI (instructor demo).

It mirrors eAPI on purpose:
  run(["show ip ospf neighbor"], fmt="json")  -> [ {...the exact JSON cEOS returns...} ]
  run(["show logging"], fmt="text")           -> [ {"output": "...the exact text..."} ]
  configure(["interface Ethernet1", "ip ospf area 0.0.0.0"], by="on-call")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


class CommandError(RuntimeError):
    """The device rejected a command (EOS prints '% Invalid input')."""


@dataclass
class ConfigResult:
    device: str
    applied: list[str] = field(default_factory=list)
    by: str = "operator"


class DeviceDriver(Protocol):
    hostname: str
    nos: str

    def run(self, cmds: list[str], fmt: Literal["json", "text"] = "json") -> list[dict]: ...

    def configure(self, cmds: list[str], *, by: str = "operator") -> ConfigResult: ...

    def wait(self, seconds: float) -> None:
        """Let time pass (virtual on the simulator, real on hardware). Used for convergence polling."""
        ...
