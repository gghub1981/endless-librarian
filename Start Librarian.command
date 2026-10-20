#!/bin/bash
# Double-click to start the Endless Librarian and open it in your browser.
cd "$(dirname "$0")"
# Stop a librarian that is still running (e.g. an older version), so this one can start.
OLD=$(lsof -ti tcp:8765 -sTCP:LISTEN 2>/dev/null)
if [ -n "$OLD" ]; then kill $OLD; sleep 1; fi
(sleep 1; open "http://127.0.0.1:8765") &
exec /usr/bin/python3 app/server.py
