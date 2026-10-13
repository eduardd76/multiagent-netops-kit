from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab3_config_validation", "Lab 3 -- Propose from the Playbook, Validate Everything",
                expect=["BLOCKED", "needs_human", "FAIL  blast_radius_evidenced", "reachability() = FAIL"])
    b.md("""
        The config specialist never writes CLI. It picks a **playbook** entry; the playbook renders the commands;
        a **command gate** rejects anything not in `allowed_commands` *before* a proposal even exists.
        The validation specialist re-reads the live network and checks the proposal against the playbook.
        """)
    b.code("""
        from netops.playbook import load_playbook
        print(open(__import__("netops").__path__[0] + "/playbook.yaml").read())
        """)
    b.md("## 1 -- Write the command gate")
    b.todo("lab3_gate",
           student='''
            def allowed(command: str, allowed_commands: list[str]) -> bool:
                """True only if the command IS an allowed prefix, or starts with one followed by a space.
                Reject anything containing ; | & or a newline (one command per line)."""
                raise NotImplementedError("TODO(lab3_gate): write the command gate")
            ''',
           solution='''
            def allowed(command: str, allowed_commands: list[str]) -> bool:
                if any(ch in command for ch in ";|&\\n"):
                    return False
                cmd = " ".join(command.split())
                return any(cmd == p or cmd.startswith(p + " ") for p in allowed_commands)
            ''')
    b.code("""
        rules = load_playbook()["ospf_area_mismatch"].allowed_commands
        tests = {"interface Ethernet1": True, "ip ospf area 0.0.0.0": True, "router ospf 1": False,
                 "clear ip ospf process": False, "no ip ospf area": False, "ip ospf area 0.0.0.0; reload": False}
        for cmd, want in tests.items():
            got = allowed(cmd, rules)
            print(f"{'ALLOW' if got else 'BLOCKED':8} {cmd}")
            assert got == want, f"gate wrong for {cmd!r}"
        """)
    b.md("## 2 -- The team proposes. A model that 'helpfully' adds an extra command gets gated.")
    b.code("""
        from netops.llm import MockLLM
        from netops.orchestrator import new_incident, ALERT, team
        # tempt=True: the stand-in model also suggests `clear ip ospf process` (live models do this too).
        inc = new_incident(llm=llm if type(llm).__name__ != "MockLLM" else MockLLM(tempt=True))
        c = team(inc)
        c.diagnose(ALERT); c.decide()
        proposal = c.propose()
        print("status of the config reply:", inc.bus.transcript[-1].status)
        """)
    b.md("## 3 -- Validation: what must be true AFTER the change? (defined before anything is touched)")
    b.todo("lab3_post_state",
           student='''
            def post_state_ok(net) -> bool:
                """The playbook's expected_post_state: 'ospf neighbor state = FULL' AND 'branch l3 reachable = true'.
                Check both with read tools (net.ospf_neighbors, net.ping or net.reachability)."""
                raise NotImplementedError("TODO(lab3_post_state): check the expected post-state")
            ''',
           solution='''
            def post_state_ok(net) -> bool:
                full = any(n.interface == "Ethernet1" and n.state == "full" for n in net.ospf_neighbors("BRANCH-7"))
                return full and net.reachability() == "PASS"
            ''')
    b.code("""
        gate = c.request_approval(proposal)   # validation pre-checks, then the request waits for a human
        render.gate(gate)
        assert not post_state_ok(inc.network), "nothing was applied, so the post-state must still be false"
        print("reachability() =", inc.network.reachability(), "-- proposed, validated, NOT applied")
        render.audit(inc.network)
        """)
    b.md("""
        The proposal reached the human gate with one failing check: the blast radius isn't backed by evidence from
        *both* ends of the link. That's Lab 4's opening scene.
        """)
    b.knowledge_check([
        ("""The model proposes `no router ospf 1`. What happens?""",
         """The command gate rejects it before a proposal exists: it is not prefixed by any `allowed_commands`
         entry of the playbook. It never reaches the human, and it never reaches the router."""),
        ("""Why does validation poll after the change instead of reading the state once?""",
         """Convergence takes time. On real cEOS the adjacency reaches FULL 3-9 s after the fix and the route
         arrives 9-16 s after it. One immediate read would report a failure for a fix that works (or, worse,
         teach you to skip the check)."""),
    ])
    return b
