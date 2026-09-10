#!/usr/bin/env bash
# Regenerate Pydantic models from packages/schemas. Run from the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/apps/api/src/rhapto/models"
rm -rf "$OUT"
# The exported OpenAPI document lives in packages/schemas too (see below) so the
# frontend can generate its client from it, but it is not a JSON Schema input for
# the Pydantic models: remove it before scanning the directory, then regenerate it.
rm -f "$ROOT/packages/schemas/openapi.json"
(cd "$ROOT/apps/api" && uv run datamodel-codegen \
  --input "$ROOT/packages/schemas" \
  --input-file-type jsonschema \
  --output "$OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --use-title-as-name \
  --strict-nullable \
  --use-annotated \
  --field-constraints \
  --enum-field-as-literal all \
  --use-standard-collections \
  --use-union-operator \
  --collapse-root-models \
  --use-schema-description \
  --use-field-description \
  --target-python-version 3.12 \
  --disable-timestamp)
touch "$OUT/__init__.py" "$OUT/profile/__init__.py"
echo "models regenerated in $OUT"

(cd "$ROOT/apps/api" && uv run python scripts/export_openapi.py)
if [ -d "$ROOT/apps/web/node_modules" ]; then
  (cd "$ROOT/apps/web" && pnpm gen:api)
  echo "TypeScript API types regenerated"
fi
