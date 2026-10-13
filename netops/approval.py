"""Human approval as code: a single-use token bound to the EXACT proposal, minted only on a human's action.

The Executor refuses to apply anything without a valid token. If anyone edits the proposal after approval,
its digest changes and the token no longer fits. A used token can never be used again.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from netops.audit_emit import emit
from netops.ports import AuditEvent


class GateError(PermissionError):
    pass


def digest_of(proposal: dict) -> str:
    return hashlib.sha256(json.dumps(proposal, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ApprovalToken:
    digest: str
    approver: str
    run_id: str
    expiry: float
    mac: str = field(repr=False)
    tenant: str = "default"
    device: str = ""
    change_id: str = ""

    def __repr__(self) -> str:
        return f"ApprovalToken(approver={self.approver!r}, digest={self.digest[:8]}..., mac=[redacted])"

    __str__ = __repr__


class Approvals:
    def __init__(self, ttl_s: int = 900, clock: Callable[[], float] = time.time, secret: bytes | None = None,
                 run_id: str | None = None, audit=None):
        self._secret = secret or secrets.token_bytes(32)
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self._ttl, self._clock = ttl_s, clock
        self._used: set[str] = set()
        self.log: list[dict] = []
        self.audit = audit

    def _mac(self, t_digest: str, approver: str, run_id: str, expiry: float, tenant: str, device: str,
             change_id: str) -> str:
        msg = f"{t_digest}|{approver}|{run_id}|{expiry!r}|{tenant}|{device}|{change_id}"
        return hmac.new(self._secret, msg.encode(), hashlib.sha256).hexdigest()

    def approve(self, proposal: dict, approver: str, *, change_id: str = "", tenant: str = "default") -> ApprovalToken:
        d, exp, dev = digest_of(proposal), self._clock() + self._ttl, proposal.get("device", "")
        entry = {"event": "approved", "approver": approver, "digest": d[:12]}
        if change_id:
            entry["change_id"] = change_id
        self.log.append(entry)
        if self.audit is not None:
            emit(self.audit, AuditEvent("approved", approver, dev, {"digest": d[:12], "change_id": change_id}))
        return ApprovalToken(d, approver, self.run_id, exp, self._mac(d, approver, self.run_id, exp, tenant, dev,
                                                                        change_id), tenant, dev, change_id)

    def consume(self, token: ApprovalToken | None, proposal: dict) -> None:
        if not isinstance(token, ApprovalToken):
            raise GateError("no approval: a human must approve this change first")
        if not hmac.compare_digest(self._mac(token.digest, token.approver, token.run_id, token.expiry, token.tenant, token.device,
                                      token.change_id), token.mac):
            raise GateError("invalid approval signature")
        if token.run_id != self.run_id:
            raise GateError("approval belongs to a different run")
        if token.digest != digest_of(proposal):
            raise GateError("the proposal changed after it was approved")
        if token.device != proposal.get("device", ""):
            raise GateError("approval is for a different device")
        if self._clock() > token.expiry:
            raise GateError("approval expired")
        if token.mac in self._used:
            raise GateError("approval already used")
        self._used.add(token.mac)
        self.log.append({"event": "consumed", "approver": token.approver})
        if self.audit is not None:
            emit(self.audit, AuditEvent("consumed", token.approver, token.device, {"change_id": token.change_id}))
