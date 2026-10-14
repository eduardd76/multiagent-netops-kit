"""LabBook: one source -> student notebook (TODO cells raise) + solution notebook + %%writefile fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

REPO = "eduardd76/multiagent-netops-kit"
REF = "v0.1.4"
PKG = Path(__file__).resolve().parents[2] / "netops"


def setup_cell() -> str:
    return dedent(f'''\
        # SETUP -- run once. Installs the lab package from GitHub (about 15 s).
        # No GitHub access? Run the cells in the APPENDIX at the bottom, then come back and run this cell again.
        import os, importlib.util
        if not os.environ.get("NETOPS_LOCAL") and importlib.util.find_spec("netops") is None:
            get_ipython().run_line_magic("pip", "install -q git+https://github.com/{REPO}@{REF}")
        from netops.llm import make_llm
        from netops import render
        llm = make_llm()       # instructor endpoint if NETOPS_BASE_URL/NETOPS_MODEL/NETOPS_API_KEY are set, else MockLLM
        print("LLM:", render.llm_label(llm))''')


def writefile_cells() -> list:
    """The %%writefile fallback: the whole package, one file per cell."""
    cells = [new_markdown_cell("## APPENDIX -- offline fallback\nOnly if `pip install` failed: run every cell below "
                               "(top to bottom), then re-run the SETUP cell.")]
    files = sorted(p for p in PKG.rglob("*") if p.suffix in (".py", ".yaml") and "__pycache__" not in p.parts)
    dirs = sorted({str(p.parent.relative_to(PKG.parent)) for p in files})
    cells.append(new_code_cell("import os\n" + "\n".join(f"os.makedirs({d!r}, exist_ok=True)" for d in dirs)))
    for p in files:
        cells.append(new_code_cell(f"%%writefile {p.relative_to(PKG.parent)}\n{p.read_text()}"))
    return cells


@dataclass
class _Cell:
    kind: str
    src: str
    todo: str | None = None
    solution: str | None = None


@dataclass
class LabBook:
    slug: str
    title: str
    expect: list[str] = field(default_factory=list)      # markers the solution run must print
    cells: list[_Cell] = field(default_factory=list)

    def md(self, text: str) -> None:
        self.cells.append(_Cell("md", dedent(text).strip()))

    def code(self, src: str) -> None:
        self.cells.append(_Cell("code", dedent(src).strip()))

    def knowledge_check(self, items: list[tuple[str, str]]) -> None:
        """A short self-check at the end of a lab. Answers are collapsed so students try first."""
        parts = ["## Knowledge check", "Answer in your head (or out loud to your neighbor) before you open the answer."]
        for n, (q, a) in enumerate(items, 1):
            parts.append(f"**{n}. {dedent(q).strip()}**\n\n<details><summary>Answer</summary>\n\n"
                         f"{dedent(a).strip()}\n\n</details>")
        self.cells.append(_Cell("md", "\n\n".join(parts)))

    def todo(self, todo_id: str, student: str, solution: str) -> None:
        self.cells.append(_Cell("code", dedent(student).strip(), todo_id, dedent(solution).strip()))

    def build(self, variant: str, fallback: bool = True) -> nbformat.NotebookNode:
        sub = "" if variant == "student" else "solutions/"
        badge = (f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]"
                 f"(https://colab.research.google.com/github/{REPO}/blob/{REF}/labs/{sub}{self.slug}.ipynb)")
        nb = new_notebook()
        nb.cells.append(new_markdown_cell(f"{badge}\n\n# {self.title}" + (" -- SOLUTION" if variant == "solution" else "")))
        nb.cells.append(new_code_cell(setup_cell()))
        for c in self.cells:
            if c.kind == "md":
                nb.cells.append(new_markdown_cell(c.src))
            else:
                cell = new_code_cell(c.solution if (variant == "solution" and c.todo) else c.src)
                if c.todo:
                    cell.metadata["netops"] = {"todo": c.todo}
                nb.cells.append(cell)
        if fallback:
            nb.cells.extend(writefile_cells())
        nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
        nb.metadata["language_info"] = {"name": "python"}
        return nb

    def write(self, root: Path) -> list[Path]:
        out = []
        for variant, sub in (("student", ""), ("solution", "solutions")):
            p = Path(root) / sub / f"{self.slug}.ipynb"
            p.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(self.build(variant), p)
            out.append(p)
        return out
