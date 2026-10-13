"""Build the lab notebooks:  python -m labs.build   (from the kit/ directory)."""
from importlib import import_module
from pathlib import Path

LABS = ["lab1", "lab2", "lab3", "lab4"]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for lab in LABS:
        for p in import_module(f"labs.src.{lab}").book().write(root):
            print("wrote", p.relative_to(root.parent))
    demo = import_module("labs.src.demo_ceos").book()
    import nbformat
    nbformat.write(demo.build("solution", fallback=False), root / "demo_ceos.ipynb")
    print("wrote labs/demo_ceos.ipynb")
