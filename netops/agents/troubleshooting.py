"""Troubleshooting specialist: READ-ONLY. Runs the runbook, detects faults deterministically,
lets the model rank and narrate them in a validated structure. It can't drop or invent a finding."""
from __future__ import annotations

import json
from importlib import resources

import yaml
from pydantic import BaseModel, Field

from netops.agents.loop import run_agent
from netops.agents.tools import ToolBox
from netops.evidence import EvidenceStore
from netops.llm import LLM, ToolSpec
from netops.network import Network
from netops.playbook import load_playbook
from netops.ports import as_tool
from netops.protocol import Message

ALLOW = ["ping", "route", "ospf_neighbors", "ospf_interface", "interface", "log_summary"]
FLAP_THRESHOLD = 4

SYSTEM = """ROLE: tier-2 troubleshooting specialist in a NOC team.
YOU OWN: explaining why the branch lost service AND why it did not recover.
YOU MAY NOT: change anything -- your tools are read-only.
OUTPUT: call submit_diagnosis once. Keep every detected finding; rank the one that explains the outage first.
EVIDENCE RULE: cite evidence ids (ev_03) for every claim."""

SUBMIT = ToolSpec(name="submit_diagnosis", description="Submit the ranked findings with a short narrative each.",
                  parameters={"type": "object", "properties": {
                      "findings": {"type": "array", "items": {"type": "object", "properties": {
                          "id": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}},
                          "narrative": {"type": "string"}}, "required": ["id", "narrative"]}},
                      "summary": {"type": "string"}}, "required": ["findings", "summary"]})


class Finding(BaseModel):
    id: str                       # a playbook entry id when one matches
    title: str
    explains_outage: bool
    evidence_ids: list[str]
    observed: dict = Field(default_factory=dict)
    narrative: str = ""


def topology_params(net: Network, device: str | None = None) -> dict:
    return net.context(device)


def run_runbook(tools: ToolBox, params: dict) -> dict[str, str]:
    """Run diagnose.yaml in order. Returns {step_key: evidence_id}."""
    skill = yaml.safe_load(resources.files("netops").joinpath("data", "diagnose.yaml").read_text())
    got = {}
    for step in skill["steps"]:
        args = {k: v.format(**params) for k, v in step["args"].items()}
        tools.call(step["tool"], args)
        key = f"{step['tool']}:{args['device']}"
        got[key] = tools.calls[-1]["ev"]
    return got


def detect(ev: EvidenceStore, got: dict[str, str], p: dict) -> list[Finding]:
    """Deterministic detectors -- the outcome never depends on the model."""
    playbook = load_playbook()
    findings: list[Finding] = []
    intf = ev.get(got[f"interface:{p['device']}"]).result
    logs = ev.get(got[f"log_summary:{p['device']}"]).result
    if intf["link_status_changes"] > FLAP_THRESHOLD or logs["counts"].get("LINK", 0) > 20:
        e = playbook["interface_flap"]
        findings.append(Finding(id=e.id, title=e.title, explains_outage=e.root_cause,
                                evidence_ids=[got[f"interface:{p['device']}"], got[f"log_summary:{p['device']}"]],
                                observed={"link_status_changes": intf["link_status_changes"],
                                          "link_log_lines": logs["counts"].get("LINK", 0)}))
    nbrs = ev.get(got[f"ospf_neighbors:{p['device']}"]).result
    full = any(n["interface"] == p["uplink"] and n["state"] == "full" for n in nbrs)
    local = ev.get(got[f"ospf_interface:{p['device']}"]).result
    peer = ev.get(got[f"ospf_interface:{p['peer']}"]).result
    if not full:
        base = [got[f"ospf_neighbors:{p['device']}"], got[f"ospf_interface:{p['device']}"],
                got[f"ospf_interface:{p['peer']}"]]
        if local["area"] != peer["area"]:
            e = playbook["ospf_area_mismatch"]
            findings.append(Finding(id=e.id, title=e.title, explains_outage=e.root_cause, evidence_ids=base,
                                    observed={"uplink": p["uplink"], "local_area": local["area"], "peer": p["peer"],
                                              "peer_interface": p["peer_interface"], "peer_area": peer["area"]}))
        else:
            findings.append(Finding(id="ospf_adjacency_down_unknown", title="OSPF adjacency not FULL, cause unknown",
                                    explains_outage=True, evidence_ids=base,
                                    observed={"states": [n["state"] for n in nbrs]}))
    return findings


