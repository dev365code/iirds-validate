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
import os
import pathlib
import re
import socket
import threading
import urllib.error
import urllib.request
import uuid

import pytest

from conftest import build_package
from iirds_validate import report as report_module
from iirds_validate import runner, serve

ROOT = pathlib.Path(__file__).resolve().parents[1]


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
    caught.value.close()

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(server + "/tests/", timeout=30)
    assert caught.value.code in (400, 403, 404)
    caught.value.close()


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


def test_the_command_line_offers_it_and_refuses_a_public_address(capsys,
                                                                monkeypatch):
    """`iirdsv serve` is the way in. `--host` exists because somebody will
    want ::1, and it is the one flag that can undo the promise, so the refusal
    is part of the command and not only part of the library."""
    from iirds_validate import cli

    # The server constructor is replaced, not build_server: replacing
    # build_server would remove the refusal this is about. If the refusal
    # ever regresses, this must fail rather than bind every interface and
    # block in serve_forever() -- which is what it did before.
    def never(*a, **k):
        raise AssertionError("the command line reached a bind for a public address")

    monkeypatch.setattr(serve, "ThreadingHTTPServer", never)
    assert cli.main(["serve", "--host", "0.0.0.0", "--no-open"]) == 2
    assert "loopback" in capsys.readouterr().err.lower()


def test_serve_is_in_the_help(capsys):
    """The word alone appears in the subcommand list whatever the help text
    says, so this asks for the sentence that tells somebody what it is."""
    from iirds_validate import cli

    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "serve" in out
    assert "drop page" in out, out


def _cli(directory, name):
    """The real command line, run where the package is.

    stdout is piped, so no terminal colour is involved -- the page renders
    into a string and can never colour, and a run at a prompt can, which is
    the one difference the documents promise and this deliberately excludes.

    The import path is made absolute before it is handed over: it is relative
    in a plain `pytest` invocation, and this runs with a different working
    directory, which produced an empty stdout and a failure that said nothing
    about why.
    """
    import subprocess
    import sys as _sys

    # UTF-8 on both sides. The page always renders into UTF-8; a console
    # stdout on Windows defaults to a legacy code page, where the report now
    # writes "->" for the arrow it cannot encode -- a correct rendering that
    # is not the page's. The comparison is about the report, not the console.
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = os.pathsep.join(
        os.path.abspath(entry) for entry in _sys.path
        if entry and os.path.isdir(entry))
    done = subprocess.run(
        [_sys.executable, "-m", "iirds_validate", "all", name],
        cwd=str(directory), capture_output=True, env=env)
    assert done.stdout or done.returncode == 0, done.stderr.decode("utf-8")[-800:]
    # Line endings are the platform's, not the report's: text-mode stdout on
    # Windows writes \r\n where the page, rendering into a string for a
    # browser, writes \n. Normalised here and named in the documents, because
    # it is a third thing that differs by construction and the first two were
    # found by reading rather than by running -- this one was found by
    # running, on a machine none of the reading happened on.
    return done.stdout.decode("utf-8").replace("\r\n", "\n"), done.returncode


@pytest.mark.parametrize("broken", [None, "mimetype", "missing-content"])
def test_the_page_prints_what_the_real_command_line_prints(tmp_path, server, broken):
    """Against `python -m iirds_validate`, not against the library function the
    page itself calls.

    The first version of this compared the page with `render_text` on a
    package that had no findings at all -- a header and a footer, of a
    function, against itself. Rendering every finding differently (the
    renderer takes `verbose`) changed nothing anywhere in the suite. These
    have findings, and they come from the command line as a user would run it.
    """
    kwargs = {}
    if broken == "mimetype":
        kwargs["mimetype"] = b"application/zip"
    elif broken == "missing-content":
        kwargs["content"] = ()
    name = "cli-%s.iirds" % (broken or "clean")
    package = build_package(tmp_path, name, **kwargs)

    expected, expected_code = _cli(tmp_path, name)
    _, body = _post(server + "/check", name, package.read_bytes())
    payload = json.loads(body)

    assert payload["text"] == expected
    assert payload["exit"] == expected_code


