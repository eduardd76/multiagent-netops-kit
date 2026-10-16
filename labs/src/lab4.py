from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab4_full_team", "Lab 4 -- The Team Resolves It. A Human Holds the Gate.",
                expect=["needs_human", "Approved v2", "RESOLVED.", "reachability() = PASS", "Lab 4 (team)", "ON-CALL CHECKLIST", "THREE ARTIFACTS", "TRAJECTORY", "llm turns"])
    b.md("""
        Everything together: coordinator -> troubleshooting -> config -> validation -> **human** -> executor ->
        validation. Nothing is applied until a person approves the exact commands. The approval is a single-use token
        bound to that exact proposal; the executor (not an AI) applies it and backs out automatically if OSPF doesn't
        come up.
        """)
    b.code("""
        from netops.orchestrator import new_incident, ALERT, ONCALL_REJECT, team, run_lab1, contrast
        APPROVER = "your-name"        # put YOUR name: you are the on-call engineer holding the gate
        inc = new_incident(llm=llm)
        gate = team(inc, APPROVER).run_to_gate(ALERT)
        render.gate(gate)
        """)
    b.md("## 1 -- Your approval policy (it belongs to the human, not to the author)")
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
    b.code("""
        from netops.agents.coordinator import Escalation
        decision, reasons = review(gate)
        print(f"{APPROVER}: {decision.upper()}", reasons)
        while decision == "reject":
            try:
                gate = gate.reject(reasons)    # the team revises; after 3 rejections it stops and escalates
            except Escalation as e:
                raise SystemExit(f"{e}. Your policy never approves -- fix review() and re-run this cell.")
            render.gate(gate)
            decision, reasons = review(gate)
            print(f"{APPROVER}: {decision.upper()}", reasons)
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
    b.md("## 2 -- Lab 1 vs Lab 4")
    b.code("""
        lab1 = run_lab1(new_incident(llm=llm, verbose=False))
        print(contrast(lab1, result))
        """)
    b.md("""
        ## 3 -- Debrief: what this change leaves behind
        Three artifacts per action: the **proposal**, the **validation report**, the **approval record**. In a
        regulated network the audit trail is the product. Then the scorecard and the bill for both approaches --
        report the numbers, don't justify the pattern.
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
