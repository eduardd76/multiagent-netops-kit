# kit/tests/test_audit.py
import json

from netops.approval import Approvals
from netops.audit import Fanout, JsonlAudit, MemoryAudit, MockConfluencePage, MockServiceNowIncident
from netops.llm import MockLLM
from netops.orchestrator import ALERT, ONCALL_REJECT, Incident, team
from netops.network import Network
from netops.protocol import Bus
from netops.trace import Trace


def audited_incident(sink):
    return Incident(network=Network.simulated(), llm=MockLLM(), trace=Trace(False), bus=Bus(audit=sink),
                    approvals=Approvals(audit=sink))


def run(inc, sink):
    from netops.agents.coordinator import Coordinator
    c = Coordinator(inc.network, inc.llm, bus=inc.bus, evidence=inc.evidence, approvals=inc.approvals,
                    trace=inc.trace, audit=sink)
    return c.run_to_gate(ALERT).reject(ONCALL_REJECT).approve("Camille")


def test_every_action_reaches_the_sink(tmp_path):
    mem, jl = MemoryAudit(), JsonlAudit(tmp_path / "audit.jsonl")
    inc = audited_incident(Fanout([mem, jl]))
    run(inc, inc.bus.audit)
    kinds = [e.kind for e in mem.events]
    assert kinds.count("message") == len(inc.bus.transcript)
    assert ["approved", "consumed", "change_applied"] == [k for k in kinds if k != "message"]
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(lines) == len(mem.events) and "change_applied" in [json.loads(l)["kind"] for l in lines]


def test_confluence_page_is_a_storage_format_decision_record():
    page_sink = MockConfluencePage()
    inc = audited_incident(page_sink)
    run(inc, page_sink)
    page = page_sink.page()
    body = page["body"]["storage"]
    assert page["type"] == "page" and page["space"]["key"] == "NETOPS" and body["representation"] == "storage"
    assert "mock Confluence - real formats, no connection" in body["value"]
    assert "Camille" in body["value"] and "interface Ethernet1" in body["value"] and "<table>" in body["value"]


def test_servicenow_incident_collects_work_notes():
    sn = MockServiceNowIncident()
    inc = audited_incident(sn)
    run(inc, sn)
    assert sn.record["number"].startswith("INC") and sn.record["state"] == "resolved"
    assert any("approved" in n for n in sn.record["work_notes"])