def test_a_name_the_handler_would_have_tidied_gets_the_command_lines_answer(tmp_path,
                                                                            server):
    """`handover.iirds ` -- trailing space, which a content system produces.
    The extension rule reads the file name, so stripping it in the handler
    gave the page a PASS where the command line gives a FAIL: opposite
    verdicts and opposite exit codes, from the handler's own tidying."""
    package = build_package(tmp_path, "space.iirds")
    odd = tmp_path / "handover.iirds "
    odd.write_bytes(package.read_bytes())

    expected, expected_code = _cli(tmp_path, "handover.iirds ")
    _, body = _post(server + "/check", "handover.iirds ", package.read_bytes())
    payload = json.loads(body)

    assert expected_code == 1, "the command line should be failing this one"
    assert "C3" in expected
    assert payload["exit"] == expected_code
    assert payload["text"] == expected


def test_a_name_that_would_escape_the_directory_is_replaced(tmp_path, server):
    """Whatever the sender put in the header, nothing is written outside the
    directory made for it."""
    for sent in ("../../etc/passwd", "..", ".", "", "dir/sub/real.iirds",
                 "windows\\dir\\real.iirds"):
        assert "/" not in serve.dropped_name(sent), sent
        assert serve.dropped_name(sent) not in ("", ".", ".."), sent
    assert serve.dropped_name("handover.iirds ") == "handover.iirds "
    assert serve.dropped_name("../../etc/passwd") == "passwd"


def test_the_machine_readable_half_names_the_file_that_was_dropped(tmp_path, server):
    """Not the temporary copy's path. The JSON is what a writer attaches to a
    ticket, and a path under /var/folders says nothing about their document."""
    package = build_package(tmp_path, "ticket.iirds")
    _, body = _post(server + "/check", "ticket.iirds", package.read_bytes())
    assert json.loads(body)["report"]["package"] == "ticket.iirds"


def test_a_container_that_cannot_be_opened_names_the_copy_and_says_so(tmp_path,
                                                                      server):
    """The one divergence the docs promise. C1 puts the container's own path
    into the finding, and the page's path is the copy it made -- so this is
    pinned rather than claimed, and the rest of the text still matches."""
    _, body = _post(server + "/check", "torn.iirds", b"not a zip at all")
    payload = json.loads(body)
    assert "C1" in payload["text"]
    assert "torn.iirds" in payload["text"], payload["text"]
    assert payload["report"]["package"] == "torn.iirds"


def test_the_page_carries_the_version_it_was_served_by():
    from iirds_validate import __version__

    page = serve.page_html()
    assert "__VERSION__" not in page
    assert __version__ in page


def test_the_answer_carries_the_headers_that_keep_it_local(server):
    with urllib.request.urlopen(server + "/", timeout=30) as response:
        headers = {k.lower(): v for k, v in response.getheaders()}
    assert "no-store" in headers.get("cache-control", "")
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    policy = headers.get("content-security-policy", "")
    for directive in ("default-src 'none'", "connect-src 'self'",
                      "form-action 'none'", "base-uri 'none'"):
        assert directive in policy, directive
    assert "access-control-allow-origin" not in headers, headers


def test_a_body_larger_than_the_page_will_hold_is_refused_before_it_is_read(server):
    """Refused on the declared length, so the bytes are never read. The
    message says the command line has no such limit, because it does not."""
    boundary = "----%s" % uuid.uuid4().hex
    request = urllib.request.Request(
        server + "/check", data=b"x" * 16,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                 "Content-Length": str(serve.MAX_UPLOAD_BYTES + 1)})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)
    assert caught.value.code == 400
    assert b"command line" in caught.value.read()
    caught.value.close()


