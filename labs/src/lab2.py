from labs.src.nb import TEAM_MD, LabBook


def book() -> LabBook:
    b = LabBook("lab2_coordinator_specialist", "Lab 2 -- A Coordinator and a Troubleshooting Specialist",
                expect=["coordinator -> troubleshooting", "OSPF area mismatch", "Uplink interface flapping",
                        "acting on: OSPF area mismatch", "TRAJECTORY", "llm turns"])
    b.md("""
        Lab 1's agent did the work AND graded it. Now we **split the job**, like a NOC shift:

        - the **coordinator** (the shift lead) routes the ticket and never touches a router;
        - the **troubleshooting specialist** (tier-2) can only read, and runs the on-call engineer's checks in order.

        They talk in **one message = a ticket with 6 required fields**: from, to, intent, task, payload, status.
        You write two small things: the coordinator's first message, and which finding to act on.

        **This cell** loads the kit and builds a fresh broken network plus the team. It prints nothing - that's normal.
        """)
    b.md(TEAM_MD)
    b.code("""
        from netops.orchestrator import new_incident, ALERT, team
        from netops.protocol import Message
        inc = new_incident(llm=llm)
        coordinator = team(inc)           # registers troubleshooting / config / validation on the message bus
        """)
    b.md("""
        ## 1 -- Write the coordinator's first message
        This is the ticket from the slide: **from** the coordinator, **to** the troubleshooting specialist,
        **intent** diagnose, **task** the alert (`ALERT`), **status** requested. The payload stays empty - nothing is known yet.

        **How to edit the cell below:** keep the `def diagnose_request() -> Message:` line and the description.
        Delete **only the last line**, `raise NotImplementedError(...)`, and put **one `return` line** in its place,
        indented like the line you deleted. Do **not** write a second `def` line. Then run the cell.

        One Python detail: `from` is a Python word, so it goes in as `**{"from": "coordinator"}`.
        """)
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
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put this in its place** (same indent, 4 spaces):

        ```python
            return Message(**{"from": "coordinator"}, to="troubleshooting", intent="diagnose", task=ALERT,
                           status="requested")
        ```

        - `**{"from": "coordinator"}` - who sends the ticket (the shift lead).
        - `to="troubleshooting"` - who gets it (tier-2).
        - `intent="diagnose"` - the kind of work: find out what's wrong. (The other two are propose and validate.)
        - `task=ALERT` - the page: users at BRANCH-7 can't reach the core service.
        - `status="requested"` - the work is asked for, not done yet.

        The finished cell has **one** `def` line and ends with that `return`. Run it, then run the next cell.
        </details>
        """)
    b.md("""
        **This cell sends your ticket** and shows what comes back:

        - `reply:` - who answered, and its status (it should say *troubleshooting -> coordinator diagnose done*);
        - the **findings** - the specialist reports **two**: one loud, one silent. Each cites its evidence ids;
        - the **transcript** - every message so far, in order: the incident timeline.

        `NotImplementedError` here means you haven't written step 1 yet - it's your turn, go up one cell.
        """)
    b.code("""
        msg = diagnose_request()
        assert msg is not None, "diagnose_request returned None - keep ONE def line, and make the last line a return"
        reply = inc.bus.send(msg)
        print("reply:", reply.from_, "->", reply.to, reply.intent, reply.status)
        from netops.agents.troubleshooting import Finding
        findings = [Finding(**f) for f in reply.payload["findings"]]
        render.findings(findings)
        render.transcript(inc.bus)
        assert {f.id for f in findings} == {"interface_flap", "ospf_area_mismatch"}, "both faults must be found"
        """)
    b.md("""
        ## Before you write the rule: where do these two cards come from?

        You just got **two findings**. Think of each one as a **card** on the NOC wall. Before you decide which card
        the coordinator acts on, see where the cards come from. **Nothing to write here: run the 4 short cells and
        read.** About 3 minutes.

        **The journey of the data, in 5 steps:**

        | # | Step | Who does it | Where it lives |
        |---|---|---|---|
        | 1 | **The network**: 4 routers, 2 links, and tonight's faults | a file (the simulator reads it) | `netops/data/incident.yaml` |
        | 2 | **The checklist**: the on-call engineer's checks, in order | **code** runs them, read-only | `netops/data/diagnose.yaml` |
        | 3 | **The detectors**: simple *if* rules over the answers. Each match makes one card | **code** | `detect()` in `netops/agents/troubleshooting.py` |
        | 4 | **The stamp** on each card: YES or NO, *"does this explain why the site is still down?"* | **engineers wrote it once**, code copies it | `netops/playbook.yaml` (`root_cause`) |
        | 5 | **The words**: put the cards in order and write one sentence each | **the model** (the only AI step here) | the prompt in `troubleshooting.py` |

        **Where does the data really come from?** In your Colab, the 4 routers are a **simulator**, built from step
        1's file. The instructor's laptop runs the **same design on real Arista routers**. The tools return the same clean
        records from both, so the agents can't tell the difference. Only the driver changes, like moving the same
        config to new hardware.

        **NOC analogy:** the checklist is your runbook, the detectors are your alarm rules, the stamp is the
        *severity* your senior engineer gave each alarm years ago, and the model is the colleague who writes the
        ticket summary.
        """)
    b.code("""
        # 1/4  THE NETWORK - where the data comes from. Nothing to write: run and read.
        # In Colab the 4 routers are a simulator built from ONE file. The instructor's real Arista lab runs the same design.
        import yaml
        from importlib import resources
        spec = yaml.safe_load(resources.files("netops").joinpath("data", "incident.yaml").read_text())
        print("routers:", ", ".join(spec["devices"]))
        for link in spec["links"]:
            print(f"link   : {link['a']} <-> {link['b']}   OSPF area {link['area']}")
        print()
        print("what happened before the 3:14 page (minutes before the page, from the same file):")
        for f in spec["fault"]:
            extra = {k: v for k, v in f.items() if k not in ("at_min", "op", "link")}
            print(f"  {f['at_min']:>4} min   {f['op']:<9} {f['link']}   {extra}")
        """)
    b.md("""
        **What you just saw:** the uplink **flapped and recovered** an hour before the page (loud, lots of log lines).
        Five minutes before the page, BRANCH-7's uplink was set to **area 0.0.0.1** (silent: no log line). Then it
        flapped again. Two faults, one loud and one silent. The agents never read this file. They only see what the
        router tools return, like you on the CLI.
        """)
    b.code("""
        # 2/4  THE CHECKLIST - the on-call engineer's checks, in order. CODE runs them, not the model.
        # Each answer is saved as numbered evidence (ev_01, ev_02, ...), like show output attached to a ticket.
        skill = yaml.safe_load(resources.files("netops").joinpath("data", "diagnose.yaml").read_text())
        for n, step in enumerate(skill["steps"], 1):
            print(f"check {n}: {step['tool']:<15} {step['args']}")
        from netops.agents.troubleshooting import topology_params
        print()
        print("the {blanks} are filled in from the topology, for tonight's page:")
        for k, v in topology_params(inc.network).items():
            print(f"  {{{k}}} = {v}")
        print()
        print("the evidence YOUR run collected, with its number:")
        for ev in inc.evidence.all():
            print(f"  {ev.id}   {ev.tool:<15} on {ev.args.get('device', '')}")
        """)
    b.md("""
        **Read the order:** first the user's view (ping, route), then the OSPF neighbor, then the OSPF settings on
        **both ends** of the link (BRANCH-7 *and* HUB-1), then the interface and the logs, and last the healthy
        BRANCH-8 to compare. The loud logs come *late* on purpose. Lab 1's agent read them first and chased the flap.
        """)
    b.code("""
        # 3/4  THE STAMP - written by engineers ONCE, before any incident: does this fault explain a dead site?
        from netops.playbook import load_playbook
        for entry in load_playbook().values():
            print(f"{entry.title:<36} root_cause = {str(entry.root_cause):<5}   detected when: {entry.detect}")
        """)
    b.md("""
        **The detectors, in plain words.** The next cell prints the real code. Read it like an ACL, top to bottom:

        | In the code | In plain words | Card it makes |
        |---|---|---|
        | `intf["link_status_changes"] > FLAP_THRESHOLD` | the uplink went up/down **more than 4 times** (or more than 20 link lines in the log) | *Uplink interface flapping*, stamp from the playbook: **NO** |
        | `full = any(... n["state"] == "full")` | is there a **FULL** OSPF neighbor on the uplink? | (just a question) |
        | `if not full:` ... `if local["area"] != peer["area"]` | no FULL neighbor, **and the two ends of the link disagree on the area** | *OSPF area mismatch*, stamp from the playbook: **YES** |
        | `else:` ... `explains_outage=True` | no FULL neighbor, areas agree, **cause unknown** | *adjacency not FULL, cause unknown*: **YES** (a dead adjacency is never ignored) |
        | `explains_outage=e.root_cause` | **copy the stamp** from the playbook onto the card | - |
        | `evidence_ids=[...]` | write on the card **which evidence numbers** prove it | - |

        There's no AI in this function. Same evidence in, same cards out, every time.
        """)
    b.code("""
        # 4/4  THE DETECTORS - the real code that makes the cards and stamps them. No model inside.
        import inspect
        from netops.agents import troubleshooting
        print(inspect.getsource(troubleshooting.detect))
        print("=" * 70)
        print("YOUR two cards, as the coordinator receives them:")
        print()
        for f in findings:
            print(f"CARD  {f.title}")
            print(f"  stamp   explains_outage = {f.explains_outage}      <- copied from playbook.yaml by the code above")
            print(f"  proof   evidence {f.evidence_ids}   observed {f.observed}")
            print(f"  words   (the model) {f.narrative}")
            print()
        """)
    b.md("""
        **And the model?** It got the evidence and the two cards. It may do only two things: **put the cards in
        order** and **write one sentence per card**. Then code checks its answer: exactly the same cards, none dropped
        and none invented, and every evidence number it cites must exist. If the answer breaks a rule, it goes back to
        the model. If the model fails completely, the cards are kept exactly as the code made them. **The model can't
        change a stamp.**

        **So the full chain is:** engineers write the stamp → code runs the checklist → code makes and stamps the
        cards → the model explains → **your rule (next cell) picks the card the coordinator acts on.**
        """)
    b.md("""
        ## 2 -- Which finding does the coordinator act on?
        You now have **two findings**. One is **loud** (hundreds of log lines). One is **silent** (no log line at all).
        Each card has the stamp **`explains_outage`** you just saw: True if it explains why the site is *still* down.
        Your rule is the coordinator's policy: which card does the shift lead act on?

        The shift lead must act on the one that explains the outage - **not the loudest one**, and not just the
        first one in the list.

        **How to edit the cell below:** keep the `def choose_root_cause(findings):` line and the description.
        Delete **only the last line**, `raise NotImplementedError(...)`, and put your lines in its place,
        indented like the line you deleted. Do **not** write a second `def` line. Then run the cell.
        """)
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
    b.md("""
        <details><summary><b>Stuck for 3 minutes? Open the answer - explained</b></summary>

        **Delete the `raise NotImplementedError(...)` line and put these 4 lines in its place** (same indent):

        ```python
            for f in findings:            # look at each finding, one by one
                if f.explains_outage:     # does THIS one explain why the site is still down?
                    return f              # yes - act on it
            return None                   # none does - hand it to a human
        ```

        In NOC words: read every finding, and act on the one that explains the outage - not the one that
        shouts loudest. If none explains it, escalate to a person.

        Run the cell, then run the next one.
        </details>
        """)
    b.md("""
        **This cell lets the coordinator decide** with your rule. You should see **acting on: OSPF area mismatch**
        and `reachability() = FAIL` - nothing has been changed yet, **by design**. Diagnosis isn't a fix; the fix
        comes in Lab 4, with a human's approval.

        If it says *"you chose Uplink interface flapping"*, your rule picked the loud one - use `explains_outage`.
        """)
    b.code("""
        coordinator.findings = findings
        coordinator.choose = choose_root_cause
        chosen = coordinator.decide()
        assert chosen is not None, "choose_root_cause returned None - keep ONE def line, and return the finding whose explains_outage is True"
        assert chosen.id == "ospf_area_mismatch", f"you chose {chosen.title} - use explains_outage, not the loudest"
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
