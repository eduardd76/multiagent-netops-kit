"""The ONLY component that writes in team mode. Not an AI. It needs a human's approval token,
applies exactly the approved commands, and backs out automatically if the playbook's backout checks don't pass in time."""
from __future__ import annotations

from typing import Callable

from netops.approval import ApprovalToken, Approvals, GateError
from netops.audit_emit import emit
from netops.checks import READS, evaluate
from netops.network import Network
from netops.playbook import PlaybookError, render
from netops.ports import AuditEvent


def default_backout_triggered(full: bool, elapsed_s: float, timer_s: float) -> bool:
    return (not full) and elapsed_s >= timer_s


class Executor:
    def __init__(self, network: Network, approvals: Approvals, backout_s: float = 60, poll_s: float = 3,
                 backout_triggered: Callable[[bool, float, float], bool] = default_backout_triggered, *,
                 allowed_devices: set[str] | None = None, playbook: dict | None = None,
                 recheck: Callable[[dict], list[dict]] | None = None, audit=None):
        self.net, self.approvals, self.backout_s, self.poll_s = network, approvals, backout_s, poll_s
        self.backout_triggered = backout_triggered
        self.allowed_devices, self.playbook, self.recheck, self.audit = allowed_devices, playbook, recheck, audit

    def _refuse_unless_safe(self, proposal: dict) -> None:
        """Hardened mode: the token is not enough. Re-derive the change and re-check the world first."""
        dev = proposal["device"]
        if self.allowed_devices is not None and dev not in self.allowed_devices:
            raise GateError(f"{dev} is not on the lab allowlist -- refusing to write")
        if self.playbook is not None:
            entry = self.playbook[proposal["playbook_entry"]]
            nos = self.net.nos(dev)                          # the device's real NOS, never the proposal's claim
            if (proposal.get("nos") != nos
                    or render(entry, proposal["params"], nos=nos) != proposal["commands"]
                    or proposal.get("post_checks") != [c.model_dump() for c in entry.post_checks]):
                raise GateError("the proposal differs from the re-rendered playbook fix -- refusing to write")
            self._refuse_unless_rollback_rerenders(entry, proposal, nos)
        if self.recheck is not None:
            failing = [c["check"] for c in self.recheck(proposal) if not c["ok"]]
            if failing:
                raise GateError(f"pre-checks fail at apply time ({', '.join(failing)}) -- refusing to write")

    @staticmethod
    def _refuse_unless_rollback_rerenders(entry, proposal: dict, nos: str) -> None:
        """The executor owns the rollback, so it runs only what the playbook renders -- gated, same interface."""
        rp = proposal.get("rollback_params")
        try:
            same = (isinstance(rp, dict) and rp.get("uplink") == proposal["params"].get("uplink")
                    and render(entry, rp, "rollback", nos=nos) == proposal["rollback"])
        except PlaybookError:
            same = False
        if not same:
            raise GateError("the proposal's rollback differs from the re-rendered playbook rollback -- refusing to write")

    def _audit(self, kind: str, actor: str, dev: str, commands: list[str]) -> None:
        if self.audit is not None:
            emit(self.audit, AuditEvent(kind, actor, dev, {"commands": commands}))

    def apply(self, proposal: dict, token: ApprovalToken | None) -> dict:
        self._refuse_unless_safe(proposal)
        watch = [c for c in proposal.get("post_checks", []) if c.get("backout")]
        if not watch:                                        # refuse before the token is spent or anything is touched
            raise GateError("proposal has no backout check -- the executor can't own its rollback")
        unknown = sorted({c["tool"] for c in watch if c["tool"] not in READS})
        if unknown:
            raise GateError(f"backout check uses unknown read tool(s) {unknown}")
        self.approvals.consume(token, proposal)              # raises before anything is touched
        dev = proposal["device"]
        self.net.configure(dev, proposal["commands"], by=f"executor:{token.approver}")
        self._audit("change_applied", f"executor:{token.approver}", dev, proposal["commands"])
        waited = 0.0
        try:
            ctx = {**self.net.context(dev), **proposal["params"]}
            while True:
                ok = all(evaluate(self.net, c, ctx)[0] for c in watch)
                if ok:
                    return {"applied": proposal["commands"], "rolled_back": False, "waited_s": waited}
                if self.backout_triggered(ok, waited, self.backout_s) or waited >= self.backout_s * 5:
                    break
                self.net.wait(self.poll_s)
                waited += self.poll_s
        except BaseException:                                # a check we cannot evaluate must not leave the change in place
            self.net.configure(dev, proposal["rollback"], by="executor:auto-backout")
            self._audit("change_rolled_back", f"executor:{token.approver}", dev, proposal["rollback"])
            raise
        self.net.configure(dev, proposal["rollback"], by="executor:auto-backout")
        self._audit("change_rolled_back", f"executor:{token.approver}", dev, proposal["rollback"])
        return {"applied": proposal["commands"], "rolled_back": True, "waited_s": waited}
