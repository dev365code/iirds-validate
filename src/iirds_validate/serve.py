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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple

from . import __version__, resources, runner
from . import report as report_module

#: Bigger than this and the browser is the wrong tool; the message says so
#: rather than letting the tab go quiet while the process reads.
#:
#: The number is set by what the drop costs, and that is now the body once on
#: disk plus one chunk in memory: measured, a sixteen-megabyte upload moves
#: the process's peak by one megabyte. It was thirty-two when the body was
#: read whole and handed to a MIME parser that copied it eleven times over,
#: and that limit was a bandage over the parse rather than a fact about
#: packages. A quarter gigabyte is a real package; the command line has no
#: limit at all because it opens the file where it lies.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024

#: The page is one path and one response, assembled from the files under
#: data/web/ at request time. Split for editing, not for serving: a stylesheet
#: and a script at their own URLs would be two more paths on a server whose
#: smallness is the point, and the assembly is three substitutions.
WEB = "web"
PAGE, STYLE, SCRIPT, STRINGS = "page.html", "style.css", "app.js", "i18n.json"


def origin_of(address: str, port: int) -> str:
    """`http://host:port`, with an IPv6 literal bracketed.

    `localhost` resolves to ::1 on a machine with IPv6, so this is not the
    exotic branch it looks like: without the brackets the address the command
    prints is one a browser cannot open, and the same-origin check compares
    against a string no browser would ever send.
    """
    host = "[%s]" % address if ":" in address else address
    return "http://%s:%d" % (host, port)


def loopback_address(host: str) -> Optional[str]:
    """The literal `host` resolves to, if every answer is this machine.

    By name as well as by address, because `localhost` is what a person
    types. It returns the address rather than a yes, and the caller binds
    what it returns: resolving the name again at bind time would be a second
    lookup that could answer differently from the one that was checked, and a
    record with no time to live is enough to make it.
    """
    if not host:
        return None
    try:
        return host if ipaddress.ip_address(host).is_loopback else None
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return None
    if not infos:
        return None
    addresses = [info[4][0] for info in infos]
    if not all(ipaddress.ip_address(a).is_loopback for a in addresses):
        return None
    return addresses[0]


def _is_loopback(host: str) -> bool:
    return loopback_address(host) is not None


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


