"""The SDK's one promise: what pack() writes, open() reads, faithfully."""
import pathlib
import unicodedata
import zipfile

import pytest

import iirds

MINIMAL_RDF = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion> 1.3 </iirds:iiRDSVersion>
    <iirds:title>SDK fixture</iirds:title>
  </iirds:Package>
</rdf:RDF>
"""


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "pkg"
    (root / "META-INF").mkdir(parents=True)
    (root / "META-INF" / "metadata.rdf").write_text(MINIMAL_RDF, "utf-8")
    (root / "content").mkdir()
    (root / "content" / "topic1.xhtml").write_text("<html/>", "utf-8")
    return root


def test_pack_then_open_round_trips(source):
    packed = iirds.pack(source)
    with iirds.open(packed) as pkg:
        assert pkg.version == "1.3"          # stripped, as consumers compare it
        assert pkg.variant == "unrestricted"
        assert "content/topic1.xhtml" in pkg.names()
        assert pkg.read("content/topic1.xhtml") == b"<html/>"
        assert len(pkg.graph) >= 2


def test_mimetype_is_first_and_stored(source):
    packed = iirds.pack(source)
    with zipfile.ZipFile(packed) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/iirds+zip"


def test_packing_twice_produces_identical_bytes(source, tmp_path):
    one = iirds.pack(source, tmp_path / "a.iirds")
    two = iirds.pack(source, tmp_path / "b.iirds")
    assert one.read_bytes() == two.read_bytes()


def test_a_zip_without_metadata_is_refused(tmp_path):
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(iirds.IirdsError):
        iirds.open(plain)


def test_variant_reads_h(source):
    meta = source / "META-INF" / "metadata.rdf"
    meta.write_text(MINIMAL_RDF.replace(
        "</iirds:Package>",
        "  <iirds:formatRestriction>H</iirds:formatRestriction>\n  </iirds:Package>"), "utf-8")
    with iirds.open(iirds.pack(source, overwrite=True)) as pkg:
        assert pkg.variant == "H"


def test_a_symlink_in_the_source_is_refused(source, tmp_path):
    """A container is meant to be self-contained, and a link is not.

    `p.is_file()` answers for what a link points at, so a link to a file
    outside the directory had those bytes read and written into the archive:
    whatever is on the other side goes to the customer, quietly. A link to a
    directory is the same silence pointing the other way -- `rglob` does not
    descend through it, so the author sees a folder in the source and finds
    nothing in the package.

    Refused rather than followed or skipped, because either of those is a
    decision made on the author's behalf about what their delivery contains.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manual.pdf").write_bytes(b"%PDF-1.4 not part of the package")
    _link(source / "content" / "manual.pdf", outside / "manual.pdf")

    with pytest.raises(iirds.PackError) as raised:
        iirds.pack(source, tmp_path / "linked.iirds", overwrite=True)
    assert "content/manual.pdf" in str(raised.value)


def test_a_symlinked_directory_is_refused_too(source, tmp_path):
    """The other direction, and the reason the rule is about links rather
    than about what they point at."""
    outside = tmp_path / "shared"
    outside.mkdir()
    (outside / "a.txt").write_text("outside", "utf-8")
    _link(source / "shared", outside, target_is_directory=True)

    with pytest.raises(iirds.PackError) as raised:
        iirds.pack(source, tmp_path / "linkdir.iirds", overwrite=True)
    assert "shared" in str(raised.value)


def test_a_failed_pack_leaves_the_previous_package_alone(source, tmp_path):
    """The archive was opened for writing before anything was read.

    `ZipFile(output, "w")` truncates at once, so a failure part-way through --
    a file that moved, a permission, a full disk -- destroyed whatever was
    there and left what had been written so far. And that remainder is not
    obviously broken: the context manager still writes a central directory, so
    the file passes `testzip()` and opens. A release is replaced by a package
    that reports its version, answers questions, and is missing most of its
    content, with nothing anywhere saying so.

    The one thing a packer must never do is make a delivery that is wrong and
    looks right.
    """
    for index in range(4):
        (source / "content" / ("t%d.xhtml" % index)).write_text("<html/>", "utf-8")
    output = tmp_path / "release.iirds"
    iirds.pack(source, output, overwrite=True)
    with zipfile.ZipFile(output) as archive:
        before = archive.namelist()
    assert len(before) == 7, before          # mimetype + rdf + five content files

    read_bytes = pathlib.Path.read_bytes
    seen = []

    def fails_partway(self):
        seen.append(self)
        if len(seen) == 3:                   # part way, with content still to write
            raise OSError("the file moved")
        return read_bytes(self)

    pathlib.Path.read_bytes = fails_partway
    try:
        with pytest.raises(OSError):
            iirds.pack(source, output, overwrite=True)
    finally:
        pathlib.Path.read_bytes = read_bytes

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == before, "the previous package was overwritten"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pkg", "release.iirds"], \
        "a temporary file was left behind"


