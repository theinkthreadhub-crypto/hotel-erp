#!/usr/bin/env bash
# Runs every Setu test against a local cloud (cd cloud && node scripts/copy-assets.mjs && npx wrangler dev --port 8787).
# Needs SETU_HOTEL / SETU_PIN of a TEST hotel (its data is wiped), optional SETU_OTHER (another test hotel)
# and SETU_ADMIN_KEY (local cloud Admin Key, for the delete-code test).
cd "$(dirname "$0")/.."
fail=0
for t in regression qr-ordering inventory expenses reports security data gst autobackup whatsapp; do
  [ "$t" = data ] && [ -z "$SETU_ADMIN_KEY" ] && { echo 'data         skipped (set SETU_ADMIN_KEY)'; continue; }
  printf '%-12s ' "$t"
  out=$(node "tests/$t.js" 2>&1); code=$?
  echo "$out" | grep -E '^FAIL' ; echo "$out" | tail -1
  [ $code -ne 0 ] && fail=1
done
exit $fail
