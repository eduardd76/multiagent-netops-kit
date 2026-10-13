"""Customer names on the outside, canonical ids on the inside.

The agents, the simulator and the playbook always use the canonical topology (BRANCH-7, HUB-1...). Everything a
human or a model reads goes through display(); every tool call a model makes comes back through canonical()."""
from __future__ import annotations

import re
from typing import Any, Callable


class Skin:
    def __init__(self, naming: dict[str, str] | None = None):
        self.to_display = dict(naming or {})
        self.to_canon = {v: k for k, v in self.to_display.items()}
        clash = set(self.to_canon) & set(self.to_display)
        if clash or len(self.to_canon) != len(self.to_display):
            raise ValueError(f"ambiguous naming: {sorted(clash) or 'two devices share a display name'}")
        self._d, self._c = self._pattern(self.to_display), self._pattern(self.to_canon)

    @staticmethod
    def _pattern(table: dict[str, str]):
        if not table:
            return None
        alts = "|".join(re.escape(k) for k in sorted(table, key=len, reverse=True))
        return re.compile(rf"(?<![\w-])({alts})(?![\w-])")

    def display(self, text: str) -> str:
        return self._d.sub(lambda m: self.to_display[m.group(1)], text) if self._d else text

    def canonical(self, text: str) -> str:
        return self._c.sub(lambda m: self.to_canon[m.group(1)], text) if self._c else text

    def deep(self, obj: Any, fn: Callable[[str], str]) -> Any:
        if isinstance(obj, str):
            return fn(obj)
        if isinstance(obj, dict):
            return {k: self.deep(v, fn) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.deep(v, fn) for v in obj]
        return obj


_SECRET = re.compile(r"(?im)\b(community|secret(?:\s+\d)?|password(?:\s+\d)?|pre-shared-key|auth-key|md5)\s+(\S+)")


def redact(text: str) -> str:
    """Strip credentials before anything leaves for a model endpoint."""
    return _SECRET.sub(lambda m: f"{m.group(1)} <redacted>", text)


class BoundaryLLM:
    """Wraps any LLM: customer names and no secrets going out; canonical ids coming back."""

    def __init__(self, llm, skin: Skin | None = None, redact_secrets: bool = True):
        self.inner, self.skin, self.redact_secrets = llm, skin or Skin(), redact_secrets

    def _out(self, text: str | None) -> str | None:
        if text is None:
            return None
        return self.skin.display(redact(text) if self.redact_secrets else text)

    def chat(self, *, role: str, messages: list[dict], tools):
        out = []
        for m in messages:
            m = dict(m)
            if isinstance(m.get("content"), str):
                m["content"] = self._out(m["content"])
            if m.get("tool_calls"):
                m["tool_calls"] = [{**tc, "function": {**tc["function"],
                                                       "arguments": self._out(tc["function"]["arguments"])}}
                                   for tc in m["tool_calls"]]
            out.append(m)
        reply = self.inner.chat(role=role, messages=out, tools=tools)
        for c in reply.tool_calls:
            c.arguments = self.skin.deep(c.arguments, self.skin.canonical)
        return reply
