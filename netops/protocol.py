"""The ONE message every agent sends and receives.

    { from, to, intent: diagnose|propose|validate, task, payload, status: requested|done|needs_human }

(If you know Google's Agent2Agent protocol: this is a tiny cousin. `needs_human` plays the role of A2A's
`input-required` state -- the task is paused until a person decides.)
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["diagnose", "propose", "validate"]
Status = Literal["requested", "done", "needs_human"]


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    from_: str = Field(alias="from")
    to: str
    intent: Intent
    task: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Status
    reply_to: str | None = None

    def dump(self) -> dict:
        return self.model_dump(by_alias=True, mode="json")


class TokenLeak(ValueError):
    """Approval tokens are handed to the Executor directly; they never travel in a message."""


def _scrub(obj: Any) -> None:
    from netops.approval import ApprovalToken          # local import: approval depends on nothing here
    if isinstance(obj, ApprovalToken):
        raise TokenLeak("approval tokens never travel in messages")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("token", "mac"):
                raise TokenLeak(f"refusing to carry a field named {k!r}")
            _scrub(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _scrub(v)


Handler = Callable[[Message], "Message | None"]


class Bus:
    """Delivers messages to registered agents and keeps the full transcript (the 'conversation on screen')."""

    def __init__(self, audit=None):
        self.handlers: dict[str, Handler] = {}
        self.transcript: list[Message] = []
        self.audit = audit

    def _log(self, msg: Message) -> None:
        self.transcript.append(msg)
        if self.audit is not None:
            from netops.audit_emit import emit
            from netops.ports import AuditEvent
            emit(self.audit, AuditEvent("message", msg.from_, "", {"to": msg.to, "intent": msg.intent,
                                                                   "status": msg.status, "task": msg.task}))

    def register(self, name: str, handler: Handler) -> None:
        self.handlers[name] = handler

    def send(self, msg: Message) -> Message | None:
        _scrub(msg.payload)
        self._log(msg)
        handler = self.handlers.get(msg.to)
        if handler is None:
            return None
        reply = handler(msg)
        if reply is not None:
            _scrub(reply.payload)
            reply.reply_to = msg.id
            self._log(reply)
        return reply
