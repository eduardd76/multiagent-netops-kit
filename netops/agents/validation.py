"""Validation specialist: independent, read-only, no ego in the fix.
  pre  -- before a human sees it: is the proposal exactly what the playbook allows? is the fault still live?
          is the blast radius backed by neighbor tables on BOTH ends?
  post -- after apply: poll the playbook's executable expected_post_state until it holds or the deadline passes.
          (Real cEOS: FULL arrives 3-9 s after the fix, the route 9-16 s. One immediate read would lie.)"""
from __future__ import annotations

from netops.agents.tools import ToolBox
from netops.checks import poll
from netops.evidence import EvidenceStore
from netops.network import Network
from netops.playbook import CommandGate, PlaybookError, load_playbook, render
from netops.protocol import Message

ALLOW = ["ospf_neighbors", "ospf_interface", "route", "ping"]


class ValidationAgent:
    name = "validation"

    def __init__(self, network: Network, evidence: EvidenceStore, trace=None, deadline_s: float = 60, poll_s: float = 3):
        self.net, self.ev, self.trace = network, evidence, trace or (lambda *a: None)
        self.deadline_s, self.poll_s = deadline_s, poll_s
        self.playbook = load_playbook()

    def _tools(self) -> ToolBox:
        return ToolBox(self.net, self.ev, ALLOW, agent=self.name)

    def pre_check(self, prop: dict) -> list[dict]:
        checks = []
        entry = self.playbook.get(prop["playbook_entry"])

        def add(name, ok, detail):
            checks.append({"check": name, "ok": bool(ok), "detail": detail})

        add("playbook_entry_exists", entry is not None, prop["playbook_entry"])
        if entry is None:
            return checks
        nos = prop.get("nos", "eos")
        _, rejected = CommandGate(entry.allowed_for(nos)).split(prop["commands"])
        add("commands_in_allowed_commands", not rejected, "all allowed" if not rejected else str([r.command for r in rejected]))
        try:
            same = render(entry, prop["params"], nos=nos) == prop["commands"]
        except PlaybookError as e:
            same = False
        add("commands_equal_playbook_render", same, "commands are exactly the rendered playbook fix")
        add("expected_post_state_matches", prop["expected_post_state"] == entry.expected_post_state,
            "; ".join(entry.expected_post_state))
        t = self._tools()
        dev, up = prop["device"], prop["params"]["uplink"]
        peer = self.net.uplink(dev)
        t.call("ospf_interface", {"device": dev, "interface": up})
        t.call("ospf_interface", {"device": peer["peer"], "interface": peer["peer_interface"]})
        local, remote = (self.ev.get(c["ev"]).result for c in t.calls[-2:])
        add("fault_still_present", local["area"] != remote["area"],
            f"{dev} {up} area {local['area']} vs {peer['peer']} area {remote['area']}")
        add("target_matches_neighbor", prop["params"]["expected_area"] == remote["area"],
            f"expected_area {prop['params']['expected_area']} vs neighbor {remote['area']}")
        cited = [i for i in prop.get("blast_radius_evidence_ids", []) if i in self.ev]
        seen = {self.ev.get(i).args.get("device") for i in cited if self.ev.get(i).tool == "ospf_neighbors"}
        need = {dev, peer["peer"]}
        add("blast_radius_evidenced", need <= seen,
            "neighbor tables on both ends cited" if need <= seen else
            f"no neighbor-table evidence for {sorted(need - seen)} -- what else rides on this link?")
        return checks

    def post_check(self, prop: dict) -> list[dict]:
        ctx = {**self.net.context(prop["device"]), **prop["params"]}
        rows, waited = poll(self.net, prop["post_checks"], ctx, deadline_s=self.deadline_s, poll_s=self.poll_s,
                            evidence=self.ev)
        self.trace(self.name, f"after {waited:.0f}s: " + "; ".join(
            f"{r['check']} {'PASS' if r['ok'] else 'FAIL'}" for r in rows))
        return rows

    def handle(self, msg: Message) -> Message:
        prop = msg.payload["proposal"]
        checks = self.pre_check(prop) if msg.payload.get("phase") == "pre" else self.post_check(prop)
        return Message(**{"from": self.name}, to=msg.from_, intent="validate", task=msg.task,
                       payload={"phase": msg.payload.get("phase", "post"), "checks": checks,
                                "passed": all(c["ok"] for c in checks)}, status="done")
