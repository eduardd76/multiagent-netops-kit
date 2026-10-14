"""Swappable model client. One conversation format (OpenAI chat + tools) everywhere.

  OpenAICompatLLM  any OpenAI-compatible endpoint: the instructor's shared endpoint, Ollama, vLLM, OpenRouter...
  MockLLM          deterministic, offline. Per-role POLICIES that read the conversation and answer.
                   Always labelled "mock" in traces -- it is a teaching stand-in, not a model.
  FallbackLLM      tries the live endpoint; on any transport error it answers with MockLLM and SAYS SO.

Configuration (env vars, or Colab secrets with the same names):
  NETOPS_LLM       auto (default) | mock | shared | ollama
  NETOPS_BASE_URL  e.g. https://llm.example.org/v1   (handed out by the instructor)
  NETOPS_API_KEY   the session token (revoked after class)
  NETOPS_MODEL     model name served by the endpoint
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict          # JSON schema


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class LLMReply(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    source: str = ""          # "live:<model>" or "mock" -- shown in every trace


class LLM(Protocol):
    def chat(self, *, role: str, messages: list[dict], tools: list[ToolSpec]) -> LLMReply: ...


def _setting(name: str, default: str | None = None) -> str | None:
    """Env var first, then a Colab secret with the same name."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        from google.colab import userdata          # type: ignore
        return userdata.get(name)
    except Exception:
        return default


# --------------------------------------------------------------------------- live endpoint
class OpenAICompatLLM:
    def __init__(self, base_url: str, model: str, api_key: str = "not-needed", timeout: float = 30.0, client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1)
        self.client, self.model = client, model
        self.sampling: dict[str, Any] = {"temperature": 0, "seed": 7}   # repeatable runs where the endpoint allows it

    def _create(self, kwargs: dict):
        """Some endpoints reject sampling settings (Claude 5.x: 'temperature is deprecated'). Drop the rejected one
        once, remember it for this client, and carry on -- a lab must not fall back to the mock for a knob."""
        while True:
            try:
                return self.client.chat.completions.create(**kwargs, **self.sampling)
            except Exception as e:
                rejected = [k for k in self.sampling if k in str(e)]
                if getattr(e, "status_code", None) != 400 or not rejected:
                    raise
                for k in rejected:
                    self.sampling.pop(k)

    def chat(self, *, role: str, messages: list[dict], tools: list[ToolSpec]) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                                 "parameters": t.parameters}} for t in tools]
        msg = self._create(kwargs).choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_unparseable": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args if isinstance(args, dict) else {}))
        return LLMReply(text=msg.content or "", tool_calls=calls, source=f"live:{self.model}")


# --------------------------------------------------------------------------- deterministic mock
def _call(name: str, **arguments) -> ToolCall:
    return ToolCall(id=f"mock_{uuid.uuid5(uuid.NAMESPACE_OID, name + json.dumps(arguments, sort_keys=True)).hex[:8]}",
                    name=name, arguments=arguments)


def _tool_results(messages: list[dict]) -> list[tuple[str, str]]:
    """[(tool_name, content)] in order, by pairing tool results with the assistant calls that caused them."""
    names = {}
    for m in messages:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["function"]["name"]
    return [(names.get(m["tool_call_id"], "?"), m["content"]) for m in messages if m["role"] == "tool"]


def _context(messages: list[dict]) -> dict:
    """Agents put a machine-readable CONTEXT_JSON line in their task. The mock reads it; a live model can too."""
    for m in messages:
        if m["role"] == "user":
            hit = re.search(r"CONTEXT_JSON: (\{.*\})", m["content"], re.S)
            if hit:
                return json.loads(hit.group(1))
    return {}


