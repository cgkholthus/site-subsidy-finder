#!/bin/sh
# Start Develop Affordable on http://localhost:8000
cd "$(dirname "$0")"
exec python3 app/server.py
