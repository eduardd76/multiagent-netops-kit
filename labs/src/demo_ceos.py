from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("demo_ceos", "Instructor demo -- the SAME agents on real Arista cEOS (containerlab)",
                expect=["reachability() = FAIL", "RESOLVED."])
    b.md("""
        **Instructor only** (needs Docker + containerlab + a cEOS image; not for Colab). See `ceos/README.md`.

        The lab is deployed once with containerlab (on a Mac it runs inside a Linux VM, e.g. OrbStack: prefix commands
        with `orb -m <vm>`). Before the session: `ceos/reset.sh` then `ceos/break.sh` (~2.5 min:
        6 flaps that recover, the silent area change, 12 flaps that don't). One cell per beat of the speaker script --
        run each cell when the script says so, not all at once. To re-arm afterwards: `ceos/reset.sh` then `ceos/break.sh`.
        """)
    b.md("## 0 -- Connect to the real routers (before the session). Must print FAIL.")
    b.code("""
        from netops import render
        from netops.clab import ContainerLab
        from netops.network import Network

        HOSTS = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021",     # each router's API (eAPI),
                 "BRANCH-8": "clab.orb.local:8012", "HUB-2": "clab.orb.local:8022"}     # published by containerlab
        net = Network.ceos(HOSTS)                # the ONE line your Colab doesn't have: there it's Network.simulated()
        lab = ContainerLab("netops", vm="clab")  # to type on the routers' own CLI (show and ping only)
        print("reachability() =", net.reachability(), "   <- must be FAIL before the session (ceos/break.sh)")
        """)
    b.md("## Slide 3 -- meet the lab. ONE cell: shift-enter once, then talk over the three blocks it prints.")
    b.code("""
        print("1/3  THE LAB IS REAL: 4 Arista cEOS routers in containerlab, on this laptop\\n")
        lab.containers()

        print("2/3  WHAT AN ENGINEER TYPES on the routers: the healthy branch first\\n")
        for router, lan in [("BRANCH-8", "10.30.30.1"), ("BRANCH-7", "10.20.20.1")]:
            lab.cli(router, "show ip ospf neighbor")
            lab.cli(router, "show ip route 10.100.10.0/24")
            lab.cli(router, f"ping 10.100.10.10 source {lan} repeat 2")

        print("3/3  THE SAME CHECK IN CODE: the real routers, then your simulator\\n")
        render.lab(net)
        render.lab(Network.simulated(), brief=True)
        """)
    b.md("## Slide 5 -- one agent, every tool. ONE cell: the same line the room runs in Lab 1, on the simulator.")
    b.code("""
        from netops.agents.single import SingleAgent
        from netops.orchestrator import ALERT, new_incident

        inc = new_incident(llm=llm)            # a fresh copy of the attendees' network (the simulator), incident state
        print("model:", render.llm_label(llm), "\\nALERT:", ALERT, "\\n")
        run = SingleAgent(llm, inc.network, inc.evidence).run(ALERT, trace=inc.trace)   # one agent, every tool
        print("\\nreachability() =", inc.network.reachability())        # the users' check, after it says 'resolved'
        render.audit(inc.network)                                       # what it changed on the router, and who approved
        """)
    b.md("## Slide 16 (itch) -- what the on-call engineer types: ping, route, neighbors. Do NOT show the areas yet.")
    b.code("""
        print("ping 10.100.10.10 source 10.20.20.1 :", net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1"))
        print("route 10.100.10.0/24               :", net.route("BRANCH-7", "10.100.10.0/24"))
        print("OSPF neighbors on BRANCH-7         :", net.ospf_neighbors("BRANCH-7"))
        """)
    b.md("## Lab 2 reveal (slide 28) -- one digit")
    b.code("""
        render.lab(net, show_area=True)      # the same view, now with the area column: 0.0.0.1 vs 0.0.0.0
        """)
    b.md("## Optional -- Lab 1's single agent on real gear (it changes the router: re-arm with reset.sh + break.sh after)")
    b.code("""
        from netops.orchestrator import new_incident, run_lab1
        lab1 = run_lab1(new_incident(llm=llm, network=Network.ceos(HOSTS)))
        print("the agent says:", lab1["agent_says"])
        print("reachability() =", lab1["reachability"], "| ungated writes:", lab1["writes"])
        """)
    b.md("## Lab 4 live (slides 43-46) -- the team stops at the gate; the volunteer is the on-call engineer")
    b.code("""
        from netops.orchestrator import ALERT, ONCALL_REJECT, contrast, new_incident, team
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
        render.lab(net, show_area=True)      # the lab after the one approved write: FULL, route, PASS on both branches
        """)
    b.md("## The contrast (slide 47) -- needs the optional Lab 1 cell above; otherwise read the students' table")
    b.code("""
        if "lab1" in globals():
            print(contrast(lab1, result))
        """)
    b.md("**After the session:** `ceos/reset.sh` then `ceos/break.sh` re-arms the incident for the next run.")
    return b
