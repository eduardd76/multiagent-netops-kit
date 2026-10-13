from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("lab1_single_agent", "Lab 1 -- One Agent, Every Tool",
                expect=["Incident resolved", "reachability() = FAIL", "did_it_work: False", "Expecting value: line 1 column 1 (char 0)", "guard : invalid_output | submitted: None", "STRETCH (mtu_mismatch)"])
    b.md("""
        **03:14.** Users at **BRANCH-7** can't reach the core service. The dashboard is green: no alarm, no threshold,
        nothing red. The network is a simulated Arista cEOS fabric (the same agent code runs on real cEOS).

        You'll do what most demos do: give **one** agent every tool -- including tools that change the network -- and
        let it work the incident.
        """)
    b.md("## 1 -- Look at it like the on-call engineer")
    b.code("""
        from netops.orchestrator import new_incident, ALERT
        inc = new_incident(llm=llm)
        net = inc.network
        print(ALERT, "\\n")
        print("reachability():", net.reachability())
        print("OSPF neighbors on BRANCH-7:", net.ospf_neighbors("BRANCH-7"))
        logs = net.logs("BRANCH-7")
        print(f"\\nshow logging -- {len(logs)} lines. The last five:")
        for l in logs[-5:]:
            print("  ", l.ts.time(), l.text)
        render.dashboard(None)
        """)
    b.md("## 2 -- One agent, every tool, no gate. Watch its reasoning.")
    b.code("""
        from netops.agents.single import SingleAgent
        run = SingleAgent(llm, net, inc.evidence).run(ALERT, trace=inc.trace)
        """)
    b.md("""
        ## 3 -- It has an answer. You decide what "it worked" means.
        Write `did_it_work(net)` with READ tools only. Whatever you choose becomes the Validation agent later.
        """)
    b.todo("lab1_did_it_work",
           student='''
            def did_it_work(net) -> bool:
                """True only if the incident is really resolved. Read tools you can use:
                net.ping(device, destination, source), net.route(device, prefix), net.ospf_neighbors(device),
                net.interface(device, interface).   3-5 lines."""
                raise NotImplementedError("TODO(lab1_did_it_work): define success")
            ''',
           solution='''
            def did_it_work(net) -> bool:
                """Success = users reach the service (and the route is back). Not 'the logs went quiet'."""
                route_back = net.route("BRANCH-7", "10.100.10.0/24").present
                users_ok = net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1").success
                return route_back and users_ok
            ''')
    b.code("""
        print("the agent says :", run.final_text)
        print("did_it_work:", did_it_work(net))
        print("reachability() =", net.reachability())
        assert did_it_work(net) == (net.reachability() == "PASS"), "your definition disagrees with ground truth"
        render.audit(net)
        render.dashboard(net.reachability())
        """)
    b.md("""
        ## The wall
        The flap was real. The fix was valid. And it changed nothing: the agent cleared the loudest symptom, graded its
        own work, and declared victory -- while users still can't reach the core. *Confidently, articulately wrong.*

        Notice what was missing: no second opinion, no check of the outcome, no human between the agent and the router.

        > The loudest log is not the outage.

        *(With a live model, the agent may sometimes find the real cause. Look at the audit above: it still changed a
        production router with no ticket, no approval and no independent check.)*
        """)
    b.md("""
        ## 4 -- How a crash becomes a "root cause" (and the 15 lines that stop it)
        A real output from an earlier OSPF agent: `Root Cause: Expecting value: line 1 column 1 (char 0)` --
        `Solution: unknown`. That is not a diagnosis. It is Python's JSON error, written into the root-cause field
        by code that caught the exception and returned its message. Nobody checked. Run both versions.
        """)
    b.code("""
        import json
        prose = "The interface flapped. I bounced it and cleared the counters. Incident resolved."

        def naive_parse(model_text: str) -> dict:          # the anti-pattern
            try:
                return json.loads(model_text)
            except Exception as e:                          # the error message becomes the answer
                return {"root_cause": str(e), "solution": "unknown"}

        print("naive :", naive_parse(prose))

        # The kit's guard: the answer must arrive as a validated tool call, never as prose.
        from netops.agents.loop import run_agent
        from netops.llm import LLMReply, ToolSpec

        class ProseOnly:                                    # a model that never calls the submit tool
            def chat(self, role, messages, tools):
                return LLMReply(text=prose, source="stub")

        SUBMIT = ToolSpec(name="submit_diagnosis", description="Report the root cause with its evidence.",
                          parameters={"type": "object", "required": ["root_cause", "evidence_ids"], "properties": {
                              "root_cause": {"type": "string"},
                              "evidence_ids": {"type": "array", "items": {"type": "string"}}}})

        def validate(answer: dict) -> str | None:          # None = accepted, a string = the correction sent back
            return None if answer.get("evidence_ids") else "cite at least one evidence id"

        guarded = run_agent(ProseOnly(), role="demo", system="Diagnose the alert.", task=ALERT,
                            submit=SUBMIT, validate=validate)
        print("guard :", guarded.stopped, "| submitted:", guarded.submitted)
        print("        why:", guarded.invalid_outputs)
        # No valid structured answer -> nothing is recorded as a root cause; the caller takes its deterministic path.
        """)
    b.md("""
        ## Stretch (optional, 5 min) -- "just add a line to the prompt"
        The usual reaction to a bad incident: patch the prompt with the answer. *"Also check the OSPF areas on both
        ends of the link."* Then the NEXT incident arrives. Same branch, same loud flap -- but this time the silent
        fault is an **MTU mismatch** (the neighbor sticks in ExStart), and the areas match.

        You wrote last week's answer into the prompt. Watch whether it transfers.
        """)
    b.code("""
        # A fresh, different incident: variant="mtu_mismatch". Same alert, same flapping logs.
        nxt = new_incident(variant="mtu_mismatch", llm=llm, verbose=False)
        patched = SingleAgent(llm, nxt.network, nxt.evidence,
                              extra_instructions="Also check the OSPF areas on both ends of the link.")
        print("system prompt now ends with:", repr(patched.system.splitlines()[-1]))
        run2 = patched.run(ALERT, trace=nxt.trace)
        print("STRETCH (mtu_mismatch) the agent says :", run2.final_text)
        print("STRETCH (mtu_mismatch) reachability() =", nxt.network.reachability())
        # MockLLM: still chases the flap. A live model may check the areas -- they MATCH this time -- and then
        # what? A prompt line is a patch for one incident. Structure (runbook, detectors, validation) transfers.
        """)
    b.knowledge_check([
        ("""The uplink flapped at 10:02. Users lost the service at 10:03. Is the flap the root cause?""",
         """Not proven. Correlation in time is not causation. In this incident the flap is real but the earlier
         flaps recovered on their own; the outage persists because the OSPF areas disagree. You need evidence
         that explains *why the adjacency stays down*, not just something that happened just before."""),
        ("""The agent says "Incident resolved" while `reachability()` is FAIL. What would have caught it?""",
         """An independent check of the *outcome* (users reach the service), run by something other than the
         agent that made the change -- and allowed to gate the status. "Resolved" should be a result of
         validation, not a sentence the model writes."""),
    ])
    return b
