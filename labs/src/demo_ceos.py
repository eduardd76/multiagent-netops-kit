from labs.src.nb import LabBook


def book() -> LabBook:
    b = LabBook("demo_ceos", "Instructor demo -- the SAME agents on real Arista cEOS (containerlab)",
                expect=["reachability() = FAIL", "RESOLVED."])
    b.md("""
        **Instructor only** (needs Docker + containerlab + a cEOS image; not for Colab). See `ceos/README.md`.

        The lab is deployed once with containerlab (on a Mac it runs inside a Linux VM, e.g. OrbStack: prefix commands
        with `orb -m <vm>`). Before the session: `ceos/reset.sh` then `ceos/break.sh` (~2.5 min:
        6 flaps that recover, the silent area change, 12 flaps that don't). One cell per beat of the speaker script --
        run each cell when the script says so, not all at once. To re-arm afterwards: `facilitator/rearm.sh`
        (it runs `ceos/reset.sh` then `ceos/break.sh`).

        **For the room:** the AI model's wording changes every run and will not match the slides word for word.
        Read the screen, not the slide.
        """)
    b.md("## 0 -- Connect to the real routers (before the session). Must print FAIL.")
    b.md("""
        - **What this does:** connects to the 4 real routers over their API, like opening SSH to each box.
          `net` = the real network; `lab` = a read-only CLI (show and ping only).
        - **What you'll see:** `reachability() = FAIL` -- the users at BRANCH-7 cannot reach the service.
        - **Why it matters:** FAIL means the incident is armed. PASS? Run `facilitator/rearm.sh` (~2.5 min).
        """)
    b.code("""
        from netops import render
        from netops.clab import ContainerLab
        from netops.network import Network

        HOSTS = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021",     # each router's API (eAPI),
                 "BRANCH-8": "clab.orb.local:8012", "HUB-2": "clab.orb.local:8022"}     # published by containerlab
        net = Network.ceos(HOSTS)                # the ONE line your Colab doesn't have: there it's Network.simulated()
        lab = ContainerLab("netops", vm="clab")  # to type on the routers' own CLI (show and ping only)
        print("reachability() =", net.reachability(), "   <- must be FAIL before the session (ceos/break.sh)")
        """)
    b.md("## Slide 3 -- meet the lab. ONE cell: shift-enter once, then talk over the three blocks it prints.")
    b.md("""
        - **What this does:** shows the same 4 routers three ways: the running containers, the show commands an
          engineer types, then the same check done by code.
        - **What you'll see:** `1/3  THE LAB IS REAL`, `2/3  WHAT AN ENGINEER TYPES`, `3/3  THE SAME CHECK IN CODE`.
          At the bottom: BRANCH-7 `---- no OSPF ------` ... `: FAIL  <- incident`.
        - **Why it matters:** `render.lab(net)` = one table of the real lab. Your Colab runs the same lab, simulated.
        """)
    b.code("""
        print("1/3  THE LAB IS REAL: 4 Arista cEOS routers in containerlab, on this laptop\\n")
        lab.containers()

        print("2/3  WHAT AN ENGINEER TYPES on the routers: the healthy branch first\\n")
        for router, lan in [("BRANCH-8", "10.30.30.1"), ("BRANCH-7", "10.20.20.1")]:
            lab.cli(router, "show ip ospf neighbor")
            lab.cli(router, "show ip route 10.100.10.0/24")
            lab.cli(router, f"ping 10.100.10.10 source {lan} repeat 2")

        print("3/3  THE SAME CHECK IN CODE: the real routers, then your simulator\\n")
        render.lab(net)
        render.lab(Network.simulated(), brief=True)
        """)
    b.md("## Slide 5 -- one agent, every tool. ONE cell: the same line the room runs in Lab 1, on the simulator.")
    b.md("""
        - **What this does:** replays Lab 1 on the simulator: ONE AI agent with every tool, write tools included.
          No change ticket, no approval -- like giving an intern enable on every router.
        - **What you'll see:** the agent's steps, then `reachability() = FAIL` and `DEVICE CHANGE AUDIT`
          listing what it changed on the router.
        - **Why it matters:** it says "resolved". The users' check still says FAIL.
        """)
    b.code("""
        from netops.agents.single import SingleAgent
        from netops.orchestrator import ALERT, new_incident

        inc = new_incident(llm=llm)            # a fresh copy of the attendees' network (the simulator), incident state
        print("model:", render.llm_label(llm), "\\nALERT:", ALERT, "\\n")
        run = SingleAgent(llm, inc.network, inc.evidence).run(ALERT, trace=inc.trace)   # one agent, every tool
        print("\\nreachability() =", inc.network.reachability())        # the users' check, after it says 'resolved'
        render.audit(inc.network)                                       # what it changed on the router, and who approved
        """)
    b.md("## Slide 20 (itch) -- what the on-call engineer types: ping, route, neighbors. Do NOT show the areas yet.")
    b.md("""
        - **What this does:** the first three things the on-call checks on BRANCH-7: ping from the user LAN,
          the route to the service, the OSPF neighbors. Read-only.
        - **What you'll see:** the ping line with `received=0`, the route with `present=False`,
          and the neighbor list `[]` -- empty.
        - **Why it matters:** HUB-1 is simply missing. No log, no alarm. That is the itch.
        """)
    b.code("""
        print("ping 10.100.10.10 source 10.20.20.1 :", net.ping("BRANCH-7", "10.100.10.10", "10.20.20.1"))
        print("route 10.100.10.0/24               :", net.route("BRANCH-7", "10.100.10.0/24"))
        print("OSPF neighbors on BRANCH-7         :", net.ospf_neighbors("BRANCH-7"))
        """)
    b.md("## Lab 2 reveal (slide 34) -- one digit")
    b.md("""
        - **What this does:** the same lab table as slide 3, plus one column: the OSPF area on each uplink
          (what `show ip ospf interface` tells you).
        - **What you'll see:** in the `AREA` column, BRANCH-7 `0.0.0.1`, HUB-1 `0.0.0.0`.
        - **Why it matters:** one digit. Different areas, so the neighbor never forms -- and nothing logs it.
        """)
    b.code("""
        render.lab(net, show_area=True)      # the same view, now with the area column: 0.0.0.1 vs 0.0.0.0
        """)
    b.md("## Optional -- Lab 1's single agent on real gear (it changes the router: re-arm with reset.sh + break.sh after)")
    b.md("""
        - **What this does:** the Lab 1 agent again, now on the REAL routers. It may bounce the interface with
          nobody's approval. **It changes the router: re-arm afterwards with `facilitator/rearm.sh`.**
        - **What you'll see:** `the agent says:` (its claim), then `reachability() = FAIL | ungated writes:`
          (what it changed, unapproved).
        - **Why it matters:** this feeds the contrast table at slide 56.
        """)
    b.code("""
        from netops.orchestrator import new_incident, run_lab1
        lab1 = run_lab1(new_incident(llm=llm, network=Network.ceos(HOSTS)))
        print("the agent says:", lab1["agent_says"])
        print("reachability() =", lab1["reachability"], "| ungated writes:", lab1["writes"])
        """)
    b.md("""
        ## Lab 4 live (slides 52-55) -- the team stops at the gate; Edy is the on-call engineer (two hats)

        Two hats: Edy presents, and Edy plays the on-call engineer who holds the gate -- the CAB step.
        Say it out loud: in production you never approve your own team's change.
        The live model's wording differs run to run and from the slides: read the screen.
        A `BLOCKED before proposal` line may appear: the model tried to add an extra command; the command gate threw it out.
        """)
    b.md("""
        - **What this does:** the AI team investigates the real routers, writes change request v1, then STOPS
          and waits for a human. `gate` = that change request, waiting for you. `render.gate(gate)` = print the ticket.
        - **What you'll see:** `explains the outage: True` (area mismatch) vs `False` (the flap), then
          `no neighbor-table evidence for ['HUB-1']`, checklist `4. [NO  ]`, `ready for approval: False`.
        - **Why it matters:** nobody read HUB-1's neighbor table. What else rides on this link?
        """)
    b.code("""
        from netops.orchestrator import ALERT, ONCALL_REJECT, contrast, new_incident, team
        inc = new_incident(llm=llm, network=Network.ceos(HOSTS))
        gate = team(inc, "on-call").run_to_gate(ALERT)
        render.gate(gate)                     # v1: six PASS, blast_radius_evidenced FAIL, ready for approval: False
        """)
    b.md("""
        Optional, 20 s: try to approve v1 anyway -- the gate refuses.

        - **What this does:** tries to approve v1 anyway -- like signing a CAB ticket whose pre-check failed.
          `gate.approve("on-call")` = say yes as the on-call. Nothing is written.
        - **What you'll see:** `GateError: pre-checks are failing (...) -- reject with your reasons instead`
        - **NEVER run this cell after the reject cell below:** `gate` is then v2, ready, and this WOULD write
          to the real routers.
        """)
    b.code("""
        try:
            gate.approve("on-call")
        except Exception as e:
            print(type(e).__name__ + ":", e)
        """)
    b.md("""
        On-call hat on: read the rejection (`ONCALL_REJECT`) out loud, then run this cell.

        - **What this does:** `gate.reject(ONCALL_REJECT)` = reject the ticket, with that reason. The team reads
          BOTH neighbor tables (BRANCH-7 and HUB-1) and files v2.
        - **What you'll see:** `CHANGE REQUEST v2`, `PASS  blast_radius_evidenced: neighbor tables on both ends cited`,
          `ready for approval: True`.
        - **Why it matters:** a reject is not a dead end. It sends the team back for evidence.
        """)
    b.code("""
        gate = gate.reject(ONCALL_REJECT)
        render.gate(gate)                     # v2: blast radius cites both neighbor tables, ready for approval: True
        """)
    b.md("""
        On-call says yes. **This cell WRITES to the real routers.** It first asks you to **type APPROVE** (like signing
        the CAB ticket) - anything else writes nothing. Afterwards re-arm: `facilitator/rearm.sh`.

        - **What this does:** approving creates the approval token (the signed CAB number for this exact change:
          15 min, one use). The executor -- plain code, not AI -- applies the 2 commands once. The validator re-checks until FULL.
        - **What you'll see:** `RESOLVED. reachability() = PASS`, `by executor:on-call`, `>>> RESOLVED. <<<`
        - **Ran it twice?** `GateError`: one approval token, one write.
        """)
    b.code("""
        from netops.approval import GateError
        # safety: a double Shift-Enter must never write. You type APPROVE - like signing the CAB ticket.
        if input("On-call: type APPROVE to write to the real routers: ").strip() != "APPROVE":
            print("Not approved - nothing was written.")
        else:
            try:
                result = gate.approve("on-call")
                render.transcript(inc.bus)
                print("\\nreachability() =", result["reachability"])
                render.audit(inc.network)
                render.dashboard(result["reachability"])
                render.lab(net, show_area=True)  # after the one approved write: FULL, route, PASS on both branches
            except GateError as e:               # ran it again? one approval token = one write: the gate refuses
                print("GateError:", e)
        """)
    b.md("## The contrast (slide 56) -- needs the optional Lab 1 cell above; otherwise read the students' table")
    b.md("""
        - **What this does:** a side-by-side scorecard: Lab 1's lone agent vs Lab 4's team.
          Prints nothing if the optional Lab 1 cell was skipped -- then read the students' table.
        - **What you'll see:** columns `Lab 1 (one agent)` and `Lab 4 (team)`; rows like `Says 'resolved'`
          and `A human approved the change`.
        - **Why it matters:** both said "resolved". Only one was.
        """)
    b.code("""
        if "lab1" in globals() and "result" in globals():
            print(contrast(lab1, result))
        """)
    b.md("**After the session:** `facilitator/rearm.sh` (= `ceos/reset.sh` then `ceos/break.sh`) re-arms the incident for the next run.")
    return b
