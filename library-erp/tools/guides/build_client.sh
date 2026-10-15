#!/bin/sh
# Build the client guide PDF. Needs screenshots in $SHOTS (see shots_*.js).
set -e; cd "$(dirname "$0")"; OUT=${OUT:-/tmp/claude-0/guide}
python3 client_guide.py $OUT/client_body.html
node render.js $OUT/client_body.html $OUT/client_body.pdf "Setu Pro · Library ERP — Use Karne Ki Guide · 6392995127"
node render.js client_cover.html $OUT/client_cover.pdf --cover
python3 assemble.py $OUT/client_cover.pdf $OUT/client_body.pdf $OUT/Library-ERP-Client-Guide.pdf "Library ERP — Use Karne Ki Guide"