def test_a_post_with_no_file_and_a_post_with_no_body_are_both_refused(server):
    boundary = "----%s" % uuid.uuid4().hex
    empty = ('--%s\r\nContent-Disposition: form-data; name="not-a-file"\r\n\r\nx'
             '\r\n--%s--\r\n' % (boundary, boundary)).encode("utf-8")
    request = urllib.request.Request(
        server + "/check", data=empty,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)
    assert caught.value.code == 400
    caught.value.close()

    plain = urllib.request.Request(server + "/check", data=b"hello",
                                   headers={"Content-Type": "text/plain"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(plain, timeout=30)
    assert caught.value.code == 400
    caught.value.close()


def test_requests_are_not_logged_unless_asked_for(tmp_path, capfd):
    """A request line carries the name of the file that was dropped, and the
    stdlib handler writes one to stderr for every request."""
    httpd = serve.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:%d" % httpd.server_address[1]
        package = build_package(tmp_path, "private-name.iirds")
        _post(base + "/check", "private-name.iirds", package.read_bytes())
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert "private-name.iirds" not in capfd.readouterr().err


def test_a_body_with_no_boundary_is_refused_and_does_not_crash_the_thread(server,
                                                                          capfd):
    """`iter_parts()` keys on the declared content type, not on whether a
    boundary was found, so a body without one left the payload a string and
    the loop walked it a character at a time: an AttributeError in a request
    thread, no response at all, and a traceback on the operator's terminal.
    Reachable from any page the user has open, because this content type
    needs no preflight."""
    for content_type in ("multipart/form-data",
                         "multipart/form-data; boundary=nowhere-in-the-body"):
        request = urllib.request.Request(
            server + "/check", data=b"this body has no boundary in it",
            headers={"Content-Type": content_type})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=30)
        assert caught.value.code == 400, content_type
        caught.value.close()
    assert "Traceback" not in capfd.readouterr().err


def test_a_post_from_another_page_is_refused(tmp_path, server):
    """A browser sends Origin on a cross-site POST, and multipart needs no
    preflight, so any page the user has open can reach this port. It can
    never read the answer -- nothing here allows an origin -- but it can
    spend this process's memory and time."""
    package = build_package(tmp_path, "drive-by.iirds")
    boundary = "----%s" % uuid.uuid4().hex
    body = (('--%s\r\nContent-Disposition: form-data; name="package"; '
             'filename="x.iirds"\r\n\r\n' % boundary).encode()
            + package.read_bytes() + ("\r\n--%s--\r\n" % boundary).encode())
    request = urllib.request.Request(
        server + "/check", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                 "Origin": "https://example.com"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)
    assert caught.value.code == 403
    caught.value.close()


def test_its_own_page_is_not_refused(tmp_path, server):
    """The check above must not fire on the page this server serves."""
    package = build_package(tmp_path, "mine.iirds")
    boundary = "----%s" % uuid.uuid4().hex
    body = (('--%s\r\nContent-Disposition: form-data; name="package"; '
             'filename="mine.iirds"\r\n\r\n' % boundary).encode()
            + package.read_bytes() + ("\r\n--%s--\r\n" % boundary).encode())
    request = urllib.request.Request(
        server + "/check", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                 "Origin": server})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200


def test_the_policy_names_this_page_rather_than_permitting_inline_code(server):
    """A nonce, not 'unsafe-inline'. There is one author for the bytes served
    -- the page is assembled per response -- so naming them costs a
    substitution and nothing has to be kept in step."""
    with urllib.request.urlopen(server + "/", timeout=30) as response:
        policy = response.getheader("Content-Security-Policy")
        page = response.read().decode("utf-8")
    assert "unsafe-inline" not in policy, policy
    nonce = re.search(r"script-src 'nonce-([^']+)'", policy)
    assert nonce, policy
    assert 'nonce="%s"' % nonce.group(1) in page
    assert "frame-ancestors 'none'" in policy


def test_a_method_nobody_implemented_answers_like_everything_else(server):
    """The base class writes an HTML error page with no policy headers and a
    doctype pointing at a URL on the web, which is a strange thing to serve
    from a tool whose subject is not loading pages."""
    request = urllib.request.Request(server + "/", method="TRACE")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)
    assert caught.value.code in (400, 501)
    headers = {k.lower(): v for k, v in caught.value.headers.items()}
    caught.value.close()
    assert headers.get("content-type", "").startswith("text/plain")
    assert "content-security-policy" in headers
    assert b"w3.org" not in caught.value.read()


def test_the_banner_does_not_volunteer_the_version(server):
    with urllib.request.urlopen(server + "/", timeout=30) as response:
        assert "0." not in (response.getheader("Server") or "")


# ---------------------------------------------------------------------------
# The page itself: assembled from data/web/, translated, and switchable.
# ---------------------------------------------------------------------------

def _strings():
    from iirds_validate import resources

    return json.loads(resources.read_text(serve.WEB, serve.STRINGS))


def test_the_page_is_assembled_with_nothing_left_to_substitute():
    page = serve.page_html("test-nonce")
    for token in ("__STYLE__", "__SCRIPT__", "__VERSION__", "__NONCE__", "__I18N__"):
        assert token not in page, token
    assert "#drop" in page, "the stylesheet did not make it in"
    assert "addEventListener" in page, "the script did not make it in"
    assert '"iiRDS package check"' in page, "the translations did not make it in"


