"""eAPI output -> small typed models. ONE set of parsers for both backends: that is what makes the
same agent code run on the simulator and on a real cEOS. Tested on JSON captured from real cEOS."""
from __future__ import annotations

import re
from datetime import datetime

from netops.models import InterfaceStatus, LogLine, LogSummary, OspfInterface, OspfNeighbor, PingResult, Route


def _inst(data: dict) -> dict:
    return data["vrfs"]["default"]["instList"].get("1", {})


def parse_ospf_neighbors(device: str, data: dict) -> list[OspfNeighbor]:
    return [OspfNeighbor(device=device, neighbor_id=e["routerId"], interface=e["interfaceName"],
                         state=e["adjacencyState"], area=e.get("details", {}).get("areaId", ""),
                         raw_command="show ip ospf neighbor")
            for e in _inst(data).get("ospfNeighborEntries", [])]


def parse_ospf_interface(device: str, interface: str, data: dict) -> OspfInterface:
    body = _inst(data)["interfaces"][interface]
    return OspfInterface(device=device, interface=interface, area=body["area"], hello=body["helloInterval"],
                         dead=body["deadInterval"], neighbor_count=body["neighborCount"],
                         passive=body.get("passive", False), raw_command=f"show ip ospf interface {interface}")


def parse_interface(device: str, interface: str, data: dict) -> InterfaceStatus:
    body = data["interfaces"][interface]
    counters = body.get("interfaceCounters", {})
    return InterfaceStatus(device=device, interface=interface, line_protocol=body["lineProtocolStatus"],
                           link_status_changes=counters.get("linkStatusChanges", 0),
                           in_errors=counters.get("totalInErrors", 0), description=body.get("description", ""),
                           mtu=body.get("mtu"), raw_command=f"show interfaces {interface}")


def parse_route(device: str, prefix: str, data: dict) -> Route:
    routes = data["vrfs"]["default"]["routes"]
    if not routes:
        return Route(device=device, prefix=prefix, present=False, raw_command=f"show ip route {prefix}")
    shown, body = next(iter(routes.items()))
    return Route(device=device, prefix=shown, present=True, route_type=body.get("routeType"),
                 next_hops=[v.get("nexthopAddr") or v.get("interface", "") for v in body.get("vias", [])],
                 raw_command=f"show ip route {prefix}")


_PING = re.compile(r"(\d+) packets transmitted, (\d+) received")


def parse_ping(device: str, destination: str, source: str | None, text: str) -> PingResult:
    m = _PING.search(text)
    sent, received = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    cmd = f"ping {destination}" + (f" source {source}" if source else "")
    return PingResult(device=device, destination=destination, source=source, sent=sent, received=received,
                      raw_command=cmd)


_LOG = re.compile(r"^(\w{3} +\d+ \d\d:\d\d:\d\d) (\S+) ([^:]+): (.*)$")


def _category(text: str) -> str:
    if "LINEPROTO" in text or "UPDOWN" in text:
        return "LINK"
    if "%OSPF" in text:
        return "OSPF"
    if "CONFIG" in text:
        return "CONFIG"
    return "OTHER"


def parse_logging(device: str, text: str, year: int) -> list[LogLine]:
    """Lines after 'Log Buffer:'. Syslog has no year, so the caller supplies it."""
    body = text.split("Log Buffer:", 1)[-1]
    out = []
    for line in body.splitlines():
        m = _LOG.match(line.strip())
        if not m:
            continue
        ts = datetime.strptime(f"{year} {' '.join(m.group(1).split())}", "%Y %b %d %H:%M:%S")
        msg = f"{m.group(3)}: {m.group(4)}"
        out.append(LogLine(device=device, ts=ts, category=_category(msg), text=msg, raw_command="show logging"))
    return out


def summarize_logs(device: str, lines: list[LogLine]) -> LogSummary:
    """Event filtering for specialists: counts per category, and only the non-link lines verbatim."""
    counts: dict[str, int] = {}
    for l in lines:
        counts[l.category] = counts.get(l.category, 0) + 1
    notable = [f"{l.ts:%H:%M:%S} {l.text}" for l in lines if l.category in ("OSPF", "CONFIG")]
    if len(notable) > 20:
        notable = notable[:5] + ["..."] + notable[-14:]
    return LogSummary(device=device, total=len(lines), counts=counts, notable=notable, raw_command="show logging")
