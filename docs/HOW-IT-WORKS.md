# How it works - the lab, the kit, and the code you run

This page explains everything you touch in the workshop, in plain words. No step here needs you to read the
code first. Every name in `code style` is a real file, class or function you can open.

---

## 1. In one sentence

You get a small network with a real-looking outage, and a Python kit called **`netops`** that lets AI agents
investigate it, propose a fix, and wait for a human to approve it. You watch one agent fail, then build a team that
gets it right.

---

## 2. The network

```
  users 10.20.20.0/24 -- [BRANCH-7] --Et1-- 10.0.12.0/31 --Et1-- [HUB-1] --+
                                                                           +-- core service 10.100.10.10
  users 10.30.30.0/24 -- [BRANCH-8] --Et1-- 10.0.22.0/31 --Et1-- [HUB-2] --+
```

| | BRANCH-7 | HUB-1 | BRANCH-8 | HUB-2 |
|---|---|---|---|---|
| role | branch (the broken one) | hub | branch (the healthy control) | hub |
| router ID (Loopback0) | 1.1.1.11 | 1.1.1.1 | 1.1.1.12 | 2.2.2.2 |
| uplink Ethernet1 | 10.0.12.0/31 | 10.0.12.1/31 | 10.0.22.0/31 | 10.0.22.1/31 |
| users' LAN (Loopback1) | 10.20.20.1/24 | - | 10.30.30.1/24 | - |
| core service (Loopback100) | - | 10.100.10.10/24 | - | 10.100.10.10/24 |

- **Routing:** OSPF process 1, point-to-point uplinks, hello 10 s / dead 40 s. One uplink per branch, no backup path.
- **The ticket:** BRANCH-7's users can't reach the core service. BRANCH-8's can. BRANCH-8 is the same design, so
  whenever you wonder "is this normal?", compare with BRANCH-8.
- **What "fixed" means:** a ping from the branch LAN (10.20.20.1) to the service (10.100.10.10) succeeds. In code
  that is `net.reachability()` - it says `PASS` or `FAIL`. Not a quiet log, not an interface that is up: the users' view.

The whole network, including the incident's timeline, is described in one file: `netops/data/incident.yaml`.

---

## 3. Two ways to run the same network

| | **You (Colab)** | **The presenter (laptop)** |
|---|---|---|
| where | Google Colab, in your own account | JupyterLab on the presenter's laptop |
| the routers | `Network.simulated()` - a simulator of the 4 routers | `Network.ceos(HOSTS)` - 4 real Arista cEOS routers in containerlab |
| how the code talks to them | in memory; the simulator answers with the same JSON a cEOS router returns | eAPI (JSON over HTTP) |
| the model | Claude Haiku via the 3 secrets, or the MockLLM stand-in | the same |
| everything else | the same kit, the same agents, the same tools | the same |

**One line is different**, and it's the one that builds the network:

```python
net = Network.simulated()      # your Colab
net = Network.ceos(HOSTS)      # the presenter's real routers
```

Nothing above that line knows which network it has. That's why your results and the presenter's real routers
agree - and if they ever don't, tell the presenter: that's a finding.

### The presenter's real lab, in brief

- **cEOS** is Arista's EOS - the same operating system as on Arista hardware - packaged as a container.
- **containerlab** starts the containers and wires them together from one file, `ceos/topology.clab.yml`:
  four nodes, two links. On the presenter's Mac it runs inside a small Linux VM (OrbStack). Each router uses about
  1 GB of memory.
- Each router publishes its API (eAPI) on a port, which is what `HOSTS` lists. `ceos/README.md` explains how to
  build the same lab yourself; `ceos/break.sh` injects the incident and `ceos/reset.sh` heals it.

---

## 4. What `netops` is

**`netops` is the kit: the code built for this workshop.** It's a Python package - one folder of plain `.py`
files (36 files, about 3,500 lines), at `netops/` in this repository. When a notebook says
`from netops import ...`, it means "use a file from the kit". No framework, nothing hidden: you can open every
file.

Your setup cell installs it from GitHub with `pip`. On the presenter's laptop it's already installed.

### The folder, file by file

