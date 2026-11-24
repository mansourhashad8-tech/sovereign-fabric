import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sovereign.guardians.base import default_fetch


class _Large(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"x" * 100
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_fetch_rejects_non_http_schemes():
    with pytest.raises(ValueError, match="non-http"):
        default_fetch("file:///etc/passwd")


def test_fetch_enforces_response_size_limit():
    server = HTTPServer(("127.0.0.1", 0), _Large)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        with pytest.raises(ValueError, match="limit|exceeds"):
            default_fetch(url, max_bytes=10)
    finally:
        server.shutdown()
        thread.join(timeout=2)
