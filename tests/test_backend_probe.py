"""Regression test for the backend liveness probe.

`backends._openai_compat_alive` used to call `import request` (not a module), so
it always returned False and `koboldcpp_status()` reported a running server as
inactive.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import backends  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": []}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture()
def live_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_probe_finds_live_server(live_server):
    assert backends._openai_compat_alive(live_server) is True


def test_status_reports_active(live_server):
    active, message = backends.koboldcpp_status({"host": live_server})
    assert active is True
    assert "active" in message.lower()


def test_probe_reports_dead_port():
    assert backends._openai_compat_alive("127.0.0.1:9") is False
