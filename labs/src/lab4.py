from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab4_full_team", "Lab 4 -- The Team Resolves It. A Human Holds the Gate.",
                expect=["needs_human", "Approved v2", "RESOLVED.", "reachability() = PASS", "Lab 4 (team)", "ON-CALL CHECKLIST", "THREE ARTIFACTS", "TRAJECTORY", "llm turns"])
    b.md("""
        Everything together: coordinator -> troubleshooting -> config -> validation -> **human** -> executor ->
        validation. Nothing is applied until a person approves the exact commands. The approval is a single-use token
        bound to that exact proposal; the executor (not an AI) applies it and backs out automatically if OSPF doesn't
        come up.

        **This cell** builds a fresh broken network and runs the team all the way to the **human gate**: diagnose,
        decide, propose, validate. Put your name in `APPROVER` - you are the on-call engineer.

        You should see the gate: the proposed commands and the pre-checks, with one **FAIL**
        (the blast radius isn't backed by evidence from both ends of the link - Lab 3's ending). Nothing is applied yet.
        """)
    b.code("""
        from netops.orchestrator import new_incident, ALERT, ONCALL_REJECT, team, run_lab1, contrast
        APPROVER = "your-name"        # put YOUR name: you are the on-call engineer holding the gate
        inc = new_incident(llm=llm)
        gate = team(inc, APPROVER).run_to_gate(ALERT)
        render.gate(gate)
        """)
    b.md("""
        ## 1 -- Your approval policy (it belongs to the human, not to the author)
        You are the **CAB** for this change. The team designed it; you decide. Your rule is the on-call rule:
        **never approve while any pre-check fails.** A failing pre-check is like a change ticket with a missing
        rollback plan - you send it back with the reason, you don't sign it "just this once".

        `gate.pre_checks` is a list. Each pre-check looks like `{"check": ..., "ok": True/False, "detail": ...}`.

        - If **any** pre-check has `ok` False: answer `("reject", ONCALL_REJECT)` - `ONCALL_REJECT` is the
          on-call engineer's written reason, ready in the kit. The team reads it and must fix it in v2.
        - If **all** pass: answer `("approve", "")`.

        **How to edit the cell below:** keep the `def review(gate) -> tuple[str, str]:` line and the description.
        Delete **only the last line**, `raise NotImplementedError(...)`, and put your lines in its place,
        indented like the line you deleted. Do **not** write a second `def` line. Then run the cell.

        Running this cell prints nothing - it only defines your policy.
        """)
    b.todo("lab4_review",
           student='''
            def review(gate) -> tuple[str, str]:
                """Return ("approve", "") or ("reject", reasons). gate.pre_checks is a list of
                {"check", "ok", "detail"}. The on-call rule: never approve while any pre-check fails."""
                raise NotImplementedError("TODO(lab4_review): write your approval policy")
            ''',
           solution='''
            def review(gate) -> tuple[str, str]:
                failing = [c for c in gate.pre_checks if not c["ok"]]
                if failing:
                    return "reject", ONCALL_REJECT
                return "approve", ""
            ''')
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put these 4 lines in its place** (same indent, 4 spaces):

        ```python
            failing = [c for c in gate.pre_checks if not c["ok"]]   # 1. list every pre-check that failed
            if failing:                                              # 2. is there at least one?
                return "reject", ONCALL_REJECT                       # 3. yes - send it back, with the reason
            return "approve", ""                                     # 4. all green - approve
        ```

        - **Line 1** walks the pre-checks and keeps only the failed ones (`ok` is False).
        - **Line 2** asks: is that list empty or not?
        - **Line 3** rejects, and gives the team the on-call engineer's reason, so v2 must fix it.
        - **Line 4** approves only when nothing failed. Without a `return` line the function answers `None`.

        The finished cell has **one** `def` line and ends with `return`. Run it, then run the next cell.
        </details>
        """)
    b.md("""
        **This cell runs your policy on the gate.** You should see **REJECT** for v1 with the reason, then the team
        revises, a new gate (v2) with all pre-checks passing, and **APPROVE**. Your answer sets `decision`; the
        actual approval happens in the next cell.

        - `NotImplementedError` here means you haven't written your policy yet - it's your turn, go up one cell.
        - *"Your policy never approves"* means `review()` rejects even when every pre-check passes - check line 4.
        """)
    b.code("""
        from netops.agents.coordinator import Escalation
        answer = review(gate)
        assert answer is not None, "review returned None - keep ONE def line, and make the last line a return"
        decision, reasons = answer
        print(f"{APPROVER}: {decision.upper()}", reasons)
        while decision == "reject":
            try:
                gate = gate.reject(reasons)    # the team revises; after 3 rejections it stops and escalates
            except Escalation as e:
                raise SystemExit(f"{e}. Your policy never approves -- fix review() and re-run this cell.")
            render.gate(gate)
            answer = review(gate)
            assert answer is not None, "review returned None - keep ONE def line, and make the last line a return"
            decision, reasons = answer
            print(f"{APPROVER}: {decision.upper()}", reasons)
        """)
    b.md("""
        **This cell approves - and only now does anything touch the router.** Your approval mints a single-use
        token bound to v2; the executor (plain code, not an AI) applies the exact commands, and validation
        re-checks the network. You should see **Approved v2** in the transcript, **RESOLVED.**,
        `reachability() = PASS`, the device audit, and a green dashboard.

        - *GateError* means you ran this cell twice: one approval = one write, the gate refuses a second.
          That's the design, not a bug.
        - `NameError: result` after a GateError: re-run from the first cell of this lab for a fresh incident.
        """)
    b.code("""
        from netops.approval import GateError
        try:
            result = gate.approve(APPROVER)  # token minted here, handed only to the executor
        except GateError as e:               # re-ran this cell? one approval = one write: the gate refuses a second
            print("GateError:", e)
        render.transcript(inc.bus)
        print("\\nreachability() =", result["reachability"])
        render.audit(inc.network)
        render.dashboard(result["reachability"])
        assert result["resolved"]
        """)
    b.md("""
        ## 2 -- Lab 1 vs Lab 4
        **This cell** re-runs Lab 1's single agent on a fresh incident and puts it next to your team's run.
        You should see a side-by-side table (**Lab 4 (team)** column): who changed what, who approved it, and
        whether the network is really fixed. Read the approval row first.
        """)
    b.code("""
        lab1 = run_lab1(new_incident(llm=llm, verbose=False))
        print(contrast(lab1, result))
        """)
    b.md("""
        ## 3 -- Debrief: what this change leaves behind
        Three artifacts per action: the **proposal**, the **validation report**, the **approval record**. In a
        regulated network the audit trail is the product. Then the scorecard and the bill for both approaches --
        report the numbers, don't justify the pattern.

        **This cell** prints the three artifacts, then the **TRAJECTORY** scorecard and the bill (`llm turns`,
        tokens) for the single agent vs the full team. It runs two fresh incidents, so it takes a few seconds.
        If the team costs more, say so - that's the honest number.
        """)
    b.code("""
        render.artifacts(gate, inc.approvals)
        from netops.scoring import measure_single, measure_team, scorecard, cost_table
        single, full = measure_single(llm), measure_team(llm)        # fresh incidents, same alert
        print()
        print(scorecard(single["score"], full["score"]), "\\n")
        print(cost_table(single["cost"], full["cost"]))
        """)
    b.knowledge_check([
        ("""The config specialist designed the change. Why can't it (or the coordinator) approve it?""",
         """Separation of duties: whoever designs a change does not approve it (four-eyes). The model
         *proposes*; evidence grounds it; validation checks it; a human *disposes*. The token is minted only on
         the human's action and is bound to the exact proposal."""),
        ("""After a month the approver clicks "approve" on everything in 10 seconds. What do you change?""",
         """That is automation bias (rubber-stamping). Show the measured before/after evidence delta, not a
         confidence score; make the human-owned checklist rows explicit; track how often approved changes are
         reversed. A rising reversal rate or falling review time is a signal, not a success."""),
    ])
    b.md("""
        > A single agent will always find you an answer. A team -- with a human at the gate -- is what finds you the
        > right one. **AI proposes. Humans dispose.**
        """)
    return b