| You'll hear… | File | What it is, in network terms |
|---|---|---|
| "the network" | `network.py` | The show-command menu: `ping`, `route`, `ospf_neighbors`, `ospf_interface`, `interface`, `logs`, `log_summary`, and `reachability()`. Each call returns parsed data, not screen text. |
| "real routers" | `device/ceos.py` | Talks to Arista cEOS over eAPI. |
| "the simulator" | `device/simulator.py`, `device/fabric.py` | A pretend cEOS that answers with the same JSON. `fabric.py` plays the incident's timeline from `data/incident.yaml`. |
| "parsing" | `readers/eos.py`, `parsers.py`, `models.py` | Turn router JSON into small typed records (neighbor, route, interface...). One set of parsers for both backends. |
| "tools" | `agents/tools.py` | The only way an agent touches the network. Each role gets an allowlist, enforced in code - like command authorization per role on your AAA server. |
| "evidence" | `evidence.py` | Every tool result gets a number - `ev_01`, `ev_02`... - like show output attached to a ticket. Claims must cite it. |
| "the agent loop" | `agents/loop.py` | About 70 lines: the model asks for a tool, our code runs it, the result goes back in; repeat until done or a turn cap. |
| "the model" | `llm.py` | `make_llm()` picks the model: the live endpoint from your secrets, or `MockLLM`, a labelled stand-in. |
| "the single agent" | `agents/single.py` | Lab 1: one agent, every tool, writes with no approval. |
| "the team" | `agents/coordinator.py`, `troubleshooting.py`, `config.py`, `validation.py` | Labs 2-4: the shift lead, tier-2 troubleshooting, the change author, the independent check. |
| "the playbook" | `playbook.py`, `data/diagnose.yaml` | The approved fixes and the runbook. Change commands can only come from here. |
| "the human gate" | `approval.py`, `checklist.py` | Your approval becomes a single-use token for that exact change - like a change number valid once, for 15 minutes. Plus the on-call engineer's nine questions. |
| "the executor" | `executor.py` | The only thing that writes on the team. Plain code, no AI. Refuses without your token; puts the old config back if OSPF isn't FULL within about 60 s. |
| "the checks" | `checks.py` | The expected state after a change, as code: what to read, where, and what passing looks like. |
| "the messages" | `protocol.py` | The one message format the agents use: who, to whom, what task, what status. Your incident timeline. |
| "the views" | `render.py` | Prints the tables you see: the gate, the transcript, the audit, `render.lab`. |
| "the grade" | `scoring.py` | Scores how the agents worked (the trajectory), not only their answer - and what it cost. |
| "wiring" | `orchestrator.py` | Puts it all together for a lab: `new_incident()`, the single agent, the team. |
| "typing on the router" | `clab.py` | The presenter's read-only window onto a containerlab router's own CLI (show and ping only). The agents never use it. |
| "MCP" | `mcp_server.py` | The kit's read tools as a read-only MCP server, for any MCP client. |

---

## 5. The kit in five layers

Read it from the bottom - it's the same picture as the "how the kit is built" slide.

```
  THE TEAM (Labs 2-4)   Coordinator -> 3 specialists -> HUMAN GATE (you) -> Executor (the only write)
  ONE AGENT (Lab 1)     SingleAgent: every tool, writes with no gate
  LOOP + MODEL          run_agent(): the model asks, code runs the tool  |  make_llm(): Haiku or MockLLM
  TOOLS                 ToolBox(allow=[...]): a command list per role    |  EvidenceStore: ev_01, ev_02...
  NETWORK               Network.simulated() or Network.ceos()  ->  ping, route, ospf_neighbors, reachability()
```

1. **Network.** The show-command menu, on the simulator or on real routers.
2. **Tools.** An agent never gets the network itself, only a toolbox with an allowlist. Every answer is numbered evidence.
3. **Loop + model.** The model never holds a session to a router. It asks; our code runs the tool.
4. **One agent.** Lab 1's agent has every tool, including writes, and nothing checks it.
5. **The team.** Separate roles, a human who owns the yes, and an executor that is code, not AI.

---

## 6. The cells you run, line by line

### The setup cell - first cell of every notebook

```python
if not os.environ.get("NETOPS_LOCAL") and importlib.util.find_spec("netops") is None:
    %pip install git+https://github.com/eduardd76/multiagent-netops-kit@<version>   # install the kit
llm = make_llm()                         # pick the model
print("LLM:", render.llm_status(llm))    # one test call, then say what you got
```

- **Line 1-2:** if the kit isn't installed yet, install it from GitHub. A wall of install text is normal.
- **`make_llm()`:** reads three settings - `NETOPS_BASE_URL`, `NETOPS_MODEL`, `NETOPS_API_KEY` (Colab secrets, the key
  icon on the left). All set: the live model. None set: `MockLLM`, a deterministic stand-in - and it says so.