def test_the_metadata_must_be_spelled_the_way_it_will_be_read(tmp_path):
    """`pack()` must not write a package `open()` refuses.

    The check for metadata asked the filesystem, and on a case-insensitive one
    -- macOS and Windows, where most authoring happens -- it answers yes for
    `meta-inf/Metadata.rdf`. The archive then carried the spelling that was on
    disk, and a ZIP member name is bytes: `open()` looked for the spelling the
    standard names and did not find it. A packer whose one promise is that
    what it writes is what opens cannot decide that question by asking a
    filesystem that answers a different one.
    """
    source = tmp_path / "pkg"
    (source / "meta-inf").mkdir(parents=True)
    (source / "meta-inf" / "Metadata.rdf").write_text(MINIMAL_RDF, "utf-8")

    with pytest.raises(iirds.PackError) as raised:
        iirds.pack(source, tmp_path / "cased.iirds", overwrite=True)
    assert "META-INF/metadata.rdf" in str(raised.value)


def test_a_decomposed_filename_is_stored_composed(source, tmp_path):
    """One name, one spelling, and the one everything else writes.

    A file created with a decomposed name -- which is what several macOS tools
    produce -- was listed decomposed and stored decomposed, while the metadata
    that refers to it is written by a person in an editor and is composed. The
    two are different byte strings, so a lookup by the name in the RDF missed
    a file that is plainly there. The validator reports that as a dangling
    reference; through the SDK's own API it was simply a KeyError.

    Members are stored composed. That is what XML and RDF are written in, and
    it is one spelling rather than whichever the filesystem happened to hand
    back.
    """
    composed = unicodedata.normalize("NFC", "Prüfung.xhtml")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    (source / "content" / decomposed).write_text("<html/>", "utf-8")

    output = iirds.pack(source, tmp_path / "nfd.iirds", overwrite=True)
    with zipfile.ZipFile(output) as archive:
        members = [name for name in archive.namelist() if name.startswith("content/")]
    assert "content/" + composed in members, members

    with iirds.open(output) as package:
        assert package.read("content/" + composed) == b"<html/>"


def _link(link, target, **kwargs):
    """A symbolic link, or a skip where the runner may not make one.

    Windows grants that to administrators and to developer mode; a hosted
    runner has it, a contributor's machine may not. The two tests above are
    about what pack() does with a link, not about who may create one."""
    try:
        link.symlink_to(target, **kwargs)
    except OSError as reason:
        pytest.skip("this runner cannot create a symbolic link: %s" % reason)


def test_two_spellings_of_one_name_are_refused_before_anything_is_written(source, tmp_path, monkeypatch):
    """`_member_name` composes every name, so a decomposed `Prüfung.xhtml`
    and a composed one would be stored under one member name. A filesystem
    that keeps both spellings apart hands pack() two files for one name;
    one that folds them (macOS) hands it one, so the two are injected here
    rather than created, and the refusal is asserted before any byte is
    read."""
    import unicodedata

    from iirds import _pack

    composed = unicodedata.normalize("NFC", "content/Prüfung.xhtml")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    real = _pack._entries(source)
    monkeypatch.setattr(_pack, "_entries",
                        lambda root: real + [root / decomposed, root / composed])
    with pytest.raises(iirds.PackError) as raised:
        iirds.pack(source, tmp_path / "collide.iirds", overwrite=True)
    assert "same name once written composed" in str(raised.value)
    assert not (tmp_path / "collide.iirds").exists()
