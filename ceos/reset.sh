#!/usr/bin/env bash
# Back to healthy between runs: correct area, clear counters, wait for FULL + route (9-16 s on cEOS).
set -u
B=clab-netops-branch7
printf "configure\ninterface Ethernet1\nip ospf area 0.0.0.0\nno shutdown\nend\nclear counters\n" | docker exec -i $B Cli -p 15 >/dev/null
for i in $(seq 1 30); do
  docker exec $B Cli -p 15 -c "show ip route 10.100.10.0/24" | grep -q "10.100.10.0/24" && { echo "healthy after ${i}x2s"; exit 0; }
  sleep 2
done
echo "WARNING: route not back after 60 s"; exit 1
