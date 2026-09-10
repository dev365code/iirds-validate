"""A directory can hold a link, and this checker reads directories.

The archive form cannot point anywhere: an entry is its bytes. A directory was
listed with `is_file()`, which answers for the far end of a link, so a link to
any file the user running the check could read was listed, read and judged as
part of the package. Linked as `mimetype`, such a file had its first bytes
quoted in a finding; linked as `META-INF/metadata.rdf`, somebody else's
metadata was judged in place of the package's own, which passed with nothing
to say. A directory of packages was searched the same way, so a `.iirds` name
that was a link put another file's digest and size in the report. S6 -- every
entry must stay inside the container -- said nothing about any of it.

Every link is followed here one hop at a time and never out of the container,
so nothing outside it is consulted to decide. One that leads out is named by
S6 and not read; a chain too long to follow is reported as that; one that
stays inside reads as it always did. The packer in this repository refuses a
source with any link at all and says why (`tests/library/test_roundtrip.py`),
so the two are not the same rule: the packer is the stricter of them.
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from iirds_validate.cli import EXIT_ERROR, main
from iirds_validate.model import MAX_LISTED_PER_RULE
from iirds_validate.package import MAX_LINK_HOPS, DirectoryPackage, Package, PackageError, search

MARK = "TOPSECRET-4f2a"


@pytest.fixture
def unpacked(make_package, tmp_path):
    """The same package, extracted -- what a build has before it zips."""
    archive = make_package(name="src.iirds")
    out = tmp_path / "unpacked"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(out)
    return out


@pytest.fixture
def outside(tmp_path):
    """A file in no package: the thing that must not be read."""
    secret = tmp_path / "elsewhere" / "secret.txt"
    secret.parent.mkdir()
    secret.write_text(MARK + "\n", "utf-8")
    return secret


def link(at, target):
    """A symbolic link at `at`, or a skip where the runner may not make one.

    Windows grants that to administrators and to developer mode; a hosted
    runner has it, a contributor's machine may not."""
    at.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(target), str(at), target_is_directory=os.path.isdir(str(target)))
    except OSError as reason:
        pytest.skip("this runner cannot create a symbolic link: %s" % reason)


def named_by_s6(report, saying=None):
    return sorted(f.violation.subject for f in report.findings
                  if f.rule.id == "S6" and (saying is None or saying in f.violation.message))


def test_a_link_out_of_the_container_is_neither_listed_nor_read(unpacked, outside):
    """Written the way one usually is: an absolute path. That is its own
    answer rather than "it leads out", because a container reached by one of
    its names holds links written with another, and telling those apart would
    mean resolving a path outside the container."""
    link(unpacked / "content" / "outside.xhtml", outside)

    package = DirectoryPackage(unpacked)
    assert "content/outside.xhtml" not in package.names
    assert not package.has("content/outside.xhtml")
    with pytest.raises(KeyError):
        package.read("content/outside.xhtml")
    assert package.absolute_links == ("content/outside.xhtml",)
    assert package.outward_links == () and package.chained_links == ()


def test_s6_names_the_link_and_not_what_is_behind_it(unpacked, outside):
    """The report is the thing that travels -- into a build log, a ticket, a
    customer's inbox. What the link points at is the checking machine's
    business, so neither its bytes nor its path goes into it."""
    link(unpacked / "content" / "outside.xhtml", outside)

    report = runner.run(unpacked, runner.ALL_KINDS)
    assert named_by_s6(report) == ["content/outside.xhtml"]
    assert not report.ok
    document = json.dumps(report.as_dict())
    for private in (MARK, str(outside.parent), os.path.realpath(str(outside.parent))):
        assert json.dumps(private)[1:-1] not in document, private


def test_metadata_linked_from_elsewhere_does_not_pass(unpacked, tmp_path):
    """Measured before the repair: this container passed with no findings,
    judged on a file it does not contain."""
    elsewhere = tmp_path / "elsewhere.rdf"
    metadata = unpacked / "META-INF" / "metadata.rdf"
    elsewhere.write_bytes(metadata.read_bytes())
    metadata.unlink()
    link(metadata, elsewhere)

    report = runner.run(unpacked, runner.ALL_KINDS)
    assert "META-INF/metadata.rdf" in named_by_s6(report)
    assert not report.ok


