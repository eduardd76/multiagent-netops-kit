"""Type on a containerlab router from a notebook -- what an engineer would type, read-only.

    lab = ContainerLab("netops", vm="clab")       # vm: the OrbStack machine when containerlab runs in a VM
    lab.containers()                              # docker ps for this lab: the routers are real
    lab.cli("BRANCH-8", "show ip ospf neighbor")  # the router's own CLI (EOS Cli inside the container)

Only show and ping commands are allowed. The agents never use this: they read through Network and the tools.
"""
from __future__ import annotations

import subprocess

READ_ONLY = ("show ", "ping ")


class ContainerLab:
    def __init__(self, name: str, vm: str | None = None):
        self.name, self.vm = name, vm

    def _sh(self, cmd: str) -> str:
        argv = ["orb", "-m", self.vm, "bash", "-lc", cmd] if self.vm else ["bash", "-lc", cmd]
        return subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout

    def container(self, router: str) -> str:
        """BRANCH-7 -> clab-netops-branch7 (containerlab names containers clab-<lab>-<node>)."""
        return f"clab-{self.name}-{router.lower().replace('-', '')}"

    def containers(self) -> None:
        out = self._sh("docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'")
        print("\n".join(l for l in out.splitlines() if l.startswith(("NAMES", f"clab-{self.name}-"))) + "\n")

    def cli(self, router: str, command: str) -> None:
        if not command.startswith(READ_ONLY):
            raise ValueError(f"read-only: only show and ping commands, not {command!r}")
        out = self._sh(f"docker exec {self.container(router)} Cli -p 15 -c '{command}'")
        if command.startswith("show ip route"):          # drop the route-code legend, keep the answer
            out = "\n\n".join(b for b in out.split("\n\n") if "Source Codes" not in b)
        if command.startswith("ping"):                   # keep the verdict: transmitted / received / loss
            out = "\n".join(l for l in out.splitlines() if "packets transmitted" in l)
        print(f"{router}# {command}\n{out.strip() or '(nothing)'}\n")
