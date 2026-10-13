import json
from pathlib import Path

import pytest

from netops import render
from netops.orchestrator import ALERT, ONCALL_REJECT, team
from netops.wiring import PackError, build, load_pack

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "customer.example.yaml"


@pytest.fixture(autouse=True)
def _reset_render_skin():
    yield
    render.configure(None)


def test_example_pack_runs_end_to_end_in_customer_names():
    inc = build(EXAMPLE, verbose=False)
    approver = inc.pack.approval["approver"]
    g1 = team(inc).run_to_gate(ALERT)
    t1 = g1.submit(inc.channel)
    assert t1.record["cmdb_ci"] == "LYON-BR07" and "BRANCH-7" not in json.dumps(t1.record)
    inc.channel.decide(t1, approve=False, by=approver, reason=ONCALL_REJECT)
    g2 = g1.resolve(inc.channel, t1)
    t2 = g2.submit(inc.channel)
    inc.channel.decide(t2, approve=True, by=approver)
    res = g2.resolve(inc.channel, t2)
    assert res["resolved"] and res["reachability"] == "PASS"
    page = next(s for s in inc.audit.sinks if hasattr(s, "page")).page()["body"]["storage"]["value"]
    assert approver in page and "LYON-BR07" in page and "BRANCH-7" not in page
    assert all("BRANCH-7" not in t for _, t in inc.trace.lines)
    assert "splunk_search" in [e.tool for e in inc.evidence.all()] and inc.evidence.fence


def test_presenter_cannot_approve_in_a_pack():
    inc = build(EXAMPLE, verbose=False)
    g = team(inc).run_to_gate(ALERT).reject(ONCALL_REJECT)
    from netops.approval import GateError
    with pytest.raises(GateError, match="approval channel"):
        g.approve(inc.pack.approval["approver"])
    for who in (inc.pack.requester, inc.pack.requester.capitalize()):
        t = g.submit(inc.channel)
        inc.channel.decide(t, approve=True, by=who)
        with pytest.raises(GateError, match="separation of duties"):
            g.resolve(inc.channel, t)
    assert inc.network.fabric.audit == []


@pytest.mark.parametrize("patch,match", [
    ({"approval": {"adapter": "teams"}}, "unknown approval adapter 'teams'; known:"),
    ({"mode": "production"}, "mode"),
    ({"llm": {"adapter": "openai_compat", "base_url": "${NOPE_URL}", "model": "m"}}, "NOPE_URL is not set"),
])
def test_broken_packs_fail_clearly(tmp_path, patch, match):
    import yaml
    data = yaml.safe_load(EXAMPLE.read_text()) | patch
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(PackError, match=match):
        build(p, verbose=False)


def test_no_pack_is_the_workshop_default():
    inc = build(None, verbose=False)
    assert inc.pack is None and inc.channel is None and not inc.evidence.fence


def test_lab1_ungated_agent_is_refused_in_a_pack():
    from netops.approval import GateError
    from netops.orchestrator import run_lab1
    inc = build(EXAMPLE, verbose=False)
    with pytest.raises(GateError, match="Lab 1's ungated agent is not available in customer mode"):
        run_lab1(inc)
    assert inc.network.fabric.audit == []


def test_customer_skin_does_not_leak_into_the_next_workshop_incident(capsys):
    from netops.orchestrator import new_incident
    build(EXAMPLE, verbose=False)
    new_incident(verbose=False)
    render.banner("BRANCH-7")
    assert "BRANCH-7" in capsys.readouterr().out


def test_a_pack_that_fails_to_build_leaves_no_skin(tmp_path, capsys):
    import yaml
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(yaml.safe_load(EXAMPLE.read_text()) | {"approval": {"adapter": "teams"}}))
    with pytest.raises(PackError):
        build(p, verbose=False)
    render.banner("BRANCH-7")
    assert "BRANCH-7" in capsys.readouterr().out


def test_evidence_sources_get_a_read_only_network():
    inc = build(EXAMPLE, verbose=False)
    assert inc.sources
    for s in inc.sources:
        with pytest.raises(PermissionError):
            s.net.configure("BRANCH-7", ["interface Ethernet1"], by="source")
