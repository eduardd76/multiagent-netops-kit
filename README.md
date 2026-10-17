# Build Multi-Agent AI Systems for Network Operations — lab kit

Students build a **team** of AI agents that resolves a live network incident on a simulated Arista cEOS
fabric, entirely in Google Colab. The same agent code runs unchanged against real cEOS in containerlab
(the instructor demo).

**New here? Start with [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)** - the network, the two ways to run it, what `netops` is, every folder and every cell, in plain words.

## The incident
Branch **BRANCH-7** reaches its hub **HUB-1** over `Ethernet1` running OSPF.
- **The trigger (loud):** the uplink flapped. `show logging` is full of up/down lines. The interface is up now.
- **The root cause (silent):** BRANCH-7 `Ethernet1` is in OSPF **area 0.0.0.1**; HUB-1 is in **0.0.0.0**. Hellos
  are dropped, the neighbor is **absent** (verified on cEOS 4.34.8M), there is no route to the core, and
  `reachability()` returns **FAIL**. No log line mentions it.
- **The fix:** `interface Ethernet1` / `ip ospf area 0.0.0.0`. FULL in ~9 s, route ~6.5 s later (real cEOS timing), then **PASS**.
- **The single-agent trap:** a naive agent reads the logs, bounces the interface, clears the counters, sees the
  interface up, says "Incident resolved" — and `reachability()` is still FAIL.

## Labs (Colab)
| Notebook | What students do | Acceptance (tested) |
|---|---|---|
| `labs/lab1_single_agent.ipynb` | Four steps: the symptom, one agent with every tool, define success (`did_it_work`), check it | says "resolved" while `reachability()=="FAIL"`; the audit shows its ungated changes |
| `labs/lab2_coordinator_specialist.ipynb` | Write the diagnose message; choose the root cause. Stretch: trajectory scorecard + cost table vs Lab 1 | coordinator sends `diagnose`; troubleshooting returns **both** faults |
| `labs/lab3_config_validation.ipynb` | Write the command gate and the expected post-state | proposal = playbook commands only, `needs_human`; off-playbook command blocked; nothing applied |
| `labs/lab4_full_team.ipynb` | Write the approval policy; reject → revise → approve; debrief: three artifacts, scorecard, cost | validation confirms OSPF FULL + reachable; gate shows the 9-question on-call checklist |
| `labs/demo_ceos.ipynb` | Instructor: the same agents on real cEOS | see `ceos/README.md` |

Every lab ends with a two-question knowledge check (answers collapsed). Solutions are in `labs/solutions/`. Each notebook installs the kit with `pip install git+…`. If GitHub is unreachable,
an appendix of `%%writefile` cells rebuilds the package locally.

## The model (no per-student keys)
| Setting | Meaning |
|---|---|
| `NETOPS_BASE_URL`, `NETOPS_MODEL`, `NETOPS_API_KEY` | the instructor's shared OpenAI-compatible endpoint (session token, revoked after class). Env vars or Colab secrets. |
| `NETOPS_LLM=ollama` | local Ollama (`http://localhost:11434/v1`, `NETOPS_MODEL`, default `qwen2.5:7b-instruct`) |
| `NETOPS_LLM=mock` (default when no endpoint is set) | `MockLLM`: deterministic per-role stand-in, always labelled as such |

If the live endpoint fails, `FallbackLLM` answers with MockLLM **and says so** in the trace. The model drives the
reasoning and the narrative. The **outcome** is guaranteed by the tools and the playbook:
- diagnosis findings come from deterministic detectors, and the model ranks and narrates them in a validated structure (it can't drop or invent one)
- change commands come only from `playbook.yaml`
- parameters are checked against the evidence

A model that answers "maybe it's DNS" still ends in a correct, human-approved fix (`tests/test_acceptance.py::test_weak_model_still_reaches_the_right_outcome`).

## Safety by design
- **No free-form CLI.** Commands are rendered from `netops/playbook.yaml`. The `CommandGate` rejects anything not
  prefixed by `allowed_commands` *before* a proposal exists. Template parameters are validated, so an interface name can't smuggle in a second command.
- **Least privilege in code.** Each agent gets an allowlisted `ToolBox`; specialists are read-only.
- **Human in the loop.** Nothing is applied without a single-use approval token. The token is bound to the exact
  proposal, minted on the human's action, never sent in a message, and consumed by the `Executor` (not an AI), which
  backs out automatically if OSPF doesn't reach FULL.
- **Independent validation.** It runs before the human sees the change (playbook match, fault still present, blast
  radius evidenced on both ends) and after the change (polls until FULL + reachable, because real convergence takes 9–16 s).

## Read-only MCP server
The same seven read tools, served over MCP to any client (Claude Code, Claude Desktop, an IDE, your own agent).
No write tool exists in it, the network behind it is a read-only view, and device output is wrapped as untrusted data.

```bash
pip install "netops[mcp] @ git+https://github.com/eduardd76/multiagent-netops-kit@v0.1.16"
claude mcp add netops -- python -m netops.mcp_server          # the simulated incident: BRANCH-7 is down
# real cEOS: set NETOPS_CEOS_HOSTS="BRANCH-7=clab.orb.local:8011,HUB-1=clab.orb.local:8021,..." for the server
```

## Extending the kit: six ports
`netops/ports.py` defines the six shapes an adapter implements: Inventory, DeviceDriver + Reader, EvidenceSource,
ChangeExecutor, ApprovalChannel, AuditSink. Agents never import an adapter -- only these shapes.
`ports.as_tool(source)` turns any EvidenceSource into one more read-only runbook step for the troubleshooting agent.

In hardened mode (`Coordinator(..., demo=True)`) approvals come only through an external approval channel
(`gate.submit(channel)`, then `gate.resolve(channel, ticket)`), the requester can't approve their own change, writes go
only to lab devices, and the executor re-renders the fix and the rollback and re-checks before applying.

## Code map (read in this order)
`netops/device/` (driver, fabric state machine, simulated cEOS, real cEOS over eAPI) → `parsers.py` → `network.py`
→ `playbook.py` + `playbook.yaml` → `protocol.py` → `llm.py` → `agents/` (`loop`, `tools`, `single`,
`troubleshooting`, `config`, `validation`, `coordinator`) → `executor.py`, `approval.py`, `checklist.py` → `orchestrator.py` → `scoring.py` (trajectory scorecard + cost table). Extension points: `ports.py` → `readers/` → `inventory.py` → `checks.py` → `audit_emit.py`.

## Develop
```bash
uv venv && uv pip install -e ".[dev]"
python -m ipykernel install --sys-prefix --name netops-kit
pytest                               # unit + acceptance + notebooks (offline, MockLLM)
NETOPS_CEOS=1 pytest -m live -s      # against a running containerlab cEOS lab
python -m labs.build                 # regenerate the notebooks
```
License: Apache-2.0.
