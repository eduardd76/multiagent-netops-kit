"""Execute every lab headless (MockLLM): solutions must run clean, students must stop at a TODO,
and the %%writefile fallback must rebuild an importable package from nothing."""
import importlib
import os
import subprocess
import sys

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

pytestmark = pytest.mark.notebooks
LABS = ["lab1", "lab2", "lab3", "lab4"]
ENV = {"NETOPS_LOCAL": "1", "NETOPS_LLM": "mock"}


def _run(nb, cwd=None):
    old = {k: os.environ.get(k) for k in ENV}
    os.environ.update(ENV)
    for k in ("NETOPS_BASE_URL", "NETOPS_MODEL", "NETOPS_API_KEY"):
        os.environ.pop(k, None)
    try:
        NotebookClient(nb, timeout=300, kernel_name="netops-kit",
                       resources={"metadata": {"path": cwd or os.getcwd()}}).execute()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return "\n".join(o.get("text", "") for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", []))


@pytest.mark.parametrize("lab", LABS)
def test_solution_runs_clean(lab):
    book = importlib.import_module(f"labs.src.{lab}").book()
    text = _run(book.build("solution", fallback=False))
    for marker in book.expect:
        assert marker in text, f"{lab}: expected {marker!r} in the output"


@pytest.mark.parametrize("lab", LABS)
def test_student_stops_at_a_todo(lab):
    book = importlib.import_module(f"labs.src.{lab}").book()
    with pytest.raises(CellExecutionError) as e:
        _run(book.build("student", fallback=False))
    assert "NotImplementedError" in str(e.value) and "TODO(" in str(e.value)


def test_writefile_fallback_rebuilds_the_package(tmp_path):
    from labs.src.nb import writefile_cells
    nb = nbformat.v4.new_notebook()
    nb.cells = writefile_cells()[1:]          # skip the markdown
    _run(nb, cwd=str(tmp_path))
    out = subprocess.run([sys.executable, "-c",
                          "import netops, netops.orchestrator as o; print(netops.__file__); "
                          "i=o.new_incident(verbose=False); print(o.run_lab1(i)['reachability'])"],
                         cwd=tmp_path, capture_output=True, text=True, env={**os.environ, "NETOPS_LLM": "mock"})
    assert str(tmp_path) in out.stdout and "FAIL" in out.stdout, out.stderr
