"""The playbook and the command gate.

Rule 1: agents never free-form device CLI. Change commands are RENDERED from playbook templates.
Rule 2: every rendered command passes the CommandGate. Any command whose prefix is not in the entry's
        allowed_commands is rejected BEFORE a proposal exists -- so it can never reach a human, let alone a device.
Rule 3: template parameters are validated (an interface name can't smuggle in a second command).
Rule 4: templates are per network OS; parameters are typed (an interface name is checked by that NOS's reader).
"""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

import yaml
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class PlaybookError(ValueError):
    pass


class PostCheck(BaseModel):
    """One executable line of expected_post_state: run `tool` on `on`, pass if any result matches `expect`."""
    name: str
    tool: str
    on: str = "device"                      # a key of Network.context(): device, peer, control
    args: dict[str, str] = Field(default_factory=dict)
    expect: dict[str, Any]
    backout: bool = False                   # the executor backs out if this one isn't true in time


class PlaybookEntry(BaseModel):
    REFERENCE_NOS: ClassVar[str] = "eos"
    id: str
    title: str
    root_cause: bool
    detect: str
    params_schema: dict[str, str] = Field(default_factory=dict)
    fixes: dict[str, list[str]] = Field(default_factory=dict)
    rollbacks: dict[str, list[str]] = Field(default_factory=dict)
    allowed: dict[str, list[str]] = Field(default_factory=dict)
    post_checks: list[PostCheck] = Field(default_factory=list)

    def templates(self, which: str, nos: str) -> list[str]:
        table = {"fix": self.fixes, "rollback": self.rollbacks}[which]
        if not table:
            return []
        if nos not in table:
            raise PlaybookError(f"playbook entry {self.id} has no {which} for nos {nos!r} (has: {', '.join(table)})")
        return table[nos]

    def allowed_for(self, nos: str) -> list[str]:
        if not self.allowed:
            return []
        if nos not in self.allowed:
            raise PlaybookError(f"playbook entry {self.id} has no allowed_commands for nos {nos!r}")
        return self.allowed[nos]

    # the reference-NOS views the workshop labs read
    @property
    def fix(self) -> list[str]:
        return self.templates("fix", self.REFERENCE_NOS)

    @property
    def rollback(self) -> list[str]:
        return self.templates("rollback", self.REFERENCE_NOS)

    @property
    def allowed_commands(self) -> list[str]:
        return self.allowed_for(self.REFERENCE_NOS)

    @property
    def expected_post_state(self) -> list[str]:
        return [c.name for c in self.post_checks]


class GateDecision(BaseModel):
    command: str
    allowed: bool
    reason: str


class CommandGate:
    """Allow a command only if it IS an allowed prefix or starts with one followed by a space."""

    def __init__(self, allowed_commands: list[str]):
        self.allowed = allowed_commands

    def check(self, command: str) -> GateDecision:
        if any(ch in command for ch in "\n;|&`$"):
            return GateDecision(command=command, allowed=False, reason="more than one command in a line")
        cmd = " ".join(command.split())
        for prefix in self.allowed:
            if cmd == prefix or cmd.startswith(prefix + " "):
                return GateDecision(command=cmd, allowed=True, reason=f"matches allowed '{prefix}'")
        return GateDecision(command=cmd, allowed=False, reason=f"not in allowed_commands {self.allowed}")

    def split(self, commands: list[str]) -> tuple[list[str], list[GateDecision]]:
        """(allowed commands, rejected decisions)."""
        decisions = [self.check(c) for c in commands]
        return [d.command for d in decisions if d.allowed], [d for d in decisions if not d.allowed]


_AREA = re.compile(r"\d{1,3}(\.\d{1,3}){3}")
PARAM_TYPES = {"interface", "ospf_area"}


def _valid(kind: str, value: str, nos: str) -> bool:
    if kind == "ospf_area":
        return bool(_AREA.fullmatch(value))
    if kind == "interface":
        from netops.readers import get_reader
        return bool(re.fullmatch(get_reader(nos).interface_pattern, value))
    raise PlaybookError(f"unknown parameter type {kind!r}; known: {sorted(PARAM_TYPES)}")


def load_playbook(path: str | Path | None = None) -> dict[str, PlaybookEntry]:
    if path is None:
        text = resources.files("netops").joinpath("playbook.yaml").read_text()
    else:
        text = Path(path).read_text()
    out = {}
    for k, v in yaml.safe_load(text).items():
        out[k] = PlaybookEntry(id=k, title=v["title"], root_cause=v["root_cause"], detect=v["detect"],
                               params_schema=v.get("params", {}), fixes=v.get("fix", {}),
                               rollbacks=v.get("rollback", {}), allowed=v.get("allowed_commands", {}),
                               post_checks=[PostCheck(**c) for c in v.get("expected_post_state", [])])
    return out


def render(entry: PlaybookEntry, params: dict, which: str = "fix", nos: str = PlaybookEntry.REFERENCE_NOS) -> list[str]:
    """Fill the templates for this NOS, validate every parameter by its declared type, then gate every command."""
    templates = entry.templates(which, nos)     # first: a NOS with no fix fails here, before any reader lookup
    for name, value in params.items():
        kind = entry.params_schema.get(name)
        if kind is None:
            raise PlaybookError(f"parameter {name} has no validation rule in {entry.id}")
        if not _valid(kind, str(value), nos):
            raise PlaybookError(f"parameter {name}={value!r} is not valid")
    try:
        commands = [t.format(**params) for t in templates]
    except KeyError as e:
        raise PlaybookError(f"playbook entry {entry.id} needs parameter {e}") from None
    _, rejected = CommandGate(entry.allowed_for(nos)).split(commands)
    if rejected:
        raise PlaybookError(f"playbook entry {entry.id} renders blocked commands: {[r.command for r in rejected]}")
    return commands
