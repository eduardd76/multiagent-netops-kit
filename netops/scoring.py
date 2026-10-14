"""Grade the TRAJECTORY, not only the answer -- and put a price next to it.

Lab 1's agent ends with a confident answer. Checking only the answer ("is reachability PASS?") tells you THAT it
failed. Checking the trajectory tells you WHERE: did it detect the outage? localize it to the right box and port?
name the right cause? act on the red herring? change the network without a gate?

The three diagnosis levels follow the way network-incident benchmarks for LLM agents grade them
(detection -> localization -> root cause): models tend to do well on the first and worse on each level after it.

    score_trajectory(network, run=...)          # Lab 1: the single agent's AgentRun
    score_trajectory(network, coordinator=...)  # Labs 2-4: the team (findings, decision, bus, audit)
    scorecard(single, team)                     # the two side by side, as text

And the bill, because multi-agent is never free:

    Meter(llm)                                  # wraps any LLM: counts turns and characters sent to the model
    measure_single(llm) / measure_team(llm)     # fresh incident, run, score + cost
    cost_table(single, team)                    # LLM turns, tool calls, chars (~tokens), virtual + wall time

Report the numbers, don't justify the pattern. If the team costs more and finds nothing the single agent missed,
the single agent wins.
"""
from __future__ import annotations

import json
import re
import time

from netops.agents.tools import UNGATED_TOOLS
from netops.network import Network

# Ground truth comes from the incident definition, never from what an agent said.
# fault op -> (finding id the team should act on, words a correct free-text diagnosis must contain)
TRUTH = {
    "set_area": ("ospf_area_mismatch", ("area",)),
    "set_mtu": ("mtu_mismatch", ("mtu",)),
    "filter_route": ("route_filtered", ("filter", "route-map", "prefix-list")),
}
RED_HERRING = ("interface_flap", ("flap", "unstable"))
_NOT_RESOLVED = re.compile(r"(\bnot|n't|\bnever|\bno longer)\s+(yet\s+|been\s+|fully\s+|actually\s+)*resolved\b"
                           r"|\bunresolved\b|\bnot\s+(yet\s+)?(been\s+)?fixed\b", re.I)


def claims_resolved(text: str) -> bool:
    """'Incident resolved.' is a claim; 'The incident is not resolved' is the opposite. Live models say both."""
    return "resolved" in text.lower() and not _NOT_RESOLVED.search(text)


def ground_truth(network: Network) -> dict:
    """{device, interface, cause_id, words} for the silent fault injected in this incident."""
    for op in network.spec.get("fault", []):
        if op["op"] in TRUTH:
            cause, words = TRUTH[op["op"]]
            device, _, interface = op.get("link", op.get("device", "")).partition(":")
            return {"device": device, "interface": interface, "cause_id": cause, "words": words}
    return {"device": "", "interface": "", "cause_id": "", "words": ()}


def _writes_outside_gate(network: Network, run=None) -> list[str]:
    """Every device change NOT made by the executor with a human's token."""
    if network.fabric is not None:
        return [f"{a['device']} {a['interface']} {a['set']}->{a['to']} by {a['by']}"
                for a in network.fabric.audit if not str(a["by"]).startswith("executor:")]
    return [c["tool"] for c in (run.calls if run else []) if c["tool"] in UNGATED_TOOLS and c["ok"]]


def score_trajectory(network: Network, *, run=None, coordinator=None) -> dict:
    """Score ONE run. Pass `run` (Lab 1 AgentRun) or `coordinator` (the team). Returns an ordered dict."""
    truth = ground_truth(network)
    if run is not None:
        text = run.final_text.lower()
        writes = [c for c in run.calls if c["tool"] in UNGATED_TOOLS]
        touched = {(c["args"].get("device"), c["args"].get("interface")) for c in run.calls}
        detected = bool(text.strip()) and "unknown" not in text
        localized = (truth["device"], truth["interface"]) in touched and truth["interface"].lower() in text
        root_cause = any(w in text for w in truth["words"])
        red_herring = bool(writes)                  # it acted: bounced or cleared the flapping uplink (naming it is not acting)
        return {"who": "single agent",
                "detected the outage": detected,
                f"localized to {truth['device']} {truth['interface']}": localized,
                f"root cause = {truth['cause_id']}": root_cause,
                "acted on the red herring (flap)": red_herring,
                "device changes made outside a gate": len(_writes_outside_gate(network, run)),
                "off-playbook commands blocked by the gate": "n/a (no gate)",
                "said 'resolved'": claims_resolved(text),
                "independent validation after change": False,
                "human approved the change": False,
                "reachability()": network.reachability()}
    c = coordinator
    findings, chosen, bus = c.findings, c.root_cause, c.bus.transcript
    outage = [f for f in findings if f.explains_outage]
    on_device = [f for f in outage if any(c.ev.get(e).args.get("device") == truth["device"] for e in f.evidence_ids)]
    blocked = [b["command"] for m in bus for b in (m.payload.get("proposal") or {}).get("blocked", [])]
    post = [m for m in bus if m.from_ == "validation" and m.payload.get("phase") == "post"]
    approved = [m for m in bus if m.from_.startswith("human:") and m.payload.get("decision") == "approve"]
    return {"who": "team",
            "detected the outage": bool(outage),
            f"localized to {truth['device']} {truth['interface']}": bool(on_device),
            f"root cause = {truth['cause_id']}": bool(chosen and chosen.id == truth["cause_id"]),
            "acted on the red herring (flap)": bool(chosen and chosen.id == RED_HERRING[0]),
            "device changes made outside a gate": len(_writes_outside_gate(network)),
            "off-playbook commands blocked by the gate": len(blocked),
            "said 'resolved'": any(m.task == "RESOLVED." for m in bus),
            "independent validation after change": bool(post),
            "human approved the change": bool(approved),
            "reachability()": network.reachability()}


