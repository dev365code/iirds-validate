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
import re
import secrets
import socket
import tempfile
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple

from . import __version__, resources, runner
from . import report as report_module

#: Bigger than this and the browser is the wrong tool; the message says so
#: rather than letting the tab go quiet while the process reads.
#:
#: The number is set by what the parse costs, not by what a package might be.
#: The body is read whole and handed to a MIME parser that copies it several
#: times over: measured, a declared body costs the process roughly eleven
#: times its own size in resident memory, so a quarter-gigabyte upload asked
#: for nearly three. The command line has no such limit because it never
#: makes a copy -- it opens the file where it lies.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

#: The page is one path and one response, assembled from the files under
#: data/web/ at request time. Split for editing, not for serving: a stylesheet
#: and a script at their own URLs would be two more paths on a server whose
#: smallness is the point, and the assembly is three substitutions.
WEB = "web"
PAGE, STYLE, SCRIPT, STRINGS = "page.html", "style.css", "app.js", "i18n.json"


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


def page_html(nonce: str = "") -> str:
    """The page, with its parts and its translations put in.

    The nonce is what lets the Content-Security-Policy name this script and
    this stylesheet instead of permitting inline code in general. It is
    generated per response and substituted the same way the version is --
    there is one author for the bytes served and no second copy to keep in
    step, which is the reason a nonce is available here and a checked-in hash
    would have been awkward.
    """
    page = resources.read_text(WEB, PAGE)
    parts = {"__STYLE__": resources.read_text(WEB, STYLE),
             "__SCRIPT__": resources.read_text(WEB, SCRIPT),
             "__VERSION__": __version__,
             "__NONCE__": nonce}
    parts["__SCRIPT__"] = parts["__SCRIPT__"].replace(
        "__I18N__", resources.read_text(WEB, STRINGS))
    for token, value in parts.items():
        page = page.replace(token, value)
    return page


def dropped_name(name: str) -> str:
    """The name to give the copy on disk.

    C3 answers a MUST about the file name extension by reading the container's
    path, so this decides that rule for every package the page is handed. It
    keeps the name the other side sent, including trailing whitespace: a first
    version stripped it, and `handover.iirds ` -- which a content system will
    produce -- then passed here while the command line failed it. Opposite
    verdicts from the handler's own tidying, in the one rule that reads a path.

    What it does change, because a name is not a path and what arrives in a
    multipart header is whatever the sender chose: everything up to the last
    separator goes, so nothing can be written outside the directory made for
    it, and the three names that would still escape or fail to open are
    replaced. Backslashes count as separators regardless of the server's
    platform -- a name from a Windows client should not become a filename
    here that it would not be there.
    """
    candidate = name.replace("\\", "/").rsplit("/", 1)[-1]
    if candidate in ("", ".", "..") or "\x00" in candidate:
        return "dropped.iirds"
    return candidate


def verdict(name: str, payload: bytes) -> Tuple[str, int, dict]:
    """The rendered report, the exit code, and the machine-readable form.

    The renderer is the one the command line calls, on the report the command
    line would have built, so the findings and their wording are the command
    line's. Two things differ and both are by construction: this stream is not
    a terminal, so the page never carries the colour a terminal run does; and
    where a finding quotes the container's own path -- C1 and S1 do, when the
    file cannot be opened at all -- it quotes the copy this function made. The
    machine-readable form is given the name that was dropped rather than that
    copy's path, because the path is a fact about the transport and the name
    is the fact about the document.
    """
    safe = dropped_name(name)
    with tempfile.TemporaryDirectory() as scratch:
        target = os.path.join(scratch, safe)
        with open(target, "wb") as handle:
            handle.write(payload)
        report = runner.run(target, runner.ALL_KINDS)
        rendered = io.StringIO()
        report_module.render_text(report, stream=rendered)
        machine = report.as_dict()
        machine["package"] = safe
        return rendered.getvalue(), (0 if report.ok else 1), machine


