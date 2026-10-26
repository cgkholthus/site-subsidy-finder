"""HTTP server: static front end, the JSON lookup endpoint and the chatbot endpoint."""

import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import chat
import cities
import geo
import programs

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


def _load_env_file():
    """Read KEY=value lines from .env into the environment without overriding real env vars."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))


_load_env_file()
_lookups = OrderedDict()  # address -> lookup result, so repeat searches skip the map queries
MAX_CACHED_LOOKUPS = 500
MAX_CHAT_BODY = 64_000

# Per-visitor limits, so a public deployment can't exhaust the free Gemini quota or hammer the map services.
RATE_LIMITS = {  # bucket -> [(max requests, window seconds), ...]
    "lookup": [(20, 60), (300, 86_400)],
    "chat": [(6, 60), (60, 86_400)],
}
_hits = {}
_hits_lock = threading.Lock()


def _allow(bucket, client):
    now = time.time()
    with _hits_lock:
        times = _hits.setdefault((bucket, client), deque())
        longest = max(window for _, window in RATE_LIMITS[bucket])
        while times and now - times[0] > longest:
            times.popleft()
        for limit, window in RATE_LIMITS[bucket]:
            if sum(1 for t in times if now - t <= window) >= limit:
                return False
        times.append(now)
        return True


def _lookup(address):
    key = address.strip().lower()
    if key not in _lookups:
        result = geo.lookup_site(address)
        result["programs"] = programs.match(result)
        city = result["city"]
        result["city"] = {k: city[k] for k in ("id", "name", "last_reviewed", "local_context")}
        result["district_chips"] = cities.district_chips(city, result["districts"])
        result["neighborhood"] = ", ".join(cities.display_name(n) for n in result["districts"].get("neighborhood", []))
        _lookups[key] = result
        if len(_lookups) > MAX_CACHED_LOOKUPS:
            _lookups.popitem(last=False)
    return _lookups[key]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def _client(self):
        # Behind a hosting proxy the visitor's address is the first X-Forwarded-For entry.
        forwarded = self.headers.get("X-Forwarded-For", "")
        return forwarded.split(",")[0].strip() or self.client_address[0]

    def _send_json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        address = (query.get("address") or [""])[0].strip()

        if url.path == "/api/lookup":
            if not address:
                return self._send_json(400, {"error": "Enter an address."})
            if not _allow("lookup", self._client()):
                return self._send_json(429, {"error": "Too many lookups. Please wait a minute and try again."})
            try:
                return self._send_json(200, _lookup(address))
            except geo.LookupError_ as e:
                return self._send_json(404, {"error": str(e)})
            except Exception as e:
                sys.stderr.write(f"lookup failed: {e!r}\n")
                return self._send_json(502, {"error": "The lookup failed. A map service may be down; try again shortly."})

        if url.path == "/api/status":
            return self._send_json(200, {"chat_enabled": chat.enabled()})

        return self._serve_static(url.path)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/api/chat":
            return self._send_json(404, {"error": "Not found"})
        if not _allow("chat", self._client()):
            return self._send_json(429, {"error": "You've asked a lot of questions in a short time. Please wait and try again."})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_CHAT_BODY:
            return self._send_json(413, {"error": "Message too long."})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            address = str(body.get("address") or "").strip()
            lookup = _lookup(address) if address else None
            return self._send_json(200, chat.ask(lookup, body.get("messages") or []))
        except chat.ChatError as e:
            return self._send_json(503, {"error": str(e)})
        except geo.LookupError_ as e:
            return self._send_json(404, {"error": str(e)})
        except (json.JSONDecodeError, AttributeError, TypeError):
            return self._send_json(400, {"error": "Bad request."})

    def _serve_static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        file = (STATIC_DIR / rel).resolve()
        if STATIC_DIR not in file.parents or not file.is_file():
            return self._send_json(404, {"error": "Not found"})
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")  # hosting platforms set HOST=0.0.0.0
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