def test_what_a_linked_file_says_stays_out_of_the_report(unpacked, tmp_path):
    """Measured before the repair: with the version in somebody else's
    metadata set to the marker, S4 put the marker in the report as the
    subject of its finding. A finding quotes what it judges, so judging a file
    from elsewhere was a way to carry it into a build log."""
    elsewhere = tmp_path / "elsewhere.rdf"
    metadata = unpacked / "META-INF" / "metadata.rdf"
    text = metadata.read_text("utf-8")
    assert "<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>" in text
    elsewhere.write_text(text.replace("<iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>",
                                      "<iirds:iiRDSVersion>%s</iirds:iiRDSVersion>" % MARK), "utf-8")
    metadata.unlink()
    link(metadata, elsewhere)

    report = runner.run(unpacked, runner.ALL_KINDS)
    assert MARK not in json.dumps(report.as_dict())
    assert "S4" not in {f.rule.id for f in report.findings}


def test_every_way_out_is_named(unpacked, outside, tmp_path):
    """Absolute, relative, through another link, to a directory, and to
    nothing at all: each one is an entry that leads out of the container."""
    content = unpacked / "content"
    link(content / "absolute.xhtml", outside)
    link(content / "relative.xhtml", os.path.join("..", "..", "elsewhere", "secret.txt"))
    link(content / "second.xhtml", outside)
    link(content / "first.xhtml", "second.xhtml")
    link(content / "shared", outside.parent)
    link(content / "gone.xhtml", tmp_path / "nowhere" / "gone.xhtml")

    leaving = ["content/absolute.xhtml", "content/first.xhtml", "content/gone.xhtml",
               "content/relative.xhtml", "content/second.xhtml", "content/shared"]
    assert named_by_s6(runner.run(unpacked, runner.ALL_KINDS)) == leaving
    package = DirectoryPackage(unpacked)
    assert not set(leaving) & set(package.names)
    # Which of them is which: a `..` out of the root is one fact, and a path
    # written from the filesystem's root is another.
    assert package.outward_links == ("content/relative.xhtml",)
    assert set(package.absolute_links) == set(leaving) - {"content/relative.xhtml"}
    assert not [name for name in package.names if name.startswith("content/shared/")]


def test_a_link_that_stays_inside_reads_as_before(unpacked):
    content = unpacked / "content"
    content.mkdir(exist_ok=True)
    (content / "real.xhtml").write_bytes(b"<html/>")
    link(content / "alias.xhtml", "real.xhtml")

    package = DirectoryPackage(unpacked)
    assert "content/alias.xhtml" in package.names
    assert package.read("content/alias.xhtml") == b"<html/>"
    assert package.outward_links == () and package.chained_links == ()
    assert named_by_s6(runner.run(unpacked, runner.ALL_KINDS)) == []


def test_a_container_reached_through_a_link_is_the_same_container(unpacked, tmp_path):
    """Where the container itself lives behind a link -- `/var` is one on
    macOS -- nothing inside it has left, and a link inside it still stays."""
    content = unpacked / "content"
    content.mkdir(exist_ok=True)
    (content / "real.xhtml").write_bytes(b"<html/>")
    link(content / "alias.xhtml", "real.xhtml")
    via = tmp_path / "via"
    link(via, unpacked)

    package = DirectoryPackage(via)
    assert package.names == DirectoryPackage(unpacked).names
    assert package.outward_links == ()
    assert package.read("content/alias.xhtml") == b"<html/>"
    assert named_by_s6(runner.run(via, runner.ALL_KINDS)) == []


def test_a_file_that_becomes_a_link_after_the_listing_is_not_read(unpacked, outside):
    """The listing is taken once, when the container is opened, and the rules
    read later. A directory that changes in between -- a file swapped for a
    link -- is refused at the read rather than trusted from the listing."""
    package = DirectoryPackage(unpacked)
    entry = next(name for name in package.names if name.startswith("content/"))
    (unpacked / entry).unlink()
    link(unpacked / entry, outside)

    with pytest.raises(PackageError):
        package.read(entry)


def test_a_name_the_listing_does_not_hold_is_refused_as_the_archive_refuses_it(
        unpacked, outside, make_package):
    """Every rule asks `has()` first, so no rule has reached this. It is the
    one path by which a caller could, and the archive form already closes it."""
    stray = os.path.relpath(str(outside), str(unpacked)).replace(os.sep, "/")
    with pytest.raises(KeyError):
        DirectoryPackage(unpacked).read(stray)
    with Package(make_package(name="refuses.iirds")) as archive, pytest.raises(KeyError):
        archive.read(stray)


