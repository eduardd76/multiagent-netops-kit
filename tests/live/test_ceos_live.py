"""The SAME agent code against a running containerlab cEOS lab (instructor demo). Opt-in:
    NETOPS_CEOS=1 pytest -m live -s
Hosts default to the OrbStack VM 'clab' with eAPI published on 8011/8021/8012/8022 (see ceos/topology.clab.yml).
Override with NETOPS_CEOS_HOSTS='BRANCH-7=host:port,HUB-1=host:port,...'. Break/reset run ceos/*.sh in the VM."""
import os
import subprocess
from pathlib import Path

import pytest

from netops.llm import MockLLM
from netops.network import Network
from netops.orchestrator import new_incident, run_lab1, run_team

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("NETOPS_CEOS") != "1", reason="set NETOPS_CEOS=1 with the lab running")]
CEOS_DIR = Path(__file__).resolve().parents[2] / "ceos"
DEFAULT = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021",
           "BRANCH-8": "clab.orb.local:8012", "HUB-2": "clab.orb.local:8022"}


def hosts() -> dict:
    raw = os.environ.get("NETOPS_CEOS_HOSTS")
    return dict(kv.split("=", 1) for kv in raw.split(",")) if raw else DEFAULT


def lab(script: str) -> None:
    cmd = os.environ.get("NETOPS_CEOS_EXEC", "orb -m clab bash -lc")
    subprocess.run(f"{cmd} 'cd {CEOS_DIR} && ./{script}'", shell=True, check=True)


def test_live_lab1_trap_then_lab4_resolution_on_real_ceos():
    lab("reset.sh")
    lab("break.sh")
    net = Network.ceos(hosts())
    assert net.reachability() == "FAIL"
    r1 = run_lab1(new_incident(llm=MockLLM(), network=net))
    print("\nLAB 1 on real cEOS:", r1)
    assert r1["claimed_resolved"] and r1["reachability"] == "FAIL"
    r4 = run_team(new_incident(llm=MockLLM(), network=Network.ceos(hosts())))
    print("LAB 4 on real cEOS:", r4)
    assert r4["resolved"] and r4["reachability"] == "PASS"