class _Handler(BaseHTTPRequestHandler):
    #: No version in the banner. Anything that can reach the port can read a
    #: response, and the version of the tool holding somebody's documentation
    #: is not something to volunteer.
    server_version = "iirds-validate"
    sys_version = ""

    #: Without this a request thread waits for ever on a Content-Length that
    #: was never going to arrive, and nothing reaps it. Measured: fifty
    #: half-open posts left fifty parked threads.
    timeout = 30

    def log_message(self, fmt, *args):            # noqa: A003 - base class name
        """Quiet by default. The default handler writes every request to
        stderr, and the request line carries the name of somebody's document."""
        if self.server.verbose:                   # type: ignore[attr-defined]
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str,
              nonce: str = "") -> None:
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
            "default-src 'none'; style-src 'nonce-%s'; script-src 'nonce-%s'; "
            "img-src data:; form-action 'none'; frame-ancestors 'none'; "
            "connect-src 'self'; base-uri 'none'" % (nonce, nonce))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, status: int, message: str) -> None:
        self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def _same_origin(self) -> bool:
        """Whether this request came from the page this server serves.

        A browser sends Origin on every cross-site POST and on same-origin
        ones too; something that sends none is not a browser and gets the
        benefit of the doubt, because that is how a curl or a test speaks.
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host, port = self.server.server_address[:2]
        return origin.rstrip("/") in ("http://%s:%d" % (host, port),
                                      "http://localhost:%d" % port)

    def send_error(self, code, message=None, explain=None):
        """The base class writes an HTML page here with no policy headers on
        it and a doctype pointing at a URL on the web, which is a strange
        thing for a tool whose subject is not loading pages. Everything
        answers as text, through one place."""
        self._fail(code, "%s\n" % (message or code))

    def do_GET(self) -> None:                     # noqa: N802 - base class name
        if self.path.split("?")[0] not in ("/", "/index.html"):
            # Without this the page answers at every path, which is not a
            # disclosure but is a lie about what is there. `BaseHTTPRequestHandler`
            # has no do_GET of its own -- serving the working directory is
            # `SimpleHTTPRequestHandler`, which this deliberately is not.
            self._fail(404, "not found\n")
            return
        nonce = secrets.token_urlsafe(16)
        self._send(200, page_html(nonce).encode("utf-8"),
                   "text/html; charset=utf-8", nonce=nonce)

    def do_HEAD(self) -> None:                    # noqa: N802 - base class name
        self.do_GET()

    def do_POST(self) -> None:                    # noqa: N802 - base class name
        if self.path.split("?")[0] != "/check":
            self._fail(404, "not found\n")
            return
        if not self._same_origin():
            # multipart/form-data needs no preflight, so any page the user has
            # open can post here. It can never read the answer -- no response
            # carries an allow-origin header -- but it can spend this
            # process's memory and time, and this is the line that stops it.
            self._fail(403, "this page answers the machine it runs on\n")
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
        if not message.is_multipart():
            # iter_parts() keys on the declared content type, not on whether a
            # boundary was actually found, so a body with none leaves the
            # payload a string and the loop below walks it one character at a
            # time -- an AttributeError in a request thread, no response, and
            # a traceback on the operator's terminal. Reachable from any page
            # the user has open: this content type needs no preflight.
            raise ValueError("no multipart boundary in the body")
        for part in message.iter_parts():
            if part.get_filename() is None:
                continue
            return _sent_filename(part), part.get_payload(decode=True) or b""
        raise ValueError("no file in the form")


def _sent_filename(part) -> str:
    """The name as it was sent, before parameter tidying.

    `get_filename()` applies RFC 2045 parameter rules, and one of them strips
    trailing whitespace out of a quoted value: `handover.iirds ` arrived as
    `handover.iirds`. The extension rule reads the container's file name, so
    that made the page pass a package the command line fails -- opposite
    verdicts, decided by the transport rather than by the document. The quoted
    form is read back off the raw header when there is one, which there is for
    every client that does not need escaping.
    """
    disposition = str(part.get("Content-Disposition") or "")
    quoted = re.search(r'filename="([^"\\]*)"', disposition)
    return quoted.group(1) if quoted else (part.get_filename() or "")


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
    print("iirds-validate %s — drop a package at %s" % (__version__, url),
          file=stream, flush=True)
    print("nothing leaves this machine. ctrl-c to stop.", file=stream, flush=True)
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
