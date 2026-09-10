"""Write the API's OpenAPI document to packages/schemas/openapi.json (the frontend generates its client from it)."""

from __future__ import annotations

import json
from pathlib import Path

from rhapto.api.app import create_app
from rhapto.config import Settings

OUT = Path(__file__).resolve().parents[3] / "packages" / "schemas" / "openapi.json"


def main() -> None:
    app = create_app(Settings(_env_file=None))
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
