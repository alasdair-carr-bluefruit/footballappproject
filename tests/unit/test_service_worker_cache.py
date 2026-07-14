"""Guard: the service worker pre-caches every frontend module (C.7).

app.js is a thin entry point whose only job is to side-effect-import the six
feature modules. If the service worker's SHELL list caches app.js but not those
modules, an offline / stale-cache load gets a broken app. This test parses the
actual import list out of app.js and asserts sw.js's SHELL covers all of it, so
the two can't silently drift apart (as they did before C.7).
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _app_module_imports() -> set[str]:
    """Root-absolute paths of the modules app.js imports, e.g. {'/state.js', ...}."""
    text = (FRONTEND / "app.js").read_text()
    # matches:  import "./state.js";   /   import x from "./api.js";
    rel = re.findall(r"""import\s+(?:.*?\s+from\s+)?['"]\.\/([\w-]+\.js)['"]""", text)
    return {f"/{name}" for name in rel}


def _shell_entries() -> set[str]:
    text = (FRONTEND / "sw.js").read_text()
    block = re.search(r"const SHELL\s*=\s*\[(.*?)\]", text, re.DOTALL)
    assert block, "Could not find the SHELL array in sw.js"
    return set(re.findall(r"""['"]([^'"]+)['"]""", block.group(1)))


def test_shell_caches_every_app_module():
    imported = _app_module_imports()
    assert imported, "expected app.js to import at least one module"
    missing = imported - _shell_entries()
    assert not missing, f"sw.js SHELL is missing app.js modules: {sorted(missing)}"


def test_shell_includes_entry_point_and_core_assets():
    shell = _shell_entries()
    for essential in ("/", "/app.js", "/api.js", "/style.css"):
        assert essential in shell, f"sw.js SHELL is missing {essential}"


def test_shell_entries_all_exist_on_disk():
    # Every cached .js path must map to a real file (typo guard).
    for entry in _shell_entries():
        if entry.endswith(".js"):
            assert (FRONTEND / entry.lstrip("/")).is_file(), f"SHELL lists missing file {entry}"
