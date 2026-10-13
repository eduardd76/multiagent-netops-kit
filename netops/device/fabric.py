"""The incident as a state machine (the "physics" behind the simulated switches).

Truth table, kept deliberately small and technically correct:
  * An OSPF adjacency can form only if both ends are up, not passive, in the SAME area, with the
    SAME hello/dead timers. Area mismatch => hellos are dropped => the neighbor is ABSENT
    (verified on cEOS 4.34.8M). MTU mismatch => the neighbor is stuck in exchStart (that's MTU, not area).
  * A compatible adjacency becomes FULL `full_after_s` after the link/config settles, and routes
    learned over it install `route_after_full_s` later (SPF hold) -- the real "FULL but no route yet" window.
  * A device reaches the service prefix iff it originates it, or it has a FULL adjacency whose routes
    have installed to a hub that originates it (and the route isn't filtered).

Logs are produced BY state transitions (never hand-scripted): flaps before the area change recover
(adjacency re-established), flaps after it never do. The absence of recovery is the real tell.
"""
from __future__ import annotations

import ipaddress
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

import yaml


def load_incident(variant: str | None = None) -> dict:
    """Load the incident definition (optionally a variant that replaces the fault list)."""
    with resources.files("netops").joinpath("data", "incident.yaml").open() as f:
        spec = yaml.safe_load(f)
    if variant:
        spec["fault"] = spec["variants"][variant]["fault"]
        spec["variant"] = variant
    return spec


@dataclass
class Port:
    """One end of a point-to-point link."""
    device: str
    name: str
    ip: str
    peer_device: str
    peer_port: str
    peer_ip: str
    description: str
    area: str
    hello: int
    dead: int
    mtu: int = 1500
    passive: bool = False
    admin_up: bool = True
    oper_up: bool = True
    link_status_changes: int = 0
    in_errors: int = 0
    last_change: datetime | None = None


@dataclass
class LinkTiming:
    """When the adjacency on a link became/will become FULL, and when its routes install."""
    full_at: datetime | None
    route_at: datetime | None


@dataclass
class LogEntry:
    ts: datetime
    device: str
    process: str      # "Ebra", "Ospf", "ConfigAgent" -- as cEOS prints them
    text: str
    category: str     # LINK / OSPF / CONFIG


