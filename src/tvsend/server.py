"""The small file server the TV fetches the video from.

It listens on ONE address of this computer (the one facing the TV), never on all
interfaces, and hands out only files that were queued for playing, each under a random
token: no folder listing, no guessing of other files.
"""

import os
import re
import secrets
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .backends.dlna import DLNA_FLAGS

ALL_INTERFACES = ("", "0.0.0.0", "::", "*")
IDLE_TIMEOUT = 75  # seconds a silent or stuck connection is kept
GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, socket.timeout)

MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
}


def mime_for(name: str) -> str:
    return MIME.get(os.path.splitext(name)[1].lower(), "video/mp4")


def parse_range(header: str | None, size: int):
    """(start, end) for a single 'bytes=' range, None for 'send it all', 'bad' when outside the file."""
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header or "")
    if not m or not (m.group(1) or m.group(2)):
        return None
    if m.group(1):
        start = int(m.group(1))
        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        if start >= size or end < start:
            return "bad"
        return start, end
    n = int(m.group(2))  # "bytes=-N": the last N bytes
    if n == 0 or size == 0:
        return "bad"
    return max(size - n, 0), size - 1


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive: TVs re-use connections for their many range requests
    server_version = "tvsend"
    sys_version = ""
    timeout = IDLE_TIMEOUT

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)

    def _refuse(self, code, extra=()):
        self.send_response(code)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self._note(code, 0, 0, False)

    def _find(self):
        """Path of the requested file, or None. Only '/<token>/<name>' of a queued file is accepted."""
        parts = self.path.split("?", 1)[0].split("#", 1)[0].split("/")
        if len(parts) != 3 or parts[0]:
            return None
        return self.server.owner.lookup(parts[1], self.client_address[0])

    def _serve(self, body):
        self.t0, self.what = time.time(), self.headers.get("Range", "") or "whole file"
        path = self._find()
        if not path:
            return self._refuse(404)
        try:
            f = open(path, "rb")
        except OSError:
            return self._refuse(404)
        with f:
            size = os.fstat(f.fileno()).st_size
            rng = parse_range(self.headers.get("Range"), size)
            if rng == "bad":
                return self._refuse(416, [("Content-Range", "bytes */%d" % size), ("Accept-Ranges", "bytes")])
            start, end = rng or (0, size - 1)
            length = max(end - start + 1, 0)
            self.send_response(206 if rng else 200)
            if rng:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Content-Type", mime_for(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("transferMode.dlna.org", "Streaming")
            self.send_header("contentFeatures.dlna.org", DLNA_FLAGS)
            self.end_headers()
            sent, dropped = 0, False
            if body and length:
                try:
                    self.wfile.flush()
                    sent = self.connection.sendfile(f, start, length)
                except OSError:  # includes the TV hanging up and idle timeouts
                    sent = max(f.tell() - start, 0)
                if sent < length:  # the TV hung up mid-file (normal when it seeks or stops)
                    dropped = True
                    self.close_connection = True
            self._note(206 if rng else 200, sent, length if body else 0, dropped)

    def _note(self, code, sent, wanted, dropped):
        log = self.server.owner.log
        if not log:
            return
        name = urllib.parse.unquote(self.path.split("?", 1)[0].rsplit("/", 1)[-1])[:120]
        tail = ""
        if wanted:
            tail = "  %.1f of %.1f MB in %.1fs%s" % (
                sent / 1e6,
                wanted / 1e6,
                time.time() - getattr(self, "t0", time.time()),
                "  (TV closed the connection)" if dropped else "",
            )
        log(
            "%s %s %s %s [%s] -> %d%s"
            % (
                time.strftime("%H:%M:%S"),
                self.client_address[0],
                self.command,
                name,
                getattr(self, "what", "-"),
                code,
                tail,
            )
        )

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except GONE:
            self.close_connection = True

    def send_error(self, code, message=None, explain=None):  # bad requests: short answer, no HTML page
        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
        except OSError:
            pass
        self.close_connection = True

    def log_message(self, fmt, *args):  # the default per-request chatter is replaced by _note()
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True  # a stuck TV connection never keeps the program alive
    request_queue_size = 64  # TVs open several connections at once

    def handle_error(self, request, client_address):
        pass


class FileServer:
    def __init__(self, host: str, port: int, log=None):
        if host in ALL_INTERFACES:
            raise ValueError("the file server needs this computer's single network address, not %r" % host)
        self.host, self.port, self.log = host, port, log
        self._tokens: dict[str, str] = {}  # token -> path
        self._by_path: dict[str, str] = {}
        self._fetched: dict[str, set[str]] = {}  # token -> addresses that asked for it
        self._lock = threading.Lock()
        self._srv: _Server | None = None

    @property
    def base(self) -> str:
        return "http://%s:%d/" % (self.host, self.port)

    def start(self) -> None:
        """Start listening. Raises OSError when the address or port cannot be used."""
        if self._srv:
            return
        self._srv = _Server((self.host, self.port), _Handler)
        self._srv.owner = self
        self.port = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, name="tvsend-server", daemon=True).start()

    def stop(self) -> None:
        srv, self._srv = self._srv, None
        if srv:
            srv.shutdown()
            srv.server_close()

    def add(self, path: str) -> str:
        """Make a file fetchable and return its URL. The same file always gets the same URL."""
        path = os.path.realpath(path)
        if not os.path.isfile(path):
            raise OSError("no such file: %s" % path)
        with self._lock:
            token = self._by_path.get(path)
            if not token:
                token = secrets.token_urlsafe(9)
                self._tokens[token], self._by_path[path] = path, token
        return self.base + token + "/" + urllib.parse.quote(os.path.basename(path))

    def lookup(self, token: str, client: str = "") -> str | None:
        """The file behind a token. `client` (who asked) is remembered for fetched()."""
        with self._lock:
            path = self._tokens.get(token)
            if path and client:
                self._fetched.setdefault(token, set()).add(client)
            return path

    def fetched(self, url: str, client: str | None = None) -> bool:
        """Has this URL been asked for - by anyone, or by one address? (Used by the connection test.)"""
        token = url[len(self.base) :].split("/", 1)[0] if self.owns(url) else ""
        with self._lock:
            who = self._fetched.get(token, set())
            return client in who if client else bool(who)

    def owns(self, url: str) -> bool:
        return bool(url) and url.startswith(self.base)