def test_every_language_says_everything_english_says():
    """A missing key is a page that shows `undefined` to the reader who
    chose that language, and nobody who ships in English would see it."""
    data = _strings()
    expected = set(data["strings"]["en"])
    assert len(expected) > 8, sorted(expected)
    for code in data["order"]:
        assert code in data["strings"], code
        assert code in data["names"], code
        assert set(data["strings"][code]) == expected, (
            code, sorted(expected ^ set(data["strings"][code])))
        assert all(str(v).strip() for v in data["strings"][code].values()), code


def test_every_language_says_the_report_itself_is_not_translated():
    """The chrome is translated and the verdict is not -- it is the command
    line's own output, word for word, which is the whole point of it. A
    reader who picked their own language has to be told that in it."""
    data = _strings()
    # Counted low on purpose: a character of Chinese carries what several of
    # English do, and the Chinese line is exactly twenty. This catches an
    # empty or stub value; the named words below are what check the meaning.
    for code in data["order"]:
        note = data["strings"][code]["reportNote"]
        assert len(note) >= 10, (code, note)
    for code, word in (("en", "English"), ("ko", "영어"), ("de", "Englisch"),
                       ("ja", "英語"), ("zh", "英文")):
        assert word in data["strings"][code]["reportNote"], (code, word)


def test_the_page_offers_the_languages_the_strings_file_has():
    page = serve.page_html("n")
    data = _strings()
    for code in data["order"]:
        assert data["names"][code] in page, code


def test_the_page_offers_a_theme_that_is_not_only_the_systems():
    """`color-scheme: light dark` alone follows the operating system and
    gives a reader no way to disagree with it."""
    page = serve.page_html("n")
    for value in ('value="system"', 'value="light"', 'value="dark"'):
        assert value in page, value
    assert 'data-theme="dark"' in page, "the dark tokens are not defined"
    assert ':root:not([data-theme="light"])' in page, (
        "the system default must not override an explicit choice of light")


def test_the_page_survives_the_single_file_distribution(tmp_path):
    """The delivery this project says matters for a closed network.

    Every part of the page is data, and data is exactly what a packaging
    change drops: the wheel's package-data line and the archive's own copy
    are two places that have to agree, and neither is read by any other test.
    The archive is built and opened rather than trusted.
    """
    import subprocess
    import sys as _sys
    import zipfile

    pyz = tmp_path / "iirds.pyz"
    built = subprocess.run(
        [_sys.executable, str(ROOT / "tools" / "build_zipapp.py"), "-o", str(pyz)],
        capture_output=True, text=True, cwd=str(ROOT))
    assert pyz.exists(), built.stderr[-800:]

    inside = set(zipfile.ZipFile(pyz).namelist())
    for part in (serve.PAGE, serve.STYLE, serve.SCRIPT, serve.STRINGS):
        assert "iirds_validate/data/%s/%s" % (serve.WEB, part) in inside, part
    # The library travels the same way: from the tree, not from an index.
    assert "iirds/__init__.py" in inside
    assert not [name for name in inside if name.startswith("iirds-") and ".dist-info/" in name]


def test_the_address_it_prints_is_one_a_browser_can_open():
    """`localhost` resolves to ::1 on a machine with IPv6, and an unbracketed
    v6 literal is not a URL. The flag exists so somebody can ask for ::1, so
    this is the ordinary case rather than the exotic one."""
    assert serve.origin_of("127.0.0.1", 8080) == "http://127.0.0.1:8080"
    assert serve.origin_of("::1", 8080) == "http://[::1]:8080"


def test_the_ipv6_loopback_is_served_not_refused():
    """It was accepted by the check and then failed to bind, because the
    server class asks for IPv4 unless told otherwise -- so the one flag that
    exists for this could not be used for it."""
    httpd = serve.build_server("::1", 0)
    try:
        assert httpd.server_address[0] == "::1"
        assert httpd.address_family == socket.AF_INET6
    finally:
        httpd.server_close()


def test_what_is_bound_is_what_was_checked(monkeypatch):
    """The check resolved the name and the constructor resolved it again, so
    a record with no time to live could answer differently the second time.
    The address is carried from one to the other now."""
    seen = {}

    for name in ("_ServerV4", "_ServerV6"):
        base = getattr(serve, name)

        class Watching(base):                     # noqa: B903 - a test double
            def __init__(self, address, handler):
                seen["address"] = address[0]
                super().__init__(address, handler)

        monkeypatch.setattr(serve, name, Watching)

    serve.build_server("localhost", 0).server_close()
    assert seen["address"] != "localhost", "the name reached the constructor"
    assert serve.loopback_address(seen["address"]) == seen["address"]


