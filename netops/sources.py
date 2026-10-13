"""Observations from outside the device CLI. The mocks read the lab's own syslog and answer in Splunk's and Loki's
real response shapes, so the leave-behind shows the customer's admins exactly what a real connector would fetch."""
from __future__ import annotations

from netops.channels import MOCK_LABEL
from netops.ports import EvidenceItem

_SCHEMA = {"type": "object", "properties": {"device": {"type": "string"}, "limit": {"type": "integer"}},
           "required": ["device"], "additionalProperties": False}


class DeviceLogs:
    name, description = "device_logs", "The device's own syslog buffer, newest last."

    def __init__(self, net):
        self.net = net

    def query(self, device: str, *, limit: int = 400) -> list[EvidenceItem]:
        return [EvidenceItem(ts=l.ts.isoformat(), device=device, source="device", text=l.text)
                for l in self.net.logs(device)[-limit:]]


class MockSplunk(DeviceLogs):
    name = "splunk_search"
    description = "Search Splunk for a device's syslog (index=network host=<device>), newest last."
    label = MOCK_LABEL.format(system="Splunk")

    def __init__(self, net, index: str = "network"):
        super().__init__(net)
        self.index = index

    def raw(self, device: str, limit: int = 400) -> dict:
        """POST /services/search/jobs/export ... output_mode=json, collected into one document."""
        return {"preview": False, "results": [{"_time": l.ts.isoformat(), "host": device, "index": self.index,
                                               "sourcetype": "syslog", "_raw": l.text}
                                              for l in self.net.logs(device)[-limit:]]}

    def query(self, device: str, *, limit: int = 400) -> list[EvidenceItem]:
        return [EvidenceItem(ts=r["_time"], device=device, source=self.label, text=r["_raw"])
                for r in self.raw(device, limit)["results"]]


class MockLoki(DeviceLogs):
    name = "loki_query"
    description = "Query Loki for a device's syslog ({host=\"<device>\"}), newest last."
    label = MOCK_LABEL.format(system="Loki")

    def raw(self, device: str, limit: int = 400) -> dict:
        """GET /loki/api/v1/query_range?query={host="<device>"}&limit=N"""
        values = [[str(int(l.ts.timestamp() * 1e9)), l.text] for l in self.net.logs(device)[-limit:]]
        return {"status": "success", "data": {"resultType": "streams",
                                              "result": [{"stream": {"host": device}, "values": values}]}}

    def query(self, device: str, *, limit: int = 400) -> list[EvidenceItem]:
        from datetime import datetime, timezone
        vals = self.raw(device, limit)["data"]["result"][0]["values"]
        return [EvidenceItem(ts=datetime.fromtimestamp(int(t) / 1e9, timezone.utc).isoformat(), device=device,
                             source=self.label, text=line) for t, line in vals]


def as_tool(source) -> tuple[str, tuple]:
    return source.name, (source.description, _SCHEMA,
                         lambda n, a: source.query(a["device"], limit=int(a.get("limit", 400))))
