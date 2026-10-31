#!/usr/bin/env bash
# Puts the newest Setu installer (GitHub release "setu-latest") into cloud/public/download/ with latest.json,
# so counter PCs can update themselves and clients can download "Install for PC" from the cloud.
# Needs GH_TOKEN (the workflow's github.token). Without a release it does nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p public/download
if ! gh release download setu-latest -p Setu-POS-Setup.exe -D public/download --clobber; then
  echo "::warning::No setu-latest installer found; the cloud has no download."
  rm -rf public/download
  exit 0
fi
body=$(gh release view setu-latest --json body -q .body)
version=$(echo "$body" | grep -oE 'Setu v[0-9]+\.[0-9]+\.[0-9]+' | head -1 | sed 's/Setu v//')
sha=$(sha256sum public/download/Setu-POS-Setup.exe | cut -d' ' -f1)
size=$(stat -c %s public/download/Setu-POS-Setup.exe)
# Cloudflare serves files up to 25 MiB: a bigger installer goes up in 20 MiB parts that the worker joins (installerDownload)
parts=0
if [ "$size" -gt 25000000 ]; then
  (cd public/download && split -b 20M -d -a 2 Setu-POS-Setup.exe Setu-POS-Setup.exe.part && rm Setu-POS-Setup.exe)
  parts=$(ls public/download/Setu-POS-Setup.exe.part* | wc -l)
fi
printf '{"version":"%s","sha256":"%s","size":%s,"parts":%s,"at":"%s"}\n' "$version" "$sha" "$size" "$parts" "$(date -u +%FT%TZ)" > public/download/latest.json
cat public/download/latest.json
