"""Is there a nested iiRDS container in this archive?

The question the metadata cannot answer. §5.3 says nested packages "are stored
as iiRDS ZIP archives", §5.1.2 counts them among the content files that live in
subdirectories, and §5.2 says what one looks like: the file name carries the
extension `.iirds`, and the root of the ZIP holds a file named `mimetype`,
first, stored uncompressed, containing `application/iirds+zip` and nothing
else.

The name alone is not the test, and that is the whole point of the file. A
container that declares a nested package and carries an empty `nested.iirds`
would otherwise buy the same silence as one that carries the real thing.
"""
from __future__ import annotations

import zipfile

from conftest import MIMETYPE
from iirds_validate.package import nested_containers, open_package
from make_fixture_package import build_package


def built(tmp_path, where, name, **kw):
    """A package built the ordinary way in its own directory, as bytes."""
    directory = tmp_path / where
    directory.mkdir(parents=True, exist_ok=True)
    return build_package(directory, name, **kw).read_bytes()


def a_real_one(tmp_path, name="inner.iirds"):
    return built(tmp_path, "src", name)


def wrapping(tmp_path, *entries):
    outer = build_package(tmp_path, "outer.iirds", extra=entries)
    return sorted(nested_containers(open_package(outer)))


def test_a_container_with_nothing_nested_reports_nothing(tmp_path):
    assert wrapping(tmp_path) == []


def test_a_real_nested_container_is_found(tmp_path):
    assert wrapping(tmp_path, ("content/inner.iirds", a_real_one(tmp_path))) == \
        ["content/inner.iirds"]


def test_a_file_that_only_ends_in_iirds_is_not_one(tmp_path):
    """The decoy. Without the header test a rule that asks this question is
    satisfied by twenty-eight bytes of anything."""
    assert wrapping(tmp_path, ("content/inner.iirds", b"not a zip at all")) == []


def test_a_zip_without_the_mimetype_entry_is_not_one(tmp_path):
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("content/topic.xhtml", "<html/>")
    assert wrapping(tmp_path, ("content/inner.iirds", other.read_bytes())) == []


def test_a_zip_whose_mimetype_is_not_first_is_not_one(tmp_path):
    """§5.2: "The file MUST be the first entry in the ZIP file". A ZIP whose
    mimetype is somewhere in the middle is not an iiRDS ZIP archive, and this
    reads the first local header rather than the central directory, so a
    directory that says otherwise does not change the answer."""
    inner = built(tmp_path, "late", "late.iirds", mimetype_first=False)
    assert wrapping(tmp_path, ("content/inner.iirds", inner)) == []


def bend(raw, at, replacement):
    """One field of a real archive changed and nothing else.

    Built this way on purpose. A fixture that breaks the thing under test *and*
    something else is answered by whichever check runs first, and the check it
    was written for can then be deleted with the test still green -- which is
    what happened to the three below: a deflated mimetype also has the wrong
    compressed size, a mimetype with a newline is also 22 bytes long, and
    sixteen bytes of prose is also too short to be a header at all.
    """
    return raw[:at] + replacement + raw[at + len(replacement):]


def test_a_zip_whose_mimetype_is_compressed_is_not_one(tmp_path):
    """§5.2: "it MUST be stored uncompressed ("Stored" mode)". The method
    field alone, with the sizes left saying twenty-one bytes."""
    bent = bend(a_real_one(tmp_path), 8, b"\x08\x00")
    assert wrapping(tmp_path, ("content/inner.iirds", bent)) == []


def test_a_zip_that_does_not_begin_like_a_zip_is_not_one(tmp_path):
    """The signature alone, with every other field still well formed."""
    bent = bend(a_real_one(tmp_path), 0, b"PK\x05\x06")
    assert wrapping(tmp_path, ("content/inner.iirds", bent)) == []


def test_a_mimetype_of_the_right_length_that_says_something_else_is_not_one(tmp_path):
    """Twenty-one bytes sharing a prefix with the real value, so neither the
    length test nor a prefix comparison separates them."""
    inner = built(tmp_path, "cased", "cased.iirds", mimetype=b"application/iirds+ZIP")
    assert wrapping(tmp_path, ("content/inner.iirds", inner)) == []


def test_a_zip_whose_mimetype_says_something_else_is_not_one(tmp_path):
    inner = built(tmp_path, "wrong", "wrong.iirds", mimetype=b"application/zip")
    assert wrapping(tmp_path, ("content/inner.iirds", inner)) == []


def test_the_mimetype_must_be_the_whole_content(tmp_path):
    """§5.2: "in a single line, without any line delimiters such as CR or LF".
    A trailing newline is the commonest way to get this wrong, and a prefix
    test would accept it."""
    inner = built(tmp_path, "nl", "nl.iirds", mimetype=MIMETYPE + b"\n")
    assert wrapping(tmp_path, ("content/inner.iirds", inner)) == []


def test_several_nested_containers_come_back_in_a_fixed_order(tmp_path):
    real = a_real_one(tmp_path)
    got = wrapping(tmp_path,
                   ("content/b.iirds", real),
                   ("content/a.iirds", real),
                   ("content/c.iirds", b"decoy"))
    assert got == ["content/a.iirds", "content/b.iirds"]


def test_a_real_container_under_another_name_is_not_one(tmp_path):
    """§5.2: "The file name of the iiRDS ZIP archive MUST feature the file name
    extension .iirds". A well-formed archive filed as content/inner.zip is not
    an iiRDS ZIP archive, so a container declaring a nested package and
    carrying only this has not carried it -- which is the answer a nesting rule
    needs, and the opposite of the one a bytes-only test would give."""
    assert wrapping(tmp_path, ("content/inner.zip", a_real_one(tmp_path))) == []