class MockLLM:
    """Deterministic stand-in. It behaves like a plausible model, so the labs teach the same lessons offline."""

    def __init__(self, tempt: bool = False):
        self.tempt = tempt          # config policy also suggests an off-playbook command (to show the gate)

    def chat(self, *, role: str, messages: list[dict], tools: list[ToolSpec]) -> LLMReply:
        policy = {"single-agent": self._single, "troubleshooting": self._troubleshooting,
                  "config": self._config}.get(role)
        if policy is None:
            return LLMReply(text=f"(mock has no policy for role {role})", source="mock")
        reply = policy(messages)
        reply.source = "mock"
        return reply

    # Lab 1: the tired engineer at 3am -- the loudest log wins.
    def _single(self, messages: list[dict]) -> LLMReply:
        done = _tool_results(messages)
        if not done:
            return LLMReply(text="Users at BRANCH-7 can't reach the core. Logs first.",
                            tool_calls=[_call("logs", device="BRANCH-7")])
        if len(done) == 1:
            flaps = done[0][1].count("LINEPROTO")
            return LLMReply(text=f"The log is dominated by Ethernet1 up/down events ({flaps} lines). The uplink is "
                                 "flapping -- that's the problem. Bouncing the interface and clearing the counters.",
                            tool_calls=[_call("bounce_interface", device="BRANCH-7", interface="Ethernet1"),
                                        _call("clear_counters", device="BRANCH-7", interface="Ethernet1")])
        if len(done) == 3:
            return LLMReply(text="Checking the interface.",
                            tool_calls=[_call("interface", device="BRANCH-7", interface="Ethernet1")])
        return LLMReply(text="Ethernet1 is up and the link-status counter is back to 0 -- no more flapping. "
                             "Root cause: unstable uplink. Incident resolved.")

    # Lab 2: rank and narrate the detector findings; never drop one.
    def _troubleshooting(self, messages: list[dict]) -> LLMReply:
        ctx = _context(messages)
        findings = []
        for f in sorted(ctx.get("detected", []), key=lambda f: not f["explains_outage"]):
            narrative = ("Silent: no log line mentions it. The adjacency never re-formed after the change window "
                         "because the two ends disagree on the area." if f["explains_outage"] else
                         "Loud: hundreds of up/down lines. Real, but earlier flaps recovered on their own -- it "
                         "does not explain why the adjacency stays down.")
            findings.append({"id": f["id"], "evidence_ids": f["evidence_ids"], "narrative": narrative})
        return LLMReply(text="Two faults: one loud, one silent.",
                        tool_calls=[_call("submit_diagnosis", findings=findings,
                                          summary="The flap is the trigger; the OSPF area mismatch is why it did "
                                                  "not recover.")])

    # Lab 3/4: pick the playbook entry and its parameters from the evidence.
    def _config(self, messages: list[dict]) -> LLMReply:
        ctx = _context(messages)
        obs = ctx.get("observed", {})
        nbr = ctx.get("neighbor_evidence_ids", [])
        args = {"playbook_entry": "ospf_area_mismatch",
                "params": {"uplink": obs.get("uplink"), "expected_area": obs.get("peer_area")},
                "rationale": f"BRANCH-7 {obs.get('uplink')} is in area {obs.get('local_area')}; its neighbor "
                             f"{obs.get('peer')} is in {obs.get('peer_area')}. Align BRANCH-7 to the neighbor.",
                "blast_radius": ("Only the BRANCH-7 <-> HUB-1 adjacency; neighbor tables on both ends show no "
                                 "other adjacency on these interfaces." if nbr else
                                 "Only the BRANCH-7 <-> HUB-1 adjacency."),
                "blast_radius_evidence_ids": nbr}
        if self.tempt:
            args["extra_commands"] = ["clear ip ospf process"]
        return LLMReply(text="Proposing the playbook fix.", tool_calls=[_call("submit_proposal", **args)])


# --------------------------------------------------------------------------- fallback + factory
class FallbackLLM:
    def __init__(self, primary: LLM, fallback: LLM | None = None, allow_fallback: bool = True):
        self.primary, self.fallback, self.allow_fallback = primary, fallback or MockLLM(), allow_fallback
        self.events: list[dict] = []
        self.primary_ok: bool | None = None        # None = not probed; False = probe failed, go straight to the stand-in
        self.problem = ""

    def probe(self) -> bool:
        """One tiny call, so a bad key or URL shows up at setup -- not as a stand-in answer passing for the model's."""
        try:
            self.primary.chat(role="setup", messages=[{"role": "user", "content": "Reply with: ok"}], tools=[])
            self.primary_ok, self.problem = True, ""
        except Exception as e:
            self.primary_ok, self.problem = False, short_error(e)
        return self.primary_ok

    def chat(self, *, role: str, messages: list[dict], tools: list[ToolSpec]) -> LLMReply:
        if self.primary_ok is not False:
            try:
                return self.primary.chat(role=role, messages=messages, tools=tools)
            except Exception as e:                 # endpoint down, timeout, auth...
                if not self.allow_fallback:
                    raise RuntimeError(f"live endpoint failed for {role} and the stand-in model is not allowed here: "
                                       f"{type(e).__name__}") from e
                self.events.append({"role": role, "reason": f"{type(e).__name__}: {e}"[:200]})
                if len(self.events) == 1:          # say it once, loudly: what follows is not the model
                    print(f"[!] live endpoint failed for {role} ({short_error(e)}) -- answers from here on come "
                          f"from the MockLLM stand-in, not {getattr(self.primary, 'model', 'the model')}.")
        reply = self.fallback.chat(role=role, messages=messages, tools=tools)
        reply.source = f"mock (fallback: live endpoint failed for {role})"
        return reply


def short_error(e: Exception) -> str:
    """'401 - the key was rejected' beats a page of JSON for a room of attendees."""
    code = getattr(e, "status_code", None)
    hint = {401: "the key was rejected", 403: "the key has no access to this model", 404: "unknown model or URL",
            429: "rate limited -- tell the instructor"}.get(code)
    if code and hint:
        return f"{code} - {hint}"
    return f"{type(e).__name__}: {str(e)[:80]}"


def make_llm(mode: str | None = None) -> LLM:
    mode = mode or _setting("NETOPS_LLM", "auto")
    if mode == "mock":
        return MockLLM()
    if mode == "ollama":
        return FallbackLLM(OpenAICompatLLM(_setting("NETOPS_BASE_URL", "http://localhost:11434/v1"),
                                           _setting("NETOPS_MODEL", "qwen2.5:7b-instruct"), "ollama"))
    base_url, model = _setting("NETOPS_BASE_URL"), _setting("NETOPS_MODEL")
    if base_url and model:
        return FallbackLLM(OpenAICompatLLM(base_url, model, _setting("NETOPS_API_KEY", "not-needed")))
    if mode == "shared":
        raise RuntimeError("NETOPS_BASE_URL and NETOPS_MODEL are not set -- ask your instructor, or use NETOPS_LLM=mock")
    return MockLLM()