class Fabric:
    """All simulated devices share one fabric: links, timing, logs and a virtual clock."""

    def __init__(self, variant: str | None = None, inject: bool = True):
        self.spec: dict[str, Any] = load_incident(variant)
        self.rng = random.Random(self.spec["seed"])
        self.start = datetime.fromisoformat(self.spec["start_time"])
        self.clock = self.start
        self.conv = self.spec["convergence"]
        self.ports: dict[tuple[str, str], Port] = {}
        self.timing: dict[frozenset, LinkTiming] = {}
        self.logs: dict[str, list[LogEntry]] = {d: [] for d in self.spec["devices"]}
        self.route_filters: set[str] = set()       # devices whose inbound service route is filtered
        self.saved: dict[str, bool] = {d: True for d in self.spec["devices"]}
        self.audit: list[dict] = []                # every configuration change, who made it, when
        self._build_links()
        if inject:
            self._inject_faults()

    # ------------------------------------------------------------------ topology
    def _build_links(self) -> None:
        t = self.spec["timers"]
        long_ago = self.start - timedelta(days=30)
        for link in self.spec["links"]:
            (ad, ap), (bd, bp) = link["a"].split(":"), link["b"].split(":")
            net = ipaddress.ip_network(link["subnet"])
            aip, bip = str(net.network_address), str(net.network_address + 1)
            self.ports[(ad, ap)] = Port(ad, ap, aip, bd, bp, bip, link["a_description"], link["area"],
                                        t["hello"], t["dead"], last_change=long_ago)
            self.ports[(bd, bp)] = Port(bd, bp, bip, ad, ap, aip, link["b_description"], link["area"],
                                        t["hello"], t["dead"], last_change=long_ago)
            self.timing[frozenset({(ad, ap), (bd, bp)})] = LinkTiming(full_at=long_ago, route_at=long_ago)

    def port(self, device: str, name: str) -> Port:
        try:
            return self.ports[(device, name)]
        except KeyError:
            raise KeyError(f"{device} has no interface {name}") from None

    def peer(self, p: Port) -> Port:
        return self.ports[(p.peer_device, p.peer_port)]

    def ports_of(self, device: str) -> list[Port]:
        return [p for (d, _), p in self.ports.items() if d == device]

    def _key(self, p: Port) -> frozenset:
        return frozenset({(p.device, p.name), (p.peer_device, p.peer_port)})

    # ------------------------------------------------------------------ protocol truth
    def compatible(self, p: Port) -> bool:
        """Can these two ends form an adjacency at all (ignoring time)? MTU is checked separately."""
        q = self.peer(p)
        return (p.oper_up and q.oper_up and not p.passive and not q.passive
                and p.area == q.area and p.hello == q.hello and p.dead == q.dead)

    def adjacency_state(self, p: Port) -> str | None:
        """None = no neighbor entry at all (area/timer mismatch, link down)."""
        if not self.compatible(p):
            return None
        if p.mtu != self.peer(p).mtu:
            return "exchStart"
        t = self.timing[self._key(p)]
        if t.full_at is not None and self.clock >= t.full_at:
            return "full"
        return "init"

    def routes_installed(self, p: Port) -> bool:
        t = self.timing[self._key(p)]
        return self.adjacency_state(p) == "full" and t.route_at is not None and self.clock >= t.route_at

    def originates(self, device: str, prefix: str) -> bool:
        dev = self.spec["devices"][device]
        if prefix == self.spec["service"]["prefix"]:
            return bool(dev.get("originates_service"))
        return dev.get("lan") == prefix

    def has_route(self, device: str, prefix: str) -> tuple[bool, Port | None]:
        """(present, via-port). Connected if originated locally; else learned over a FULL adjacency."""
        if self.originates(device, prefix):
            return True, None
        if prefix == self.spec["service"]["prefix"] and device in self.route_filters:
            return False, None
        for p in self.ports_of(device):
            if self.routes_installed(p) and self.originates(p.peer_device, prefix):
                return True, p
        return False, None

    def prefix_for(self, address: str) -> str | None:
        ip = ipaddress.ip_address(address)
        candidates = [self.spec["service"]["prefix"]] + [d["lan"] for d in self.spec["devices"].values() if "lan" in d]
        for pfx in candidates:
            if ip in ipaddress.ip_network(pfx):
                return pfx
        return None

    def can_ping(self, device: str, destination: str, source: str | None) -> bool:
        """Forward path (device -> destination prefix) and return path (destination owner -> source prefix)."""
        dst_pfx = self.prefix_for(destination)
        if dst_pfx is None or not self.has_route(device, dst_pfx)[0]:
            return False
        if source is None:
            return True
        src_pfx = self.prefix_for(source)
        owners = [d for d in self.spec["devices"] if self.originates(d, dst_pfx)]
        return src_pfx is not None and any(self.has_route(o, src_pfx)[0] for o in owners)

    # ------------------------------------------------------------------ time
    def advance(self, seconds: float) -> None:
        """Move the virtual clock, logging every adjacency that reaches FULL along the way."""
        end = self.clock + timedelta(seconds=seconds)
        pending = sorted((t.full_at, key) for key, t in self.timing.items()
                         if t.full_at is not None and self.clock < t.full_at <= end)
        for when, key in pending:
            self.clock = when
            a, b = (self.ports[k] for k in key)
            if self.adjacency_state(a) == "full":
                for p in (a, b):
                    q = self.peer(p)
                    self._log(p.device, "Ospf", "OSPF",
                              f"Instance 1: %OSPF-4-OSPF_ADJACENCY_ESTABLISHED: NGB {self._rid(q.device)}, "
                              f"interface {p.ip} adjacency established")
        self.clock = end

    def _rid(self, device: str) -> str:
        return self.spec["devices"][device]["router_id"]

    def _log(self, device: str, process: str, category: str, text: str) -> None:
        self.logs[device].append(LogEntry(self.clock, device, process, text, category))

    def _restart_adjacency(self, p: Port, was_full: bool) -> None:
        """Re-evaluate timing after any change on a link."""
        t = self.timing[self._key(p)]
        if self.compatible(p) and p.mtu == self.peer(p).mtu:
            if not was_full:
                t.full_at = self.clock + timedelta(seconds=self.conv["full_after_s"])
                t.route_at = t.full_at + timedelta(seconds=self.conv["route_after_full_s"])
        else:
            t.full_at = t.route_at = None

    # ------------------------------------------------------------------ events (used by faults AND by CLI)
    def set_oper(self, p: Port, up: bool) -> None:
        """A physical link state change hits BOTH ends of a point-to-point link."""
        was_full = self.adjacency_state(p) == "full"
        for x in (p, self.peer(p)):
            if x.oper_up == up:
                continue
            x.oper_up = up
            x.link_status_changes += 1
            x.in_errors += self.rng.randint(0, 2)
            x.last_change = self.clock
            self._log(x.device, "Ebra", "LINK", f"%LINEPROTO-5-UPDOWN: Line protocol on Interface {x.name} "
                                                f"({x.description}), changed state to {'up' if up else 'down'}")
            if not up and was_full:
                self._log(x.device, "Ospf", "OSPF",
                          f"Instance 1: %OSPF-4-OSPF_ADJACENCY_TEARDOWN: NGB {self._rid(self.peer(x).device)}, "
                          f"interface {x.ip} adjacency dropped: interface went down, state was: FULL")
        self._restart_adjacency(p, was_full and up)

    def flap(self, p: Port, count: int = 1, every_s: float = 15.0, down_s: float = 1.0) -> None:
        for _ in range(count):
            self.set_oper(p, False)
            self.advance(down_s)
            self.set_oper(p, True)
            self.advance(max(every_s - down_s, 0) + self.rng.uniform(0, 0.4))

    def configure_port(self, p: Port, attr: str, value: Any, by: str) -> None:
        """A configuration change (area, mtu, admin state...). Logged like cEOS's ConfigAgent."""
        was_full = self.adjacency_state(p) == "full"
        setattr(p, attr, value)
        self.saved[p.device] = False
        self._log(p.device, "ConfigAgent", "CONFIG", f"%SYS-5-CONFIG_I: Configured from console by {by} on vty3")
        self.audit.append({"ts": self.clock.isoformat(), "device": p.device, "interface": p.name,
                           "set": attr, "to": value, "by": by})
        if was_full and self.adjacency_state(p) != "full":
            for x in (p, self.peer(p)):
                self._log(x.device, "Ospf", "OSPF",
                          f"Instance 1: %OSPF-4-OSPF_STATE_CHANGE: NGB {self._rid(self.peer(x).device)} "
                          f"({self.peer(x).ip}) on interface {x.ip} changed from <FULL> to <DOWN>")
        self._restart_adjacency(p, was_full and self.adjacency_state(p) == "full")

    def set_admin(self, p: Port, up: bool, by: str) -> None:
        """`shutdown` / `no shutdown` on one end: the link goes down/up for both ends."""
        p.admin_up = up
        self.saved[p.device] = False
        self._log(p.device, "ConfigAgent", "CONFIG", f"%SYS-5-CONFIG_I: Configured from console by {by} on vty3")
        self.audit.append({"ts": self.clock.isoformat(), "device": p.device, "interface": p.name,
                           "set": "admin", "to": "up" if up else "down", "by": by})
        self.set_oper(p, up and self.peer(p).admin_up)

    def clear_counters(self, device: str, name: str | None, by: str) -> None:
        """`clear counters` — the flap counter goes to zero. The flap is 'gone'. Nothing is fixed."""
        for p in self.ports_of(device):
            if name is None or p.name == name:
                p.link_status_changes = 0
                p.in_errors = 0
        self.audit.append({"ts": self.clock.isoformat(), "device": device, "interface": name,
                           "set": "clear_counters", "to": 0, "by": by})

    # ------------------------------------------------------------------ the fault timeline
    def _inject_faults(self) -> None:
        events = sorted(self.spec["fault"], key=lambda e: e["at_min"])
        self.clock = self.start + timedelta(minutes=events[0]["at_min"])
        for e in events:
            target = self.start + timedelta(minutes=e["at_min"])
            if target > self.clock:
                self.advance((target - self.clock).total_seconds())
            if e["op"] == "filter_route":
                self.route_filters.add(e["device"])
                self._log(e["device"], "ConfigAgent", "CONFIG",
                          "%SYS-5-CONFIG_I: Configured from console by change-window-automation on vty3")
                continue
            p = self.port(*e["link"].split(":"))
            if e["op"] == "flap":
                self.flap(p, e["count"], e["every_s"])
            elif e["op"] == "set_area":
                self.configure_port(p, "area", e["area"], by="change-window-automation")
            elif e["op"] == "set_mtu":
                self.configure_port(p, "mtu", e["mtu"], by="change-window-automation")
            else:
                raise ValueError(f"unknown fault op {e['op']}")
        self._pad_logs(events)
        if self.clock < self.start:
            self.advance((self.start - self.clock).total_seconds())
        self.audit.clear()          # the fault is history, not something an agent or operator did today
        self.saved = {d: True for d in self.spec["devices"]}   # the bad config was saved in the change window

    def _pad_logs(self, events: list[dict]) -> None:
        """Keep flapping (genuinely) until BRANCH-7's buffer holds `log_volume` lines, without passing 03:14."""
        last = next((e for e in reversed(events) if e["op"] == "flap"), None)
        if not last:
            return
        p = self.port(*last["link"].split(":"))
        need = self.spec["log_volume"] - len(self.logs[p.device])
        if need <= 0:
            return
        flaps = -(-need // 2)                                   # 2 LINEPROTO lines per flap on a dead adjacency
        window = max((self.start - self.clock).total_seconds() - 2, flaps * 0.2)
        step = window / flaps
        for _ in range(flaps):
            self.set_oper(p, False)
            self.advance(step / 2)
            self.set_oper(p, True)
            self.advance(step / 2)