def test_an_archive_has_no_links_to_follow(make_package):
    """The two forms answer alike, including about this -- all four ways."""
    with Package(make_package(name="plain.iirds")) as archive:
        assert archive.outward_links == ()
        assert archive.absolute_links == ()
        assert archive.chained_links == ()
        assert archive.dangling_links == ()


@pytest.mark.skipif(os.name != "nt", reason="a junction is a Windows directory link")
def test_a_junction_that_leaves_is_named_too(unpacked, outside):
    """`islink` does not call a junction a link, and a walk that asks only
    `islink` walks straight through one -- listing what is behind it as though
    the package held it."""
    import _winapi
    (unpacked / "content").mkdir(exist_ok=True)
    _winapi.CreateJunction(str(outside.parent), str(unpacked / "content" / "junction"))

    package = DirectoryPackage(unpacked)
    told = (package.names, package.outward_links, package.absolute_links,
            package.chained_links, package.dangling_links)
    # The one that matters even more than the name: nothing behind it is in
    # the package. A junction `islink` does not recognise is one a walk goes
    # straight through.
    assert not [name for name in package.names if name.startswith("content/junction")], told
    # Windows hands a junction's target back as an absolute path, so that is
    # what it is reported as. Which of the two it is matters less than that it
    # is named and that nothing behind it is in the package.
    assert package.absolute_links == ("content/junction",), told
    assert package.outward_links == (), told
    assert named_by_s6(runner.run(unpacked, runner.ALL_KINDS)) == ["content/junction"]


def test_a_chain_longer_than_a_reader_would_follow_is_reported_as_itself(unpacked):
    """Neither read nor called an escape.

    Resolving a name used to be one recursive call per link, so a package
    holding a chain of them ended the run with a traceback on the Pythons this
    supports and read fine on the newest. It is followed a hop at a time now,
    and a chain past the end of the count is a third thing the package can be:
    saying it leaves would claim it points somewhere it may not.
    """
    content = unpacked / "content"
    previous = "topic1.xhtml"
    for i in range(1200):
        link(content / ("l%d.xhtml" % i), previous)
        previous = "l%d.xhtml" % i

    package = DirectoryPackage(unpacked)
    assert package.outward_links == ()
    assert len(package.chained_links) == 1200 - MAX_LINK_HOPS
    assert "content/l1199.xhtml" in package.chained_links  # 1200 links from the file
    assert "content/l0.xhtml" in package.names             # one link from it

    report = runner.run(unpacked, runner.ALL_KINDS)
    listed = named_by_s6(report, saying="chain")
    assert set(listed) <= set(package.chained_links)
    assert len(listed) == MAX_LISTED_PER_RULE
    assert (report.as_dict()["summary"]["findingsNotListed"]
            == len(package.chained_links) - MAX_LISTED_PER_RULE)
    assert named_by_s6(report, saying="leads out") == []
    assert "S3" not in {f.rule.id for f in report.findings}


def test_a_link_swapped_after_the_listing_is_not_read(unpacked, outside):
    """The other half of the same question: the listing is taken once, and a
    link that pointed inside when it was taken may point out by the time a
    rule asks for it."""
    content = unpacked / "content"
    (content / "real.xhtml").write_bytes(b"<html/>")
    link(content / "alias.xhtml", "real.xhtml")
    package = DirectoryPackage(unpacked)
    assert package.read("content/alias.xhtml") == b"<html/>"

    (content / "alias.xhtml").unlink()
    link(content / "alias.xhtml", outside)
    with pytest.raises(PackageError):
        package.read("content/alias.xhtml")


def test_whether_the_far_end_exists_does_not_reach_the_report(unpacked, tmp_path, outside):
    """A dangling link out and a link to a file that is there must read alike.

    The two markers were looked for with `exists()`, which answers for the far
    end: the container opened when the file out there happened to be present
    and was refused as "not a container" when it was not. That is one bit
    about a path of the sender's choosing, and it arrived in the verdict.
    """
    verdicts = []
    for tag, target in (("present", outside), ("absent", tmp_path / "nowhere" / "gone")):
        directory = tmp_path / ("oracle-" + tag)
        shutil.copytree(unpacked, directory, symlinks=True)
        (directory / "mimetype").unlink()
        (directory / "META-INF" / "metadata.rdf").unlink()
        link(directory / "META-INF" / "metadata.rdf", target)
        report = runner.run(directory, runner.ALL_KINDS)
        assert "META-INF/metadata.rdf" in named_by_s6(report), tag
        verdicts.append((report.ok, sorted({f.rule.id for f in report.findings})))
    assert verdicts[0] == verdicts[1], verdicts


