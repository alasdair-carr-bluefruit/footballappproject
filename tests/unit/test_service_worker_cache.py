"""Guard: the service worker pre-caches every frontend module (C.7).

app.js is a thin entry point that side-effect-imports the feature modules, which
in turn import shared helpers (api.js, toast.js). If sw.js's SHELL caches only
some of them, an offline / stale-cache load gets a broken app. This test asserts
SHELL covers *every* served frontend module, so the list can't silently drift
out of sync with frontend/*.js (as it did before C.7, when only app.js was
cached).
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _frontend_modules() -> set[str]:
    """Root-absolute paths of every served frontend module, e.g. {'/state.js', ...}.

    Excludes sw.js itself — the service worker is registered, never imported or
    cached as shell.
    """
    return {f"/{p.name}" for p in FRONTEND.glob("*.js") if p.name != "sw.js"}


def _shell_entries() -> set[str]:
    text = (FRONTEND / "sw.js").read_text()
    block = re.search(r"const SHELL\s*=\s*\[(.*?)\]", text, re.DOTALL)
    assert block, "Could not find the SHELL array in sw.js"
    return set(re.findall(r"""['"]([^'"]+)['"]""", block.group(1)))


def test_shell_caches_every_frontend_module():
    modules = _frontend_modules()
    assert modules, "expected to find frontend modules"
    missing = modules - _shell_entries()
    assert not missing, f"sw.js SHELL is missing frontend modules: {sorted(missing)}"


def test_shell_includes_entry_point_and_core_assets():
    shell = _shell_entries()
    for essential in ("/", "/app.js", "/api.js", "/style.css"):
        assert essential in shell, f"sw.js SHELL is missing {essential}"


def test_shell_entries_all_exist_on_disk():
    # Every cached .js path must map to a real file (typo guard).
    for entry in _shell_entries():
        if entry.endswith(".js"):
            assert (FRONTEND / entry.lstrip("/")).is_file(), f"SHELL lists missing file {entry}"
