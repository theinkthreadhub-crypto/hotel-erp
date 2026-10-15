#!/bin/sh
# Build the vendor guide PDF. Needs screenshots in $SHOTS (see shots_*.js).
set -e; cd "$(dirname "$0")"; OUT=${OUT:-/tmp/claude-0/guide}
python3 vendor_guide.py $OUT/vendor_body.html
node render.js $OUT/vendor_body.html $OUT/vendor_body.pdf "Setu Pro · Team Guide (internal)  · 6392995127"
node render.js vendor_cover.html $OUT/vendor_cover.pdf --cover
python3 assemble.py $OUT/vendor_cover.pdf $OUT/vendor_body.pdf $OUT/Setu-Pro-Team-Guide.pdf "Setu Pro Team Guide (internal)"
