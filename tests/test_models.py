from netops.models import PingResult, OspfNeighbor


def test_ping_success_only_when_all_packets_return():
    assert PingResult(device="BRANCH-7", destination="10.100.10.10", source=None, sent=5, received=5).success
    assert not PingResult(device="BRANCH-7", destination="10.100.10.10", source=None, sent=5, received=4).success


def test_for_llm_is_json_safe():
    n = OspfNeighbor(device="BRANCH-7", neighbor_id="1.1.1.1", interface="Ethernet1", state="full", area="0.0.0.0",
                     raw_command="show ip ospf neighbor")
    assert n.for_llm()["state"] == "full"
