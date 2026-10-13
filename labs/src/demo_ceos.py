from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("demo_ceos", "Instructor demo -- the SAME agents on real Arista cEOS (containerlab)",
                expect=["reachability() = FAIL", "RESOLVED."])
    b.md("""
        **Instructor only** (needs Docker + containerlab + a cEOS image; not for Colab). See `ceos/README.md`.

        1. `sudo containerlab deploy -t ceos/topology.clab.yml`  (healthy at deploy)
        2. `ceos/break.sh` -- 6 flaps that recover, the silent area change, 12 flaps that don't (~2.5 min)
        3. Run the cells. The only line that differs from the student labs is `Network.ceos(...)`.
        4. `ceos/reset.sh` between runs.
        """)
    b.code("""
        import os
        from netops.network import Network
        from netops.orchestrator import new_incident, run_lab1, run_team, contrast
        HOSTS = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021",     # eAPI published by containerlab
                 "BRANCH-8": "clab.orb.local:8012", "HUB-2": "clab.orb.local:8022"}     # change to your lab host
        net = Network.ceos(HOSTS)
        print("reachability() =", net.reachability())
        print("BRANCH-7 neighbors:", net.ospf_neighbors("BRANCH-7"))
        print("areas:", net.ospf_interface("BRANCH-7", "Ethernet1").area, "vs", net.ospf_interface("HUB-1", "Ethernet1").area)
        """)
    b.md("## Lab 1 on real gear -- one agent, no gate")
    b.code("""
        lab1 = run_lab1(new_incident(llm=llm, network=Network.ceos(HOSTS)))
        print(lab1)
        """)
    b.md("## Lab 4 on real gear -- the team, the playbook, and the human gate (a volunteer from the room approves live)")
    b.code("""
        lab4 = run_team(new_incident(llm=llm, network=Network.ceos(HOSTS)))
        print(contrast(lab1, lab4))
        """)
    return b
