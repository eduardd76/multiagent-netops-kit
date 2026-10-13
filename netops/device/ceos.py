"""CeosDevice -- a real Arista cEOS (or EOS) over eAPI (JSON-RPC over HTTP). Standard library only.

Same DeviceDriver interface as SimulatedDevice, same commands, same JSON -> the SAME agent code runs unchanged.
Configuration goes through a configure session + commit, so a change applies atomically.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request
import uuid
from typing import Callable, Literal

from netops.device.driver import CommandError, ConfigResult

Transport = Callable[[dict], dict]       # takes a JSON-RPC request, returns the JSON-RPC response


class CeosDevice:
    nos = "eos"

    def __init__(self, hostname: str, host: str, username: str = "admin", password: str = "admin",
                 port: int = 80, https: bool = False, timeout: float = 15, transport: Transport | None = None):
        self.hostname = hostname
        if ":" in host:                                   # "clab.orb.local:8011" style
            host, port = host.rsplit(":", 1)[0], int(host.rsplit(":", 1)[1])
        self.url = f"{'https' if https else 'http'}://{host}:{port}/command-api"
        self._auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.timeout = timeout
        self._transport = transport or self._http

    def _http(self, request: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(request).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Basic {self._auth}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def _rpc(self, cmds: list[str], fmt: str) -> list[dict]:
        # eAPI sessions start unprivileged; ping-with-source and config sessions need `enable` (verified on 4.34.8M).
        request = {"jsonrpc": "2.0", "method": "runCmds", "id": uuid.uuid4().hex[:8],
                   "params": {"version": 1, "cmds": ["enable", *cmds], "format": fmt}}
        response = self._transport(request)
        if "error" in response:
            err = response["error"]
            details = [d.get("errors") for d in err.get("data", []) if isinstance(d, dict) and d.get("errors")]
            raise CommandError(f"{self.hostname}: {err.get('message')} {details or ''}".strip())
        return response["result"][1:]                     # drop the result of `enable`

    def run(self, cmds: list[str], fmt: Literal["json", "text"] = "json") -> list[dict]:
        return self._rpc(cmds, fmt)

    def configure(self, cmds: list[str], *, by: str = "operator") -> ConfigResult:
        session = f"netops-{uuid.uuid4().hex[:6]}"
        self._rpc([f"configure session {session}", *cmds, "commit"], "json")
        return ConfigResult(device=self.hostname, applied=list(cmds), by=by)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
