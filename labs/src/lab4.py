from labs.src.nb import TEAM_MD, LabBook


def book() -> LabBook:
    b = LabBook("lab4_full_team", "Lab 4 -- The Team Resolves It. A Human Holds the Gate.",
                expect=["needs_human", "Approved v2", "RESOLVED.", "reachability() = PASS", "Lab 4 (team)", "ON-CALL CHECKLIST", "THREE ARTIFACTS", "TRAJECTORY", "llm turns"])
    b.md("""
        **Lab 4 in one line** - the whole team, with you in the middle:

        `coordinator -> troubleshooting -> config -> validation -> YOU (the CAB) -> executor -> validation`

        - Nothing touches the router until **you** approve the exact commands.
        - Your approval becomes an **approval token**: usable once, and only for that exact change.
        - The **executor** applies it. It is plain code, not AI, and it backs out by itself if OSPF doesn't come up.
        """)
    b.md(TEAM_MD)
    b.md("""
        **What this does:** builds a fresh broken network and runs the team up to the **gate** (the CAB step):
        diagnose, propose, pre-check. Nothing applied.

        - `APPROVER` = your name. You are the on-call engineer.
        - `gate` = the change request now waiting for you.
        - `render.gate(gate)` = prints it like a change ticket.

        **Your job:** replace `"your-name"` with your name, then run.

        **What you'll see** at the bottom: `FAIL  blast_radius_evidenced` and `ready for approval: False`.
        Nobody read the neighbor tables on both ends.
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
        You are the **CAB**: the team designed the change, you approve or reject it.
        The on-call rule: **never approve while any pre-check fails.** A failing pre-check is like a change ticket
        with no rollback plan - you send it back with the reason.
        """)
    b.md("""
        **The rule in code.** `gate.pre_checks` is a list, one item per check: `{"check": ..., "ok": True/False, "detail": ...}`

        `review(gate)` must return a **pair** `(decision, reasons)`:

        | pre-checks | return |
        |---|---|
        | any `ok` is False | `("reject", ONCALL_REJECT)` |
        | all pass | `("approve", "")` |

        `ONCALL_REJECT` = the on-call engineer's written reason, ready in the kit. The team must fix it in v2.
        """)
    b.md("""
        **What this does:** defines your policy, `review`. The next cell uses it.

        **Your job:** keep the `def review(gate) -> tuple[str, str]:` line and the description. Replace **only**
        the last line, `raise NotImplementedError(...)`, with your lines, same indent. Do **not** write a second
        `def` line.

        **What you'll see:** nothing. This cell only defines the function.
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

        - **Line 1** keeps only the failed pre-checks (`ok` is False).
        - **Line 2** asks: is that list empty or not?
        - **Line 3** rejects, with the on-call reason, so v2 must fix it.
        - **Line 4** approves only when nothing failed. Without a `return` line the function answers `None`.

        The finished cell has **one** `def` line and ends with `return`. Run it, then run the next cell.
        </details>
        """)
    b.md("""
        **What this does:** the CAB meeting. Your `review` judges the gate. On reject, the team reads the neighbor
        tables on both ends and comes back with **v2**. Nothing is applied yet: you only set `decision` here.

        **What you'll see** (with your name):
        - `your-name: REJECT No. You're telling me what to type. ...`
        - `CHANGE REQUEST v2` with `PASS  blast_radius_evidenced: neighbor tables on both ends cited`
          and `ready for approval: True`
        - `your-name: APPROVE`
        """)
    b.md("""
        **If it stops:**
        - `NotImplementedError` - you haven't written `review` yet. Your turn: go up one cell.
        - `review returned None` - keep ONE `def` line, and make the last line a `return`.
        - `Your policy never approves` - the kit caps rejections at **3**, then the team stops and **ESCALATES**
          to a person (nothing applied). Your `review` rejects even when every pre-check passes: check line 4.
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
        **What this does:** you sign v2. **Only now does anything touch the router.**

        - `gate.approve(APPROVER)` creates the **approval token** (single-use, valid only for v2) and hands it
          only to the executor.
        - The executor (plain code, not AI) applies the 2 commands once. Validation then re-checks until OSPF is
          FULL, the route is back and the ping works.

        **What you'll see:** `Approved v2.`, then `RESOLVED. reachability() = PASS`, the `DEVICE CHANGE AUDIT`
        (one change, by `executor:` + your name) and `>>> RESOLVED. <<<`.
        """)
    b.md("""
        **If it stops:**
        - `GateError: v2 was already approved and applied ...` - you ran this cell twice. One approval = one
          write; the gate refuses a second. That's the design, not a bug.
        - `GateError: pre-checks are failing ...` - your `review` approved v1 with a FAIL. Fix `review`.
        - `NameError: result` after a GateError - re-run from the first cell of this lab for a fresh incident.
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
        **What this does:** re-runs Lab 1's single agent on a fresh incident and puts it next to your team's run.

        **What you'll see:** a table with columns `Lab 1 (one agent)` and `Lab 4 (team)`. How to read it:
        - `Says 'resolved'`: True for **both** - an agent's "resolved" proves nothing.
        - `reachability()`: `FAIL` vs `PASS` - only the team really fixed it.
        - Last three rows (playbook, human approval, validation): the difference. Read `A human approved the change` first.
        """)
    b.code("""
        lab1 = run_lab1(new_incident(llm=llm, verbose=False))
        print(contrast(lab1, result))
        """)
    b.md("""
        ## 3 -- Debrief: what this change leaves behind
        In a regulated network the audit trail is the product. Every action leaves **three artifacts**:

        1. **Proposal** - the commands, the rollback, the evidence.
        2. **Validation report** - every pre-check and post-check.
        3. **Approval record** - who approved, and proof the approval token was used once
           (`event=consumed`). `digest=` is a fingerprint of the exact change that was approved.
        """)
    b.md("""
        **What this does:** prints the three artifacts, then runs two fresh incidents (single agent vs team, same
        alert) and scores both. Takes a few seconds.

        **What you'll see:**
        - `THREE ARTIFACTS PER ACTION`
        - `TRAJECTORY` - who found the real cause, who chased the flap (`acted on the red herring (flap)`),
          who changed devices outside a gate.
        - `COST` - `llm turns` and model tokens (`~input tokens`).

        Report the numbers, don't justify the pattern. If the team costs more, say so.
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
         *proposes*; evidence grounds it; validation checks it; a human *disposes*. The approval token is minted
         only on the human's action and is bound to the exact proposal."""),
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
