from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab2_coordinator_specialist", "Lab 2 -- A Coordinator and a Troubleshooting Specialist",
                expect=["coordinator -> troubleshooting", "OSPF area mismatch", "Uplink interface flapping",
                        "acting on: OSPF area mismatch", "TRAJECTORY", "llm turns"])
    b.md("""
        Lab 1's agent did the work AND graded it. Split the job.

        Every agent speaks one message:
        `{from, to, intent: diagnose|propose|validate, task, payload, status: requested|done|needs_human}`.
        The **coordinator** routes messages and never touches a device. The **troubleshooting specialist** has
        read-only tools and runs a runbook (the on-call engineer's ordered checks) before the model reasons.
        """)
    b.code("""
        from netops.orchestrator import new_incident, ALERT, team
        from netops.protocol import Message
        inc = new_incident(llm=llm)
        coordinator = team(inc)           # registers troubleshooting / config / validation on the message bus
        """)
    b.md("## 1 -- Write the coordinator's first message")
    b.todo("lab2_message",
           student='''
            def diagnose_request() -> Message:
                """Build the coordinator's request to the troubleshooting specialist.
                Use Message(**{"from": ...}, to=..., intent=..., task=ALERT, status=...)."""
                raise NotImplementedError("TODO(lab2_message): build the diagnose message")
            ''',
           solution='''
            def diagnose_request() -> Message:
                return Message(**{"from": "coordinator"}, to="troubleshooting", intent="diagnose", task=ALERT,
                               status="requested")
            ''')
    b.code("""
        reply = inc.bus.send(diagnose_request())
        print("reply:", reply.from_, "->", reply.to, reply.intent, reply.status)
        from netops.agents.troubleshooting import Finding
        findings = [Finding(**f) for f in reply.payload["findings"]]
        render.findings(findings)
        render.transcript(inc.bus)
        assert {f.id for f in findings} == {"interface_flap", "ospf_area_mismatch"}, "both faults must be found"
        """)
    b.md("## 2 -- Which finding does the coordinator act on?")
    b.todo("lab2_choose",
           student='''
            def choose_root_cause(findings):
                """Return the ONE finding to act on, or None to escalate to a human.
                Each finding has .id .title .explains_outage .evidence_ids .narrative.
                Hint: the loudest finding is not necessarily the one that explains the outage."""
                raise NotImplementedError("TODO(lab2_choose): choose the root cause")
            ''',
           solution='''
            def choose_root_cause(findings):
                for f in findings:
                    if f.explains_outage:
                        return f
                return None
            ''')
    b.code("""
        coordinator.findings = findings
        coordinator.choose = choose_root_cause
        chosen = coordinator.decide()
        assert chosen is not None and chosen.id == "ospf_area_mismatch", f"you chose {chosen and chosen.title}"
        print("reachability() =", inc.network.reachability(), "-- nothing has been changed yet, by design")
        """)
    b.md("""
        **The flap was the understudy; the mismatch was the actor.** The coordinator found both and acted on the one
        that explains why the adjacency never came back. Next lab: who is allowed to propose a change, and how.
        """)
    b.md("""
        ## Stretch (optional, 5 min) -- grade the trajectory, and read the bill
        Did each approach *detect* the outage, *localize* it to BRANCH-7 Ethernet1, and name the *root cause*?
        Did it act on the red herring? Did it change anything without a gate? And what did it cost?

        Report the numbers, don't justify the pattern. If the team cost more and found nothing new, the single agent
        would win. (With MockLLM, the team is cheap because code -- the runbook and the detectors -- does work the
        single agent pushes through the model, and the single agent drags 400 log lines through every turn. With
        live models, multi-agent usually costs MORE tokens. Measure yours.)
        """)
    b.code("""
        from netops.scoring import measure_single, measure_team, scorecard, cost_table
        single = measure_single(llm)                       # Lab 1's agent, on a fresh incident
        diag = measure_team(llm, through="diagnosis")       # this lab's team: diagnose + decide, nothing applied
        print(scorecard(single["score"], diag["score"]), "\\n")
        print(cost_table(single["cost"], diag["cost"]))
        """)
    b.knowledge_check([
        ("""Which specialist gets tools that write to the network?""",
         """None of them. Troubleshooting, config and validation are read-only. The only writer is the executor
         -- plain code, not an AI -- and it needs a human's single-use approval token for the exact proposal."""),
        ("""The human rejects the same proposal three times. What should the coordinator do?""",
         """Not loop forever. Each rejection should carry a structured reason the next version must address (in
         this kit, the on-call engineer's reason goes into the v2 request). It should also refuse a revision that is a near-copy of
         the last one, and after a retry cap it stops proposing and escalates the diagnosis to a person. The kit
         enforces the cap: `Coordinator(max_rejections=3)` -- the third rejection raises `Escalation`, sends a
         `needs_human` message and applies nothing."""),
    ])
    return b
