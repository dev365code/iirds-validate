"""The local drop page.

A technical writer is not a person who reads a terminal, and this project's
report has only ever existed as text on one. `iirdsv serve` puts a drop zone
in front of the same run: a page served from the loopback interface, a file
posted to a handler in the same process, and the verdict rendered by the
function the command line already calls.

That last part is the whole design. A second renderer would be a second
encoding of the report, and this project's rule is that two encodings of the
same thing must be proven to agree -- which costs a parity harness. Calling
`report.render_text` on the same `Report` object costs nothing and cannot
disagree, so the tests below assert byte-identity rather than similarity.
"""
from __future__ import annotations

import io
import json
import socket
import threading
import urllib.error
import urllib.request
import uuid

import pytest

from conftest import build_package
from iirds_validate import report as report_module
from iirds_validate import runner, serve


def _post(url, filename, payload):
    """A multipart body, hand-built so the test does not share a helper with
    the thing it is testing."""
    boundary = "----%s" % uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="package"; '
            'filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n'
            % (boundary, filename)).encode("utf-8")
    body = head + payload + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read().decode("utf-8")


@pytest.fixture
def server():
    httpd = serve.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_the_page_is_served_and_names_the_tool(server):
    with urllib.request.urlopen(server + "/", timeout=30) as response:
        page = response.read().decode("utf-8")
    assert "<!doctype html>" in page.lower()
    assert "iiRDS" in page


def test_the_verdict_is_the_one_the_command_line_prints(tmp_path, server):
    """Byte-identical, not similar. The page runs the same renderer on the
    same report, so anything less than equality means a second encoding got
    in, which is the thing this design exists to avoid."""
    package = build_package(tmp_path, "plain.iirds")
    status, body = _post(server + "/check", "plain.iirds", package.read_bytes())
    assert status == 200

    expected = io.StringIO()
    report_module.render_text(runner.run(package, runner.ALL_KINDS), stream=expected)

    payload = json.loads(body)
    assert payload["text"] == expected.getvalue()


def test_a_broken_package_says_so_and_reports_the_exit_code(tmp_path, server):
    """A page that renders a green verdict while the command line exits 1 is
    the failure this is for, so the exit code travels with the text."""
    broken = build_package(tmp_path, "broken.iirds", mimetype=b"application/zip")
    status, body = _post(server + "/check", "broken.iirds", broken.read_bytes())
    assert status == 200
    payload = json.loads(body)
    assert payload["exit"] == 1, payload["text"]
    assert "ERROR" in payload["text"]
    assert payload["report"]["findings"], "the machine-readable half is empty"


def test_the_name_the_browser_sent_decides_the_extension_rule(tmp_path, server):
    """C3 reads the container's file name, so whatever the handler calls the
    temporary copy decides a catalogued MUST. A package posted as .zip must
    fail the way it fails on the command line, and one posted as .iirds must
    not -- which is only true if the browser's name is carried through
    verbatim rather than replaced with a name of the handler's choosing."""
    package = build_package(tmp_path, "named.iirds")
    _, as_iirds = _post(server + "/check", "handover.iirds", package.read_bytes())
    _, as_zip = _post(server + "/check", "handover.zip", package.read_bytes())
    assert "C3" not in json.loads(as_iirds)["text"]
    assert "C3" in json.loads(as_zip)["text"]


def test_it_refuses_to_listen_anywhere_but_loopback():
    """The one thing this must never become is a service on a network. The
    product is that the document does not leave the machine, and a bind
    address is the only line between those two."""
    for address in ("0.0.0.0", "::", "192.168.1.10", ""):
        with pytest.raises(ValueError) as caught:
            serve.build_server(address, 0)
        assert "loopback" in str(caught.value).lower(), address


def test_the_refusal_happens_before_anything_is_bound(monkeypatch):
    """The refusal must come first, and this is the only way to say so without
    binding.

    Removing the check and re-running the test above does not turn it red on
    every machine: a bind to 0.0.0.0 can raise a firewall prompt and the run
    stops instead of failing, which is worse than either outcome. So the
    server constructor is replaced with something that refuses to be called,
    and the assertion is that the address was rejected before it was reached.
    """
    def never(*a, **k):
        raise AssertionError("a socket was opened for an address that is not "
                             "loopback; the refusal is no longer first")

    monkeypatch.setattr(serve, "ThreadingHTTPServer", never)
    for address in ("0.0.0.0", "::", "10.0.0.1", ""):
        with pytest.raises(ValueError):
            serve.build_server(address, 0)


def test_loopback_by_name_is_still_loopback():
    httpd = serve.build_server("localhost", 0)
    try:
        assert httpd.server_address[0] in ("127.0.0.1", "::1")
    finally:
        httpd.server_close()


def test_a_post_that_is_not_a_package_is_answered_not_crashed(server):
    """Whatever a browser sends, the answer is a verdict or a sentence -- an
    unhandled traceback in a request thread would leave the page waiting for
    ever with no way to tell why.

    Sixteen bytes of prose is a finding about the package and not an operator
    error, which is the command line's own reading: it opens, C1 says it is
    not a ZIP, and the run exits 1. Measured before this was written, because
    the first draft asserted 2."""
    status, body = _post(server + "/check", "junk.iirds", b"not a zip at all")
    assert status == 200
    payload = json.loads(body)
    assert payload["exit"] == 1, payload
    assert "C1" in payload["text"], payload["text"]


def test_an_unknown_path_is_a_404_and_not_a_directory_listing(server):
    """http.server's default handler serves the working directory. This one
    must not: the process is holding somebody's documentation."""
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(server + "/../setup.py", timeout=30)
    assert caught.value.code in (400, 403, 404)

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(server + "/tests/", timeout=30)
    assert caught.value.code in (400, 403, 404)


def test_the_handler_opens_no_outbound_connection(tmp_path, monkeypatch):
    """It is a server, not a client. Nothing a drop sets off may reach out.

    Called directly rather than over HTTP, because sealing the socket module
    seals this test's own client first -- which is how the first version of
    this passed for the wrong reason and then failed for the wrong reason.
    `verdict` is the whole of what a request does once the body is parsed."""
    def die(*a, **k):
        raise AssertionError("the drop page tried to open a connection")

    monkeypatch.setattr(socket, "create_connection", die)
    monkeypatch.setattr(socket, "getaddrinfo", die)
    monkeypatch.setattr(socket.socket, "connect", die, raising=True)

    package = build_package(tmp_path, "quiet.iirds")
    text, code, machine = serve.verdict("quiet.iirds", package.read_bytes())
    assert code == 0, text
    assert machine["findings"] == []


def test_the_command_line_offers_it_and_refuses_a_public_address(capsys):
    """`iirdsv serve` is the way in. `--host` exists because somebody will
    want ::1, and it is the one flag that can undo the promise, so the refusal
    is part of the command and not only part of the library."""
    from iirds_validate import cli

    assert cli.main(["serve", "--host", "0.0.0.0", "--no-open"]) == 2
    assert "loopback" in capsys.readouterr().err.lower()


def test_serve_is_in_the_help(capsys):
    from iirds_validate import cli

    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "serve" in capsys.readouterr().out
