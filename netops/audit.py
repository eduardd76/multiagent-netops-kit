# kit/netops/audit.py
"""Where the record of every action goes: each message, each approval event, each device change.
The decision record is the product -- this is what an auditor reads.

A sink is anything with record(event). MockServiceNowIncident keeps its data in `.record`, so its sink method
is record_event(); netops.audit_emit.emit() calls whichever one a sink has."""
from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from netops.audit_emit import emit
from netops.channels import MOCK_LABEL
from netops.ports import AuditEvent


def _identity(t: str) -> str:
    return t


class MemoryAudit:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class JsonlAudit:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: AuditEvent) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(event), default=str) + "\n")


class Fanout:
    def __init__(self, sinks):
        self.sinks = list(sinks)

    def record(self, event: AuditEvent) -> None:
        for s in self.sinks:
            emit(s, event)


def _line(e: AuditEvent, show) -> str:
    if e.kind == "message":
        d = e.detail
        return show(f"{e.actor} -> {d['to']}  {d['intent']}/{d['status']}  {d['task']}")
    if e.kind in ("change_applied", "change_rolled_back"):
        return show(f"{e.kind} on {e.device} by {e.actor}: " + " / ".join(e.detail.get("commands", [])))
    return show(f"{e.kind} by {e.actor} " + " ".join(f"{k}={v}" for k, v in e.detail.items() if v))


class MockServiceNowIncident:
    """A ServiceNow incident record whose work_notes are the audit trail."""

    def __init__(self, skin=None, number: str = "INC0010001"):
        self.show = skin.display if skin is not None else _identity
        self.record = {"number": number, "short_description": "", "state": "in_progress", "work_notes": [],
                       "u_source": MOCK_LABEL.format(system="ServiceNow")}

    def record_event(self, event: AuditEvent) -> None:
        r = self.record
        r["work_notes"].append(_line(event, self.show))
        if event.kind == "message" and not r["short_description"]:
            r["short_description"] = self.show(event.detail["task"])[:160]
        if event.kind == "change_applied":
            r["state"] = "resolved"


class MockConfluencePage:
    """The decision record as one Confluence page (REST v1 create-page payload, storage format)."""

    def __init__(self, skin=None, space: str = "NETOPS"):
        self.show = skin.display if skin is not None else _identity
        self.space, self.events = space, []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def page(self, title: str = "Decision record") -> dict:
        rows = "".join(f"<tr><td>{html.escape(e.kind)}</td><td>{html.escape(self.show(e.actor))}</td>"
                       f"<td>{html.escape(_line(e, self.show))}</td></tr>" for e in self.events)
        value = (f'<ac:structured-macro ac:name="info"><ac:rich-text-body><p>'
                 f'{html.escape(MOCK_LABEL.format(system="Confluence"))}</p></ac:rich-text-body></ac:structured-macro>'
                 f"<h2>{html.escape(title)}</h2><table><tbody><tr><th>event</th><th>who</th><th>what</th></tr>"
                 f"{rows}</tbody></table>")
        return {"type": "page", "title": title, "space": {"key": self.space},
                "body": {"storage": {"value": value, "representation": "storage"}}}
