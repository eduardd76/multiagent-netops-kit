"""netops — build a TEAM of AI agents that resolves a network incident safely.

Read the package in this order:
  device/   the network (simulated Arista cEOS, or a real one over eAPI)
  parsers   turn device output (eAPI JSON) into small typed models
  network   the read tools agents may use, plus reachability()
  playbook  the ONLY source of change commands, and the command gate
  protocol  the message every agent sends and receives
  llm       swappable model client (OpenAI-compatible, Ollama, deterministic Mock)
  agents/   the single agent (Lab 1) and the team (Labs 2-4)
"""
__version__ = "0.1.0"
