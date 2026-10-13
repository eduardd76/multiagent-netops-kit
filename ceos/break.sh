#!/usr/bin/env bash
# Inject the incident on the running lab: 6 flaps that RECOVER, the silent area change, 12 flaps that don't.
set -u
B=clab-netops-branch7
flap() { docker exec $B ip link set eth1 down; sleep 1; docker exec $B ip link set eth1 up; sleep "$1"; }
for i in $(seq 1 6); do flap 15; done
printf "configure\ninterface Ethernet1\nip ospf area 0.0.0.1\nend\n" | docker exec -i $B Cli -p 15 >/dev/null
for i in $(seq 1 12); do flap 2; done
echo "incident injected: BRANCH-7 Ethernet1 area 0.0.0.1 (HUB-1 is 0.0.0.0), uplink flapped"