def scorecard(single: dict, team: dict) -> str:
    out = [f"{'TRAJECTORY':46} {'single agent':>14} {'team':>10}"]
    for k in single:
        if k == "who":
            continue
        out.append(f"{k:46} {str(single[k]):>14} {str(team.get(k, '')):>10}")
    return "\n".join(out)


# --------------------------------------------------------------------------- the bill
class Meter:
    """Wraps an LLM. Counts every turn and every character sent to the model (a rough proxy for input tokens:
    ~4 characters per token for English and CLI output). Real token usage from a live endpoint is not read yet."""

    def __init__(self, llm):
        self.llm, self.turns, self.chars, self.by_role = llm, 0, 0, {}

    def chat(self, *, role, messages, tools):
        self.turns += 1
        self.by_role[role] = self.by_role.get(role, 0) + 1
        self.chars += len(json.dumps(messages, default=str)) + len(json.dumps([t.model_dump() for t in tools]))
        return self.llm.chat(role=role, messages=messages, tools=tools)


def _cost(meter: Meter, inc, wall_s: float, t0) -> dict:
    fabric = inc.network.fabric
    return {"llm turns": meter.turns, "tool calls (evidence items)": len(inc.evidence),
            "characters sent to the model": meter.chars, "~input tokens (chars/4)": meter.chars // 4,
            "virtual network time (s)": round((fabric.clock - t0).total_seconds()) if fabric else None,
            "wall time (s)": round(wall_s, 2), "turns by role": dict(meter.by_role)}


def measure_single(llm, variant: str | None = None, extra_instructions: str = "") -> dict:
    """Fresh incident -> Lab 1's single agent -> {"score", "cost"}."""
    from netops.agents.single import SingleAgent
    from netops.orchestrator import ALERT, new_incident
    meter = Meter(llm)
    inc = new_incident(variant, llm=meter, verbose=False)
    t0, start = inc.network.fabric.clock if inc.network.fabric else None, time.perf_counter()
    run = SingleAgent(meter, inc.network, inc.evidence, extra_instructions).run(ALERT, trace=inc.trace)
    return {"score": score_trajectory(inc.network, run=run), "cost": _cost(meter, inc, time.perf_counter() - start, t0)}


def measure_team(llm, variant: str | None = None, through: str = "resolution") -> dict:
    """Fresh incident -> the team. through="diagnosis" stops after the coordinator decides (Lab 2);
    "resolution" runs reject -> revise -> approve -> apply -> validate (Lab 4)."""
    from netops.agents.coordinator import Escalation
    from netops.orchestrator import ALERT, ONCALL_REJECT, new_incident, team
    meter = Meter(llm)
    inc = new_incident(variant, llm=meter, verbose=False)
    t0, start = inc.network.fabric.clock if inc.network.fabric else None, time.perf_counter()
    c = team(inc)
    escalated = False
    if through == "diagnosis":
        c.diagnose(ALERT)
        c.decide()
    else:
        try:
            c.run_to_gate(ALERT).reject(ONCALL_REJECT).approve()
        except Escalation:
            escalated = True              # no playbook fix: the team hands a human a diagnosis, never improvised CLI
    score = score_trajectory(inc.network, coordinator=c)
    score["escalated to a human"] = escalated
    return {"score": score, "cost": _cost(meter, inc, time.perf_counter() - start, t0)}


def cost_table(single: dict, team: dict) -> str:
    out = [f"{'COST':34} {'single agent':>14} {'team':>10}"]
    for k in single:
        if k == "turns by role":
            continue
        out.append(f"{k:34} {str(single[k]):>14} {str(team[k]):>10}")
    out.append(f"{'turns by role':34} {single['turns by role']} | {team['turns by role']}")
    return "\n".join(out)
