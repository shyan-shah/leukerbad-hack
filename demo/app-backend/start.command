#!/bin/bash
# Double-click to start the Vita backend and its public tunnel. Close this window (or press Ctrl+C) to stop it.
cd "$(dirname "$0")"
open "http://localhost:8787" 2>/dev/null &
exec python3 server.py "$@"
