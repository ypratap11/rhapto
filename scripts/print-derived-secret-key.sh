#!/usr/bin/env bash
# Prints the RHAPTO_SECRET_KEY value an existing install must use, derived from RHAPTO_API_TOKEN.
#
# WHAT THIS DOES
#   On an install that ran with RHAPTO_SECRET_KEY blank, provider keys and aggregator credentials
#   already saved in Settings were encrypted under a key derived from RHAPTO_API_TOKEN (see
#   `derive_key` in apps/api/src/rhapto/services/secrets.py):
#     base64.urlsafe_b64encode(sha256(RHAPTO_API_TOKEN).digest())
#   Setting RHAPTO_SECRET_KEY to anything else -- including a freshly generated key -- permanently
#   and irreversibly loses that data; there is no recovery once it happens. This script prints the
#   one value that is safe to set: the derived value itself, byte-identical to what the code
#   already derives.
#
# USAGE
#   RHAPTO_API_TOKEN=<the live value> ./scripts/print-derived-secret-key.sh
#   or, against a running deployment:
#     docker compose exec -T api env RHAPTO_API_TOKEN="$(grep -E '^RHAPTO_API_TOKEN=' .env | cut -d= -f2-)" \
#       python3 -c "import base64,hashlib,os; print(base64.urlsafe_b64encode(hashlib.sha256(os.environ['RHAPTO_API_TOKEN'].encode()).digest()).decode())"
#
#   RHAPTO_API_TOKEN is read from the environment only -- never from a committed file -- and the
#   token itself is never printed, only the derived key. See docs/runbook-deploy.md step 5 for
#   where this fits in a deploy.
set -euo pipefail

if [ -z "${RHAPTO_API_TOKEN:-}" ]; then
  echo "error: RHAPTO_API_TOKEN is not set in the environment" >&2
  exit 1
fi

python3 -c "
import base64, hashlib, os
print(base64.urlsafe_b64encode(hashlib.sha256(os.environ['RHAPTO_API_TOKEN'].encode()).digest()).decode())
"
