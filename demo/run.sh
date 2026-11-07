#!/bin/sh
# Serve the static demo on http://127.0.0.1:8797 (loopback only). No model or LLM calls at run time.
# Any static web server works: the page is the folder site/.
cd "$(dirname "$0")/site"
exec python3 -m http.server 8797 --bind 127.0.0.1