def test_a_linked_mimetype_does_not_put_a_private_file_in_the_report(unpacked, tmp_path):
    """The worst of it, measured before the repair: the rule that reads
    `mimetype` quotes what it read, so any readable file linked there had its
    first bytes in the report -- and a report is the thing that travels."""
    private = tmp_path / "id_ed25519"
    private.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n%s\n" % MARK, "utf-8")
    (unpacked / "mimetype").unlink()
    link(unpacked / "mimetype", private)

    report = runner.run(unpacked, runner.ALL_KINDS)
    assert "mimetype" in named_by_s6(report)
    document = json.dumps(report.as_dict())
    for private_text in (MARK, "BEGIN OPENSSH"):
        assert private_text not in document


def test_an_archive_entry_marked_as_a_link_is_read_as_its_bytes(tmp_path, outside):
    """Why the archive form needs none of this: an entry is bytes.

    An extractor that restores links makes the directory this repair is about,
    which is how a supplier's archive reaches it -- but checking the archive
    itself reads the entry, and the entry is the link's text.
    """
    archive = tmp_path / "linked.iirds"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("META-INF/metadata.rdf", MINIMAL_RDF)
        info = zipfile.ZipInfo("mimetype")
        info.create_system = 3                       # a POSIX mode to carry
        info.external_attr = 0o120777 << 16          # S_IFLNK
        zf.writestr(info, str(outside))

    report = runner.run(archive, runner.ALL_KINDS)
    document = json.dumps(report.as_dict())
    assert MARK not in document                      # nothing was read from the disk
    quoted = json.dumps(str(outside))[1:-1]          # as JSON spells it, backslashes and all
    assert quoted[:40] in document                   # the entry's own bytes
    assert named_by_s6(report) == []


# --- a directory of packages ----------------------------------------------

def test_a_link_out_of_a_searched_directory_is_refused_not_followed(
        make_package, tmp_path, outside):
    """One layer up, and the same leak: the search followed links too.

    A build directory holding `x.iirds -> ~/.ssh/id_ed25519` had that file's
    digest and its size in the report, and one holding a link to somebody
    else's package had that package's metadata quoted in it.
    """
    searched = tmp_path / "builds"
    searched.mkdir()
    mine = make_package(name="mine.iirds")
    shutil.copy(mine, searched / "mine.iirds")
    theirs = make_package(name="theirs.iirds")
    link(searched / "theirs.iirds", theirs)
    link(searched / "secret.iirds", outside)

    found, refused = search(searched)
    assert [p.name for p in found] == ["mine.iirds"]
    assert sorted(p.name for p in refused) == ["secret.iirds", "theirs.iirds"]