# ---------------------------------------------------------------------------
# What a dropped file costs the process. Measured in a fresh subprocess,
# because ru_maxrss is a high-water mark: inside one process only the first
# request's delta means anything, and the suite has already made requests.
# ---------------------------------------------------------------------------

_MEASURE = r'''
import sys, threading, tracemalloc, urllib.request, uuid
from iirds_validate import serve
size = int(sys.argv[1])
httpd = serve.build_server("127.0.0.1", 0)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/check" % httpd.server_address[1]
b = "----%s" % uuid.uuid4().hex
head = ('--%s\r\nContent-Disposition: form-data; name="package"; '
        'filename="big.iirds"\r\nContent-Type: application/octet-stream\r\n\r\n'
        % b).encode()
body = head + b"\x00" * size + ("\r\n--%s--\r\n" % b).encode()
req = urllib.request.Request(url, data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + b})
tracemalloc.start()
urllib.request.urlopen(req, timeout=120).read()
peak = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
print(peak)
'''


def _peak_delta_for(size):
    import subprocess
    import sys as _sys

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        os.path.abspath(entry) for entry in _sys.path
        if entry and os.path.isdir(entry))
    done = subprocess.run([_sys.executable, "-c", _MEASURE, str(size)],
                          capture_output=True, text=True, env=env, timeout=300)
    assert done.returncode == 0, done.stderr[-800:]
    return int(done.stdout.strip())


def test_a_dropped_file_does_not_cost_the_process_many_times_its_size():
    """The upload was read whole and handed to a MIME parser that copies it
    several times over: measured, a body cost the process eleven to twelve
    times its own size, so a quarter-gigabyte drop asked for nearly three.
    Capping the size made that survivable and did not make it go away.

    Streaming the payload to the temporary file as it arrives costs the body
    once on disk and a chunk in memory. Three times the body is the line here
    -- enough headroom for the client's own copy in this same process and the
    interpreter's slack, and a third of what the whole-body parse cost.

    Measured with tracemalloc, the Python heap's own high-water mark. A first
    version used the resource module's resident-set figure, which Windows does
    not have, and the row that lacks it failed before measuring anything.
    The heap is the right instrument regardless: the copies the old parser
    made were Python bytes, and against that parser this measurement reads
    eleven times the body -- the same figure -- while against the streaming
    handler it reads none of it.
    """
    size = 16 * 1024 * 1024
    delta = _peak_delta_for(size)
    assert delta < 3 * size, "peak RSS grew by %.1fx the body" % (delta / size)


