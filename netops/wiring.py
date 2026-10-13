# kit/netops/wiring.py
"""One file per customer -> one Incident. Pick adapters by name; nothing in netops/ changes per customer.

    inc = build("customers/acme.yaml")      # customer demo
    inc = build()                           # the workshop default (same as new_incident())
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from netops import render
from netops.approval import Approvals
from netops.audit import Fanout, JsonlAudit, MemoryAudit, MockConfluencePage, MockServiceNowIncident
from netops.channels import MockJiraApproval, MockServiceNowCR, NotebookApproval
from netops.evidence import EvidenceStore
from netops.inventory import NetBoxExportInventory, YamlInventory, to_netbox_export
from netops.llm import FallbackLLM, MockLLM, OpenAICompatLLM, make_llm
from netops.network import Network
from netops.orchestrator import Incident, new_incident
from netops.protocol import Bus
from netops.skin import BoundaryLLM, Skin
from netops.sources import DeviceLogs, MockLoki, MockSplunk
from netops.trace import Trace


class PackError(ValueError):
    pass


class Pack(BaseModel):
    name: str
    requester: str = "presenter"
    branding: dict = Field(default_factory=dict)
    naming: dict[str, str] = Field(default_factory=dict)
    scenario: str = "ospf_area_mismatch"
    mode: Literal["simulated", "lab"] = "simulated"
    variant: str | None = None
    inventory: dict = Field(default_factory=lambda: {"adapter": "yaml"})
    evidence: list[dict] = Field(default_factory=lambda: [{"adapter": "device_logs"}])
    approval: dict = Field(default_factory=lambda: {"adapter": "notebook"})
    audit: list[dict] = Field(default_factory=lambda: [{"adapter": "memory"}])
    llm: dict = Field(default_factory=lambda: {"adapter": "auto"})
    lab: dict = Field(default_factory=dict)            # mode: lab -> {hosts: {name: "host:port"}, username, password}


def _llm_compat(spec):
    return FallbackLLM(OpenAICompatLLM(spec["base_url"], spec["model"], spec.get("api_key", "not-needed")),
                       allow_fallback=spec.get("fallback") == "mock")


ADAPTERS = {
    "inventory": {"yaml": lambda spec, net, skin: YamlInventory(net.spec),
                  "netbox_export": lambda spec, net, skin: NetBoxExportInventory(
                      spec["path"] if "path" in spec else to_netbox_export(YamlInventory(net.spec)))},
    "evidence": {"device_logs": lambda spec, net, skin: DeviceLogs(net.read_only()),
                 "mock_splunk": lambda spec, net, skin: MockSplunk(net.read_only(), spec.get("index", "network")),
                 "mock_loki": lambda spec, net, skin: MockLoki(net.read_only())},
    "approval": {"notebook": lambda spec, net, skin: NotebookApproval(skin),
                 "mock_servicenow": lambda spec, net, skin: MockServiceNowCR(skin),
                 "mock_jira": lambda spec, net, skin: MockJiraApproval(skin)},
    "audit": {"memory": lambda spec, net, skin: MemoryAudit(),
              "jsonl": lambda spec, net, skin: JsonlAudit(spec["path"]),
              "mock_servicenow_incident": lambda spec, net, skin: MockServiceNowIncident(skin),
              "mock_confluence": lambda spec, net, skin: MockConfluencePage(skin, spec.get("space", "NETOPS"))},
    "llm": {"auto": lambda spec, net, skin: make_llm(), "mock": lambda spec, net, skin: MockLLM(),
            "openai_compat": lambda spec, net, skin: _llm_compat(spec)},
}


def _env(obj, where: Path):
    """Substitute ${ENV} in parsed string values only -- YAML comments may mention ${...} harmlessly."""
    if isinstance(obj, str):
        def sub(m):
            if m.group(1) not in os.environ:
                raise PackError(f"environment variable {m.group(1)} is not set (needed by {where.name})")
            return os.environ[m.group(1)]
        return re.sub(r"\$\{(\w+)\}", sub, obj)
    if isinstance(obj, dict):
        return {k: _env(v, where) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_env(v, where) for v in obj]
    return obj


def load_pack(path: str | Path) -> Pack:
    path = Path(path)
    try:
        return Pack(**_env(yaml.safe_load(path.read_text()), path))
    except ValidationError as e:
        raise PackError(f"{path.name}: {e.errors()[0]['loc'][0]} -- {e.errors()[0]['msg']}") from None


def _pick(kind: str, spec: dict, net, skin):
    table, name = ADAPTERS[kind], spec.get("adapter")
    if name not in table:
        raise PackError(f"unknown {kind} adapter {name!r}; known: {', '.join(sorted(table))}")
    return table[name](spec, net, skin)


def build(path: str | Path | None = None, *, verbose: bool = True) -> Incident:
    if path is None:
        render.configure(None)
        return new_incident(verbose=verbose)
    pack = load_pack(path)
    skin = Skin(pack.naming)
    if pack.mode == "simulated":
        net = Network.simulated(pack.variant)
    else:
        net = Network.ceos(pack.lab["hosts"], pack.lab.get("username", "admin"), pack.lab.get("password", "admin"))
    net.inventory = _pick("inventory", pack.inventory, net, skin)
    audit = Fanout([_pick("audit", a, net, skin) for a in pack.audit])
    sources = tuple(s for s in (_pick("evidence", e, net, skin) for e in pack.evidence)
                    if type(s) is not DeviceLogs)          # the device's own logs are already a read tool
    llm = BoundaryLLM(_pick("llm", pack.llm, net, skin), skin)
    channel = _pick("approval", pack.approval, net, skin)
    render.configure(skin)                                 # last: a pack that fails to build leaves no skin behind
    return Incident(network=net, llm=llm, trace=Trace(verbose, skin=skin), evidence=EvidenceStore(fence=True),
                    bus=Bus(audit=audit), approvals=Approvals(audit=audit), pack=pack, skin=skin,
                    channel=channel, audit=audit, sources=sources)
