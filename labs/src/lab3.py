from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab3_config_validation", "Lab 3 -- Propose from the Playbook, Validate Everything",
                expect=["BLOCKED", "needs_human", "FAIL  blast_radius_evidenced", "reachability() = FAIL"])
    b.md("""
        ## Lab 3 in one picture

        Lab 2 found the cause: **BRANCH-7's uplink is in the wrong OSPF area.** Now the team prepares the fix, the
        way a NOC prepares a **standard change**. Nothing touches the router in this lab.

        | Step | Who | What happens | Like in your NOC |
        |---|---|---|---|
        | 1 | **Config** specialist | picks the fix from the **playbook**. It never types free CLI | a change built from a pre-approved template - still signed by a human before it runs |
        | 2 | **Command gate** (code, **you write it**) | lets only the change's own commands through | command authorization on your TACACS server |
        | 3 | **Validation** specialist (code) | checks the proposal before anyone signs it | the CAB reviewer reading the ticket |
        | 4 | **Post-change check** (**you write it**) | says how we'll know the fix worked, written **before** the change | the verification steps in your MOP |
        | 5 | **You** (Lab 4) | approve or reject | the CAB |

        **You write two small things, 2 to 4 lines each:**
        1. **The command gate**: "is this command allowed?"
        2. **The post-change check**: "after the change, is the neighbor FULL **and** can the branch reach the service?"

        Stuck for 3 minutes? Every TODO has a folded answer under it. Open it, paste, and keep going.

        Nothing to set up: if the setup cell printed `MockLLM`, the lab still works, with a scripted stand-in model.

        **This cell** shows the one playbook entry we use. It only reads a file.
        """)
    b.code("""
        from netops.playbook import load_playbook
        entry = load_playbook()["ospf_area_mismatch"]
        print("THE STANDARD CHANGE:", entry.title)
        print()
        print("the fix (a template):               ", "  /  ".join(entry.fix), "   <- {uplink} = Ethernet1, {expected_area} = 0.0.0.0")
        print("the ONLY commands it may use:       ", entry.allowed_commands)
        print("how we'll know it worked (2 checks):", entry.expected_post_state)
        """)
    b.md("""
        **Read it like a change ticket:** the fix is a template with two lines. For tonight it becomes
        `interface Ethernet1` then `ip ospf area 0.0.0.0` (code fills in the blanks, the model never types them).
        Only commands starting with `interface` or `ip ospf area` are allowed. (The gate checks the command type only:
        the template has already pinned the interface to Ethernet1.) After the change, two things must be
        true: the OSPF neighbor is FULL, and the branch can reach the service.

        ## 1 -- Write the command gate (an ACL for commands)
        The model may *suggest* commands. Your gate decides which ones survive. Two rules:

        1. **Only listed commands.** A command passes if it **is** a listed command, or **starts with** one followed
           by a space. `interface Ethernet1` starts with `interface` + space, so it passes.
        2. **One command per line.** If it contains `;` `|` `&` or a new line, it could hide a second command
           (`ip ospf area 0.0.0.0; reload`). Block it.

        **Your gate must give exactly these answers** (the cell after yours tests them):

        | Command | Answer | Why |
        |---|---|---|
        | `interface Ethernet1` | ALLOW | starts with `interface` + space |
        | `ip ospf area 0.0.0.0` | ALLOW | starts with `ip ospf area` + space |
        | `router ospf 1` | BLOCKED | not on the list |
        | `clear ip ospf process` | BLOCKED | not on the list (it would reset OSPF on the whole box) |
        | `no ip ospf area` | BLOCKED | starts with `no`, not with a listed command |
        | `ip ospf area 0.0.0.0; reload` | BLOCKED | has a `;` - a hidden second command |

        **How to edit the cell below:** keep the `def allowed(...)` line and the description. Replace **only the
        last line**, `raise NotImplementedError(...)`, with your lines, indented like it. The comments tell you the
        two steps. Then run the cell (it prints nothing).
        """)
    b.todo("lab3_gate",
           student='''
            def allowed(command: str, allowed_commands: list[str]) -> bool:
                """True only if the command is exactly a listed command, or starts with a listed command
                followed by a space. Reject anything containing ; | & or a newline (one command per line)."""
                # step 1: if the command contains ; or | or & or a new line ("\\n") -> return False
                # step 2: return True if the command == a listed command, or starts with (listed command + " ")
                raise NotImplementedError("TODO(lab3_gate): write the command gate")
            ''',
           solution='''
            def allowed(command: str, allowed_commands: list[str]) -> bool:
                if any(ch in command for ch in ";|&\\n"):
                    return False
                cmd = " ".join(command.split())
                return any(cmd == p or cmd.startswith(p + " ") for p in allowed_commands)
            ''')
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Replace the `raise NotImplementedError(...)` line with these 4 lines** (same indent, 4 spaces):

        ```python
            if any(ch in command for ch in ";|&\\n"):    # step 1: a hidden second command?
                return False                            #         yes -> BLOCKED
            cmd = " ".join(command.split())              # optional: tidy double spaces ("ip  ospf area" -> "ip ospf area")
            return any(cmd == p or cmd.startswith(p + " ") for p in allowed_commands)   # step 2: on the list?
        ```

        In plain words: *if you see `;` `|` `&` or a new line, say no. Otherwise say yes only if the command is a
        listed one, or starts with a listed one plus a space.* The `+ " "` matters: without it, `interfaceX` would
        sneak through as `interface`.
        </details>
        """)
    b.md("""
        **This cell tests your gate** on the six commands from the table. You should see two **ALLOW** and four
        **BLOCKED**.

        - `NotImplementedError` = you haven't written the gate yet. Scroll up to the code cell with `TODO(lab3_gate)`.
        - *"gate wrong for ..."* names the command your gate got wrong. Most often: the `; reload` one (check for
          `;`) or `no ip ospf area` (it does not *start* with an allowed command).
        """)
    b.code("""
        rules = load_playbook()["ospf_area_mismatch"].allowed_commands
        tests = {"interface Ethernet1": True, "ip ospf area 0.0.0.0": True, "router ospf 1": False,
                 "clear ip ospf process": False, "no ip ospf area": False, "ip ospf area 0.0.0.0; reload": False}
        for cmd, want in tests.items():
            got = allowed(cmd, rules)
            assert got is not None, "allowed returned None - keep ONE def line, and make the last line a return"
            print(f"{'ALLOW' if got else 'BLOCKED':8} {cmd}")
            assert got == want, f"gate wrong for {cmd!r}"
        """)
    b.md("""
        ## 2 -- Watch: the team proposes the fix, and the gate catches an extra command
        **Nothing to write. Just run and read.** This cell runs the team: diagnose, decide, propose.
        If your setup cell printed `MockLLM` (the scripted stand-in), it suggests `clear ip ospf process` on purpose,
        an extra command nobody asked for. A live model may or may not. Both are fine.

        **What you should see, in plain words:**
        - `[config] BLOCKED before proposal ...` (always with MockLLM; with a live model only if it tried something
          extra): the gate threw out the extra command. It never reaches a human.
        - `status of the config reply: needs_human`: the proposal is ready and **waits for a person**.
        - Nothing touched the router.
        """)
    b.code("""
        from netops.llm import MockLLM
        from netops.orchestrator import new_incident, ALERT, team
        # tempt=True: the stand-in also suggests `clear ip ospf process`. Live models sometimes do; the gate blocks it either way.
        inc = new_incident(llm=llm if type(llm).__name__ != "MockLLM" else MockLLM(tempt=True))
        c = team(inc)                    # c = the coordinator; it asks the specialists, one message at a time
        c.diagnose(ALERT); c.decide()    # Lab 2 again: find the cause, pick the YES card
        proposal = c.propose()           # asks the Config specialist for the fix; its answer is the 'config reply'
        print("status of the config reply:", inc.bus.transcript[-1].status)
        """)
    b.md("""
        ## 3 -- Write the post-change check (before the change)
        Like the verification steps you write in a MOP **before** the change window. Written after the change,
        people tend to check whatever happens to look good.

        The check has two parts, and **both** must be true:
        1. **The OSPF neighbor on BRANCH-7 Ethernet1 is FULL**, like `show ip ospf neighbor` on BRANCH-7;
        2. **The branch reaches the core service**: `net.reachability()` returns `"PASS"`.

        FULL alone is not enough: an adjacency can be FULL while the route is still missing. The users only care
        about the second part.

        **First, look at the data you'll check.** This cell only reads. Today the network is still broken.
        """)
    b.code("""
        net = inc.network
        print("BRANCH-7 neighbors:", net.ospf_neighbors("BRANCH-7"), "  <- empty: the broken branch has no neighbor")
        print()
        print("BRANCH-8 neighbors (the healthy branch, to see what FULL looks like):")
        for n in net.ospf_neighbors("BRANCH-8"):
            print(f"   n.interface = {n.interface!r}   n.state = {n.state!r}")
        print()
        print("net.reachability() =", repr(net.reachability()), "  <- 'PASS' when users reach the service, 'FAIL' now")
        """)
    b.md("""
        **So your check is:** "is there a neighbor on BRANCH-7 with `interface == "Ethernet1"` and `state == "full"`?"
        **and** "is `net.reachability()` equal to `"PASS"`?". Return True only if both are true.

        **How to edit the cell below:** keep the `def post_state_ok(net) -> bool:` line and the description.
        Replace **only the last line**, `raise NotImplementedError(...)`, with your lines. The comments tell you
        the two steps. Then run the cell (it prints nothing).
        """)
    b.todo("lab3_post_state",
           student='''
            def post_state_ok(net) -> bool:
                """Both must hold: a BRANCH-7 neighbor on "Ethernet1" with state "full" (lowercase),
                AND net.reachability() == "PASS". Use only these two calls."""
                # step 1: full = is there a neighbor n in net.ospf_neighbors("BRANCH-7")
                #                with n.interface == "Ethernet1" and n.state == "full"?
                # step 2: return full and net.reachability() == "PASS"
                raise NotImplementedError("TODO(lab3_post_state): check the expected post-state")
            ''',
           solution='''
            def post_state_ok(net) -> bool:
                full = any(n.interface == "Ethernet1" and n.state == "full" for n in net.ospf_neighbors("BRANCH-7"))
                return full and net.reachability() == "PASS"
            ''')
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Replace the `raise NotImplementedError(...)` line with these 2 lines** (same indent, 4 spaces):

        ```python
            full = any(n.interface == "Ethernet1" and n.state == "full" for n in net.ospf_neighbors("BRANCH-7"))  # step 1
            return full and net.reachability() == "PASS"   # step 2: FULL AND the users reach the service
        ```

        In plain words: *look at BRANCH-7's neighbors; is one on Ethernet1 FULL? And can the users reach the
        service? Say yes only if both are true.*
        </details>
        """)
    b.md("""
        ## 4 -- Watch: the proposal goes to the human gate
        **Nothing to write.** This cell sends the proposal to validation, which checks it, and then it **waits for a
        human**. Your check from step 3 runs too.

        **What you should see, in plain words:**
        - a list of pre-checks, all **PASS** except one: **FAIL  blast_radius_evidenced** (= *"did anyone check what else uses this link?"*). The validator asks
          *"what else rides on this link? Show me the neighbor tables on BOTH ends."* Nobody has read HUB-1's
          neighbor table yet, so the proof is missing;
        - `ready for approval: False`: a human should not sign this yet;
        - `post_state_ok: False`, which is correct: nothing was changed, so the network is still broken;
        - `reachability() = FAIL` and an empty device audit: **nothing was applied**.

        Errors you may see:
        - `NotImplementedError` = you haven't written step 3 yet. Scroll up to the code cell with `TODO(lab3_post_state)`.
        - *"nothing was applied, so the post-state must still be false"* = your check is too loose. Check FULL
          **and** reachability.
        """)
    b.code("""
        gate = c.request_approval(proposal)   # validation pre-checks, then the request waits for a human
        render.gate(gate)
        ok = post_state_ok(inc.network)
        assert ok is not None, "post_state_ok returned None - keep ONE def line, and make the last line a return"
        assert not ok, "nothing was applied, so the post-state must still be false"
        print("post_state_ok:", ok, "  <- False is correct: nothing was applied yet")
        print("reachability() =", inc.network.reachability(), "-- proposed, validated, NOT applied")
        render.audit(inc.network)
        """)
    b.md("""
        **Where we are:** the fix is ready, only allowed commands are in it, and you know how to check it worked.
        But the validator says the proof of "what else breaks" is missing. **That's how Lab 4 starts:** you, the
        on-call engineer, reject it and ask for the neighbor tables on both ends.
        """)
    b.knowledge_check([
        ("""The model proposes `no router ospf 1`. What happens?""",
         """The command gate rejects it before a proposal exists: it is not prefixed by any `allowed_commands`
         entry of the playbook. It never reaches the human, and it never reaches the router."""),
        ("""Your check reads the network once. After a real change, why should it be re-run for about 20
         seconds before anyone calls the change a failure?""",
         """OSPF needs time to converge. On the live lab's Arista routers (cEOS) the neighbor reaches FULL 3-9 s
         after the fix and the route arrives 9-16 s after it. One immediate read would call a working fix a
         failure. That's why the kit's validator keeps re-checking for a while (it polls) before it decides."""),
    ])
    return b
