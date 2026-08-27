"""A drop page on the loopback interface.

The report has only ever existed as text on a terminal, and the people who
build iiRDS packages are technical writers rather than people who read one.
This puts a drop zone in front of the same run: a page served from 127.0.0.1,
a file posted back to a handler in this process, and the verdict rendered by
the function the command line already calls.

That last part is the design and not an implementation detail. A second
renderer would be a second encoding of the report, and two encodings of the
same thing have to be proven to agree -- which is what the shapes cost. Here
there is nothing to prove: `report.render_text` is called on the same `Report`
object, in the same process, so the page cannot say something the command line
would not.

What this is not: a service. It binds to loopback and refuses anything else,
because the product is that the document does not leave the machine, and a
bind address is the only line between those two. It is also not the answer for
a closed network with nothing installed -- that is the single-file archive,
and docs/offline-install.md says why.
"""
from __future__ import annotations

import io
import ipaddress
import json
import os
import socket
import tempfile
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple

from . import __version__, resources, runner
from . import report as report_module

#: Bigger than this and the browser is the wrong tool; the message says so
#: rather than letting the tab go quiet while the process reads.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024

PAGE = "serve.html"


def _is_loopback(host: str) -> bool:
    """Whether `host` names this machine and only this machine.

    By name as well as by address: `localhost` is what a person types, and
    resolving it is the only honest way to answer for it.
    """
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(
        ipaddress.ip_address(info[4][0]).is_loopback for info in infos)


def page_html() -> str:
    return resources.read_text(PAGE).replace("__VERSION__", __version__)


def verdict(name: str, payload: bytes) -> Tuple[str, int, dict]:
    """The rendered report, the exit code, and the machine-readable form.

    The name is the browser's, carried through verbatim, because C3 reads the
    container's file name to answer a MUST about the extension: a handler that
    renamed the temporary copy would decide that rule for every package it was
    handed. Reduced to a basename first -- a name is not a path, and what
    arrives in a multipart header is whatever the other side chose to send.
    """
    safe = os.path.basename(name.replace("\\", "/")).strip() or "dropped.iirds"
    with tempfile.TemporaryDirectory() as scratch:
        target = os.path.join(scratch, safe)
        with open(target, "wb") as handle:
            handle.write(payload)
        report = runner.run(target, runner.ALL_KINDS)
        rendered = io.StringIO()
        report_module.render_text(report, stream=rendered)
        return rendered.getvalue(), (0 if report.ok else 1), report.as_dict()


class _Handler(BaseHTTPRequestHandler):
    server_version = "iirds-validate/%s" % __version__
    sys_version = ""

    def log_message(self, fmt, *args):            # noqa: A003 - base class name
        """Quiet by default. The default handler writes every request to
        stderr, and the request line carries the name of somebody's document."""
        if self.server.verbose:                   # type: ignore[attr-defined]
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Nothing here is meant to be embedded, cached, or reached from
        # another page: the process is holding somebody's documentation.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "img-src data:; form-action 'none'; connect-src 'self'; base-uri 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, status: int, message: str) -> None:
        self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self) -> None:                     # noqa: N802 - base class name
        if self.path.split("?")[0] not in ("/", "/index.html"):
            # Never the working directory. The base class would have served it.
            self._fail(404, "not found\n")
            return
        self._send(200, page_html().encode("utf-8"), "text/html; charset=utf-8")

    def do_HEAD(self) -> None:                    # noqa: N802 - base class name
        self.do_GET()

    def do_POST(self) -> None:                    # noqa: N802 - base class name
        if self.path.split("?")[0] != "/check":
            self._fail(404, "not found\n")
            return
        try:
            name, payload = self._read_upload()
        except ValueError as exc:
            self._fail(400, "%s\n" % exc)
            return
        try:
            text, code, machine = verdict(name, payload)
        except Exception as exc:                  # a crash is not an answer
            body = json.dumps({"text": "could not read %s: %s\n" % (name, exc),
                               "exit": 2, "report": None}, ensure_ascii=False)
            self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")
            return
        body = json.dumps({"text": text, "exit": code, "report": machine},
                          ensure_ascii=False)
        self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")

    def _read_upload(self) -> Tuple[str, bytes]:
        declared = int(self.headers.get("Content-Length") or 0)
        if declared <= 0:
            raise ValueError("no body")
        if declared > MAX_UPLOAD_BYTES:
            raise ValueError(
                "%d bytes is more than this page will hold; the command line "
                "has no such limit" % declared)
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("expected multipart/form-data")
        raw = (b"Content-Type: %s\r\nMIME-Version: 1.0\r\n\r\n"
               % content_type.encode("utf-8")) + self.rfile.read(declared)
        message = BytesParser(policy=HTTP).parsebytes(raw)
        for part in message.iter_parts():
            filename = part.get_filename()
            if filename is None:
                continue
            return filename, part.get_payload(decode=True) or b""
        raise ValueError("no file in the form")


def build_server(host: str = "127.0.0.1", port: int = 0,
                 verbose: bool = False) -> ThreadingHTTPServer:
    """A server bound to loopback, or a refusal.

    The refusal is the point. Everything else here is a convenience; this is
    the line that keeps the promise on the front of the project.
    """
    if not _is_loopback(host):
        raise ValueError(
            "%r is not a loopback address: this page serves the machine it "
            "runs on and nothing else" % host)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.verbose = verbose                       # type: ignore[attr-defined]
    return httpd


def serve(host: str = "127.0.0.1", port: int = 0, open_browser: bool = True,
          verbose: bool = False, stream=None) -> int:
    import sys

    stream = sys.stdout if stream is None else stream
    httpd = build_server(host, port, verbose=verbose)
    url = "http://%s:%d/" % (httpd.server_address[0], httpd.server_address[1])
    print("iirds-validate %s — drop a package at %s" % (__version__, url), file=stream)
    print("nothing leaves this machine. ctrl-c to stop.", file=stream)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def address_of(httpd: ThreadingHTTPServer) -> Optional[str]:
    return "http://%s:%d/" % httpd.server_address[:2]
