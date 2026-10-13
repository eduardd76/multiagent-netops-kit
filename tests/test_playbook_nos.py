import pytest

from netops.playbook import PlaybookError, load_playbook, render


def test_compat_views_are_the_eos_lists():
    e = load_playbook()["ospf_area_mismatch"]
    assert e.allowed_commands == ["interface", "ip ospf area"] == e.allowed_for("eos")
    assert e.fix == ["interface {uplink}", "ip ospf area {expected_area}"]
    assert e.expected_post_state == ["ospf neighbor state = FULL", "branch l3 reachable = true"]
    assert e.post_checks[0].backout and e.post_checks[1].tool == "ping"


def test_a_nos_without_a_fix_fails_before_a_proposal_exists():
    e = load_playbook()["ospf_area_mismatch"]
    with pytest.raises(PlaybookError, match="no fix for nos 'junos'"):
        render(e, {"uplink": "Ethernet1", "expected_area": "0.0.0.0"}, nos="junos")


def test_untyped_parameters_are_refused():
    e = load_playbook()["ospf_area_mismatch"]
    with pytest.raises(PlaybookError, match="no validation rule"):
        render(e, {"uplink": "Ethernet1", "expected_area": "0.0.0.0", "note": "hi"})


def test_interface_type_follows_the_nos_reader():
    from netops.readers import register_reader

    class SrlLike:
        nos, interface_pattern = "srl-test", r"ethernet-\d+/\d+"

    register_reader(SrlLike())
    e = load_playbook()["ospf_area_mismatch"].model_copy(update={"fixes": {"srl-test": ["x {uplink} {expected_area}"]},
                                                                  "allowed": {"srl-test": ["x"]}})
    assert render(e, {"uplink": "ethernet-1/1", "expected_area": "0.0.0.0"}, nos="srl-test") == ["x ethernet-1/1 0.0.0.0"]
    with pytest.raises(PlaybookError, match="not valid"):
        render(e, {"uplink": "Ethernet1", "expected_area": "0.0.0.0"}, nos="srl-test")


def test_proposal_carries_nos_and_executable_checks():
    from netops.llm import MockLLM
    from netops.orchestrator import ALERT, new_incident, team
    c = team(new_incident(llm=MockLLM(), verbose=False))
    c.diagnose(ALERT); c.decide()
    p = c.propose()
    assert p["nos"] == "eos" and p["post_checks"][0]["tool"] == "ospf_neighbors"
