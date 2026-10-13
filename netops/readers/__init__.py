# kit/netops/readers/__init__.py
"""One Reader per network OS, looked up by the driver's `nos`. Add a vendor: write a Reader, register it."""
from __future__ import annotations

from netops.readers.eos import EosReader

READERS: dict = {"eos": EosReader()}


def register_reader(reader) -> None:
    READERS[reader.nos] = reader


def get_reader(nos: str):
    if nos not in READERS:
        raise ValueError(f"no reader for nos {nos!r}; known: {', '.join(sorted(READERS))}")
    return READERS[nos]
