from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("demo_ceos", "Instructor demo -- the SAME agents on real Arista cEOS (containerlab)",
                expect=["reachability() = FAIL", "RESOLVED."])
    b.md("""
        **Instructor only** (needs Docker + containerlab + a cEOS image; not for Colab). See `ceos/README.md`.

        Before the session: `sudo containerlab deploy -t ceos/topology.clab.yml`, then `ceos/break.sh` (~2.5 min:
        6 flaps that recover, the silent area change, 12 flaps that don't). One cell per beat of the speaker script --
        run each cell when the script says so, not all at once. To re-arm afterwards: `ceos/reset.sh` then `ceos/break.sh`.
        """)
    b.md("## 0 -- Connect (before the session)")
    b.code("""
        from netops import render
        from netops.network import Network
        from netops.orchestrator import ALERT, ONCALL_REJECT, contrast, new_incident, run_lab1, team
        HOSTS = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021",     # eAPI published by containerlab
                 "BRANCH-8": "clab.orb.local:8012", "HUB-2": "clab.orb.local:8022"}     # change to your lab host
        net = Network.ceos(HOSTS)
        print("reachability() =", net.reachability(), "   <- must be FAIL before the session (ceos/break.sh)")
        """)
    b.md("## Slide 3 (two_logs) -- the loudest log on BRANCH-7. Scroll it; do not point at the OSPF lines.")
    b.code("""
        logs = net.logs("BRANCH-7")
        print(f"show logging on BRANCH-7 -- {len(logs)} lines")
        for l in logs[-25:]:
            print("  ", l.ts.time(), l.text)
        """)
    b.md("## Slide 14 (itch) -- what the on-call engineer types: ping, route, neighbors. Do NOT show the areas yet.")
    b.code("""
        print("ping 10.100.10.10 source 10.20.20.1 :", net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1"))
        print("route 10.100.10.0/24               :", net.route("BRANCH-7", "10.100.10.0/24"))
        print("OSPF neighbors on BRANCH-7         :", net.ospf_neighbors("BRANCH-7"))
        """)
    b.md("## Lab 2 reveal (slide 26) -- one digit")
    b.code("""
        for d in ("BRANCH-7", "HUB-1"):
            print(f"{d:9} show ip ospf interface Ethernet1 -> area {net.ospf_interface(d, 'Ethernet1').area}")
        """)
    b.md("## Optional -- Lab 1's single agent on real gear (it changes the router: re-arm with reset.sh + break.sh after)")
    b.code("""
        lab1 = run_lab1(new_incident(llm=llm, network=Network.ceos(HOSTS)))
        print("the agent says:", lab1["agent_says"])
        print("reachability() =", lab1["reachability"], "| ungated writes:", lab1["writes"])
        """)
    b.md("## Lab 4 live (slides 41-44) -- the team stops at the gate; the volunteer is the on-call engineer")
    b.code("""
        inc = new_incident(llm=llm, network=Network.ceos(HOSTS))
        gate = team(inc, "on-call").run_to_gate(ALERT)
        render.gate(gate)                     # v1: six PASS, blast_radius_evidenced FAIL, ready for approval: False
        """)
    b.md("Optional, 20 s: try to approve v1 anyway -- the gate refuses.")
    b.code("""
        try:
            gate.approve("on-call")
        except Exception as e:
            print(type(e).__name__ + ":", e)
        """)
    b.md("The volunteer reads the rejection (ONCALL_REJECT). Then run this cell: the team fetches both neighbor tables and revises.")
    b.code("""
        gate = gate.reject(ONCALL_REJECT)
        render.gate(gate)                     # v2: blast radius cites both neighbor tables, ready for approval: True
        """)
    b.md("The volunteer says yes. Approve -- the executor (code) applies, then the validator polls the real network.")
    b.code("""
        result = gate.approve("on-call")
        render.transcript(inc.bus)
        print("\\nreachability() =", result["reachability"])
        render.audit(inc.network)
        render.dashboard(result["reachability"])
        """)
    b.md("## The contrast (slide 44) -- needs the optional Lab 1 cell above; otherwise read the students' table")
    b.code("""
        if "lab1" in globals():
            print(contrast(lab1, result))
        """)
    b.md("**After the session:** `ceos/reset.sh` then `ceos/break.sh` re-arms the incident for the next run.")
    return b
