import pytest

from netops.approval import Approvals, GateError
from netops.executor import Executor
from netops.network import Network

BACKOUT = {"name": "adj", "tool": "ospf_neighbors", "expect": {"interface": "{uplink}", "state": "full"}, "backout": True}
FIX = ["interface Ethernet1", "ip ospf area 0.0.0.0"]
UNDO = ["interface Ethernet1", "ip ospf area 0.0.0.9"]


def _setup(post_checks):
    net, appr = Network.simulated(), Approvals()
    prop = {"device": "BRANCH-7", "commands": FIX, "rollback": UNDO, "params": {}, "post_checks": post_checks}
    return net, appr, prop, Executor(net, appr, backout_s=60, poll_s=3)


def test_no_backout_check_is_refused_and_token_not_spent():
    net, appr, prop, ex = _setup([{**BACKOUT, "backout": False}])
    tok = appr.approve(prop, "on-call")
    with pytest.raises(GateError, match="no backout check"):
        ex.apply(prop, tok)
    assert net.fabric.audit == [] and not [e for e in appr.log if e["event"] == "consumed"]
    prop["post_checks"] = [BACKOUT]
    assert ex.apply(prop, appr.approve(prop, "on-call"))["rolled_back"] is False


def test_unknown_backout_tool_is_refused_before_configure():
    net, appr, prop, ex = _setup([{**BACKOUT, "tool": "nope"}])
    with pytest.raises(GateError, match="nope"):
        ex.apply(prop, appr.approve(prop, "on-call"))
    assert net.fabric.audit == [] and not [e for e in appr.log if e["event"] == "consumed"]


def test_check_that_raises_after_configure_rolls_back_and_propagates():
    bad = {**BACKOUT, "args": {"x": "{missing}"}}
    net, appr, prop, ex = _setup([bad])
    with pytest.raises(KeyError):
        ex.apply(prop, appr.approve(prop, "on-call"))
    assert [a["by"] for a in net.fabric.audit][-1] == "executor:auto-backout"