@pytest.mark.parametrize("straddle", [-3, -1, 0, 1, 7])
def test_a_boundary_split_across_two_chunks_is_still_seen_whole(tmp_path, server,
                                                                straddle):
    """The one hard case in a streaming scanner, and the one the ordinary
    tests never reach: every other body here is smaller than a single chunk,
    so the closing boundary has only ever arrived in the same read as the
    payload. This sizes the payload so the delimiter begins `straddle` bytes
    before or after the 64 KiB chunk edge, and compares the spooled bytes
    with the sent bytes exactly -- a scanner that flushed too eagerly would
    keep a fragment of the delimiter as payload, and one that flushed too
    late would drop a fragment of the payload.
    """
    chunk = serve._Counted.CHUNK
    boundary = "----%s" % uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="package"; '
            'filename="edge.iirds"\r\nContent-Type: application/octet-stream\r\n\r\n'
            % boundary).encode("utf-8")
    # The delimiter is "\r\n--<boundary>"; place its first byte at
    # chunk + straddle, counted from the start of the body.
    payload_len = chunk + straddle - len(head)
    payload = bytes(i % 251 for i in range(payload_len))
    body = head + payload + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    assert body.find(("\r\n--%s" % boundary).encode()) == chunk + straddle

    seen = {}

    def keep(name, spool):
        seen["bytes"] = pathlib.Path(spool).read_bytes()
        return "kept\n", 0, {"package": name}

    original = serve.verdict
    serve.verdict = keep
    try:
        request = urllib.request.Request(
            server + "/check", data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
    finally:
        serve.verdict = original

    assert seen["bytes"] == payload, (
        "spooled %d bytes, sent %d; first difference at %d" % (
            len(seen["bytes"]), len(payload),
            next((i for i, (a, b) in enumerate(zip(seen["bytes"], payload)) if a != b),
                 min(len(seen["bytes"]), len(payload)))))


# ---------------------------------------------------------------------------
# How many drops the process will check at once.
# ---------------------------------------------------------------------------

def test_the_process_checks_a_bounded_number_of_drops_at_once(tmp_path, monkeypatch):
    """A thread per request with nothing above it: measured, thirty-two posts
    left forty-six threads standing, each one a whole validation run. The
    same-origin check keeps other pages out, but the page's own reader can
    drop a folder of files at once, and a folder is not an attack.

    Counted from inside the handler rather than with `threading.active_count()`,
    which also counts this test's own client threads -- and with every
    request held open until all have arrived, because a peak polled from
    outside is only as real as the polling window: the first version of this
    measurement saw two threads for eight posts that had simply finished
    between two samples.
    """
    import threading as _threading

    gate = _threading.Event()
    inside = {"now": 0, "peak": 0}
    lock = _threading.Lock()

    def slow(name, payload):
        with lock:
            inside["now"] += 1
            inside["peak"] = max(inside["peak"], inside["now"])
        gate.wait(timeout=30)
        with lock:
            inside["now"] -= 1
        return "held\n", 0, {"package": name}

    monkeypatch.setattr(serve, "verdict", slow)
    httpd = serve.build_server("127.0.0.1", 0)
    _threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    package = build_package(tmp_path, "many.iirds").read_bytes()

    waves = serve.MAX_CONCURRENT_CHECKS + 8
    clients = [_threading.Thread(target=_post, args=(base + "/check", "many.iirds", package))
               for _ in range(waves)]
    try:
        for client in clients:
            client.start()
        deadline = _threading.Event()
        deadline.wait(timeout=2)          # let every request arrive and queue
        assert inside["peak"] <= serve.MAX_CONCURRENT_CHECKS, inside
        assert inside["peak"] >= 1, "nothing reached the checker at all"
    finally:
        gate.set()
        for client in clients:
            client.join(timeout=30)
        httpd.shutdown()
        httpd.server_close()


def test_a_drop_that_crashes_the_checker_gives_its_slot_back(tmp_path, monkeypatch):
    """The slot is held with `with`, so a checker that raises releases it.
    Stated as a test rather than trusted, because the alternative failure is
    quiet: one bad drop would eat a slot for the life of the process, and
    after as many bad drops as there are slots every good one would wait for
    ever with nothing in the log to say why."""
    import threading as _threading

    calls = {"n": 0}

    def crashing(name, payload):
        calls["n"] += 1
        raise RuntimeError("the checker fell over")

    monkeypatch.setattr(serve, "verdict", crashing)
    httpd = serve.build_server("127.0.0.1", 0)
    _threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    package = build_package(tmp_path, "crash.iirds").read_bytes()
    try:
        for _ in range(serve.MAX_CONCURRENT_CHECKS + 2):
            status, body = _post(base + "/check", "crash.iirds", package)
            assert status == 200 and json.loads(body)["exit"] == 2
        assert calls["n"] == serve.MAX_CONCURRENT_CHECKS + 2, calls

        # Every slot has been through a crash. A drop that works must still
        # get one, promptly -- a leaked slot shows up here as a timeout.
        monkeypatch.setattr(serve, "verdict", lambda n, p: ("fine\n", 0, {"package": n}))
        finished = _threading.Event()

        def good():
            _post(base + "/check", "good.iirds", package)
            finished.set()

        _threading.Thread(target=good, daemon=True).start()
        assert finished.wait(timeout=10), "a slot was never given back"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_server_names_the_command_and_nothing_more(server):
    """The name, and no version behind it (the test above says why)."""
    response = urllib.request.urlopen(server + "/", timeout=30)
    try:
        assert response.getheader("Server") == "iirds"
    finally:
        response.close()


def test_the_console_line_names_the_command(monkeypatch):
    """The first thing `serve` prints is the name a person just typed."""
    import io

    from iirds_validate import __version__

    class Stub:
        server_address = ("127.0.0.1", 8791)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(serve, "build_server", lambda host, port, verbose=False: Stub())
    out = io.StringIO()
    assert serve.serve(open_browser=False, stream=out) == 0
    assert out.getvalue().splitlines()[0] == (
        "iirds %s — drop a package at http://127.0.0.1:8791/" % __version__)
