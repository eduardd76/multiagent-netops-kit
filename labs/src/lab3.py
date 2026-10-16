from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab3_config_validation", "Lab 3 -- Propose from the Playbook, Validate Everything",
                expect=["BLOCKED", "needs_human", "FAIL  blast_radius_evidenced", "reachability() = FAIL"])
    b.md("""
        Lab 2's team found the root cause. Now somebody has to **propose the fix** - and somebody else has to
        **check it**. Like a change ticket in a real NOC:

        - the **config specialist** never types free CLI. It picks an entry from the **playbook** (your approved
          standard changes), and the playbook writes the commands;
        - a **command gate** - like an ACL for commands - blocks anything not on the playbook's `allowed_commands`
          list, *before* a proposal even exists;
        - the **validation specialist** re-reads the live network and checks the proposal against the playbook.

        You write two small things: the command gate, and the post-change check.

        **This cell** prints the playbook. You should see an entry `ospf_area_mismatch` with its
        `allowed_commands` and its `expected_post_state`. Nothing is changed - it only reads a file.
        """)
    b.code("""
        from netops.playbook import load_playbook
        print(open(__import__("netops").__path__[0] + "/playbook.yaml").read())
        """)
    b.md("""
        ## 1 -- Write the command gate
        Think of it as an **ACL for commands**. The playbook says which commands this change may use
        (`allowed_commands`). Every command the model suggests must match that list - or it is dropped.

        Two rules, both from real change control:

        1. **Only listed commands.** A command is allowed if it *is* a listed command, or starts with one and then
           a space (so `interface Ethernet1` matches `interface`). `router ospf 1` is not on the list - blocked.
        2. **One command per line.** Anything with `;`, `|`, `&` or a new line could hide a second command
           (`ip ospf area 0.0.0.0; reload`). Block it, no questions asked.

        **How to edit the cell below:** keep the `def allowed(command: str, allowed_commands: list[str]) -> bool:`
        line and the description. Delete **only the last line**, `raise NotImplementedError(...)`, and put your lines
        in its place, indented like the line you deleted. Do **not** write a second `def` line. Then run the cell.

        Running this cell prints nothing - it only defines the gate. The next cell tests it.
        """)
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
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put these 4 lines in its place** (same indent, 4 spaces):

        ```python
            if any(ch in command for ch in ";|&\\n"):    # 1. a hidden second command? (; | & or a new line)
                return False                            # 2. yes - block it, no questions asked
            cmd = " ".join(command.split())              # 3. tidy the spaces: "ip  ospf   area" -> "ip ospf area"
            return any(cmd == p or cmd.startswith(p + " ") for p in allowed_commands)   # 4. on the list?
        ```

        - **Line 1** looks at every character of the command. If any is `;`, `|`, `&` or a new line, someone is
          trying to chain two commands.
        - **Line 2** blocks it. `return False` = BLOCKED.
        - **Line 3** squeezes extra spaces, so `ip  ospf area` can't sneak past the list check.
        - **Line 4** is the ACL: True if the command *is* a listed one, or starts with a listed one plus a space.
          `p + " "` matters: without it, `interfaceX` would match `interface`.

        The finished cell has **one** `def` line and ends with that `return`. Run it, then run the next cell.
        </details>
        """)
    b.md("""
        **This cell tests your gate** on six commands. You should see two **ALLOW** lines
        (`interface Ethernet1`, `ip ospf area 0.0.0.0`) and four **BLOCKED** lines.

        - `NotImplementedError` here means you haven't written the gate yet - it's your turn, go up one cell.
        - *"gate wrong for ..."* names the command your gate got wrong. Most often: the `; reload` one
          (check for `;`) or `no ip ospf area` (it does not *start* with an allowed command).
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
        ## 2 -- The team proposes. A model that 'helpfully' adds an extra command gets gated.
        **This cell** runs the team up to the proposal: diagnose, decide, propose. On purpose, the stand-in model
        also suggests `clear ip ospf process` - an extra command nobody asked for. Live models sometimes do this.

        You should see a `[config] BLOCKED before proposal` line and a config reply with status **needs_human**:
        the gate threw out the extra command, and the proposal now waits for a person. Nothing touched the router.
        """)
    b.code("""
        from netops.llm import MockLLM
        from netops.orchestrator import new_incident, ALERT, team
        # tempt=True: the stand-in also suggests `clear ip ospf process`. Live models sometimes do; the gate blocks it either way.
        inc = new_incident(llm=llm if type(llm).__name__ != "MockLLM" else MockLLM(tempt=True))
        c = team(inc)
        c.diagnose(ALERT); c.decide()
        proposal = c.propose()
        print("status of the config reply:", inc.bus.transcript[-1].status)
        """)
    b.md("""
        ## 3 -- Validation: what must be true AFTER the change? (defined before anything is touched)
        This is your **post-change verification**, written *before* the change window - like the checklist you
        attach to the change ticket for the CAB. If you write it after the change, you tend to check whatever
        happens to look good.

        The playbook's `expected_post_state` says two things must be true:

        1. **OSPF neighbor is FULL** on BRANCH-7 Ethernet1 - like `show ip ospf neighbor` on BRANCH-7;
        2. **The branch can reach the core service** - `net.reachability()` returns `"PASS"`.

        Both, not one. An adjacency that is FULL but no route is still an outage for the users.

        **How to edit the cell below:** keep the `def post_state_ok(net) -> bool:` line and the description.
        Delete **only the last line**, `raise NotImplementedError(...)`, and put your lines in its place,
        indented like the line you deleted. Do **not** write a second `def` line. Then run the cell.

        Running this cell prints nothing - it only defines the check.
        """)
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
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put these 2 lines in its place** (same indent, 4 spaces):

        ```python
            full = any(n.interface == "Ethernet1" and n.state == "full" for n in net.ospf_neighbors("BRANCH-7"))  # 1. neighbor FULL on Ethernet1?
            return full and net.reachability() == "PASS"   # 2. FULL AND the users reach the service
        ```

        - **Line 1** is `show ip ospf neighbor` on BRANCH-7: it looks at every neighbor and is True if one on
          `Ethernet1` is in state `full`.
        - **Line 2** gives the answer back: True only if the adjacency is FULL **and** `reachability()` is PASS.
          Without a `return` line the function answers `None`.

        The finished cell has **one** `def` line and ends with that `return`. Run it, then run the next cell.
        </details>
        """)
    b.md("""
        **This cell asks for approval** - and stops there. Validation pre-checks the proposal, then the request
        waits for a human. You should see the gate with one failing pre-check,
        **FAIL  blast_radius_evidenced**, then `reachability() = FAIL` and the device audit: nothing applied.

        Your `post_state_ok` must say **False** here - nothing was changed, so the network is still broken.

        - `NotImplementedError` here means you haven't written step 3 yet - it's your turn, go up one cell.
        - *"nothing was applied, so the post-state must still be false"* means your check is too loose -
          check both the FULL neighbor and the reachability.
        """)
    b.code("""
        gate = c.request_approval(proposal)   # validation pre-checks, then the request waits for a human
        render.gate(gate)
        ok = post_state_ok(inc.network)
        assert ok is not None, "post_state_ok returned None - keep ONE def line, and make the last line a return"
        assert not ok, "nothing was applied, so the post-state must still be false"
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
