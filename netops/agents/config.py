"""Config specialist: matches the diagnosis to a PLAYBOOK entry and proposes it. Never applies.
Commands are rendered from the playbook; anything else the model suggests is blocked before proposal."""
from __future__ import annotations

import json

from netops.agents.loop import run_agent
from netops.agents.troubleshooting import Finding
from netops.evidence import EvidenceStore
from netops.llm import LLM, ToolSpec
from netops.network import Network
from netops.playbook import CommandGate, PlaybookError, load_playbook, render
from netops.protocol import Message

SYSTEM = """ROLE: change author in a NOC team. You PROPOSE; you never apply.
YOU OWN: choosing the playbook entry that fixes the diagnosed root cause, and its parameters.
YOU MAY NOT: write device CLI -- commands come from the playbook only.
RULES: the expected value must be what the neighbor actually runs (cite evidence). State the blast radius and
cite evidence for it if you have any. If a reviewer rejected a previous version, address every reason."""

SUBMIT = ToolSpec(name="submit_proposal", description="Propose ONE playbook entry with its parameters.",
                  parameters={"type": "object", "properties": {
                      "playbook_entry": {"type": "string"},
                      "params": {"type": "object", "properties": {"uplink": {"type": "string"},
                                                                  "expected_area": {"type": "string"}}},
                      "rationale": {"type": "string"}, "blast_radius": {"type": "string"},
                      "blast_radius_evidence_ids": {"type": "array", "items": {"type": "string"}},
                      "extra_commands": {"type": "array", "items": {"type": "string"},
                                         "description": "anything else you think should be run (will be gated)"}},
                      "required": ["playbook_entry", "params", "rationale", "blast_radius"]})


class ConfigAgent:
    name = "config"

    def __init__(self, llm: LLM, network: Network, evidence: EvidenceStore, trace=None):
        self.llm, self.net, self.ev, self.trace = llm, network, evidence, trace or (lambda *a: None)
        self.playbook = load_playbook()

    def propose(self, finding: Finding, *, device: str | None = None, version: int = 1, revision_note: str = "",
                neighbor_evidence_ids: list[str] | None = None) -> dict:
        device = device or self.net.affected
        nos = self.net.nos(device)
        ctx = {"observed": finding.observed, "neighbor_evidence_ids": neighbor_evidence_ids or [],
               "playbook_entries": [e for e, v in self.playbook.items() if v.root_cause]}
        lines = [f"Root cause from troubleshooting: {finding.title}", f"Observed: {json.dumps(finding.observed)}",
                 "Evidence:"] + [self.ev.text(i, limit=600) for i in finding.evidence_ids + (neighbor_evidence_ids or [])]
        if revision_note:
            lines.append(f"Version {version - 1} was REJECTED by the on-call engineer: {revision_note}")
        lines.append(f"CONTEXT_JSON: {json.dumps(ctx)}")

        def validate(a: dict) -> str | None:
            e = self.playbook.get(a.get("playbook_entry", ""))
            if e is None or not e.root_cause:
                return f"playbook_entry must be one of {ctx['playbook_entries']}"
            try:
                render(e, a.get("params", {}), nos=nos)
            except PlaybookError as err:
                return str(err)
            return None

        run = run_agent(self.llm, role=self.name, system=SYSTEM, task="\n".join(lines), submit=SUBMIT,
                        validate=validate, trace=self.trace)
        sub = run.submitted or {}
        entry = self.playbook[sub.get("playbook_entry", finding.id)]
        # Code, not the model, has the last word on parameters: they must match the evidence.
        params = {"uplink": finding.observed["uplink"], "expected_area": finding.observed["peer_area"]}
        corrected = sub and sub.get("params") != params
        commands = render(entry, params, nos=nos)
        rollback_params = {"uplink": params["uplink"], "current_area": finding.observed["local_area"]}
        rollback = render(entry, rollback_params, "rollback", nos=nos)
        if corrected:
            self.trace(self.name, f"model parameters {sub.get('params')} corrected to the evidence: {params}")
        _, blocked = CommandGate(entry.allowed_for(nos)).split(sub.get("extra_commands", []))
        for b in blocked:
            self.trace(self.name, f"BLOCKED before proposal: '{b.command}' ({b.reason})")
        return {"version": version, "device": device, "nos": nos, "playbook_entry": entry.id, "params": params,
                "commands": commands, "rollback": rollback, "rollback_params": rollback_params,
                "expected_post_state": entry.expected_post_state,
                "post_checks": [c.model_dump() for c in entry.post_checks],
                "diagnosis": finding.title, "rationale": sub.get("rationale", "deterministic: model output invalid"),
                "blast_radius": sub.get("blast_radius") or "(model gave no blast-radius statement)",
                # Evidence gathered by code is always attached; the model can only ADD valid citations.
                "blast_radius_evidence_ids": list(dict.fromkeys(
                    (neighbor_evidence_ids or []) +
                    [i for i in sub.get("blast_radius_evidence_ids", []) if i in self.ev])),
                "blocked": [b.model_dump() for b in blocked], "params_corrected": bool(corrected)}

    def handle(self, msg: Message) -> Message:
        finding = Finding(**msg.payload["finding"])
        prop = self.propose(finding, device=msg.payload.get("device"), version=msg.payload.get("version", 1),
                            revision_note=msg.payload.get("revision_note", ""),
                            neighbor_evidence_ids=msg.payload.get("neighbor_evidence_ids"))
        return Message(**{"from": self.name}, to=msg.from_, intent="propose", task=msg.task,
                       payload={"proposal": prop}, status="needs_human")
