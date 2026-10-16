from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab1_single_agent", "Lab 1 -- One Agent, Every Tool",
                expect=["THE LAB", "did_it_work: False", "reachability() = FAIL", "DEVICE CHANGE AUDIT"])
    b.md("""
        ## Step 1 -- The symptom
        Users at BRANCH-7 can't reach the core service, and the dashboard is green. Look at the lab the way the
        on-call engineer would.
        """)
    b.code("""
        from netops.orchestrator import new_incident, ALERT
        inc = new_incident(llm=llm)
        net = inc.network
        print(ALERT, "\\n")
        render.lab(net)
        """)
    b.md("""
        ## Step 2 -- One agent, every tool
        The agent gets every tool, including two that change the router, and nobody approves its changes.
        """)
    b.code("""
        from netops.agents.single import SingleAgent
        run = SingleAgent(llm, net, inc.evidence).run(ALERT, trace=inc.trace)   # one agent works the whole incident
        """)
    b.md("""
        ## Step 3 -- Your turn
        `NotImplementedError` is not a crash -- it's your turn. Write `did_it_work(net)`: 3-5 lines, read tools only.
        """)
    b.todo("lab1_did_it_work",
           student='''
            def did_it_work(net) -> bool:
                """True only if the incident is really fixed. Read tools you can use:
                net.ping(device, destination, source), net.route(device, prefix), net.ospf_neighbors(device),
                net.interface(device, interface).   3-5 lines."""
                raise NotImplementedError("TODO(lab1_did_it_work): define success")
            ''',
           solution='''
            def did_it_work(net) -> bool:
                """Fixed = the route is back AND users reach the service. Not 'the logs went quiet'."""
                route_back = net.route("BRANCH-7", "10.100.10.0/24").present
                users_ok = net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1").success
                return route_back and users_ok
            ''')
    b.md("""
        ## Step 4 -- Check it
        Compare what the agent says with what the network says, then see what it changed on the router.
        """)
    b.code("""
        print("the agent says :", (run.final_text or "").strip().split("\\n")[0])   # first line is enough
        print("did_it_work:", did_it_work(net))
        print("reachability() =", net.reachability())
        assert did_it_work(net) == (net.reachability() == "PASS"), "your definition disagrees with the network"
        render.audit(net)
        """)
    return b
