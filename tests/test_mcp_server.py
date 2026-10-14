"""The read-only MCP server: every read tool, no write tool, real answers through a real MCP client session."""
import asyncio

import pytest

pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from netops.agents.tools import READ_TOOLS, UNGATED_TOOLS  # noqa: E402
from netops.mcp_server import build, network_from_env  # noqa: E402
from netops.network import Network  # noqa: E402


def _session(fn):
    async def go():
        async with Client(build(Network.simulated())) as client:
            return await fn(client)
    return asyncio.run(go())


def _text(result) -> str:
    return "".join(c.text for c in result.content if getattr(c, "text", None))


def test_exposes_every_read_tool_and_no_write_tool():
    tools = _session(lambda c: c.list_tools()).tools
    names = {t.name for t in tools}
    assert names == set(READ_TOOLS)
    assert not names & set(UNGATED_TOOLS)
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


def test_answers_the_incident_through_mcp():
    async def go(c):
        return (_text(await c.call_tool("ospf_neighbors", {"device": "BRANCH-7"})),
                _text(await c.call_tool("ping", {"device": "BRANCH-7", "destination": "10.100.10.10",
                                                  "source": "10.20.20.1"})))
    neighbors, ping = _session(go)
    assert "ospf_neighbors(device=BRANCH-7) ->" in neighbors and "\n[]\n" in neighbors
    assert '"sent": 5, "received": 0' in ping
    assert "<untrusted-data" in neighbors            # device output is labelled as data for the client's model


def test_a_bad_device_name_gets_an_error_that_teaches():
    out = _text(_session(lambda c: c.call_tool("ospf_neighbors", {"device": "BRANCH-9"})))
    assert "unknown device 'BRANCH-9'; devices: BRANCH-7, HUB-1, BRANCH-8, HUB-2" in out


def test_a_write_tool_is_not_there_to_call():
    result = _session(lambda c: c.call_tool("bounce_interface", {"device": "BRANCH-7", "interface": "Ethernet1"}))
    assert result.is_error


def test_the_network_behind_the_server_is_read_only():
    server_net = Network.simulated().read_only()
    with pytest.raises(PermissionError):
        server_net.configure("BRANCH-7", ["interface Ethernet1", "shutdown"], by="mcp-client")


def test_hosts_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("NETOPS_CEOS_HOSTS", raising=False)
    assert network_from_env().fabric is not None                     # default: the simulated incident
    monkeypatch.setenv("NETOPS_CEOS_HOSTS", "BRANCH-7=clab.orb.local:8011, HUB-1=clab.orb.local:8021")
    assert network_from_env().fabric is None                         # real cEOS over eAPI