def test_the_command_line_says_what_it_did_not_check_and_exits_two(
        make_package, tmp_path, outside, capsys):
    searched = tmp_path / "builds"
    searched.mkdir()
    shutil.copy(make_package(name="mine.iirds"), searched / "mine.iirds")
    link(searched / "secret.iirds", outside)

    assert main(["check", str(searched)]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "not checked" in err and "secret.iirds" in err
    assert MARK not in err


def test_a_linked_container_beside_the_others_is_refused_too(unpacked, tmp_path):
    """The other branch of the search: directories that are containers."""
    side_by_side = tmp_path / "side"
    side_by_side.mkdir()
    shutil.copytree(unpacked, side_by_side / "ours", symlinks=True)
    link(side_by_side / "theirs", unpacked)

    found, refused = search(side_by_side)
    assert [p.name for p in found] == ["ours"]
    assert [p.name for p in refused] == ["theirs"]


def test_the_path_the_operator_names_is_followed(unpacked, tmp_path):
    """A link the operator points at is the operator's choice, and the one
    they are most likely to have made on purpose."""
    via = tmp_path / "via"
    link(via, unpacked)
    found, refused = search(via)
    assert found == [via] and refused == []


def test_a_container_is_recognised_by_the_names_it_holds(unpacked, tmp_path):
    """The search asks the same question the opening does, and must ask it the
    same way: whether the marker is there, not whether something at the far end
    of it is. Otherwise a directory is a package or is not depending on a file
    somewhere else entirely."""
    side_by_side = tmp_path / "side"
    side_by_side.mkdir()
    shutil.copytree(unpacked, side_by_side / "ours", symlinks=True)
    metadata = side_by_side / "ours" / "META-INF" / "metadata.rdf"
    metadata.unlink()
    (side_by_side / "ours" / "mimetype").unlink()
    link(metadata, tmp_path / "nowhere" / "gone.rdf")

    found, refused = search(side_by_side)
    assert [p.name for p in found] == ["ours"] and refused == []


def test_a_link_that_leads_nowhere_is_named(unpacked):
    """Not listed -- there is no file to read -- and not silent either. It is
    an entry the container holds and no rule can use, which is the third thing
    a link can be after leading out and being a chain."""
    link(unpacked / "content" / "missing.xhtml", "gone.xhtml")

    package = DirectoryPackage(unpacked)
    assert "content/missing.xhtml" not in package.names
    assert package.dangling_links == ("content/missing.xhtml",)
    assert package.outward_links == () and package.chained_links == ()
    assert named_by_s6(runner.run(unpacked, runner.ALL_KINDS),
                       saying="leads nowhere") == ["content/missing.xhtml"]


def test_a_link_through_a_directory_that_leads_out_is_not_read(unpacked, outside):
    """The kernel resolves a path one component at a time, and so must this.

    Reading a link's own text and judging the joined string judged the last
    component only: `leak.xhtml -> b/secret.txt` is under the container as
    text, and `b` was a link out of it, so the file at the far end was listed
    and read all the same.
    """
    link(unpacked / "b", os.path.join("..", "elsewhere"))
    link(unpacked / "content" / "leak.xhtml", os.path.join("..", "b", "secret.txt"))

    package = DirectoryPackage(unpacked)
    assert "content/leak.xhtml" not in package.names
    assert set(package.outward_links) == {"b", "content/leak.xhtml"}
    with pytest.raises(KeyError):
        package.read("content/leak.xhtml")
    assert MARK not in json.dumps(runner.run(unpacked, runner.ALL_KINDS).as_dict())


def test_a_step_back_through_a_link_goes_where_the_kernel_goes(unpacked, outside):
    """`sub/s/..` is not `sub` when `s` is a link: the kernel follows the link
    first and steps back from wherever it landed. Folding the text instead put
    the tool's answer and the kernel's on two different files."""
    (unpacked / "sub").mkdir(exist_ok=True)
    link(unpacked / "sub" / "s", "..")                      # -> the container root
    link(unpacked / "f.xhtml", os.path.join("sub", "s", "..", "elsewhere", "secret.txt"))

    package = DirectoryPackage(unpacked)
    assert "f.xhtml" not in package.names
    assert "f.xhtml" in package.outward_links
    assert MARK not in json.dumps(runner.run(unpacked, runner.ALL_KINDS).as_dict())


@pytest.mark.skipif(os.name == "nt", reason="the mode bits that hide a directory are POSIX")
def test_a_container_holding_a_directory_it_cannot_list_is_refused(unpacked, outside):
    """A directory the check cannot list is a part of the container it did not
    look at. `os.walk` skips one in silence, and a package can make one -- so
    what a report would say is "no findings" about a container half read.
    Refused by name instead, and the reason is in the report.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root lists what the mode bits forbid")
    hidden = unpacked / "content" / "hidden"
    hidden.mkdir()
    link(hidden / "out", os.path.join("..", "..", "..", "elsewhere"))
    link(unpacked / "mimetype2", os.path.join("content", "hidden", "out", "secret.txt"))
    os.chmod(str(hidden), 0o111)
    try:
        report = runner.run(unpacked, runner.ALL_KINDS)
        assert not report.ok
        detail = [f.violation.detail for f in report.findings if f.rule.id == "S13"]
        assert detail and "content/hidden" in detail[0], detail
        assert MARK not in json.dumps(report.as_dict())
    finally:
        os.chmod(str(hidden), 0o755)


def test_a_search_does_not_follow_a_name_through_a_directory_that_leads_out(
        make_package, tmp_path, outside):
    """The same one-component-at-a-time question, one layer up."""
    searched = tmp_path / "builds"
    searched.mkdir()
    theirs = make_package(name="theirs.iirds")
    link(searched / "b", str(theirs.parent))
    link(searched / "leak.iirds", os.path.join("b", "theirs.iirds"))

    found, refused = search(searched)
    assert found == []
    assert [p.name for p in refused] == ["leak.iirds"]


def test_a_directory_named_through_a_link_keeps_its_own_links(make_package, tmp_path):
    """A root has two spellings when it is reached through a link -- `/tmp` and
    `/private/tmp` are that pair on macOS -- and a package written under one of
    them must not be read as leaving the other."""
    real = tmp_path / "real"
    real.mkdir()
    shutil.copy(str(make_package(name="pkg.iirds")), str(real / "pkg.iirds"))
    link(real / "latest.iirds", "pkg.iirds")
    alias = tmp_path / "alias"
    link(alias, "real")

    link(real / "absolute.iirds", real / "pkg.iirds")       # written the other way

    found, refused = search(alias)
    assert sorted(p.name for p in found) == ["absolute.iirds", "latest.iirds", "pkg.iirds"]
    assert refused == []


def test_an_absolute_link_inside_reads_under_either_spelling_of_the_root(unpacked, tmp_path):
    """A container reached through a link has two names, and an absolute link
    written inside it names one of them. Judging it against only the resolved
    one reports a package for leaving itself."""
    alias = tmp_path / "by-another-name"
    link(alias, unpacked)
    content = unpacked / "content"
    (content / "real.xhtml").write_bytes(b"<html/>")
    link(content / "spelled-as-named.xhtml", alias / "content" / "real.xhtml")
    link(content / "spelled-as-resolved.xhtml", unpacked / "content" / "real.xhtml")

    named = DirectoryPackage(alias)
    assert named.outward_links == () and named.absolute_links == ()
    assert named.read("content/spelled-as-named.xhtml") == b"<html/>"
    assert named.read("content/spelled-as-resolved.xhtml") == b"<html/>"

    # Opened by the name it resolves to, the other spelling is a path this
    # cannot show to be inside without walking out of the container. It says
    # that, rather than that the package points somewhere it may not.
    resolved = DirectoryPackage(unpacked)
    assert resolved.read("content/spelled-as-resolved.xhtml") == b"<html/>"
    assert resolved.absolute_links == ("content/spelled-as-named.xhtml",)
    assert resolved.outward_links == ()


def test_nothing_this_lists_is_a_name_the_system_refuses(unpacked):
    """The count of links a name may pass through is a fact about the system
    that opens it, not a number to pick. Read further than the system will and
    a package is judged on entries no consumer can open by name -- the mirror
    of the thing this rule is for. Measured rather than asked: `pathconf`
    answers 255 where the kernel stops at 32.
    """
    content = unpacked / "content"
    previous = "topic1.xhtml"
    for i in range(60):
        link(content / ("l%d.xhtml" % i), previous)
        previous = "l%d.xhtml" % i

    package = DirectoryPackage(unpacked)
    assert package.chained_links, "a chain of sixty is past any system's count"
    for name in package.names:
        with open(str(unpacked / name), "rb") as handle:      # what a consumer does
            handle.read(1)


def test_a_meta_inf_holding_one_link_is_not_a_missing_directory(unpacked, outside):
    """C7 reports a container with no META-INF. An entry S6 refuses to read is
    still an entry, and saying the directory is not there describes the wrong
    defect to whoever has to fix it."""
    metadata = unpacked / "META-INF" / "metadata.rdf"
    metadata.unlink()
    link(metadata, outside)

    report = runner.run(unpacked, runner.ALL_KINDS)
    assert "META-INF/metadata.rdf" in named_by_s6(report)
    assert "C7" not in {f.rule.id for f in report.findings}


@pytest.mark.skipif(os.name != "nt", reason="a junction is a Windows directory link")
def test_a_junction_that_stays_inside_is_not_called_an_escape(unpacked):
    """Windows hands a junction's target back with an extended-length prefix.
    Left on, the text does not match the container's own path and every
    junction inside one reads as leading out of it."""
    import _winapi
    inside = unpacked / "content" / "sub"
    inside.mkdir(parents=True, exist_ok=True)
    _winapi.CreateJunction(str(inside), str(unpacked / "content" / "junction-in"))

    package = DirectoryPackage(unpacked)
    assert package.outward_links == () and package.absolute_links == ()
