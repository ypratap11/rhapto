#!/usr/bin/env bash
# End-to-end smoke against a running compose stack: health, auth, profile import, job intake, tailor, package download.
# Requires: docker compose up -d (all services), .env with RHAPTO_API_TOKEN and ANTHROPIC_API_KEY, curl, jq.
set -euo pipefail
BASE="${RHAPTO_API_URL:-http://localhost:8000/api/v1}"
TOKEN="${RHAPTO_API_TOKEN:-$(grep -E '^RHAPTO_API_TOKEN=' .env 2>/dev/null | cut -d= -f2- || true)}"
[ -n "$TOKEN" ] || { echo "RHAPTO_API_TOKEN not set (env or .env)" >&2; exit 1; }
auth=(-H "Authorization: Bearer $TOKEN")

echo "health: $(curl -fsS "$BASE/health")"
echo "me: $(curl -fsS "${auth[@]}" "$BASE/me")"
files=()
for f in profile.example/*.yaml; do files+=(-F "files=@$f"); done
echo "import: $(curl -fsS "${auth[@]}" -X POST "$BASE/profile/import" "${files[@]}")"
JD='ExampleCo is hiring a Data Platform Program Manager to lead our Snowflake migration and ETL modernisation across product, data engineering, and analytics teams. Must have warehouse migration experience and cross-functional leadership.'
job=$(curl -fsS "${auth[@]}" -H 'content-type: application/json' -X POST "$BASE/jobs" -d "{\"jd_text\": $(printf '%s' "$JD" | jq -Rs .), \"company\": \"ExampleCo\", \"title\": \"Data Platform Program Manager\"}")
job_id=$(echo "$job" | jq -r .id)
echo "job: $job_id"
task=$(curl -fsS "${auth[@]}" -H 'content-type: application/json' -X POST "$BASE/jobs/$job_id/tailor" -d '{}')
task_id=$(echo "$task" | jq -r .id)
echo "task: $task_id (waiting for the worker)"
for _ in $(seq 1 60); do
  status=$(curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq -r .status)
  [ "$status" = "succeeded" ] || [ "$status" = "failed" ] && break
  sleep 2
done
curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq '{status, error, step: .progress.step}'
package_id=$(curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq -r .result_ref)
[ "$package_id" != "null" ] && curl -fsS "${auth[@]}" "$BASE/packages/$package_id/download" -o out/smoke-package.zip && echo "downloaded out/smoke-package.zip"
