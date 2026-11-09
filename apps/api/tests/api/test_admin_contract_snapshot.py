"""The committed web contract must match the admin models and routes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = API_ROOT / "scripts" / "export_admin_contract.py"
COMMITTED = API_ROOT.parent / "web" / "src" / "lib" / "admin" / "contract.json"


def _build() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("export_admin_contract", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    built: dict[str, Any] = mod.build_contract()
    return built


def test_committed_contract_matches_the_models_and_routes() -> None:
    built = _build()
    assert built["routes"], "no routes: the comparison would be vacuous"
    assert built["models"], "no models: the comparison would be vacuous"
    committed = json.loads(COMMITTED.read_text("utf-8"))
    assert committed == built, "run apps/api/scripts/export_admin_contract.py and commit the result"


def test_contract_lists_the_action_routes_and_no_catch_all() -> None:
    routes = {(r["method"], r["path"]) for r in _build()["routes"]}
    assert ("POST", "/admin/users/{user_id}/reset-runs") in routes
    assert ("POST", "/admin/users/{user_id}/block") in routes
    assert ("POST", "/admin/users/{user_id}/unblock") in routes
    assert not [p for _, p in routes if "{rest" in p or p == "/admin"]
