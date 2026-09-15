#!/usr/bin/env bash
# Regenerate Pydantic models from packages/schemas. Run from the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/apps/api/src/rhapto/models"
rm -rf "$OUT"
# datamodel-codegen rglobs every file under --input, so it is pointed at a COPY of
# packages/schemas with the two non-schema files removed: openapi.json (an OpenAPI document,
# regenerated below by export_openapi.py) and taxonomy.yaml (data validated *by* taxonomy.json).
SCAN_PARENT="$(mktemp -d)"
trap 'rm -rf "$SCAN_PARENT"' EXIT
# Kept named "schemas" (not the random mktemp basename): datamodel-codegen stamps --input's
# basename into every generated file's header comment, and a random name would make every
# regeneration churn those comments even with no real schema change.
SCAN="$SCAN_PARENT/schemas"
mkdir -p "$SCAN"
cp -R "$ROOT/packages/schemas/." "$SCAN/"
rm -f "$SCAN/openapi.json" "$SCAN/taxonomy.yaml"
(cd "$ROOT/apps/api" && uv run datamodel-codegen \
  --input "$SCAN" \
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
