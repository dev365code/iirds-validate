"""What the drop page leaves behind when it fails.

The page spools a dropped package to a file, because the alternative is
holding a quarter of a gigabyte in memory for each of four concurrent checks.
The file is a copy of somebody's documentation, and the promise the whole
surface rests on is about where documents go.

The happy path moves that copy into a directory it then removes. Every other
path is what this file is about: the promise has to hold when the run fails,
because a failure is exactly when nobody is watching.

Measured before it was written: 1008 spool files, 16 MB, every one of them a
complete iiRDS archive, sitting in this machine's temporary directory.
"""
from __future__ import annotations

import tempfile
import threading
import urllib.request
import uuid

import pytest

from conftest import build_package
from iirds_validate import serve


@pytest.fixture
def temp_dir_of_its_own(tmp_path, monkeypatch):
    """Point every `tempfile` call at a directory this test can count."""
    scratch = tmp_path / "temp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


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


def post(url, payload, *, filename="dropped.iirds", close=True, field="package"):
    boundary = "----%s" % uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="%s"; '
            'filename="%s"\r\n\r\n' % (boundary, field, filename)).encode("utf-8")
    tail = ("\r\n--%s--\r\n" % boundary).encode("utf-8") if close else b""
    body = head + payload + tail
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read()


def left_behind(scratch):
    """What is under the directory once an answer has been given.

    Read without waiting: the handler composes its response inside the
    request's own directory and sends it after that directory is gone, so
    holding an answer means the copy is already removed. A test that had to
    sleep here would be measuring a thread rather than the promise.
    """
    return sorted(p.name for p in scratch.rglob("*"))


def test_a_run_that_crashes_leaves_nothing_behind(
        tmp_path, temp_dir_of_its_own, server, monkeypatch):
    """The path that was leaking. `verdict` is what moves the spool into a
    directory that cleans itself, so anything raised before that move used to
    strand the copy -- and the handler catches the crash and answers, so
    nothing downstream ever noticed."""
    def raises(name, payload):
        raise RuntimeError("mutation")

    monkeypatch.setattr(serve, "verdict", raises)
    package = build_package(tmp_path, "plain.iirds")
    status, _ = post(server + "/check", package.read_bytes())
    assert status == 200
    assert left_behind(temp_dir_of_its_own) == []


def test_a_body_that_stops_early_leaves_nothing_behind(
        tmp_path, temp_dir_of_its_own, server):
    """The other half, and the discriminating one: a test that only checked
    the crash would pass against a handler that had stopped spooling at all."""
    package = build_package(tmp_path, "plain.iirds")
    status, _ = post(server + "/check", package.read_bytes(), close=False)
    assert status == 400
    assert left_behind(temp_dir_of_its_own) == []


def test_a_run_that_answers_leaves_nothing_behind(
        tmp_path, temp_dir_of_its_own, server):
    """And the ordinary path, so the two above cannot pass because the page
    stopped working."""
    package = build_package(tmp_path, "plain.iirds")
    status, body = post(server + "/check", package.read_bytes())
    assert status == 200
    assert b"iiRDS" in body or b"exit" in body
    assert left_behind(temp_dir_of_its_own) == []


def test_the_part_that_is_read_is_the_one_named_package(tmp_path, server):
    """The upload is taken from the first part carrying a filename, whatever
    the form called it. A form that sends anything else first has that read
    as the package instead -- and a second part is on the way."""
    boundary = "----%s" % uuid.uuid4().hex
    package = build_package(tmp_path, "plain.iirds").read_bytes()
    body = (('--%s\r\nContent-Disposition: form-data; name="previous"; '
             'filename="old-report.json"\r\n\r\n' % boundary).encode("utf-8")
            + b'{"schemaVersion": 1}'
            + ('\r\n--%s\r\nContent-Disposition: form-data; name="package"; '
               'filename="plain.iirds"\r\n\r\n' % boundary).encode("utf-8")
            + package
            + ("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    request = urllib.request.Request(
        url=server + "/check", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(request, timeout=30) as response:
        answer = response.read().decode("utf-8")
    assert "old-report.json" not in answer, answer[:400]
    assert "plain.iirds" in answer, answer[:400]


def test_the_field_is_read_even_when_the_file_name_comes_first(tmp_path, server):
    """`filename` ends in `name`, so a search for `name=` finds the file name
    when the parameters arrive in the other order. Nothing requires a client
    to write them the way a browser does, and reading the file name as the
    field refuses the one part the form actually sent."""
    boundary = "----%s" % uuid.uuid4().hex
    package = build_package(tmp_path, "plain.iirds").read_bytes()
    body = (('--%s\r\nContent-Disposition: form-data; filename="plain.iirds"; '
             'name="package"\r\n\r\n' % boundary).encode("utf-8")
            + package
            + ("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    request = urllib.request.Request(
        url=server + "/check", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
        assert "plain.iirds" in response.read().decode("utf-8")