- **`render.llm_status()`:** sends one test call and prints a line starting with `LLM:`:
  - `live endpoint (claude-haiku-5-5) - connected` - you're live.
  - `... FAILED (401 - the key was rejected) - running on the MockLLM stand-in` - it tells you why; fix the secret
    and run the cell again.
  - `MockLLM (deterministic stand-in -- not a model)` - fine: every lab passes on the stand-in.

### Then every lab starts the same way

```python
inc = new_incident(llm=llm)      # a fresh copy of the network, in the incident state, plus the model
net = inc.network                # the 4 routers (here: the simulator)
net.reachability()               # 'FAIL' - the users' check
```

`new_incident()` gives you a clean, isolated world each time: new network state, new evidence, new approvals.

### The presenter's notebook (`labs/demo_ceos.ipynb`)

**Cell 0 - connect to the real routers:**

```python
HOSTS = {"BRANCH-7": "clab.orb.local:8011", "HUB-1": "clab.orb.local:8021", ...}   # each router's API address
net = Network.ceos(HOSTS)                 # the one line Colab doesn't have: there it's Network.simulated()
lab = ContainerLab("netops", vm="clab")   # to type on the routers' own CLI (show and ping only)
print("reachability() =", net.reachability())
```

- **`net`** is how the **agents** see the network: through an API, as structured data.
- **`lab`** is how a **person** sees it: the router's own CLI, like SSH. It refuses anything but `show` and `ping`.

**The "meet the lab" cell - three blocks:**

```python
lab.containers()                                         # 1: the 4 containers are running (docker ps)
for router, lan in [("BRANCH-8", "10.30.30.1"), ("BRANCH-7", "10.20.20.1")]:
    lab.cli(router, "show ip ospf neighbor")             # 2: what an engineer types, healthy branch first
    lab.cli(router, "show ip route 10.100.10.0/24")
    lab.cli(router, f"ping 10.100.10.10 source {lan} repeat 2")
render.lab(net)                                          # 3: the same check in code, on the real routers
render.lab(Network.simulated(), brief=True)              #    ...and on the simulator: the same answer
```

What it shows today: BRANCH-8 has a FULL neighbor, the route and 0% loss; BRANCH-7 has no neighbor, no route and
100% loss. `render.lab` prints the same thing for all four routers, plus the users' ping per branch.

`render.lab(net)` works on your simulator too - try it in any lab: `render.lab(inc.network)`.

---

## 7. Glossary

| Term | Meaning |
|---|---|
| agent | a model plus tools in a loop: it asks for a tool, gets the result, decides what to do next |
| tool | one thing an agent may ask for, like "OSPF neighbors on BRANCH-7"; our code runs it |
| allowlist | the tools a role may use, enforced in code (`ToolNotAllowed` if it asks for anything else) |
| evidence (`ev_NN`) | a numbered tool result; findings and proposals must cite it |
| `MockLLM` | a deterministic stand-in for a model, always labelled; every lab passes on it |
| `make_llm()` | picks the model from your three secrets |
| `reachability()` | the users' check: ping from the branch LAN to the service - `PASS` or `FAIL` |
| playbook | the approved fixes; the only place change commands can come from |
| human gate | where the team stops and waits for a person to approve or reject |
| approval token | what your approval creates: valid once, for that exact change, for 15 minutes |
| executor | the code that applies an approved change; the only writer on the team |
| cEOS | Arista EOS in a container |
| containerlab | starts and wires router containers from one topology file |
| eAPI | Arista's JSON API over HTTP; how the kit talks to real routers |

---

## 8. Questions people ask

- **Does the model log in to a router?** No. It asks for a tool by name; the kit's code runs it and returns the
  result. On the team, the model can't even ask for a write.
- **Is the presenter's lab real?** Yes: four Arista cEOS containers. The presenter types on their CLI live.
- **Why is my notebook a simulator?** So everyone gets the same network, instantly, with nothing to install. It
  answers with the same JSON as a real cEOS router, so the agents can't tell the difference.
- **I have no key / the model is down.** You get `MockLLM`. It's labelled, and every lab passes on it.
- **Can I run this at home on real routers?** Yes - see `ceos/README.md`, then use `Network.ceos(...)` instead of
  `Network.simulated()`.
