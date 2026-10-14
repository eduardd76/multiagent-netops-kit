"""The agent loop -- the whole "framework", in ~70 lines you can read.

  1. send the conversation + the allowed tools to the model
  2. run every tool call it makes (through the allowlisted ToolBox) and append the results
  3. stop when it answers in text, or when it calls the `submit` tool with VALID structured output
Invalid structured output gets one correction round; after that the caller takes its deterministic path.
"""
from __future__ import annotations

import json
from typing import Callable

from pydantic import BaseModel, Field

from netops.agents.tools import ToolBox, ToolNotAllowed
from netops.llm import LLM, ToolSpec


class AgentRun(BaseModel):
    role: str
    final_text: str = ""
    submitted: dict | None = None
    invalid_outputs: list[str] = Field(default_factory=list)
    calls: list[dict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)      # "mock" / "live:<model>" for every turn
    stopped: str = ""


def missing_fields(schema: dict, answer) -> str | None:
    """The submit tool's own schema, enforced: required fields present, object items really objects.
    A live model sometimes drops a field; the loop sends that back as a correction instead of crashing later."""
    if not isinstance(answer, dict):
        return "the answer must be a JSON object"
    for key in schema.get("required", []):
        if key not in answer:
            return f"missing required field '{key}'"
    for key, prop in schema.get("properties", {}).items():
        items = prop.get("items", {}) if prop.get("type") == "array" else {}
        if items.get("type") == "object" and key in answer:
            if not isinstance(answer[key], list) or not all(isinstance(x, dict) for x in answer[key]):
                return f"'{key}' must be a list of objects"
            for n, x in enumerate(answer[key]):
                gone = [r for r in items.get("required", []) if r not in x]
                if gone:
                    return f"'{key}[{n}]' is missing {gone}"
    return None


def run_agent(llm: LLM, *, role: str, system: str, task: str, toolbox: ToolBox | None = None,
              submit: ToolSpec | None = None, validate: Callable[[dict], str | None] | None = None,
              max_turns: int = 10, trace: Callable[[str, str], None] | None = None) -> AgentRun:
    say = trace or (lambda who, text: None)
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    tools = (toolbox.specs() if toolbox else []) + ([submit] if submit else [])
    run = AgentRun(role=role, stopped="max_turns")
    for _ in range(max_turns):
        reply = llm.chat(role=role, messages=messages, tools=tools)
        run.sources.append(reply.source)
        if reply.text:
            say(role, reply.text)
        messages.append({"role": "assistant", "content": reply.text or None,
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                        for c in reply.tool_calls] or None})
        if not reply.tool_calls:
            if submit:
                run.invalid_outputs.append("answered in prose instead of calling " + submit.name)
                if len(run.invalid_outputs) >= 2:
                    run.final_text, run.stopped = reply.text, "invalid_output"
                    break
                messages.append({"role": "user", "content": f"Call {submit.name} with your structured answer."})
                continue
            run.final_text, run.stopped = reply.text, "end_turn"
            break
        for c in reply.tool_calls:
            if submit and c.name == submit.name:
                problem = missing_fields(submit.parameters, c.arguments) or (validate(c.arguments) if validate else None)
                if problem:
                    run.invalid_outputs.append(problem)
                    content = f"ERROR: invalid {submit.name}: {problem}. Fix it and call {submit.name} again."
                else:
                    run.submitted, content = c.arguments, "accepted"
                messages.append({"role": "tool", "tool_call_id": c.id, "content": content})
                continue
            say(role, f"-> {c.name}({', '.join(f'{k}={v}' for k, v in c.arguments.items())})")
            try:
                content = toolbox.call(c.name, c.arguments) if toolbox else "ERROR: no tools"
            except ToolNotAllowed as e:
                content = f"ERROR: ToolNotAllowed: {e}"
            run.calls.append({"tool": c.name, "args": c.arguments, "ok": not content.startswith("ERROR")})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": content})
        if run.submitted is not None:
            run.final_text, run.stopped = reply.text, "submitted"
            break
        if len(run.invalid_outputs) >= 2:
            run.stopped = "invalid_output"
            break
    if run.stopped == "max_turns":
        say(role, f"stopped: hit the {max_turns}-turn cap without an answer -- hand this to a person")
    return run
