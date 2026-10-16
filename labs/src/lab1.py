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
        ## Step 3 -- Your turn: how do YOU know it's really fixed?
        The agent just said something - "resolved" or "not resolved". That is its **opinion**. Nobody checked it.

        After any change on a real network, you don't trust the person who made the change. Before you close the
        ticket, you **check the network yourself**. Here you write that check, in code.

        **Think like the users at BRANCH-7.** They don't care about the logs or the interface light. They care about
        one thing: *can we reach the core service 10.100.10.10?* So "fixed" means two things, both true:

        1. **The route is back** - like `show ip route 10.100.10.0/24` on BRANCH-7
        2. **Users can reach the service** - like `ping 10.100.10.10 source 10.20.20.1` (from the branch LAN)

        **How to edit the cell below:** keep the first line (`def did_it_work(net) -> bool:`) and the description
        under it. Delete **only the last line**, `raise NotImplementedError(...)`, and type your 3 lines **in its
        place**, indented like the line you deleted. Do **not** write a second `def` line.
        Then run the cell, and run Step 4.

        Until you do, Step 4 stops with `NotImplementedError` - that is not a crash, it's your turn.
        """)
    b.todo("lab1_did_it_work",
           student='''
            def did_it_work(net) -> bool:
                """True only if the incident is really fixed. Read tools you can use:
                net.route(device, prefix).present        -> True if the route is in the table
                net.ping(device, destination, source).success  -> True if the ping works
                net.ospf_neighbors(device), net.interface(device, interface)   (also available)
                3-5 lines."""
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
        <details><summary><b>Stuck for 3 minutes? Open the answer - with each line explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put these 3 lines in its place** (same indent, 4 spaces):

        ```python
            route_back = net.route("BRANCH-7", "10.100.10.0/24").present          # 1. is the route back in the table?
            users_ok = net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1").success  # 2. can the branch LAN reach the service?
            return route_back and users_ok                                          # fixed = BOTH are true
        ```

        - **Line 1** is `show ip route 10.100.10.0/24` on BRANCH-7. `.present` is True if the route is there.
        - **Line 2** is `ping 10.100.10.10 source 10.20.20.1` - from the users' LAN, not from the router itself.
          `.success` is True if the ping works.
        - **Line 3** gives the answer back: fixed only if **both** are true. Without a `return` line the function
          answers `None`.

        The finished cell has **one** `def` line and ends with `return`:

        ```python
        def did_it_work(net) -> bool:
            # ...the description (between the triple quotes) stays here...
            route_back = net.route("BRANCH-7", "10.100.10.0/24").present
            users_ok = net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1").success
            return route_back and users_ok
        ```

        Run the cell, then run Step 4.
        </details>
        """)
    b.md("""
        ## Step 4 -- Check it
        This cell compares three things: what the **agent** said, what **your check** says, and what the
        **network** says (`reachability()` - the kit's own users' ping).

        Right now the network is still broken, so `reachability()` is **FAIL**, and a good check says **False**.
        They must agree. If you get *"your definition disagrees with the network"*, your check is too loose - most
        often "the interface is up". **Up isn't routed:** check the route and the ping.

        Then look at the device audit: what the agent changed on the router, and that nobody approved it.
        This check is the idea the team's **validator** runs automatically in Labs 3 and 4.
        """)
    b.code("""
        print("the agent says :", (run.final_text or "").strip().split("\\n")[0])   # first line is enough
        answer = did_it_work(net)
        assert answer is not None, "did_it_work returned None - keep ONE def line, and make the last line a return"
        print("did_it_work:", answer)
        print("reachability() =", net.reachability())
        assert answer == (net.reachability() == "PASS"), "your definition disagrees with the network"
        render.audit(net)
        """)
    return b
