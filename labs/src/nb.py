"""LabBook: one source -> student notebook (TODO cells raise) + solution notebook + %%writefile fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

REPO = "eduardd76/multiagent-netops-kit"
REF = "v0.1.16"
PKG = Path(__file__).resolve().parents[2] / "netops"


def setup_cell() -> str:
    return dedent(f'''\
        # SETUP -- run once. Installs the lab package from GitHub (about 15 s).
        # Install failed (no GitHub access)? Open the collapsed Appendix at the bottom, run its cells, then run this cell again.
        import os, importlib.util
        if not os.environ.get("NETOPS_LOCAL") and importlib.util.find_spec("netops") is None:
            get_ipython().run_line_magic("pip", "install -q git+https://github.com/{REPO}@{REF}")
        from netops.llm import make_llm
        from netops import render
        llm = make_llm()       # instructor endpoint if NETOPS_BASE_URL/NETOPS_MODEL/NETOPS_API_KEY are set, else MockLLM
        print("LLM:", render.llm_status(llm))   # tests the endpoint once''')


APPENDIX_TITLE = "Appendix - only if the setup cell failed to install (click to open)"
APPENDIX_ID = "appendix"        # fixed cell id, so Colab's collapsed_sections can name it


def writefile_cells() -> list:
    """The %%writefile fallback: the whole package, one file per cell. Collapsed by default
    (Colab: collapsed section + form view; JupyterLab: collapsed heading + hidden source/outputs).
    `%%writefile` must stay the first line of its cell, so those cells carry no #@title."""
    head = new_markdown_cell(f"## {APPENDIX_TITLE}\n"
                             "Only if `pip install` in the SETUP cell failed: run every cell below "
                             "(top to bottom), then re-run the SETUP cell.")
    head.id = APPENDIX_ID
    head.metadata.update({"collapsed": True, "heading_collapsed": True, "jupyter": {"heading_collapsed": True}})
    cells = [head]
    files = sorted(p for p in PKG.rglob("*") if p.suffix in (".py", ".yaml") and "__pycache__" not in p.parts)
    dirs = sorted({str(p.parent.relative_to(PKG.parent)) for p in files})
    cells.append(new_code_cell("#@title kit folders\nimport os\n"
                               + "\n".join(f"os.makedirs({d!r}, exist_ok=True)" for d in dirs)))
    for p in files:
        cells.append(new_code_cell(f"%%writefile {p.relative_to(PKG.parent)}\n{p.read_text()}"))
    for c in cells[1:]:
        c.metadata.update({"cellView": "form", "jupyter": {"source_hidden": True, "outputs_hidden": True}})
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
            nb.metadata["colab"] = {"collapsed_sections": [APPENDIX_ID]}
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

TEAM_MD = """
    ### Meet the team - one NOC shift, in code
    | # | Card | NOC job | Asks the model? | May touch | Lives in |
    |---|---|---|---|---|---|
    | 1 | Coordinator | shift lead | no - plain code | sends the tickets, never writes | `netops/agents/coordinator.py` |
    | 2 | Troubleshooting | tier-2 | only to rank + explain | 6 read checks, run by code | `netops/agents/troubleshooting.py` |
    | 3 | Config | change author | only to pick the playbook entry | nothing - code fills in the commands | `netops/agents/config.py` |
    | 4 | Validation | QA | no - plain code | its own read checks, before + after | `netops/agents/validation.py` |
    | 5 | **You** | **the CAB** | - | approve or reject | this notebook |
    | 6 | Executor | the hands | no - plain code | **the only writer**, once, with your approval token | `netops/executor.py` |

    **The ones who think don't touch. The one who touches doesn't think.** One line builds them all: `team(inc)`.
    The real code of each card, and a diagram of how they talk: """ + f"[docs/TEAM.md](https://github.com/{REPO}/blob/{REF}/docs/TEAM.md)."
