"""Printed reasoning traces: who said what, in order. Labs print them; tests read them."""
from __future__ import annotations


class Trace:
    def __init__(self, verbose: bool = True, width: int = 160, skin=None):
        self.verbose, self.width, self.lines, self.skin = verbose, width, [], skin

    def __call__(self, who: str, text: str) -> None:
        if self.skin is not None:
            who, text = self.skin.display(who), self.skin.display(text)
        self.lines.append((who, text))
        if self.verbose:
            for i, chunk in enumerate(text.splitlines() or [""]):
                print(f"{'[' + who + ']' if i == 0 else ' ' * (len(who) + 2):<20} {chunk[:self.width]}")