class TroubleshootingAgent:
    name = "troubleshooting"

    def __init__(self, llm: LLM, network: Network, evidence: EvidenceStore, trace=None, sources=()):
        self.llm, self.net, self.ev, self.trace = llm, network, evidence, trace or (lambda *a: None)
        self.sources = list(sources)
        self.last_run = None

    def diagnose(self, task: str) -> tuple[list[Finding], str]:
        p = topology_params(self.net)
        extra = dict(as_tool(s) for s in self.sources)
        if extra:
            tools = ToolBox(self.net, self.ev, ALLOW + list(extra), agent=self.name, extra_tools=extra)
        else:
            tools = ToolBox(self.net, self.ev, ALLOW, agent=self.name)
        self.trace(self.name, "running the runbook: ping -> route -> neighbors -> BOTH ends -> interface -> logs -> control")
        got = run_runbook(tools, p)
        for name in extra:                                    # each extra evidence source is one more runbook step
            before = len(tools.calls)
            out = tools.call(name, {"device": p["device"]})
            if len(tools.calls) == before:                    # the source failed: say so, cite nothing
                self.trace(self.name, f"{name} gave no evidence: {out}")
                continue
            got[f"{name}:{p['device']}"] = tools.calls[-1]["ev"]
        found = detect(self.ev, got, p)
        detected = [{"id": f.id, "title": f.title, "explains_outage": f.explains_outage, "evidence_ids": f.evidence_ids,
                     "observed": f.observed} for f in found]
        evidence_text = "\n".join(self.ev.text(i, limit=600) for i in got.values())
        prompt = (f"{task}\n\nRunbook evidence:\n{evidence_text}\n\nDetectors found: {json.dumps(detected)}\n"
                  f"Rank them (the one that explains the outage first) and write one narrative line each.\n"
                  f"CONTEXT_JSON: {json.dumps({'detected': detected})}")
        ids = {f.id for f in found}

        def validate(a: dict) -> str | None:
            got_ids = [x.get("id") for x in a.get("findings", [])]
            if set(got_ids) != ids:
                return f"findings must be exactly {sorted(ids)}, got {got_ids}"
            bad = [e for x in a["findings"] for e in x.get("evidence_ids", []) if e not in self.ev]
            return f"unknown evidence ids {bad}" if bad else None

        run = run_agent(self.llm, role=self.name, system=SYSTEM, task=prompt, submit=SUBMIT, validate=validate,
                        trace=self.trace)
        self.last_run = run
        if run.submitted:
            order = [x["id"] for x in run.submitted["findings"]]
            notes = {x["id"]: x["narrative"] for x in run.submitted["findings"]}
            found = sorted(found, key=lambda f: order.index(f.id))
            for f in found:
                f.narrative = notes[f.id]
            return found, run.submitted["summary"]
        self.trace(self.name, f"no valid model answer ({run.stopped}) -> deterministic findings kept as detected")
        for f in found:
            f.narrative = f"{f.title} (deterministic detector)"
        return sorted(found, key=lambda f: not f.explains_outage), "deterministic diagnosis"

    def neighbor_evidence(self, device: str, peer: str) -> list[str]:
        """Blast-radius evidence: the neighbor tables on BOTH ends of the link."""
        tools = ToolBox(self.net, self.ev, ["ospf_neighbors"], agent=self.name)
        for d in (device, peer):
            tools.call("ospf_neighbors", {"device": d})
        return [c["ev"] for c in tools.calls]

    def handle(self, msg: Message) -> Message:
        if msg.payload.get("want") == "neighbor_evidence":
            ids = self.neighbor_evidence(msg.payload["device"], msg.payload["peer"])
            return Message(**{"from": self.name}, to=msg.from_, intent="diagnose", task=msg.task,
                           payload={"evidence_ids": ids}, status="done")
        findings, summary = self.diagnose(msg.task)
        return Message(**{"from": self.name}, to=msg.from_, intent="diagnose", task=msg.task,
                       payload={"findings": [f.model_dump() for f in findings], "summary": summary}, status="done")
