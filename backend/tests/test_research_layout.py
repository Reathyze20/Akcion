"""
The boundary between the app and the research area.

One rule carries the whole design: `backend/app/` never imports
`backend/research/`. The dependency runs the other way, so that a candidate and
the reference distribution it is compared against are computed by one and the
same code, and so that a machine with no `backend/.env` and no database can
still run the research.

If that rule goes, the failure is quiet: the service starts depending on a CSV
somebody has to regenerate, and the research area starts being a second
application. Hence a test rather than a paragraph in a README.
"""

import ast
import pathlib
from typing import Final

import pytest

BACKEND: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent
APP: Final[pathlib.Path] = BACKEND / "app"
RESEARCH: Final[pathlib.Path] = BACKEND / "research"
GITIGNORE: Final[pathlib.Path] = BACKEND.parent / ".gitignore"

#: What a research module may import at the top level.
#:
#: `app.*` is on the list and that is the point: the research area is allowed to
#: reuse the app's pure functions, which is how `market_gauge.fit` and
#: `score_outcomes.fetch_bars` mean the same thing in both places. What the list
#: keeps out is a research area that grows its own framework, its own ORM and
#: its own HTTP layer, at which point nobody can tell which of the two is the
#: real program.
ALLOWED_THIRD_PARTY: Final[frozenset[str]] = frozenset({"pandas", "yfinance"})

#: Everything else has to be the standard library or the app.
STDLIB_HINT: Final[str] = (
    "Povolené jsou jen standardní knihovna, pandas, yfinance a app.*. "
    "Viz backend/research/README.md."
)


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _top_level_imports(path: pathlib.Path) -> set[str]:
    """Root module names imported at module scope. Lazy imports are exempt."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:  # module scope only — a lazy import inside a
        if isinstance(node, ast.Import):  # function is a deliberate choice
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside the package
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


# ==============================================================================
# The rule
# ==============================================================================

def test_the_app_never_imports_the_research_area():
    """
    The architectural invariant the rest of the design rests on.

    Checked over every module under `app/`, at every scope — a lazy
    `import research` inside a function would be just as fatal and much harder
    to spot, so this greps the source rather than walking the AST's top level.
    """
    offenders = []
    for path in _python_files(APP):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.split(".")[0] == "research" for a in node.names):
                    offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] == "research":
                    offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert offenders == [], (
        "backend/app/ importuje backend/research/. Závislost musí vést opačně: "
        "sdílený výpočet patří do app/services/, výzkum si ho importuje.\n"
        + "\n".join(offenders)
    )


def test_research_out_is_gitignored():
    """
    Cheap, and it catches the mistake that would otherwise land as a 40 MB diff.

    Everything under `out/` is a function of the committed inputs plus yfinance
    on a given day, and yfinance rewrites adjusted history backwards on every
    split — a committed copy drifts from its source in silence.
    """
    ignored = GITIGNORE.read_text(encoding="utf-8")
    assert "backend/research/out/" in ignored


def test_research_modules_import_only_what_they_are_allowed_to():
    offenders: list[str] = []
    for path in _python_files(RESEARCH):
        for name in _top_level_imports(path):
            if name in {"app", "research"} or name in ALLOWED_THIRD_PARTY:
                continue
            try:
                __import__(name)
            except ImportError:  # pragma: no cover — a typo'd import
                offenders.append(f"{path.relative_to(BACKEND)}: {name} (nejde importovat)")
                continue
            module = __import__(name)
            origin = getattr(getattr(module, "__spec__", None), "origin", "") or ""
            if "site-packages" in origin:
                offenders.append(f"{path.relative_to(BACKEND)}: {name}")
    assert offenders == [], STDLIB_HINT + "\n" + "\n".join(offenders)


# ==============================================================================
# The committed inputs
# ==============================================================================

@pytest.mark.parametrize(
    "name",
    ["priority_ideas.csv", "priority_ideas_labels.csv"],
)
def test_the_committed_inputs_are_where_the_loader_looks(name):
    assert (RESEARCH / "data" / name).exists()


def test_the_research_area_has_a_readme_stating_the_rule():
    """
    A test can say the import is banned; only the README can say why, and the
    why is what stops somebody "fixing" the test.
    """
    readme = (RESEARCH / "README.md").read_text(encoding="utf-8")
    assert "backend/app/` nikdy neimportuje" in readme