def verdict(name: str, payload) -> Tuple[str, int, dict]:
    """The rendered report, the exit code, and the machine-readable form.

    `payload` is bytes, or a path to a file already holding them. The handler
    passes a path: the upload is streamed to disk as it arrives and never held
    whole, so this must not ask for it whole either -- measured, a body read
    into memory and handed to a MIME parser cost the process eleven times its
    own size. Bytes are accepted for the library caller and the tests.

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
        if isinstance(payload, (bytes, bytearray)):
            with open(target, "wb") as handle:
                handle.write(payload)
        else:
            os.replace(payload, target)
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
        return origin.rstrip("/") in (origin_of(host, port),
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
        spool = None
        try:
            name, spool = self._read_upload()
        except ValueError as exc:
            self._fail(400, "%s\n" % exc)
            return
        try:
            text, code, machine = verdict(name, spool)
        except Exception as exc:                  # a crash is not an answer
            body = json.dumps({"text": "could not read %s: %s\n" % (name, exc),
                               "exit": 2, "report": None}, ensure_ascii=False)
            self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")
            return
        body = json.dumps({"text": text, "exit": code, "report": machine},
                          ensure_ascii=False)
        self._send(200, body.encode("utf-8"), "application/json; charset=utf-8")

    def _read_upload(self) -> Tuple[str, str]:
        """The sent file name, and the path of a spool file holding the bytes.

        Streamed, not parsed. The first version read the whole body and gave
        it to a MIME parser, which copies it several times over: measured,
        that cost the process eleven times the body. This reads the part's
        headers -- a few hundred bytes -- and then copies the payload to disk
        chunk by chunk, watching for the closing boundary as it goes.

        The one hard case is a boundary straddling two chunks. A tail as long
        as the boundary is held back from each flush, so the delimiter is
        always seen whole; the cost is one extra copy of that many bytes.
        """
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
        boundary = _boundary_of(content_type)
        if not boundary:
            raise ValueError("no multipart boundary declared")

        reader = _Counted(self.rfile, declared)
        delimiter = b"\r\n--" + boundary
        name = None
        while name is None:
            # Skip to the part whose headers name a file. Each part's headers
            # end at the first blank line; a part without a filename is a
            # form field and its body is drained up to the next delimiter.
            headers = reader.read_until(b"\r\n\r\n", limit=64 * 1024)
            if headers is None:
                raise ValueError("no multipart boundary in the body")
            candidate = _filename_in(headers)
            if candidate is None:
                if reader.drain_to(delimiter) is None:
                    raise ValueError("no file in the form")
                continue
            name = candidate

        # delete=False because the path outlives this block: verdict() moves
        # the file into its own directory. On any failure it is removed here,
        # so a refused upload leaves nothing behind.
        with tempfile.NamedTemporaryFile(delete=False, prefix="drop-",
                                         suffix=".spool") as handle:
            spool = handle.name
            try:
                if reader.copy_to(handle, delimiter) is None:
                    raise ValueError("the upload ended before its closing boundary")
            except BaseException:
                handle.close()
                os.unlink(spool)
                raise
        return name, spool


def _boundary_of(content_type: str) -> bytes:
    """The boundary parameter, quoted or bare, as bytes."""
    found = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type)
    if not found:
        return b""
    return (found.group(1) or found.group(2)).encode("latin-1")


def _filename_in(headers: bytes):
    """The file name from a part's headers, or None for a plain field.

    Read off the raw Content-Disposition line rather than through a MIME
    parser, for the reason `_sent_filename` gives: parameter tidying strips
    the trailing whitespace a real name can carry, and the extension rule
    reads that name.
    """
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-disposition:"):
            text = line.decode("utf-8", errors="replace")
            quoted = re.search(r'filename="([^"\\]*)"', text)
            if quoted:
                return quoted.group(1)
            bare = re.search(r"filename=([^;\s]+)", text)
            if bare:
                return bare.group(1)
            return None
    return None


class _Counted:
    """A reader over exactly `limit` bytes of a stream, in chunks.

    Never asks the socket for more than the body declares, so a client that
    lied upward cannot make it wait for bytes that will not come; the socket
    timeout on the handler covers a client that lied downward.
    """
    CHUNK = 1 << 16

    def __init__(self, stream, limit: int):
        self._stream = stream
        self._left = limit
        self._buffer = b""

    def _fill(self) -> bool:
        if self._left <= 0:
            return False
        chunk = self._stream.read(min(self.CHUNK, self._left))
        if not chunk:
            self._left = 0
            return False
        self._left -= len(chunk)
        self._buffer += chunk
        return True

    def read_until(self, marker: bytes, limit: int):
        """Bytes up to and excluding `marker`, or None if it never comes
        within `limit` bytes. The marker is consumed."""
        while True:
            at = self._buffer.find(marker)
            if at >= 0:
                out, self._buffer = self._buffer[:at], self._buffer[at + len(marker):]
                return out
            if len(self._buffer) > limit or not self._fill():
                return None

    def drain_to(self, delimiter: bytes):
        """Discard up to and including `delimiter`; None if it never comes."""
        return self.copy_to(None, delimiter)

    def copy_to(self, handle, delimiter: bytes):
        """Copy bytes to `handle` (or nowhere) until `delimiter`, which is
        consumed along with the rest of its line. Returns the byte count, or
        None if the stream ended first."""
        written = 0
        keep = len(delimiter)
        while True:
            at = self._buffer.find(delimiter)
            if at >= 0:
                if handle is not None:
                    handle.write(self._buffer[:at])
                written += at
                rest = self._buffer[at + keep:]
                # The delimiter's own line: "--" closes, "\r\n" continues.
                nl = rest.find(b"\r\n")
                self._buffer = rest[nl + 2:] if nl >= 0 else b""
                return written
            # Flush all but a delimiter's length, so one that straddles the
            # next chunk is still seen whole.
            if len(self._buffer) > keep:
                cut = len(self._buffer) - keep
                if handle is not None:
                    handle.write(self._buffer[:cut])
                written += cut
                self._buffer = self._buffer[cut:]
            if not self._fill():
                return None

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


class _ServerV4(ThreadingHTTPServer):
    address_family = socket.AF_INET


class _ServerV6(ThreadingHTTPServer):
    #: The base class asks for IPv4, so ::1 -- which is what `localhost`
    #: resolves to on a machine with IPv6, and the address the one flag here
    #: exists to accept -- was approved by the check and then failed to bind.
    address_family = socket.AF_INET6


def build_server(host: str = "127.0.0.1", port: int = 0,
                 verbose: bool = False) -> ThreadingHTTPServer:
    """A server bound to loopback, or a refusal.

    The refusal is the point. Everything else here is a convenience; this is
    the line that keeps the promise on the front of the project.
    """
    address = loopback_address(host)
    if address is None:
        raise ValueError(
            "%r is not a loopback address: this page serves the machine it "
            "runs on and nothing else" % host)

    server = _ServerV6 if ipaddress.ip_address(address).version == 6 else _ServerV4
    httpd = server((address, port), _Handler)
    httpd.verbose = verbose                       # type: ignore[attr-defined]
    return httpd


def serve(host: str = "127.0.0.1", port: int = 0, open_browser: bool = True,
          verbose: bool = False, stream=None) -> int:
    import sys

    stream = sys.stdout if stream is None else stream
    httpd = build_server(host, port, verbose=verbose)
    url = origin_of(httpd.server_address[0], httpd.server_address[1]) + "/"
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
