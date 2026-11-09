"""Write apps/web/src/lib/admin/contract.json: admin model schemas and the admin route list.

The public OpenAPI document deliberately omits the admin area, so the web app reads this file
instead. A test fails when it drifts from the models or routes.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel

from rhapto.api import admin_schemas
from rhapto.api.routers import admin

OUT = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "admin" / "contract.json"


def build_contract() -> dict[str, Any]:
    models = {
        name: obj.model_json_schema()
        for name, obj in sorted(vars(admin_schemas).items())
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj.__module__ == admin_schemas.__name__
    }
    routes = sorted(
        (
            {"method": m, "path": r.path}
            for r in admin.router.routes
            if isinstance(r, APIRoute) and "{rest" not in r.path and r.path != "/admin"
            for m in sorted(r.methods or ())
        ),
        key=lambda x: (x["path"], x["method"]),
    )
    return {"models": models, "routes": routes}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_contract(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
