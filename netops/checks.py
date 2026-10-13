"""expected_post_state as code. A check names a read tool, where to run it, and what a passing result looks like:

    {name: "ospf neighbor state = FULL", tool: ospf_neighbors, expect: {interface: "{uplink}", state: full}}

The validator and the executor run the same checks for every vendor -- neither knows anything about OSPF."""
from __future__ import annotations

from typing import Any

READS = {
    "ospf_neighbors": lambda n, dev, a: n.ospf_neighbors(dev),
    "ospf_interface": lambda n, dev, a: n.ospf_interface(dev, a["interface"]),
    "interface": lambda n, dev, a: n.interface(dev, a["interface"]),
    "route": lambda n, dev, a: n.route(dev, a["prefix"]),
    "ping": lambda n, dev, a: n.ping(dev, a["destination"], a.get("source")),
}


def _fill(value: Any, ctx: dict) -> Any:
    return value.format(**ctx) if isinstance(value, str) else value


def _matches(obj: Any, expect: dict, ctx: dict) -> bool:
    return all(str(getattr(obj, k, None)).lower() == str(_fill(v, ctx)).lower() for k, v in expect.items())


def evaluate(net, check: dict, ctx: dict, evidence=None) -> tuple[bool, Any]:
    dev = ctx[check.get("on", "device")]
    args = {k: _fill(v, ctx) for k, v in check.get("args", {}).items()}
    result = READS[check["tool"]](net, dev, args)
    if evidence is not None:
        evidence.add(check["tool"], {"device": dev, **args}, result)
    items = result if isinstance(result, list) else [result]
    return any(_matches(i, check["expect"], ctx) for i in items), result


def _detail(check: dict, ctx: dict, result: Any, waited: float) -> str:
    """What the speaker script quotes: "5/5 after 9s" for a ping, "BRANCH-7 Ethernet1" for an interface check."""
    if hasattr(result, "received") and hasattr(result, "sent"):
        return f"{result.received}/{result.sent} after {waited:.0f}s"
    dev = ctx[check.get("on", "device")]
    if "interface" in check.get("expect", {}):
        return f"{dev} {_fill(check['expect']['interface'], ctx)}"
    return f"{dev} {check['tool']}"


def poll(net, checks: list[dict], ctx: dict, *, deadline_s: float, poll_s: float,
         evidence=None) -> tuple[list[dict], float]:
    """Run every check; repeat until all pass or the deadline passes. Real convergence takes seconds."""
    waited = 0.0
    while True:
        rows = []
        for c in checks:
            ok, result = evaluate(net, c, ctx, evidence)
            rows.append({"check": c["name"], "ok": ok, "detail": _detail(c, ctx, result, waited)})
        if all(r["ok"] for r in rows) or waited >= deadline_s:
            return rows, waited
        net.wait(poll_s)
        waited += poll_s
