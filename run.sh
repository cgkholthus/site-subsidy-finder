#!/bin/sh
# Start the Site Subsidy Finder on http://localhost:8000
cd "$(dirname "$0")"
exec python3 app/server.py
