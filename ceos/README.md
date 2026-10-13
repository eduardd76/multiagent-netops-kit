# Instructor demo on real Arista cEOS

The same `netops` agents, unchanged, against a 4-node containerlab fabric that matches `netops/data/incident.yaml`.

| Node | Role | eAPI published on the lab host |
|---|---|---|
| BRANCH-7 | affected branch | `:8011` |
| HUB-1 | its hub (originates 10.100.10.0/24) | `:8021` |
| BRANCH-8 | healthy control | `:8012` |
| HUB-2 | control hub | `:8022` |

## Run it
```bash
docker import cEOS-lab-4.34.8M.tar.xz ceos:4.34.8M        # arm64: cEOSarm-lab-...; BYO image (Arista login)
sudo containerlab deploy -t ceos/topology.clab.yml         # healthy (~20 s)
./ceos/break.sh                                            # inject the incident (~2.5 min)
NETOPS_CEOS=1 pytest -m live -s                            # or open labs/demo_ceos.ipynb
./ceos/reset.sh                                            # back to healthy between runs
sudo containerlab destroy -t ceos/topology.clab.yml --cleanup
```
On macOS with OrbStack the lab runs in a Linux VM (e.g. `clab`); the VM is reachable as `clab.orb.local`, so the
notebook uses `clab.orb.local:8011` etc. Run the scripts inside the VM: `orb -m clab bash -lc 'cd <kit>/ceos && ./break.sh'`.

## Verified on ceos:4.34.8M (2026-10-12)
- Area mismatch: the neighbor is **absent** (empty `ospfNeighborEntries`). No log line, no counter.
- After the fix (10/40 timers): FULL in 3-9 s, route installed 9-16 s (SPF hold 5 s). Validation polls; it never trusts one read.
- eAPI sessions start unprivileged: `CeosDevice` sends `enable` first (needed for `ping ... source` and config sessions).
- Changes go through `configure session ... commit` (atomic).
- Links are pinned to MTU 1500: containerlab's veth default (9500) would cause an EXSTART mismatch with cEOS.
