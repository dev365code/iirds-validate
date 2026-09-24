# Changelog

The `iirds` library shipped on its own as 0.1.0 to 0.3.2; that history is in
[docs/library-changelog.md](docs/library-changelog.md). From here on, what
changes in the library is recorded beside what changes in the checker.

## 0.7.2 — unreleased

Three advisories describe what this release fixes:

- [GHSA-gv27-g2mp-8ghv](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-gv27-g2mp-8ghv): an entry's Unicode Path extra
  field could give it a name other than the one this tool judged.
- [GHSA-pj7w-78cj-j5h8](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-pj7w-78cj-j5h8): link and path lookups could
  reach past the container being checked.
- [GHSA-325m-q3mp-wx43](https://github.com/dev365code/iirds-validate/security/advisories/GHSA-325m-q3mp-wx43): a directory that could not be
  read was left out without a word, in an unpacked container or a search.

**Security. Whether a directory was a container could depend on a file
outside it.** The markers were looked up as names at the last step only, so a
`META-INF` that was itself a link out of the directory was followed, and a file
at the far end decided whether the directory was read as a container. The
directory a marker sits in is now walked like every other name, where a
directory is searched and where a container is opened, and one that does not
resolve inside the container counts as the marker being there, for S6 to name.
Where the far end held no marker, that takes the exit code from `2` -- no
package found -- to `1`. Every release through 0.7.1 looks through such a
link.

**Security. A container holding a directory that could be listed but not
searched was checked without the files in it.** Each name came back from the
listing and every question about it failed, so it was neither a file nor a link
and left the listing without a word. Such a directory now refuses the
container, as one that cannot be listed already did (S13), and so does an
entry that cannot be looked up for any other reason -- one removed after the
listing, or a name the system lists and cannot open -- named as itself. For a
package with nothing else wrong, that takes the exit code from `0` to `1`. An
archive has no such state: its entries are read from the archive whatever mode
bits they record, measured on one whose directory entry records a mode that
forbids searching it. 0.6.1 through 0.7.1 leave such files out.

**Security. `--fragment` read the whole file before the metadata limit
applied.** The file was copied into a throwaway container by reading all of it
into memory, and only the container's read was bounded. The copy now stops one
byte past the limit, and the gate refuses the document the way it refuses an
archive's (C16.1). Every release from 0.3.0, the first with `--fragment`,
through 0.7.1 reads the whole file.

**Security. Pointing at a directory of packages left out the ones in a
subdirectory it could not read.** The search walked the directory with a glob,
which skips a subdirectory it cannot list without a word; from one it can list
and not search it returns the names, and the file test after it dropped each of
them without a word. The run passed on the packages it did find. The search now
walks the directory the way a container is listed: a subdirectory it cannot
list, or a `.iirds` name it cannot look up, refuses the search with `2`, named
as the argument was given, as a name that leads out of the directory already
does. A name gone by the time it is looked up is left out, and an unpacked
container found there refuses what it cannot read itself when it is opened
(S13), with the containers beside it still checked. Where every package found
beside such a subdirectory passes, that takes the exit code from `0` to `2`;
where one of them fails, from `1`. Every release through 0.7.1 leaves out a
subdirectory it cannot list; one it can list and not search, 0.6.1 through
0.7.1 leave out, and earlier releases stop with `2` on the permission error
(under Python 3.14 they leave it out too).

**Security. A link through a name that is not a directory read the file beside
it.** A container's links are resolved one component at a time, and a component
that was not there, or was a file, was kept as if it were a directory: a `..`
after it took it away again, and a `.` or a separator after a file was dropped,
so the link was listed and read as the file beside it, where a consumer on
Linux or macOS opening the same path gets an error. The walk now asks a name
that a `..`, a `.` or a separator follows to be a directory, and a link through
one that is not leads nowhere: S6 names it, and for a package with nothing else
wrong that takes the exit code from `0` to `1`. Windows removes those by their
text and would open the file beside it; the answer here is the same wherever
the check runs. An absolute target is walked as written rather than tidied
first, so one that steps above the container on its way is named as leading
out. When a directory is searched, a `.iirds` name that is a link leading
nowhere is now refused by name with `2`, where 0.6.1 through 0.7.1 checked one
of this shape as the file beside it and left a plainly dangling one out without
a word. 0.6.1 through 0.7.1 resolve such a link as text.

**Security. Listing an unpacked container, and searching a directory, asked
each link what it points at.** The container listing sorted names into
directories and files with a question that a link answers from its far end, and
on Python 3.9 and 3.10 the directory search's glob asked the same. No verdict
depended on the answer -- every link is resolved from the root afterwards --
but the question reached wherever the link points. Each name is sorted by its
own entry now, in both. Every release through 0.7.1 asks; up to 0.6.0 the
answer also decided what was listed and read (see 0.6.1), and from 0.6.1
through 0.7.1 it decided nothing.

**Security. An entry could be judged under a name its records do not give it.**
From Python 3.12, zipfile names an entry by an Info-ZIP Unicode Path extra
field in the central directory where one holds, and libarchive names it by
the field in the local header; S10 compared only the names the two records'
bytes spell. An entry this run judged under one name could reach another
reader under another -- one that leads out of the package among them, which
S6, reading zipfile's name, passed. APPNOTE makes the field the same name in
UTF-8, so S10 now holds every field in each record to the name that record's
bytes read -- up to a NUL, and composed alike -- whatever its version or
CRC-32, since readers check those differently: zipfile the whole name's,
libarchive the name it holds by then, converted to the system's form and
renamed by any field before it. A field that renames the entry is one
finding, whose remedy is the writer's -- store names as UTF-8 under bit 11,
which needs no field; a field one reader refuses and another passes by, or
local extra data that runs past its end, is another. S10 reads the fields
itself, so the verdict is the same on every interpreter, and files its
findings under the name the directory's bytes read. S6 checks every name an
entry is read as, stopping at a NUL as the readers do. A Latin name in code
page 437 with a field giving the same name, as Info-ZIP writes, passes; one
in another code page, where readers disagree, does not. S10 also compares
the name as each record's bit 11 reads it, beside its bytes, so one set of
bytes the two flags read as two names draws S10 beside the C1 it drew.
Every release through 0.7.1 passes a package whose declared files resolve
under a directory field's name when run on Python 3.12 or later, and one
whose local header carries a field libarchive follows to another name on any
interpreter; 0.5.0 is the first with S10. For a package with nothing else
wrong, such a field takes the exit code from `0` to `1` on every
interpreter; zipfile already refused a directory field that runs past the
extra data (`S13`), and from 3.12 one too short or not UTF-8. No verdict
moves on the vendored corpus.

## 0.7.1 — 2026-09-23

**A legal package that passed on 0.6.3 can fail on 0.7.1**, and that is the
change rather than a side effect of it: two refusals of this tool's own
were named by B1 alone, which is a warning outside iiRDS/A, and the package
exited 0 with a file in it that nothing had parsed. `ERROR S16` names them
now. What that costs is under **What now fails** below.

**The search for a package's own ontology had no ceiling on what it read in
total.** R18 finds one by reading the entries under `META-INF/` the standard
does not name and parsing each as RDF, and until this release it read every
one of them, so what a package could ask a run to read was whatever its entry
count and entry sizes said. Each read was bounded per entry and nothing
bounded their sum: measured, a 524,395-byte archive carrying twenty 8 MiB
entries made a run read back 167,771,253 bytes and parse all of it, which is
three hundred and twenty times the archive, and the entry count is the
sender's to choose. A constant for the ceiling was there and was used by
nothing.

It is used now: the scan stops at eight mebibytes across all of those files,
and the scan reads back 8,388,609 bytes -- the ceiling plus one, which is what
any package that reaches the ceiling reads back however much more it holds,
because the read that crosses it is the last one. A package whose side files
come to less than that is read whole and draws no S12. That figure is the
scan's own total and not the run's: `META-INF/metadata.rdf` is read by the
container and skipped by this scan, so what a run reads under `META-INF/` is
the scan's total and that one file besides, and the two numbers are about
different readers. Stopping quietly would be the other half of the defect,
since a scan that gave up and a scan that found nothing otherwise look alike,
so `S12` names the file it stopped on and says the rest of `META-INF/` went
unexamined.

The read is bounded by what is left of the ceiling now, and the cut is recorded
where it happens. **A package carrying side files past the ceiling failed to
draw S12 before and draws it now**, and S12 is a MUST, so such a package's
verdict moves from pass to fail. That is the repair rather than a side effect
of it: a scan that stopped early and said so is the only honest answer.

What the ceiling costs is stated where it falls. The file the scan stops on is
read only as far as the ceiling had left and is never parsed, so R18 -- which
decides whether a file under `META-INF/` attaches anything to iiRDS -- cannot
answer for it, and the entries after it are not read at all. S12 names the
file the scan stopped on and says the rest of `META-INF/` went unexamined, so
a file that would have drawn R18 before is covered by that sentence rather
than by a finding naming it. Both are MUST, so the verdict does not move; the
finding says which file went unexamined and that the question about it is
open, rather than leaving R18's silence to be read as an answer.

**What now fails in a content file, and did not on 0.6.3: a rendition larger
on its own than the 64 MiB this tool reads in one piece, and a document that
declares XML entities.** The third shape this release newly fails is the one
above: a package whose `META-INF/` side files run past the scan's ceiling,
which draws `S12`. Both files are legal -- a package may carry a 200 MiB
rendition and a topic with an internal subset and breach nothing the
specification says -- and both refusals are this project's own: the ceiling is
a number chosen here rather than a setting a run can be given, and the entity
guard exists because the billion-laughs shape has nothing invalid about it and
a parser has to not meet it at all. 0.6.3 left both alone deliberately, and
said so about the ceiling, because closing them moves a legal package's
verdict and that release was a patch.

S16 is a system rule -- the statement is about the run, not about the profile
-- and it stops where another rule already speaks: `S9` and `S14` at its own
severity, and B1 for a document a parser rejected, which outside iiRDS/A is a
warning. Six things stop a content rule getting a parsed document. One is the
parser rejecting the document, which stays B1's and is below. Of the other
five, two draw an error of their own -- the run's content budget as `S9` and a
compression method no bounded read can be made of as `S14` -- and naming those
files here as well would print two errors for one fault with one remedy
between them. The remaining three are this rule's, and two of the three are
new here.

What they cost a reader is what the case 0.6.3 closed cost it in an unpacked
container; in an archive that case failed anyway, because C1 opens every entry
and reports the one the container will not hand over, and these two files are
handed over. B1 named the file, the demotion made that a warning outside
iiRDS/A, and the package came back `PASS`, exit 0 -- with B2 through B11
counted among the rules the run checked and only B6, which reads the name and
never the file, able to answer for it. `-W` was the answer on offer and it is
not one: it promotes every warning at once, and this project reports warnings
that are not failures on purpose, eleven of them from B10 across the
Consortium's own samples. A gate that wants "fail if a content file went
unparsed" could not ask for that without also failing those.

A document that does reach a parser and is rejected by it -- malformed, or
declaring an encoding no codec has -- is not this rule's: that is the
document's own defect, and where the document is a rendition B1 reports it and
the severity it carries is the profile's business. Under iiRDS/H the content
list is not a rendition, so B1 never reads it and a malformed `index.html` is
reported by nothing here. The line is whose decision left the file unparsed.

Which files the rule reports for the case 0.6.3 shipped is unchanged, and that
case is described under 0.6.3 below; what it prints is not -- the finding's
sentence, the rule's title and its remedy are rewritten for the three causes
it now carries. One thing there is not: the remedy for a document that
declares entities now names both halves, because deleting the declarations and
keeping the references clears the error and leaves a document that still does
not parse -- a package that passes with a file nothing read. Where the file is
a rendition, B1's remedy for it says so too; under iiRDS/H the content list is
not a rendition and B1 is silent there, so S16's is the only remedy that says
it. `docs/divergences.md` carries the argument, including what the change
costs.

**Three repairs that shipped in 0.6.2 and 0.6.3 and that neither release's
notes describe, kept here so the record exists somewhere.** All three are
changes a reader could meet. The notes that went out are reproduced below
unchanged rather than edited after the fact, so the account of these lives
here.

**A refused rendition stopped being reported as one that was too big**
(0.6.2). The reader returned a flag meaning "over the per-file limit", and
both refusals it could make were printed with that one sentence -- so a
rendition refused because the run had already spent what it will decompress in
total was reported to B1's reader as a file to shrink. It may be a few hundred
bytes. The second value is a reason now, and each refusal carries its own.

**B1's remedy stopped naming a list that was already short** (0.6.3). The
finding for a rendition refused rather than parsed enumerated the reasons, and
the enumeration was one short of what the reader could return. It points at
the reason printed beside the finding now, and offers the causes seen so far
as examples rather than as a list that closes.

**A graph RDF/XML writes without complaint could come back refused** (0.6.3).
Where a graph's blank nodes are not a forest there is no fingerprint to use,
so `write_metadata` compares what it read back with rdflib's isomorphism
instead -- and that canonicalises through N3, which refuses an IRI holding any
of the characters rdflib itself will not write -- a space, a brace, a bar
among them -- while others RFC 3987 leaves out of an IRI, a bare percent or a
DEL, go through. RDF/XML writes such IRIs without complaint. The refusal
reached the caller as a bare `Exception` rather than the `ValueError` the
function now documents, and a comparison that refuses its input has decided
nothing -- which is not the same as deciding the round trip failed. It is a
`ValueError` now, and says so.

**These notes now carry 0.6.1, 0.6.2 and 0.6.3, which were released from the
0.6.x line.** Their version bumps never came back here, so a reader of this
file could not see what three shipped releases changed, and the entries
describing that work sat under `unreleased` above them. The sections below are
the notes those releases published, unchanged; the paragraphs here that
described the same work are gone, except the three above. What those notes do
carry, they carry in their own words, which are not always this file's.
The gate that holds this file reads the repository's tags now: an entry above
this line's version may carry a date when it has a tag, and is refused without
one. "It has not shipped" was the sentence that became false the day a second
line existed.

**Seven rules asked the same question twice, and checking a large document
got faster when the second copy went.** The rules that ask whether a value is
an instance of a class exempt a value they should not report on, and the
exemption was written twice over: once by naming every term the bundled
ontology defines, once by the namespace the value sits in. Every term every
edition defines is in one of those namespaces, so the first was subsumed by
the second and could not change an answer -- it could only be paid for, once
per candidate value, in a membership test the published shapes carried eight
times over. `shapes/iirds-1.3/iirds-sparql.ttl` is a quarter of the size it
was, the shapes as a whole are two thirds, and a large document is checked in
a fraction of the time. **No verdict moves**: the
reading is the same in both encodings, and what makes the removal safe is a
property of the published vocabularies rather than an argument -- if an
edition ever defines a term that would be exempt in one encoding and reported
by the other, the build says so rather than a verdict going quietly missing.

**The job that builds a release no longer holds the permission that publishes
it.** It ran this project's build scripts and the whole suite, and it carried
`contents: write` for one step at the end -- so anything that reached it, a
dependency or a script or a fixture, could have rewritten a release under this
project's name. That step is a job of its own now: it takes the artifact the
build made, publishes it, and does nothing else. Nothing is rebuilt on the
way, because a second build is a second set of bytes and the checksum file
beside them would describe the first. The ordering the publishers relied on is
unchanged -- the release exists before any of them runs -- and a test refuses
any other job that asks for the same permission.

**The front page says how releases are numbered and what to pin.** What a
patch does and what it owes a reader when it moves a verdict, what a minor
release may do, that a security fix carries an advisory, and what 1.0 will
mean -- said on the page rather than inferred from the history. One of those
sentences is worth its own line: pin `iirds`. `iirds-validate` and `iirds-sdk`
are aliases that ship no engine, and their dependency on `iirds` is a floor,
so pinning either fixes the name installed and not the rules a package is
judged by.

**Breaking, and said here because the exit codes are a stable surface: a
command-line usage error exits `64` rather than `2`.** `iirds --bogus`, `iirds
check` with no package, an unknown value for `-f` or for `--iirds-version`:
each of those exited `2`, which is also the value for "there was nothing to
judge here", so a build gating on `2` could not tell a package it could not
read from a command it could not parse. `64` is `EX_USAGE` from `sysexits`.
`2` keeps the meaning it has, and nothing else moves.

Every subcommand answers the same way, not only the top level -- `iirds pack`
with no directory, `iirds diff` with one argument -- because argparse builds a
subcommand's parser from the type of its parent, and a test says so rather
than leaving it to a default nobody wrote down. One kind of mistake does not
reach it: `iirds <path>` is shorthand for `iirds all <path>`, so a mistyped
*verb* typed on its own, or with paths after it, is read as a path that is not
there and exits `2` with the name in the message. Typed with that verb's own
options -- `iirds serv --port 8080` -- it leaves `all` an option `all` has
never had, and that is a command line this cannot parse: `64`. That is what
the shorthand costs, and it is pinned rather than left to be found.

A paragraph in these notes had announced it for a release later than this one,
and the front page announced it for this one; the two never agreed, and
neither went out, because 0.6.1 through 0.6.3 were cut from another line. No
release carried the notice: it stood on the front page and in these notes,
contradicting each other, where only somebody reading the repository would
meet it. Stating a breaking change in the release that makes it is what this
file did for the last one, and is what it does here.

**`-W` decided the verdict and left no mark, so the command printed `PASS` and
exited 1 on the same run.** A package with one warning and no errors, checked
with `--warnings-as-errors`, printed `PASS  0 error(s), 1 warning(s)` and
returned 1. Whichever of those a reader believed, the other was lying to them,
and the JSON said `"ok": true` alongside both.

The gate a run was judged by is now a fact the run records: `judgedBy.gate` is
`errors` or `errors+warnings`, `ok` means "no finding at or above that gate",
and the printed headline, the JSON and the exit code are read from the one
place. A `-W` run over a package with warnings now says `FAIL` -- the exit
code has always said so.

`iirds diff` reads it too. Two reports judged by different gates are not
comparable and say which, because a baseline stored by a build that gates on
warnings and a run that does not were never asked the same question. A report written
before this -- by a development build, since no release has ever written this
report shape -- carries no gate; that side reads as "cannot say" rather than as
`errors`, which would make two questions look like one, and it is told to store
a fresh baseline rather than to run both the same way, which its build cannot do.

**The single-file `.pyz` no longer carries pip's record of the machine that
built it.** A build on Python 3.9 and a build on 3.12 now produce the same
bytes, where before they produced two files that differed in four entries on
one and five on the other -- `RECORD` for each bundled dependency, and
`REQUESTED` for each one pip was asked for by name, which is a different set
depending on which dependencies the builder's own Python already satisfies.
Neither is a term the dependency is redistributed under -- every `METADATA`,
every `WHEEL` and every licence file still travels, which is why the
`dist-info` is kept at all -- and both are written by pip about an
installation the archive is not. rdflib 7.6.0's `RECORD` listed a hundred and
fifty paths, six of them the console scripts this build deletes on purpose, so
the archive shipped a list that was false about its own contents and named the
very files removed to make it reproducible. Two builds whose pip wrote
different bookkeeping now give the same bytes; the hash on a release page is
something a rebuild of the tagged commit can be compared against, once the
dependency versions match and neither build set `SOURCE_DATE_EPOCH` -- the two
inputs nobody pins, which `SECURITY.md` names together. `SECURITY.md` and
`docs/offline-install.md` say which reproducibility this is, and the latter
now tells the reader carrying a file across an air gap how to check it against
what was published. **The `.pyz`'s hash therefore moves against the one before
it**: an approval record or a build pinning an older one has to be re-pinned
against this release's, which is on the release page beside the file. Two
entry attributes that came from the building machine are pinned with the
timestamps now, and a dependency that started publishing platform-specific
wheels would stop the build rather than put a compiled file into an archive
that promises none.

**The vendored rule catalogue and the reference corpus move to a newer upstream
commit, and one reading now differs where it did not.** The catalogue and the
132 fixtures beside it are taken from `f1119bea`, retrieved 2026-09-13, instead
of `0bcf19dd`. Between those revisions exactly one rule changed, and only in
which constructs it says it inspects and which fixtures exercise it: M30's
`path` narrowed from `Class, Property, subPropertyOf, subClassOf, domain,
range, domainIncludes, rangeIncludes` to `Class, Property`. No rule was added,
removed, renumbered or reworded, and no verdict this tool gives has changed --
neither field is read by the shipped library at all, and neither is part of the
rule-set digest a report carries, which is the same string under both
revisions. What reads them is the cross-validation tooling in `tools/`.

This project keeps the longer reading -- a statement whose both ends are iiRDS
terms is the standard's schema written out inside a package, which section 7
says a package may not carry -- and `docs/divergences.md` now records that as a
divergence with the specification's sentence behind it, rather than as
agreement. Two fixtures arrived with the move and both are agreed on: the file
that redeclares `iirds:Event` is reported, and the file that subclasses an
iiRDS class into a proprietary namespace is not. Cross-validation therefore
moves by one pair, to 114 with `agree` 43.

**The front page says which surfaces move, and a command says the rest back.**
"What is stable here, and what is not" sits under "Using this validator in
your product": the packaging is not the contract, the verdicts move and every
move is written down here, and then a table of what has held -- the report's
`schemaVersion` and its keys, each exit code, the account that every
registered rule is answered for, the commit the rule catalogue was taken from,
the ontology digests. Every figure in it is what a command printed, written by
`tools/gen_stable_section.py`, while the claim beside each figure and the way
to see it are written out; the two rows that cite `make check` and a test
rather than a command carry no captured output at all. `--check` fails the
build when the page and the commands disagree, and three copies of one
coverage figure in this repository are why a figure on that page is no longer
typed. `tools/extract_catalog.py` grew `--pin`, which answers offline which
commit the committed catalogue came from and fails when that is not the commit
the script pins -- two records of one fact the suite had been holding together
with nothing to ask it from a command line.

**A dropped file could be written outside the directory made for it, on
Windows.** `iirds serve` gives the copy the name the sender chose, minus
anything up to the last separator, and the function that does it has said
since the first release that shipped the page that this means nothing can be
written outside that directory. That was true on one platform. `ntpath.join`
**discards the directory** when the name carries a drive, so a package dropped
as `D:evil.iirds` was written to that drive's working directory, where the
per-request cleanup never saw it again.

What it is not: a way past a trust boundary. What was passed is the directory
this page makes for the request. The page is loopback-only, and a browser
cannot produce such a name from a file chooser on the one platform where a
path join reads it as a drive; what is left is a local process that can reach
the port, which on a machine with one account is already writing as this user.
What broke is a property this project states, which is the thing it sells.

A name a path join would read as more than a name — one carrying a drive, a
Windows device name, a control character — is now replaced whole rather than
repaired. Repairing it would change a verdict: one rule answers a MUST by
reading the container's file name, and the page must not answer differently
from the command line for the same file. The name the sender chose still
reaches the report.

**`iirds diff <report.json> <package>` — what changed since a report you
kept.** The command line could say whether a package is conformant and not
what moved since the last one you signed off. This reads a stored report
against a fresh run and says which rules went from clean to firing, which
stopped, and which each run answered that the other did not -- with the reason
beside it wherever the other side recorded one, and the bare id where the
other side has no record of that rule at all.

It exits 1 when this run has errors the stored report does not, 0 when it does
not, 64 when the command line was the problem, and 2 when it will not read the
stored file -- a sentence on stderr, never a traceback. That keeps the
documented meaning of the codes: 0 clean, 1 errors found, 2 could not run.

Two things it will not do. It does not say a package broke something when the
comparison itself moved underneath: if the two runs were judged by different
builds, different rules, a different command, a different profile or a
different edition, it names each of those with what to do about it and drops
the word "regression" — the change is real and the cause is not attributable.
And it does not let the two sides be judged differently without saying so:
`-W` is taken here as well, because a baseline stored by a run that counts
warnings as failures and a fresh run that does not were never asked the same
question, and every report this release writes records which gate made it.

It reads reports this release writes. An older one is refused with the reason,
and re-validating the package produces a current one.

**A report now says which bytes it judged, and which rule sources ran.** Two
reports about two different files compared without a murmur whenever the two
runs were handed the same path, because the only thing either document said
about the package was the path it was given, and a path is not the bytes. The
container's sha256 and its size are recorded, and they answer one question —
the same bytes or different bytes — and never the identity of a package:
recompressing the same content moves the digest and leaves the verdict where
it was. An unpacked container is not one file and an unreadable path has no
bytes, so both come back null with the reason said beside them rather than as
a digest of nothing.

Beside it, a digest of the rule sources. The rule-set digest is over registered
identities and cannot see a rule's implementation, and `toolVersion` moves
only at a release — over this project's whole history, no commit that changed
a rule file has ever moved it. This is the field that can say the bodies
differ. It is hashed with line endings normalised, so a
Windows checkout and a Linux one of the same release agree, and it is null with
a reason where there are no source files to read, as in the zipapp.

**A container that will not open is reported as `S13`, not `C1`.** The two are
different questions and one id was answering both: `C1` asks whether an
archive that opened gives every entry back, and it was also being reported for
a file that is not an archive at all. That made it invisible to `iirds lint`,
which of the container rules puts only the three the runner asks itself — so a
clean lint report never mentioned it and a broken one did, and a rule that
appears only when it fails has no clean state for anything to compare against.
`S13` is a system rule, so every command that opens a container puts it: clean
when the container opened and firing when it did not. A path that exists and
cannot be read is the exception in the other direction — nothing gets as far
as opening it, `S1` is the one rule answered, and `S13` is named among the
rules that were never put. `C1` keeps its own
meaning. Both claim the same obligation, so the coverage figures do not move;
the rule count goes to 236.

**The machine-readable report is version 2, and a report from an earlier
release cannot be read against a run of this one.** Not one key changed shape;
keys arrived. A report an earlier release has written carries no `judgedBy` at
all, so it cannot say which build made it, which rules ran, or which gate
decided it -- and a comparison that cannot answer those is not a comparison of
the same question. Comparing across it would report a package as having broken
something it never touched, so the version says the two are not comparable
rather than leaving a reader to find out. Re-validating the package produces a
current report; nothing else is needed and nothing is lost.

The machine-readable report also says why every rule it did not answer went
unanswered, whatever command was asked of it. A conformance run says it for
the fourteen lint rules it does not ask -- the interoperability rules less the
two that are marked conformance, which it does ask -- a lint run for every
rule it does not ask, and a container that would not open for every rule it
never put. Before this release a container that would not open named one rule
and was silent about the rest.

The reasons a report can give come to seven. Four of the names are
new -- a rule suspended for a fragment, a rule a directory cannot answer, a
rule that raised, and a rule never put because the container would not open --
and the one that had covered a single rule now covers every rule a command
does not ask. Rules nobody asked for are still not counted among the rules
that did not apply, so the printed line does not grow by them; what it gains
is the reasons it can now name. A lint run no longer shows an unasked rule
under the label for a different profile, and a container that would not open
says how many rules it never put, where it used to say none.

**`--fragment`'s report depended on the hash seed the process started with.**
The rules a snippet cannot satisfy were written into the report in the order a
set produced them, which depends on the hash seed a process starts with: seven
distinct documents across eight seeds, on a tool whose first stated property
is that the same file gives the same verdict byte for byte. Fixed, and the
gate for that property now covers the fragment path, a run of every rule, and
an unpacked container instead of one command on one archive.

**The drop page no longer leaves a copy of what you dropped.** `iirds serve`
writes the package it receives to a file — the alternative is holding a
quarter of a gigabyte in memory for each check running at the time — and moved
that file into a directory it removed. A refused body was removed by the
reader that wrote it, and a request turned away earlier made no copy at all;
what fell between those two owners was left where it lay -- a checker that
raised, which the page catches and answers, so nothing downstream noticed.
Counted on one machine: 1008 of them. The copy now lives in a directory made
for the request and removed before the answer is sent, so by the time the page
shows a verdict it is already gone. SECURITY.md says what is written, where,
why, and when it goes.

**Appendix B's rules had never looked at the content list, and the reason was
another rule.** Their population is the files the metadata declares as XHTML
renditions. Section 8.3.1.1 says the content list MUST NOT be referenced in
the metadata file -- so a package that obeys it never declares the file, and
what is never declared was never read; a package that referenced it anyway had
its content list read as an ordinary rendition, which is the shape `R40` now
reports. Measured: an iiRDS/H package whose `index.html` carries a `<script>`,
a `<form>` and an `<iframe>` — three things appendix B says MUST NOT be used —
drew eight findings, none of them from a content rule.

That file is the one a person opens in a browser, and section 8.3.1.1 also says
it MUST be based on iiRDS XHTML 5. The population now includes it under the
handover profile. No new claim is made: the claims appendix B already carried
now reach the file they were always about. For the period before this, they did
not, and that is what this entry is for.

**The one file in a handover package that nothing may point at, and nothing
said so (R40).** Section 8.3.1.1 requires an iiRDS/H package to carry a content
list as `index.html` in the root, and says of it: "It is not an information
unit and MUST NOT be referenced in the metadata file." The first half was
checked; the second was the reason another rule already had an exception. R37
reports a content file no rendition names and excludes `index.html` from that
population — not as a convenience, but because every conformant handover
package contains exactly one file nothing may name. So the pair is: nobody has
to name it, and nobody may. Only one of the two was enforced.

Whether a source names the content list is decided the way the reader decides
it, so `/index.html`, `./index.html` and `inde%78.html` are the same reference
as `index.html`, and `INDEX.HTML` is not. "Referenced" is read as "named by an
`iirds:source`" — the property section 6.3 gives no rival — rather than as any
value anywhere that spells the path, which would fail a conformant package for
a title. The narrowing is stated in the rule rather than left to be discovered.
Coverage of the standard is 172 of 280, of which 137 are held by a package.

**An obligation this tool enforces was published as one it does not (B8).**
Appendix B.6 says of the safety alert symbol: "The img element MUST be a child
of the signal word panel. Only one safety alert symbol MUST be included." Two
obligations in one sentence, and the requirement index makes a row of each with
the whole sentence written into both — so the two rows said the same thing in
every field the index recorded, until this release gave it the two that tell
them apart. B8 enforces both, with a case for each, and claimed one of
them.

Beside it, a gate for the state that made this invisible: rows the index
cannot tell apart must be claimed alike. It does not decide which answer is
right, and it does not say the rows mean the same thing — they usually do not,
and §8.3.2 states one sentence for the package's product variant and again for
the document's. It forbids the one arrangement nothing recorded can account
for, which is a rule claiming one row while the row beside it, identical in
every field, is counted as uncovered.

**A corrupt archive said which error, not which file (C1).** The finding read
`ZIP archive is corrupt: Error -3 while decompressing data` and named no entry,
on an archive of any size. `Package.testzip` is documented as returning the
name of the first corrupt entry, and it did for one kind of damage: a CRC that
does not match. For the other — a deflate stream that will not decode, which is
what a flipped byte usually makes — the reader raises, and that was caught and
returned in the name's place.

Both kinds of damage are one fact about one file, and the caller asked for a
file. The wrapper now reads the entries itself and returns the name of the
first that will not come back out, whichever way it refuses.

**A package could make a run read `META-INF` until it gave up, and giving up
looked exactly like finding nothing (S12).** Section 7 lets a package carry its
own ontology beside the metadata, and R18 finds it: every entry under
`META-INF/` that the standard does not name is read, parsed as RDF, and kept
only if it attaches something to iiRDS. A signature, a manifest, a readme is
none of that rule's business — which is decided after the file has been read
and parsed, so what a sender pays for is the deciding, not the keeping.

That had no ceiling. Each entry is read to the per-entry limit and the entry
count is whatever the archive says: measured, an archive of a tenth of a
megabyte, holding small files that attach nothing, kept a run busy far longer
than any package in the vendored corpus and finished with an empty report. The
empty report is the part that matters — the run had stopped being an
examination of the package and nothing said so.

Those reads are now counted against a ceiling of eight mebibytes, fifty times
the ontology the standard itself publishes, and past it the scan stops. S12
says that it stopped, names the file it stopped on, and says that whether that
file attaches anything to iiRDS is therefore unanswered. It states no byte
count: the read is bounded by what is left of the ceiling, so the total at the
cut is the ceiling plus one whatever the package holds -- arithmetic rather
than a measurement of anything. What has to be held instead is that the scan
stops, and the test for that counts the reads.

**A stray `iirds:Package` could decide what profile the container was judged
as, and the answer depended on how its IRI sorted (S11).** Which edition and
profile a run applies is read off the package that claims the container. Where
several claim it the run ranks them — newest edition, then whether a profile is
named — and that rank asks *whether* a profile is named, not which one. So two
packages naming different profiles tie, and the tie falls back to the order the
nodes leave the graph.

Measured: a conformant iiRDS/H container, plus one stray `iirds:Package` whose
only content is `iirds:formatRestriction A`, is judged iiRDS/A when the
stray's IRI sorts first and iiRDS/H when it sorts last. The two readings run
different rule sets. The handover rules are most of the difference, present in
the iiRDS/H reading and absent in the iiRDS/A one -- and one container rule
goes the other way, because `C11.1` is declared for the unrestricted and A
profiles while `C11.1H` carries the same obligation for handover, so the A
reading asks one of them and the H reading the other. What matters is not the
size of the difference, which is a function of how large the registry is on
the day, but that the same container is judged against two different sets of
obligations. The stray declares no edition, and a package that declares none
ranks as the newest, deliberately, so saying less cannot drop a rule the
newest edition asks; what it does drop are the two only the earlier editions
ask, `M16.1` and `M16.2` on `iirds:Event`. Here saying less won.

**And an interoperability run said nothing at all about it.** M3 reports that
several packages claim one container, but M3 is a schema rule and a lint run
asks for the lint and system rules, plus the three metadata rules the runner
puts itself — so `iirds lint` on such a container returned `ok=True`, no
findings, and no note, having silently picked one of the two. Every kind set
includes `system`, which is why this rule is one.

It reports rather than resolves, because there is nothing to prefer: A and H
are two values with no order between them, and any rule for picking is a coin
toss the report would print as a fact. A disagreement about the *edition*
alone is not reported — the rank takes the newest, which asks everything a
later edition added; what it lets go are `M16.1` and `M16.2`, the two the
editions before 1.3 ask alone.

**The library said its reading was the checker's, and it is not.**
`iirds.Package.version` takes the first package that declares one; the checker
takes the ranked winner. On a container whose packages disagree the two can
answer differently -- they part whenever the first package to declare a
version is not the one the ranking picks -- which is the whole subject above.
The docstring said "identical to the validator's reading" and now says what it
actually does, and why a library giving the document's first answer is right
for a library.

**The upgrade that leaves no working command is now said on the front page
too.** `pip install -U iirds-validate` from 0.4.2 or earlier ends with every
command gone -- and `pip list` and `pip check` both call the environment
healthy, because from pip's side nothing is missing: 0.5.0 onwards carries no
files of its own, so pip writes the new package's `iirds_validate/` and then
removes the old distribution, deleting every path the two records share. Only
the files the old record never listed survive.

The warning and the one-line repair were already on the compatibility
package's PyPI page, which is the wrong place for half the readers. Somebody
who has already run the upgrade cannot ask the tool anything -- that is the
failure -- so they arrive at the repository, where it stood in the changelog
several releases down and not on the page they land on. The front page and the
compatibility package's page both carry it now, and so does the release-notes
body a version tag lands on; a test holds all three to the same two commands,
because one hazard restated on several surfaces is several things that can
drift.

**Three MUSTs about absolute IRIs that a recommendation was standing in for
(R34, R35, R36).** Section 6.2.1 says it is RECOMMENDED to use absolute IRIs in
`rdf:about`, and M5 reports that as a warning. Three sentences elsewhere in
chapter 6 say MUST, about a named class: an information object (§6.2.2), an
`iirds:IdentityDomain` (§6.8.1) and an `iirds:ClassificationDomain` (§6.8.4).
A package giving one of those a relative IRI breached a MUST, and `iirds check`
answered with a warning whose remedy ended "RECOMMENDED, not required" — and
exited 0.

The sixty-one generated "must have an IRI" rules were right to stop asking for
absoluteness; `docs/divergences.md` records why, and appendix A's `IRI:
REQUIRED` is about having an identifier rather than about its form. What that
entry gave as its reason — "absoluteness is M5's question, and M5 is
RECOMMENDED" — was true of the classes it was measured against and not of
these three. The narrowing stays. The three sentences it was not measured
against are rules now, and the remedy on M5 no longer tells a reader the
standard does not require what it requires.

**And those rules were printing "must have an absolute IRI" while testing
something else.** The check was narrowed and the sentence it prints was not, so
each of the sixty-one told a reader that absoluteness had been tested. A user
acts on the finding, not on the divergence table.

**A relation carrying text where a reference belongs (L16).** In RDF/XML the
two forms differ by one attribute: `<iirds:relates-to-party
rdf:resource="urn:x:party1"/>` points at a party, and
`<iirds:relates-to-party>party1</iirds:relates-to-party>` puts the string
"party1" in the graph and points at nothing. The relation is present, so the
rules asking whether it is there are satisfied, and the rules asking about its
target find a literal and step over it.

Twelve rules already say this about thirteen of the forty-six relations — R10,
R12, M17, M18, M19.4, M22.2, M26, M94 and R19 to R21 and R23 — at MUST level,
M17 as a MUST NOT. Four of them answer a sentence the standard states about
that relation alone: R10's §6.8.2, R12's and M22.2's §6.8.3, M26's §6.9.2. The
others claim nothing, and the code beside them says why: the two selector rows
share one sentence stated once per property, and the sentence naming the class
an identity or classification domain must be carries no keyword at all. L16 is
the same observation across all forty-six: on the thirty-three the standard
states nothing about, it is the only rule that speaks; on the other thirteen
it restates as a warning what a MUST has already reported. Seven of the
thirteen were there when L16 was written; the number is measured rather than
listed, so adding M19.4 and R19 to R21 and R23 moved it by itself. It is a
warning and claims no obligation: `rdfs:range` in RDF is an inference and not
a constraint, and the one general-looking range MUST, section 7.3.3's, is
about a proprietary property complying with the iiRDS property it refines.
Coverage is unchanged, which is the point of keeping "claimed" and "held"
apart.

The rule reads the ontology's own word for what a relation is rather than a
list or a proxy. Every property the standard declares descends from
`iirds:iirdsRelationConcept` or from `iirds:iirdsAttribute`; the two sets are
disjoint and between them they are all of it. `iirds:title` and
`iirds:revision` are attributes and are left alone.

It reports against the edition the package is read as. Only the newest
ontology ships, so the forty-six are the same list whatever a package
declares — but eight of them are absent from iiRDS 1.0 and three from 1.2, and
a name the declared edition does not have is not one of its relations at all.
That is L15's sentence, and L15 reports it.

Over the corpus this repository vendors it finds ten, in nine files. Seven of
the ten are an empty element rather than a misspelt reference, so the rule says
which of the two a reader is looking at: "carries text where a reference
belongs" against "is empty, so it points at nothing", with a different repair
for each. A value with a datatype or a language keeps it in the finding —
`xsd:anyURI` is the one literal form that does carry a resolvable identifier.

**`iirds:ForeseeableMisuse` is no longer reported as a grouping class (L10).**
The ontology marks a class that should not be instantiated directly with a
sentence of its own, and this rule found it by looking for "not int".
`iirds:ForeseeableMisuse` is concrete, and its description is ordinary prose
beginning "Use of a product in a manner **not intended** by the producer or
supplier". The advice was impossible to follow — the class has no subclasses,
so the finding told the reader to retype the instance and could only offer
"define a proprietary subclass".

The marker is now the phrase every spelling shares. The ontology writes the
same sentence four ways — "Not intended", "Not intented", "Not indented" and
"No intended" — so the old substring read two of the four while matching prose
that negates something else; `iirds:iirdsRelationConcept` and
`iirds:relates-to-functional-metadata` were the two it missed. The shapes read
the corrected set from the rule instead of computing it beside it.

**Four sentences that name a class and a property now have both their rules
(R19–R21, R23).** A helper in this codebase says the shape out loud: *"MUST
have an X which is assigned by property P" — the X half. Three sentences of
chapter 6 have this shape and each needs two rules: one to count the property,
one to ask what it points at.* Three is what somebody found by reading.

The sharpest is the document type. A `iirds:Document` with no document type
fails; the same document naming its type as the string "OperatingInstructions"
**passed**. Writing text was better than leaving it out, which is the opposite
of what the sentence says. The other three are not verdict flips — a neighbour
reports those packages for another reason — but the finding a reader saw named
a sentence they had not broken and offered the repair for it.

**Two exemptions were letting real defects through, in both encodings.** A name
in the standard's own namespace that the standard does not define — nobody
mints one by accident — was treated as a pointer at nothing and left to L1.
The reference corpus's own designated counterexample for the document-type
sentence points `iirds:has-document-type` at
`iirds:ThisIsNotAStandardizedDocumentType`, and the rule written to catch a
document type that is not a standardised one was silent on it. And a blank node
with no statements went to L1 too, which looks at IRIs only, so it was reported
by nothing at all.

**Twenty-six appendix rows no validator can reach are named as such.**
Appendix A describes each term in a "Definition:" and a "Description:" cell,
and the specification's own markup calls a word inside many of those an RFC
2119 keyword — MAY and OPTIONAL among them, which bind nobody; the twenty-nine
at issue here are the ones that do bind, the MUSTs, REQUIREDs and SHALLs —
`<em title="REQUIRED in RFC 2119 context" class="rfc2119">` around "REQUIRED"
in "Physical items REQUIRED for the running of a manufacturing production".
Twenty-six of the twenty-nine describe a thing in the world or bind somebody
in it: `RestrictionOnUse` is about how a product may be used,
`ScopeOfDelivery` about what a supplier must deliver "according to the
purchase order". A container can neither satisfy nor breach one. (Twenty-six
markers over fewer sentences — the specification repeats several of these
verbatim between a class and its instance, and each occurrence is counted the
way every other keyword here is.)

They stay in the denominator. Counting them is faithful to the source, and
dropping them would be this project deciding the standard is wrong about its
own markup. What changes is that the coverage report names them instead of
leaving them in the unmapped remainder, where they had been sitting silently.

**An unpacked container no longer reports nine rules it did not run
(`notApplicable` gains `unpacked`).** `iirds check` on a directory reported the
same count as the same package packed -- `194 rules checked` on this build --
and nine of those were the requirements about the ZIP
archive itself — that it is not corrupt, that its name ends `.iirds`, that it
is not encrypted, that a large one uses ZIP64, that the first entry is an
uncompressed `mimetype`, that the container sits at the root of the archive
rather than inside a folder, that every entry is compressed with a method a
bounded read can be made of, that every local file header describes the entry
the central directory describes, and that the central directory carries one
record per entry name. Nine clauses for nine rules: `C1`, `C3`, `S7`, `S8`,
`C6`, `R3`, `S14`, `S10`, `S15`. Each returns at its first line when
there is no archive, and the count was incremented before it ran, so they were
presented as checked and clean.

The runner said so in a note all along, in prose no test read and no consumer of
the JSON report could act on. They are out of the checked count now and named
under a `notApplicable` reason of their own, `unpacked`; the note is written from the
same list, so the sentence and the report cannot disagree. On an unpacked
container the count moves from 194 to 185 and the nine appear where a reader
and a machine both look.

## 0.6.3 — 2026-09-20

**Who should take this release:** anyone running 0.6.2 against packages they
did not build. One rendition this checker could not decompress decided what
every other content rule examined, and a package could come back clean because
of it.

**A legal package that passed on 0.6.2 passes on 0.6.3.** The one verdict this
release moves belongs to a container that will not hand over a file it lists as
content. No rule's reading of the specification changed, and the new rule
carries no specification reference.

**Security. One rendition nobody could decompress decided what every other
content rule examined.** The reader named two reasons a rendition might not be
read -- a compression method it will not decode, and the run's content
ceiling -- and a corrupt deflate stream is neither. It escaped as itself,
killed the rule that had asked, and left a half-filled cache that every later
content rule then walked, each recorded as having answered for the package.
Measured on three renditions with the middle one's compressed data scrambled:
two rules recorded as having raised, a third reporting one file, and an intact
rendition breaking the same rules that nobody opened.

The read failure is a refusal now, like the two with names, so the damaged file
is reported and the sound ones are examined. The list of what a read can fail
with is not this project's to enumerate: the reasons that have a rule of their
own are caught by name, everything else is caught as itself, and the exception
types that mean this code is broken rather than the package are re-raised, so a
defect here cannot be reported as a defect in somebody's delivery.

**What now fails: a package holding a file the container lists as content and
will not hand over.** `ERROR S16` names each one, with the reason beside it.
0.6.2 failed such a package too -- but only when the container was an archive,
because the damage check that holds the verdict there is one of the rules an
unpacked container stands down. The same fault in a build directory was
reported and then demoted to a warning, and the package came back `PASS`,
exit 0. S16 is a system rule: whether a given file is "iiRDS XHTML5 content" is
this project's reading of the entry condition, and content findings are
warnings outside iiRDS/A for that reason, but whether the container will
produce a file it lists is not a reading of anything.

It is deliberately narrow. Where a ceiling stopped the reading, the rule for
that ceiling already says so -- `S9` for the run's content budget -- and an
entry compressed with a method no bounded read can be made of is `S14`, from
0.6.2. A rendition larger on its own than the per-file ceiling is left alone on
purpose: that ceiling is a number this project chose, such a file is legal, and
this release does not turn a legal package's pass into a failure.

**A refusal named the wrong cause, and told the reader to do something that
would not work.** `metadata.rdf` this reader will not decode is refused, and
that is still right -- XML 1.0 requires a processor to support UTF-8 and UTF-16
and nothing else. What was wrong was the sentence beside the refusal: one
explanation for every decode failure, that the bytes were damaged in transit
and the file has to be sent again. It arrives identical. The finding names the
declaration now -- including `utf-8`, where that is what the document says and
the bytes are not, which is the commonest of these in the field -- and the
remedy answers each declaration separately, including one naming a codec this
reader will not use at all. Transcoding such a package to UTF-8 and changing
nothing else turns the verdict into a pass with no findings, which is the
measurement that says the markup was never the problem.

**The check the SDK runs before writing metadata could not tell a language tag
from another.** `write_metadata` writes the graph, reads it back and compares,
and under the condition it tests for it compares by its own fingerprint rather
than by rdflib's isomorphism. That fingerprint rendered every term by lexical
form alone, so `"Getriebe"@en` and `"Getriebe"@de` read back as the same graph,
and so did `<http://example.org/o>` and the string that spells it. Terms are
rendered by what tells them apart now. The round trip preserves all three, so
the guard was weaker than it claimed rather than wrong about any package.

**Coverage of the standard is 131 of 280, of which 94 are held by a package.**
Unchanged by this release: it adds one rule and that rule carries no
specification reference, because what it reports is this run's own business.

**Also:** `read_bounded` performed an unbounded read in the unpacked form when
its budget arrived spent. No shipped caller reaches that arithmetic; the two
container forms disagreeing about a bound is how both size gates were once
silently off for the unpacked one, which is why it is repaired rather than
noted.

## 0.6.2 — 2026-09-18

**Who should take this release:** anyone who checks `.iirds` files they did not
build themselves. Every release up to 0.6.1 can be made to spend far more time
and memory on a container than its size suggests, by a container that says so
in its own records.

**A package that passed on 0.6.1 can fail on 0.6.2**, and that is the repair
rather than a side effect of it. An entry compressed with bzip2 or lzma now
draws `ERROR S14`: those entries cannot be read within a stated limit, so this
release does not open them at all, and an entry nothing will read is worth
saying rather than passing over. If you check packages built by a tool that
uses either method, this release will start refusing them and `iirds pack`
shows what to rebuild them with.

The second new rule changes no verdict. An archive whose central directory
carries one name in more than one record already failed, on C15; `ERROR S15`
now says what the archive does to a reader -- how many records carry the name,
which of them this run resolved it to, and, where they point at different
offsets, that the records describe different bytes. Before, fifty such records
drew forty-nine findings claiming one file collided with itself.

Two new rules, then, and no rule's reading of the specification changed: these
two carry no specification reference at all. The exit codes mean what they
meant.

**Security. A container of no size could make a run decompress without bound.**
The ceiling on how much content one run reads existed and did not hold: each
rendition was read in full and charged for afterwards, and the refusal that
followed was remembered against that one file rather than stopping the run, so
every rendition past the ceiling was read as well. A 49,510-byte archive
declaring forty one-megabyte renditions drew 41,945,847 bytes of decompression
against a two-megabyte ceiling. Past the ceiling a rendition is now refused
without being read. S9 has always said the renditions past the ceiling "were
not examined"; now they have not been.

**Security. An entry a few hundred bytes long could make a run allocate
hundreds of megabytes.** Every limit here bounds what a read hands back. Python
passes the caller's length to the decompressor for deflate and for no other
method; the rest are decompressed whole and the result sliced afterwards, so
the slice obeys the limit and the allocation behind it does not. One 64 KiB
read of an entry declaring 64 MiB allocated 79,898 bytes when stored, 238,399
when deflated, 71,530,984 from a 189-byte bzip2 entry and 79,972,634 from a
9,657-byte lzma one. Lowering `IIRDS_CONTENT_BUDGET` does not reach it, because
the overshoot happens inside one read. Those entries are no longer opened, and
`docs/divergences.md` carries the argument for refusing what the specification
permits, including the alternative that was rejected.

**Security. One entry could be decompressed once per directory record.** A ZIP
central directory is a list of records, not a set of names, and the check that
asks whether the archive is damaged walked the records. An 11,890-byte archive
with fifty records naming one 8 MiB entry made a run decompress 419,431,868
bytes; each repetition costs the sender a 46-byte record. The check walks the
name table now and the same archive costs 8,390,076.

`SECURITY.md` no longer implies that the ceiling bounds what a whole run
decompresses. It cannot: asking whether an archive is damaged means opening
every entry, so a run reads the whole declared size once however small the
ceiling is. That pass asks for a bounded slice at a time and keeps none of it.
The front page said a zip bomb was "refused safely — bounded reads"; that was
true of the two methods it read and not of the two it did not, and it now says
which.

**Coverage of the standard is 131 of 280, of which 94 are held by a package.**
Unchanged by this release: the two rules it adds carry no specification
reference, because neither is a reading of the standard.

## 0.6.1 — 2026-09-11

**Who should take this release:** anyone on 0.6.0 or earlier who checks an
unpacked directory, or points the checker at a directory of packages. Checking
`.iirds` files and nothing else is not affected.

**Security. Checking a directory could have the checker read files outside
it, and quote them.** A directory was listed with a file test that answers for the far
end of a link, so a link to any file the user running the check could read was
listed, read and judged as part of the package. Linked as `mimetype`, any such
file had its first 80 bytes quoted in a finding -- a private key reads back out
of the report. Linked as `META-INF/metadata.rdf`, somebody else's metadata was
judged in place of the package's own, which passed with nothing to say, and
what that file declared went into the report in the field that names it, in a
note and in a finding. The same happened one layer up: a directory of packages
was searched by the same means, so `x.iirds` as a link to any file put that
file's SHA-256 and its size in the report, and a link to somebody else's
package had that package's metadata quoted. S6, which reports any entry that
leaves the container, said nothing about any of it, and `SECURITY.md` has said
since the first release that it does. Every release up to 0.6.0 does this.

What it is not: anything the checker does with an archive. A `.iirds` file
holds bytes -- an entry whose mode marks it as a link is read as the link's
text, and nothing is followed. It takes a directory: one somebody else
prepared, or one an extractor that restores links made out of their archive,
which Info-ZIP `unzip` does. Nothing is written and nothing is extracted, and
the checker could read only what the user running it can read; what could
leave the machine is what a report carries. Until you are on this release,
check the `.iirds` file rather than a directory you did not unpack yourself.

A name is now resolved the way the kernel resolves one: from the container's
root downwards, one component at a time, each link replaced by its own text
where it stands, and never a step outside. Nothing out there is consulted to
decide, so the answer cannot depend on what happens to be there. S6 reports
four things by name, and none of them is read: a link that leads out of the
container, a link written as an absolute path -- which is not how a package
names its own files -- a chain of more links than a system will follow, and a
link that points at nothing. Neither what any of them leads to nor where it is
goes into the report. A link that stays inside reads as before. A directory the
check cannot list is refused by name rather than skipped, because a container
read in part would otherwise be reported as a container with nothing wrong.
Searching a directory of packages refuses a `.iirds` name that leads out of it,
says which, and exits 2. And whether a file somewhere else exists no longer
decides whether a directory is a container at all.

**Breaking, for one shape of input, and said here because the exit codes are a
stable surface.** A directory holding a `.iirds` name that is a link out of it
used to be searched with that link followed, so the run checked the package at
the far end and exited 0 or 1. It now refuses the name, says which, and exits
2. A build that points at a directory of links to packages elsewhere should
name those files instead.

The table in `SECURITY.md` cited, as the proof for S6, a test file that has
never mentioned it; it now cites the two that test it, and a test holds every
row of that table that names a rule to every test file it cites.

**Coverage of the standard is 131 of 280, of which 94 are held by a package.**
Unchanged by this release: it moves no rule and adds none. What it changes is
what a directory may make the checker read.

## 0.6.0 — 2026-09-05

Ten new rules, and a coverage figure that means something it did not mean
before.

**What the checker now reads that it did not.** Section 8.3.2 states six
product-variant sentences twice, once for `iirds:Package` and once for
`iirds:Document`; only the Document half had rules, so a handover package
could omit everything the Package list asks for and pass (R13–R16, one builder
read twice, so the two halves cannot drift). Section 6.8.2's "an X **which is
assigned by** P" was checked for the property and not for the type (R10).
Section 6.8.3's second limb — what a party's `iirds:relates-to-vcard` points
*at* — was unchecked (R12). Appendix A gives `iirds:IdentityDomain` at most one
`iirds:has-identity-type`, and a domain declaring two answered two of section
8.3.2's four questions with one party (R17). Section 7.1 requires a proprietary
extension used in a package to be *in* metadata.rdf, including when it is in a
side ontology under META-INF that section 5.1.1 tells consumers to ignore
(R11, R18). And appendix B forbids scripting in three ways, of which two were
checked: a URL whose scheme is a script is the third (B11).

**Coverage of the standard is 131 of 280, of which 94 are held by a package.**
The last release said 25 of 314. Those numbers moved for three reasons and
they are worth separating. The denominator is the published one now — 280
distinct obligations rather than 314 raw statements. The numerator grew
because the rules did. And fifty of it was there all along: appendix A states,
per class, that instances must have an IRI, and the generated table in
`src/iirds_validate/rules/schema_tables.py` — written *from that appendix* —
had never been told which of its rows each rule was answering. Those fifty are
claimed now, and each one is held by a package that breaks it rather than by a
name that matches. The second figure is the one to weigh. A `covers=` claim used to
be made by reading a sentence and a rule side by side; it is now made by
building the package that breaks the sentence and watching what happens, and
`tests/test_covers_is_earned.py` refuses a claim that has neither a
counterexample nor a place on the unaudited list.

**Two encodings, one answer.** The SHACL shapes and the Python rules are
compared package by package, and that comparison now includes how many
findings each reports: four graph-global checks were reporting one fact once
per participating node in SHACL and once in total in Python, so a consumer
counting errors was told a different number about the same package.

**Fixed.** A vcard reference that pointed at a name from a vocabulary drew two
findings from two rules, one of which told the reader to describe
`iirds:Topic` in their package. A finding from a rule that runs in every
profile announced itself as `iiRDS/H:`. `iirds:identifier` and
`iirds:classificationIdentifier` are declared `rdfs:range rdfs:Literal` by the
ontology and both encodings accepted an IRI in either. Two packages naming
each other as parent left the container with no corresponding
`iirds:Package` and nothing said so.

## 0.5.0 — 2026-09-03

The first release in which the checker and the library ship as one
distribution: `pip install iirds` installs both. The command is `iirds`;
`iirds-validate` and `iirdsv` are kept as aliases of it. The renaming changed
no rule, no rule identifier and not the `source` token a report carries;
three remedies that told a reader to run `iirdsv pack`, or to report a rule
that crashed, now spell the command's name and the issue tracker's address.
Four rules are new. L13, L14 and L15 are warnings: a package that passed
0.4.2 still exits 0 unless `-W` asks warnings to fail the run. S10 is an
error, about an archive no tool writes and one edit produces: it fails a
package only where the archive describes an entry two ways. One rule
reports less: C9 no longer fails an RDF/XML document
written without the `rdf:RDF` element, a form the grammar permits (see
*Fixed*).
The single-file form is `iirds.pyz`. `iirds-validate` and `iirds-sdk` stay on
PyPI as compatibility packages that depend on `iirds` at no less than their
own release — a floor now, where the alias used to pin one exact version, so
a later `pip install -U iirds` never conflicts with them. `iirds-validate`
installs nothing of its own; `iirds-sdk` keeps the `iirds_sdk` module it
published, which re-exports `iirds`. Tools that install by executable, such
as pipx and `uv tool`, want the name that has one: `iirds`.

**Upgrading from `iirds-validate` 0.4.x:** uninstall it first, then install
the new name with `-U` — `pip uninstall -y iirds-validate`, then
`pip install -U iirds`. Without `-U` the `iirds` library already present
satisfies the request and nothing new is installed. The order matters: pip
records each distribution's files separately and does not notice when two
records claim one path, so installing the new name first and uninstalling the
old one afterwards deletes files the new one had just written. If that has
already happened, `pip install --force-reinstall --no-deps iirds` restores
them.

### Added

- **An archive whose two records of an entry disagree is reported (S10).**
  A ZIP describes every entry twice, in a local file header before its data
  and in the central directory at the end. `zipfile` reads the directory,
  so that is the document every rule here judged; a consumer that reads
  the archive as a stream -- libarchive, Java's stream reader, anything
  fed from a pipe -- reads the local header instead, and `unzip` takes the
  checksum and the method from it. Where the two disagreed, this tool
  blessed the entry the directory described and a stream received the one
  the local header described, and nothing said so: seven bytes here, seven
  hundred there, every existing rule silent. S10 reads the local header
  where the directory says it is and reports the entry whose name, method,
  encryption or data-descriptor flag, crc-32 or sizes differ between the
  two records -- from the local header, or from the data descriptor it
  defers to -- and the entry whose data, as the directory describes it,
  runs into the next entry's header or the directory itself. What writers
  legitimately do differently is not a disagreement: the extra fields and
  timestamps, a data descriptor with or without its signature, ZIP64 sizes
  in an extra field or in an eight-byte descriptor, an archive with
  something prepended. The archives Python's stream writer, ZIP64 and a
  prefixed stub produce are the rule's negatives and stay silent, as do
  the Consortium's own sample packages.

- **A namespace that is nearly, but not, an iiRDS namespace is reported
  (L14).** `iirds/` for `iirds#`, `https` for `http`, `www.` in front: to
  every consumer a different vocabulary, so every name under it resolved to
  nothing -- and the package was reported as a set of proprietary classes
  not linked into iiRDS and a container declaring no package. True, and the
  wrong place to look. The finding names the namespace once, says how many
  names sit under it and how many of them the standard has, and which
  namespace was meant. Written the way the standard's own prose writes it,
  without the `#` -- so that every name runs into the namespace,
  `iirdsPackage` -- the namespace is reported as written and the names
  under it decide which one was meant, since by letters `handover#` is as
  near to `.../domain/machinery` as `machinery#` is; where several of the
  standard's namespaces begin with the one written -- the host alone, or
  `.../domain/` -- the names under it pick the one that defines them, and
  where none does all are offered rather than the shortest. `iirds#/` --
  one character past the separator -- is this finding, not eight unknown
  names under a namespace a prefix test
  took for the standard's; and the standard's host or vocabulary IRI on its
  own is not a name under anything. Anything on the standard's own host
  that is not one of its four namespaces is reported whatever its distance;
  the nearest legitimate foreign namespace in the reference corpus, read
  off the corpus in the test, scores below 0.6 against a line at 0.85.

- **The report says which layer a problem is in.** Metadata that names no
  iiRDS name at all -- the namespace misspelled, or a document that is not
  about iiRDS -- gets one note before every other, saying so and naming the
  namespace to check, before the findings that describe the absence and
  before the note that no version was declared, which is true of such a
  package and the wrong thing to read first. The footer's "21 not
  applicable" now says for what: "19 for iiRDS/H, 2 for other editions", or
  on a handover package "1 for packages that are not iiRDS/H"; `-v` lists
  them by rule, and `--format json` carries them under `notApplicable`.
  Read off the rules, not typed, and worded in the standard's profile names.

- **A name from a later edition of iiRDS than the package declares is
  reported (L15).** Only the newest ontology ships, so every package is
  judged against the 1.3 vocabulary whatever it declares: a package
  declaring 1.0 that uses `iirds:is-based-on` (1.3) passed every rule,
  since the standard does define the name -- and a consumer reading the
  package as 1.0 has no definition for it. The finding names the edition
  the name arrived in, once per name; forty-six names arrived after 1.0,
  fifteen in 1.1, eleven in 1.2, twenty in 1.3, and every one is pinned
  as an anachronism against a 1.0 declaration. The names are held to the
  edition the run validates against -- the declared one, or the one
  `--iirds-version` asked for, as with every version-scoped rule -- and
  the detail says which when they differ. A domain name is named with its
  domain: `Operation` is a core name since 1.0 and a handover name since
  1.3, and the finding about the second does not read as a claim about
  the first. The per-edition inventory, read off the Consortium's
  published schemas by `tools/version_inventory.py`, moves into the
  package for this, from `docs/`; no edition has ever dropped a name,
  which is what makes "defined from 1.2 on" one edition rather than a
  list, and a test holds the newest edition's list to the bundled
  vocabulary. A name no edition has stays L13's. What the rule cannot see
  is a value that is a literal: the profile `H`, which 1.3 introduced, is
  declared as one.

- **A name in the iiRDS namespace that the standard does not define is
  reported (L13).** The namespace was trusted and the name never was:
  `is_iirds_term` tests a prefix, and no rule asked the bundled vocabulary
  whether the name behind an arbitrary iiRDS IRI exists. So
  `iirds:relates-to-componnet`, a class spelled `iirds:Componentt` beside a
  real one, and a document type the
  standard does not have all passed every rule, in the standard's own
  namespace, where a consumer has the least reason to doubt them -- and
  found no class, no property and no label when it looked them up. The
  finding names the term once however often it occurs and, where a defined
  term is close enough, says which one was probably meant, as the whole IRI:
  the commonest case is not a misspelling but a term the standard defines in
  one of its domain vocabularies, named in core. The suggestion is measured:
  every defined term, mutated the ways names get mutated, is answered with
  the original or with nothing, never with another term -- a test holds
  that -- and the remedy fits the position the name stood in.

  A warning, not an error, on purpose. Fifty-one files of the reference
  corpus -- seven of them fixtures the catalogue marks as passing -- name
  `iirds:EnvironmentalProtectionInstruction` in core, where the standard
  defines it under machinery, and the 1.3 specification's own Example 53
  writes `iirds:vdi2770` for `VDI2770`. Whether section 7 forbids that is a question
  for the standard's editors, recorded in `docs/divergences.md`; the two
  sample packages the iiRDS Consortium publishes name nothing this rule
  reports.

### Fixed

- **A metadata.rdf written without the `rdf:RDF` element was rejected
  (C9).** The RDF 1.1 XML grammar, which the obligation C9 covers cites,
  lets a document start with `rdf:RDF` or with a single node element (§7.2.1;
  §2.6: "the rdf:RDF can be omitted although any XML namespaces must still be
  declared"). A file whose one top-level element was the package itself --
  three statements to every RDF parser, and the shape most of the standard's
  own examples are written in (with the namespace declarations the examples
  leave out) -- was reported as not an RDF document, with a remedy claiming
  no parser would read a statement from it. The rule now judges by
  the grammar: the document element is `rdf:RDF`, or its name is an absolute
  IRI outside the eleven names the grammar reserves. `<manual>` is still not
  RDF/XML -- a name with no namespace is not an IRI -- and says so with a
  remedy that is true.

- **Findings that only followed from a document not being RDF/XML were
  reported as the package's own.** rdflib reads `<manual>` as a class named
  `manual`, and the graph rules ran on that: "declares no iirds:Package",
  "proprietary class not linked into iiRDS" -- every finding true, every
  one a consequence of C9, and the note beside them said the graph rules
  could not run. The reader now refuses a document the grammar does not
  define, judged on the bytes it parses -- after the byte order mark has
  been honoured, so a UTF-16 or UTF-32 `<manual>` is refused like a UTF-8
  one -- and the report is C9 and S2, with the reader's reason in S2's
  detail. The same holds where the XML itself did not parse -- S2 says no
  metadata was usable, and "declares no iirds:Package" no longer fires on
  the empty graph beside it. `lint`, which runs no container rule, reports
  C9 the way it reports a parse failure, so a package nobody could read no
  longer lints clean. A document element the grammar reserves (`rdf:li`)
  is C9 as well, named as such, rather than a parse error in rdflib's
  words.

- **Links on the PyPI page led nowhere.** The README is the PyPI page too,
  and its nineteen links into the repository were relative -- `docs/scope.md`
  -- which PyPI resolves against itself, to a 404. They are absolute now,
  held so by a test, which also refuses a link to a file that is no longer
  where the link says.

- **Which package the version and the profile were read off.** That pair
  chooses the ontology and the applicable rules, so reading it from the wrong
  node changes what "valid" means for the whole run — before any rule runs.

  A package typed with a subclass it declares itself was not seen as a package
  at all, so it had no version and no profile, and every handover rule stood
  down: a package that fails one of them was reported clean. Section 7 permits
  exactly that typing and asks a consumer to treat the instance as its parent
  class, which the rules themselves already do.

  A package *inside* the package set the container's profile — a nested child
  declaring the handover profile switched seventeen handover MUSTs on against
  a container that never claimed to be one. That holds however deep the
  nesting goes: where a document carries a child and its parent but not the
  grandparent, the root of what is present answers, not whichever package
  sorts first.

  And the answer changed between runs. Graph order is not stable across
  processes, so the same bytes were judged against two different rule sets
  depending on the run. The version and the profile were also accumulated
  separately, so a run could answer with a pair no package in the container
  had ever declared. Both properties now come off one package, chosen under a
  fixed order.

- **Two blank nodes that said different things could be given one name.** The
  name is a digest of what the node says, and the digest joined its parts with
  a separator — so a value holding that separator and the text of a plausible
  neighbour spelled the end of its own field. Two packages then tied, and a
  tie left them in graph order, which is the order the naming exists to
  escape. The digest also left blank-node objects out entirely, so a package
  reaching a blank node and a package reaching nothing were one name too. A
  report could complain of two packages and name one of them twice.

- **A package declared part of itself claimed the exemption meant for nested
  children.** §6.3 says the package representing the enclosing container must
  not be the subject of `iirds:has-rendition`, and a package inside another
  package is exempt because it is content. That exemption was granted on the
  bare presence of `iirds:is-part-of-package`, so adding one triple pointing
  at the package's own identifier made the finding disappear — a MUST NOT
  switched off by a statement that cannot be true. §6.2 draws the line with a
  word: the container's instance must not be a member of *another* package.
  A package is a nested child when it is part of a different one now, and the
  same reading gives M3 back the case it was missing, where a self-looping
  package sits beside a genuine container.

  A parent has to be one. The exemption was granted on the bare presence of
  `iirds:is-part-of-package`, so an IRI nothing describes, a node typed
  `iirds:Topic`, a plain literal or an anonymous blank node each bought it —
  and one of those beside the self-loop re-opened the bypass the paragraph
  above closes. §6.3.3 asks the nested child's package to "reference exactly
  one `iirds:Package`", and both of its MUSTs are scoped to the parent
  container's own `metadata.rdf`, where the parent is required to exist. So a
  package is a nested child when it is part of a different package this graph
  describes as one. `docs/divergences.md` carries the reading, what it costs,
  and the fact that it reverses what that file said one release ago.

  M8's shape follows the same reading and stays SHACL Core. Core cannot
  compare a value node with the focus node it hangs off, but it does not need
  to: the value nodes of a zero-or-one path are the focus node and its direct
  parents, they are a set so a self-loop does not double them, and counting
  the Packages among them says "there is a Package-valued parent other than
  me". M3 reads the same predicate and moved with it.

- **L7 took its exemption away from the packages that use section 7.** A
  package is exempt from "every information unit should have a title", and the
  exemption was claimed by comparing types — so a package typed with a
  subclass it declares itself lost it and was reported for having no title,
  while the published shapes stayed silent.

- **L11 could not find the file every other rule found.** It reports a file
  named `.xhtml` that no content rule examined, and it resolved
  `iirds:source` its own way, so a spelling the other rules resolve was, to
  L11, a name matching no entry. It went quiet on exactly the packages it
  exists for.

- **A nesting chain, a cycle and a package inside itself are reported.** §6.3.3
  says the package a child names as its parent "MUST NOT have any outgoing
  `iirds:is-part-of-package` relations" — nesting in the parent container's
  metadata is one level deep. No rule here implemented that sentence and the
  reference catalogue has none for it, so all three shapes read as ordinary
  nesting and drew nothing. **R5** says it, under the id of the requirement,
  gated to 1.3 because that is the only edition on hand that carries §6.3.3.

- **A document that declares a nested package may not describe that package's
  content.** §5.3 carries two prohibitions on what a container may say about
  a package nested inside it, and both were recorded as checkable and
  unchecked. **R6** implements the second one. Its finding is compelled under
  every reading of an ambiguous document, which is what lets it be reported
  without deciding which container is in hand: read the file as the parent's
  and §5.3 is broken; read it as the nested child's own and §6.2 is broken
  instead, because a package's own instance must not be a member of *another*
  package; read it as describing a pair held somewhere else and §5.1.1 is,
  which gives `META-INF` to "metadata on the iiRDS package and its contents"
  exclusively. The shape is SHACL Core: keeping a package that names *itself*
  out of the nested set means comparing a value node with the focus node,
  which Core cannot do — but it can count instead, and two Packages among the
  values of a zero-or-one path is exactly "a Package parent other than me".

  **What it does not see.** R6 reports one triple pattern: a subject that is
  not a package, naming a package this document declares nested. A parent that
  copies the child's units into its own metadata and omits those relations is
  describing the child's content and draws nothing. The rest of §5.3's
  sentence stays uncovered rather than approximated, and `docs/divergences.md`
  says so. R6 is also version-gated to 1.3, the only edition on hand carrying
  the sentence, so a 1.1 or 1.2 document with the same defect passes in
  silence; what is known about those editions is that they had the nesting
  mechanism, not that they carried this prohibition.

- **A container that says it is inside another package is reported.** §6.2:
  "The corresponding `iirds:Package` instance of an iiRDS package MUST NOT be
  a member of another iiRDS package expressed by the property
  `iirds:is-part-of-package`." The sentence stands word for word since 1.0 and
  no rule here claimed it, so the commonest spelling of the nesting defect —
  a child container handed over on its own, still naming the parent it was
  packed inside — passed with **no findings at all**. **R7** reports it, on
  every edition. A package whose named parent is described in the same
  metadata is a nested child declared the way §6.3.3 asks and stays silent;
  so does a package naming itself, which is not another package and which R5
  already reports under the sentence that names that shape.

- **A declared nested package that is not in the archive is reported.** §6.3.3:
  "All nested iiRDS containers MUST be included side by side in the iiRDS ZIP
  archive of the highest level iiRDS package." **R8** is the one nesting
  question the metadata cannot answer and the archive can, and it needs no
  decision about which container is in hand either: a document declaring a
  nested package while the archive carries none is broken under the parent's
  reading (§6.3.3) and under the child's (§5.3). The evidence is §5.2's own
  description of an iiRDS ZIP archive, read out of the first local header —
  the file name alone is not the test, because a file called `nested.iirds`
  holding any sixteen bytes would otherwise answer it and read as evidence.
  The cost of one reading of "highest level" is named in
  `docs/divergences.md`.

- **A handover package that nests is refused.** Two sentences said it and no
  rule claimed either: "an iiRDS/H package MUST NOT contain another iiRDS ZIP
  archive" (§8.3.1.2) and "iiRDS/H packages MUST use this variant of hierarchy
  formation and MUST NOT contain nested packages" (§6.7.3). **R9** reports
  both sides this validator can see — a nested container in the archive, and a
  nested package declared in the metadata — because a package can breach
  either alone. Unrestricted packages are untouched: §8.3.1.2 opens by
  permitting nesting for them by name.
  193 rules, 142 SHACL shapes. Coverage of the standard: 25 of 314.

- **The sentence no single container can decide is recorded as such.** The
  other §5.3 prohibition — a nested package must not carry metadata about the
  outer one — cannot be decided from the metadata of one container. Its
  antecedent is "a nested iiRDS package", and §6.2 says a conformant package's
  own instance is not a member of *another* package, so a document declaring
  itself nested is either the child breaching that sentence or a parent
  describing its child, and the metadata does not distinguish them. Other
  sentences weigh without settling it — §6.3 says the enclosing package is the
  subject of no rendition, which is the rule M8 — and so does the archive. It
  moves to a second recorded-with-a-reason list, kept apart from the one for
  obligations addressed to reading applications so that "hard to check"
  cannot hide inside "not about the package". Neither list counts toward
  coverage and both are gated. Coverage of the standard: 21 of 314.

- **A hand-edited sentence in the published requirement index passed the whole
  suite.** `docs/requirements.json` is the enumeration the coverage figure is
  a fraction of and the thing every rule's `covers=` points at, so a wrong
  sentence there misattributes an obligation rather than merely reading badly.
  The re-derivation compared ids and counts and not the sentences, and the
  test named "the index records the fingerprint of its source" measured that
  fingerprint's *length* and compared it with nothing — so the index could
  name a source it had not been built from, which is the one thing a
  fingerprint is for. Both are closed, and both forgeries now fail. Because
  the specification is not redistributable and CI has no copy, `make check`
  refuses to skip these when the cache is absent, the way it already refuses
  to skip the differential gate.

- **`iirds serve` — a drop page on the machine you are already on.** The
  report has only ever existed as text on a terminal, and the people who build
  iiRDS packages are technical writers rather than people who read one. This
  serves one page on the loopback interface, takes a dropped `.iirds`, and
  shows the verdict `iirds <path>` would have printed. Literally that string:
  the handler calls the same renderer on the same report object in the same
  process, so there is no second implementation to keep in step and nothing to
  prove agreement about. Three things differ by construction and are now
  stated wherever the claim is: the page renders into a string and so never
  carries terminal colour; where a finding quotes the container's own path it
  quotes the handler's copy; and on Windows the command line's line endings
  are the platform's while the page's are `\n` — which the equivalence test
  found on a machine none of the reading had happened on. Flags — `-v`, `-q`, `-W`, `--format json`,
  `--fragment`, directories, several packages — belong to the command line.

  It refuses to bind to any address that is not loopback, refuses a POST that
  came from another page, logs nothing by default because a request line
  carries the name of somebody's document, and serves exactly one path.
  (An earlier version of this entry said the stdlib's default handler would
  have served the working directory. It would not: `BaseHTTPRequestHandler`
  has no `do_GET` at all — that is `SimpleHTTPRequestHandler`, which this
  deliberately is not. Without the check the page simply answers everywhere,
  which is a lie about what is there rather than a disclosure.)
  The name the browser sends is
  carried through verbatim, because the rule about the `.iirds` extension
  reads the container's file name and a handler that renamed the copy would
  decide that rule for every package it was handed.

- **The drop page speaks five languages and has a light/dark switch, and its
  parts live in one folder.** English, German, Korean, Japanese and Chinese
  for the page's own words, following the browser until the reader chooses;
  system, light or dark following the operating system until the reader
  disagrees with it; both remembered in that browser and nowhere else. **The
  report is not translated** — it is the command line's output word for word,
  and each language says so in its own words rather than leaving a reader to
  work it out. `data/web/` holds the page, the stylesheet, the script and the
  strings; they are assembled into the single response at request time, so
  splitting them for editing did not add a path to the server.

- **Fixed in the drop page, found by review**: a body whose declared multipart
  boundary appears nowhere in it crashed the request thread and printed a
  traceback — reachable from any page the reader had open, because that
  content type needs no preflight; a POST from another origin was answered
  instead of refused; a lying `Content-Length` parked a thread for ever with
  nothing to reap it; the upload limit bounded the body and not the memory,
  where the parse costs about eleven times what it reads; the policy header
  permitted inline code in general instead of naming this page's own; the
  banner volunteered the version; and a name whose trailing space matters
  reached the extension rule stripped — the page passed a package the command
  line fails, from the transport's own tidying rather than from the document.

- **A report died halfway through on a console that could not show one of its
  characters.** The remedy lines are marked with an arrow, and writing U+2192
  to a stream encoded in a legacy code page raises rather than degrades — so
  on a Windows machine outside an English locale the report stopped at the
  first remedy, mid-run, with a traceback where the rest of the findings
  should have been. The exit code was still 1, so a build reading only that
  saw nothing wrong, and a redirected report was silently truncated. The
  marker is now chosen by what the stream can encode: the arrow where it can
  be shown, two characters where it cannot. Reproduced with
  `PYTHONIOENCODING=cp1252` before it was fixed.

- **A dropped file no longer costs the process eleven times its size.** The
  upload was read whole and handed to a MIME parser that copied it several
  times over; measured, a sixteen-megabyte body moved the process's peak by
  a hundred and eighty. The body is streamed to disk as it arrives now, the
  part headers read and then the payload copied chunk by chunk up to the
  closing boundary — which can straddle two chunks, so a tail the length of
  the delimiter is held back from each flush and the scanner is tested at
  every offset around the chunk edge, byte for byte. The same body now moves
  the peak by one megabyte. The upload limit, which had been lowered to
  thirty-two megabytes as a bandage over the parse, is back at a quarter
  gigabyte.

- **The drop page checks a bounded number of files at once.** A thread per
  request with nothing above it: measured, thirty-two posts left forty-six
  threads standing, each a whole validation run. The same-origin check keeps
  other pages out, but the page's own reader can drop a folder of files, and
  a folder is not an attack. Four run at a time now and the rest wait for a
  slot — their bodies are already on disk, which is cheap, and the reader
  asked for them. A checker that crashes gives its slot back, which is stated
  as a test rather than trusted: the quiet alternative was one bad drop
  eating a slot for the life of the process.

- **A rendition is decompressed once per run, and a run states a ceiling on
  what it will decompress in total.** Measured: one rendition was read four
  times — once to refuse or accept it, once to parse it, and the same pair
  again by a second rule, because the bytes were never kept after the first
  look. Forty one-megabyte renditions in an archive that compresses to
  nothing made the run read a hundred and sixty megabytes. The bytes are
  memoised on the run now, and per-entry limits are joined by a total —
  half a gigabyte by default, `IIRDS_CONTENT_BUDGET` to change it. **S9**
  reports the first rendition the ceiling stopped at, with the numbers, and
  says that the renditions from there on were not examined; a report that
  fell silent on them would have read as a pass. 194 rules.

### Changed

- **Where two packages both represent the container, the one declaring the
  newer version answers.** M3 reports the pair either way, so the package does
  not pass — what the choice decided was whether the *other* defects in it
  were looked for, and taking whichever sorted first let a package declaring
  1.0 win an alphabetical tie-break and stand every 1.1+ rule down. A plain
  §6.3 violation beside it went unreported. A package declaring nothing ranks
  as the newest, because that is already what a missing version means.

- **A package declaring two versions is judged against the newest of them**,
  not the lowest. M4 reports the pair either way; what the newer reading keeps
  is the finding. A 1.3 package breaking a 1.1+ MUST could otherwise silence
  that finding by declaring 1.0 beside its own version, and a missing version
  already falls back to the newest for the same reason — nothing passes by
  silence. Versions are compared as numbers rather than as text.

- **L2 says which of three silences it met.** A source naming somewhere
  outside the container, one naming nothing, and one climbing out of the
  package are different things, and all three were reported as "escapes the
  package root". L2 now stays quiet about the first — that is M9's finding,
  and it is not a path that went wrong — and names the other two.

- One vendored fixture is now reported with no declared version instead of
  `1.0`. Its first package deliberately omits the property — its own comment
  says so — and the `1.0` came from a second package beside it. The findings
  are the same at either version.

### Fixed in the library

- **`pack()` refused to run under the convention it exists to support.**
  `SOURCE_DATE_EPOCH=0` is the commonest value a reproducible build is given,
  and a ZIP cannot carry a date before 1980, so the packer raised instead of
  packing. A value large enough for `OverflowError` escaped the guard
  entirely and reached the archive as a year in the millions. The stamp is
  clamped to what the format can hold, which keeps the promise the variable
  makes — two builds of one tree agree — where refusing kept nothing.

- **A metadata document was refused on a size nobody had measured.** The gate
  read the uncompressed size out of the ZIP directory, which is written by
  whoever built the archive: a few hundred bytes could be announced as a
  gigabyte and turned away, and the message named a limit and a length that
  had never been read. The read is bounded and the bytes are counted now, and
  where the directory disagrees with what is there the refusal says that
  instead — a directory that does not describe its contents is the defect,
  not an oversized document.

- **Writing the metadata for an ordinary manual took most of a minute, and
  nearly all of it was the self-check.** The bytes are parsed back and
  compared against the graph they came from, which is what makes the write
  trustworthy; the comparison asked rdflib whether the two graphs were
  isomorphic, and that is priced for the general case. iiRDS nests a
  rendition inside every information unit, so a few hundred topics is a few
  hundred blank nodes: doubling the topic count multiplied the time by four
  to six, reaching about forty-three seconds at eight hundred topics — by
  which point the check was ninety-seven per cent of what writing cost.

  Where the blank nodes form a forest — none shared, none in a cycle, which
  is every metadata document in the vendored corpus — the same answer comes
  from naming each blank node by a digest of the subtree hanging off it and
  comparing the triples with those digests standing in for the labels. Under
  that condition the two comparisons agree by construction, and where it does
  not hold the graph goes to the general check unchanged. The self-check is
  not weakened and is not optional; the same eight hundred topics now write
  in well under a second.

- **`iirds:source` is now read as the URL §6.3 calls it.** That section says
  twice, normatively, that the property relates a rendition "to the URL of
  the physical file" and that "the URL MUST be relative to the root folder".
  Read as a literal path instead, a file named `a b.xhtml` and referred to
  as `a%20b.xhtml` answered "no such entry" while sitting right there. The
  value is now percent-decoded and its fragment and query cut before it is
  matched.

  This is a choice, not a fact: Appendix A calls the same value a "relative
  path of a file" with range `rdfs:Literal`, and §5.1.3 permits `%` and `#`
  in a file name — so a package naming a file `a%20b.xhtml` or `a#b.xhtml`
  is entitled to, and this reading cannot reach it. `iirds-validate`'s
  `docs/divergences.md` carries the evidence on both sides, and tests here
  record the cost rather than leaving it to be discovered.

  §5.1.3 settles the cheaper half outright: a colon may not appear in a file
  name, so a value still holding one after decoding names nothing in this
  container. `http://…`, `mailto:…` and `urn:uuid:…` answer `None` instead of
  a path assembled out of the URL. `open()` now distinguishes the three
  silences that answer `None` — no source, an empty one, and one naming
  something that is not an entry here — instead of reporting a missing
  declaration that is not missing.

  `source_of()` resolves case for case with `iirds-validate`, which the
  docstring claimed while several readings differed.

- **`pack()` could write a package `open()` refuses.** The check for metadata
  asked the filesystem, and a case-insensitive one answers yes for a file
  spelled another way; the archive then carried the spelling from disk, which
  a reader looking for the name the standard gives does not find. The question
  is put to the names about to be written instead.

- **A file whose name was stored decomposed did not match the metadata that
  refers to it.** Several tools create names in that form, and the RDF beside
  them is composed, so one file had two byte strings and a lookup by the name
  in the metadata missed it. Members are stored composed; two names that would
  collide once composed are refused rather than silently reduced to one.

- **A failed pack destroyed the package it was replacing.** The archive was
  opened for writing before anything had been read, so a failure part-way
  through left the part already written — and that remainder is not obviously
  broken: it carries a central directory, passes an integrity check, opens,
  and reports its version while missing most of its content. It is written
  beside the destination now and moved into place only once it is whole.

- **A symbolic link in the packed directory put bytes from outside the
  package into the delivery.** `is_file()` answers for the far end of a link,
  so whatever it pointed at was read and written into the archive, quietly. A
  link to a directory was the same silence facing the other way: the walk does
  not descend through one, so a folder present in the source was absent from
  the package. Links are refused now, naming the ones found — following or
  skipping are both decisions about the delivery that belong to its author.

- **The dependency allowlist swept one directory, not the package.** The
  check that keeps this package's third-party dependencies down to rdflib
  walked `src/iirds/*.py`, which reaches every module only because the
  package is one flat directory today. The first subpackage would have
  carried any import at all past the allowlist with nothing to say so. It
  walks the tree now, and the walk itself is tested against a tree that has a
  subpackage, which the real one does not.

### Changed in the library

- **`parse_metadata` refuses a well-formed XML document that is not
  RDF/XML.** The grammar's document starts with `rdf:RDF` or with a single
  node element (RDF 1.1 XML Syntax §7.2.1, §2.6); rdflib reads anything
  else -- `<manual>`, an element in a namespace that is not an IRI, a root
  the grammar reserves -- into a graph nobody wrote. The reader now returns
  `(None, "<name>: not an RDF/XML document: <why>")`, judged on the decoded
  bytes so that the encoding cannot hide the document element, and
  `Package.parse_errors` and `metadata_sources` say so; `Package.graph`
  raises as it does for every refusal. The category is exported as
  `NOT_RDFXML`, the judgement as `is_rdfxml_document_element()`, and the
  scheme test both use as `is_absolute_name()`. A validator built on the
  library reports the same document the same way this one does.

- **A warning from this package's own code fails the suite.** Warnings were
  collected and printed at the end of a run, where one that means something
  is indistinguishable from the eleven that do not. They are errors now, with
  one exception scoped to rdflib, whose JSON-LD parser warns about its own
  deprecated internals on every parse — scoped to where the warning comes
  from rather than to its wording, so the dependency rephrasing its message
  does not turn this suite red. Expected failures are strict and unregistered
  marks are refused, both for the same reason: a test that silently applies
  to nothing is worse than no test. The settings are checked by tests that
  provoke the behaviour, because a configuration table is the one part of a
  suite that nothing else exercises.

## 0.4.2 — 2026-08-26

### Security

- **A JSON-LD `@context` could send the reader outside the package.** The
  refusal is the reader's and arrives with `iirds` 0.3.1; this release
  carries the reporting half — C16.2 stops calling a refused document
  invalid, SECURITY.md states the threat, and a version-gated test watches a
  package fail to reach anything outside its own container.

### Added

- **Three rules.** R4 reports an iiRDS/H party pointing at a vCard the package
  never describes — five MUSTs about naming an organisation deliberately stay
  quiet about that pointer so it does not arrive five times, and it used to be
  left to a rule outside the conformance run, so a handover package whose
  manufacturer, author and creator all pointed at nothing passed in silence.
  B9 reports a hazard statement with no signal word. B10 reports, as a
  warning, a hazard statement at caution, warning or danger level where no
  image is tagged as the safety alert symbol. 185 rules to 188.

### Changed

- **A file the container is judged to contain is now a file the content rules
  read.** Two layers resolved `iirds:source` separately and disagreed, so one
  value could be present to the rule that reports missing files and absent to
  the rules that would open it — a topic carrying a script drew no finding at
  all, while a reader holding the same package opened the file without
  trouble. One resolution answers for both. It follows the specification in
  calling the value a URL, so percent-encoding means what it says; it folds
  backslashes, because that is what a reader does with them; and it no longer
  reads `//content/a.xhtml` as naming a host called `content`, which had been
  resolving that value to a different file.

- **A document that described an entity declaration is no longer refused for
  making one.** The refusal matched the token anywhere in the bytes, and the
  grammar allows a declaration in one place only, so a topic explaining XML
  syntax -- an ordinary file in a documentation standard -- was turned away,
  and under iiRDS/A that is an error. The question is now put to the parser,
  which decides the encoding without being told and knows where a declaration
  may sit. A doctype naming an external DTD passes: nothing fetches it, so
  nothing can expand. docs/divergences.md carries both readings.

- **Rules about a class now see the subclasses a package declares**, where
  Appendix A says instances of that class need an IRI. Section 7 permits such
  a subclass and requires a consumer to process the instance as the parent, so
  a package could put an anonymous instance past a rule by naming its own
  type. Fifty-six rules changed population; the five whose classes the
  specification never asks for an IRI did not. M15.11a and M19.4 changed the
  same way. A package that passed 0.4.1 can report new findings for this
  reason.

- **M25 checks that a level closes**, not merely that the property is present:
  a last node pointing at something that is neither another directory node nor
  a terminator left the list open and passed. It also stops reporting the
  terminator itself when a package declares one.

- **The same package now produces the same report, every run.** It did not.
  A blank node has no identifier of its own -- the one it appears to have is
  minted afresh each time the file is read -- and three places let that reach
  the page: the fallback name for an unlabelled node, the digest meant to
  replace it, and rules that listed values or walked references in whatever
  order the store offered. One of the Consortium's own sample packages gave
  three different reports from three runs of 0.4.1, and two rules named a
  different real thing each time. A blank node is named from what it says
  now, nested nodes included, and every listing that reaches a report is
  ordered by that name. Details that mentioned a blank node will read
  differently from 0.4.1, and identically to each other.

### Fixed

- **One rule could produce a finding per element with nothing bounding the
  listing.** 20,000 repetitions of one violation in a 51 KB archive made
  17 MB of JSON and 143 MB resident. Findings now enter a report through
  one gateway that lists at most 100 per rule and counts all of them, so
  the summary, `ok` and the exit code are exactly what they were; the
  report and the JSON say how many were left out.

- The container boundary joins the parse boundary: an entry name whose bytes
  are not the encoding its flag declares raised out of `zipfile` and ended the
  run with a traceback. It is a C1 finding now, like every other way an
  archive can be unusable.
- A reader that breaks its contract no longer ends a run before any rule has
  looked at the package. This project declares a dependency floor rather than
  a pin, so it will be paired with readers it was never tested against.
- Eleven remedies named terms the standard does not have — six machinery
  classes spelled `iirds:` rather than `iirdsMch:`, `iirds:relates-to-Party`
  for `relates-to-party`, a handover property that does not exist, and a
  relation that never existed. A gate resolves every iiRDS term a remedy names.
- M2.6's remedy asked authors to write what its own shape rejects, reported
  from outside in this project's first issue. The constraint is unchanged and
  the open question is recorded in `docs/divergences.md`.
- C16.1, C16.2 and S3 stop describing the wrong failure: a refused document is
  not invalid syntax, and a rule that crashed is not a metadata parse error.

## 0.4.1 — 2026-08-25

- **The `iirds` dependency loses its upper bound** (`>=0.2.0,<0.3` →
  `>=0.2.0`). The cap was reflexive 0.x caution against a dependency
  this project authors, releases and tests in the same breath, and it
  contradicted the SDK's own published promise that what it publishes is
  intended not to break. Worse, it split one shared container layer in
  two: nobody could install this validator and the SDK's newer features
  together. An upper bound on a library is a prediction that pip cannot
  recover from when it turns out wrong; the honest moment to add one is
  when an incompatibility is known, not before. Only 0.2-era API is used
  here, the pair is exercised on every push, and CI still runs the floor
  (`iirds==0.2.0`) exactly. No behaviour changes.

## 0.4.0 — 2026-08-24

- **The container layer is shared with the [`iirds`](https://github.com/dev365code/iirds)
  SDK, in both directions.** `pack()` moved to the SDK (same bytes, same
  refusals — the eleven packing tests pass against it unedited), and the
  metadata reader — the hardening guards, the parser, the
  isomorphic-once merge — is imported back from it, so the SDK's answer
  can never contradict the validator's. The seam is pinned by object
  identity, not equality: a fork of either side fails loudly. Two
  runtime dependencies now, both pure Python: rdflib and
  `iirds>=0.2.0,<0.3`, each exercised at its floor in CI.
- **Both size gates were disabled for directory packages.**
  `DirectoryPackage.info()` answered `None`, so a 64 MiB+ document that
  an archive refuses was read and parsed whole in the
  check-before-you-zip form — and neither gate, in either form, had
  ever been observed firing by any test. Four tests now watch both;
  this entry records the silent pass.
- The section-7 class closure's data half is now literally the SDK's
  `subclasses_of`: "the SDK's answer is a subset of the validator's"
  became a property of the code rather than a claim about it.
- The `.pyz` build script reads its bundle list from `pyproject.toml`
  instead of hard-coding it, and the smoke test proves self-containment
  for every bundled dependency (887 KB with the SDK inside).
- The CLI's pack error wording is owned by the CLI: the SDK speaks API
  ("pass overwrite=True"), the terminal speaks flags ("pass
  --overwrite"), and the boundary translates.
- **The offline claim became a gate**: CI seals the network at the
  socket layer and runs every rule against a real container; "touches
  no network" is now enforced, not asserted.
- Four spec links on dcterms-backed rules stopped quoting a sentence
  about the wrong class.

## 0.3.0 — 2026-08-22

- **The five deferred iiRDS/H MUSTs land as shapes** (M15.7b, M15.7d,
  M15.8–M15.10): the named-party chains, softenings included — a party
  whose vCard the package does not describe passes (the dangling
  reference is L1's finding, once), a described-but-nameless vCard fails.
  138 shapes; the deferred bucket is down to the six long-exemption lint
  rules. The differential gate caught a SPARQL scoping trap on the way in
  (a UNION branch evaluates independently, so a filter-only branch saw
  its variable unbound) — recorded in the generator's comments.
- The `ivs:`/`ivm:` namespaces resolve through w3id.org permalinks
  (perma-id/w3id.org#6584).
- **A package shipping both metadata serialisations no longer double-counts
  its blank nodes**: two isomorphic sources now merge as one graph, so an
  inline IdentityDomain is one domain, not "2 domains". Genuinely divergent
  sources still union — their disagreement is L9's finding, and hiding
  either side would hide the evidence. Found before release, where the
  single-file SHACL shapes were the side that was right.
- **`--fragment`**: validate a bare metadata file — a spec example, a
  snippet under an editor's hands — inside a throwaway container, with the
  four rules a fragment cannot satisfy (M3, M4, L2, S6) suspended and named
  in a note. The wrapping this project offered the specification's CI in
  iirds-consortium/specification#34, shipped as a flag.

## 0.2.0 — 2026-08-21

- **SHACL shapes** (`shapes/`): 133 shapes for iiRDS 1.3 — the
  language-neutral encoding of the rules, generated from the same sources,
  differentially tested against the Python validator — fire-set equality
  over the entire reference corpus, severity equality on every mutant
  and provocation fixture — with a closing check that every emitted shape fires somewhere
  in the suite. Single-file
  `iirds-complete.ttl` / `iirds-handover-complete.ttl` forms for the pySHACL
  command line; remedy text, severity, spec link, `ivm:ruleId` and
  `ivm:versions` on every shape, node and property shapes alike; graph-global
  checks name the offending node in `sh:value` where one exists ("no
  package is declared" has none — that one result points at the shape's
  own IRI, the engine's convention for a nodeless failure). The 52 rules without a shape
  are accounted for by category in the README and manifest — 38 that no RDF
  graph can express, 11 deferred (five iiRDS/H MUSTs among them, named), 2
  out of edition, 1 no-op. Answers iirds-consortium/models#24.
- **iiRDS §7 fixes in the validator itself, found by the shapes gate**:
  instances typed with a package-declared subclass of an iiRDS class are now
  seen by every rule — including two (M15.5, M22.2) that had private
  exact-typing tests bypassing the shared closure. SHACL's `sh:targetClass`
  had these semantics by definition; the differential gate refused to let
  the two encodings differ, and the Python side was the one corrected. The
  seventeen nodekind rules M78–M94 also shed titles that were accidentally
  the ontology's description prose, for constraint-describing ones.
- Interpretation choices, where prose underdetermines a rule, remain
  documented in [docs/divergences.md](docs/divergences.md).
- pySHACL rides as a dev-only extra (`.[shacl]`); the runtime stays
  rdflib-only and the `.pyz` is unchanged.

## 0.1.0 — 2026-08-20

First public release.

### What it does

- `check` (conformance), `lint` (interoperability), `all`, `pack`, `rules`;
  JSON output; CI-friendly exit codes (`0` clean, warnings alone stay `0`
  unless `-W`; `1` errors; `2` could not run).
- **185 rules**: all 157 of the reference catalogue, plus 28 of this project's
  own — 8 content rules for iiRDS XHTML5 (Appendix B, checked by no other
  tool), 12 interoperability rules, 5 system guards, and 3 rules (R1–R3) for
  specification requirements the catalogue has no identifier for.
- Graph-based: RDF/XML and JSON-LD parse into one graph, so results do not
  depend on how the metadata was serialised. Deterministic output, ordered
  for a reader: causes first, consequences last.
- Every finding carries a remedy — what to change, where it goes, and what a
  consumer loses without it.
- Fully offline: iiRDS 1.0–1.3 term inventories and the 1.3 ontologies
  bundled verbatim and hash-verified; remote JSON-LD contexts refused; XML
  entity declarations refused; hostile archives (zip-slip, oversized
  metadata) rejected. Ships as a reproducible single-file `.pyz`.
- Profile-aware severity: the Appendix B content rules are errors under
  iiRDS/A and warnings elsewhere, because outside A the standard permits any
  content and "which files count as iiRDS XHTML5" is this project's reading.
- iiRDS 1.0, 1.0.1, 1.1, 1.2, 1.3; unrestricted, A and H profiles. An
  undeclared version falls back to the newest *and says so*; an unpublished
  version or profile is a finding, not a silent default.

### What was found while building it

The evidence lives in the repository rather than in this file: the regression
tests cover every defect the apparatus caught in its own rules — including a
rule that was backwards from the day it was written and one no input could
reach — and
[docs/divergences.md](docs/divergences.md) records every disagreement with the
reference implementation, with the specification text beside each. Seven of
the catalogue's version arrays were corrected against the Consortium's own
published schemas. Both of the Consortium's official sample packages fail
their own specification; every error this tool reports on them survived
verification against the 1.0 text they declare.

### Known limits

Coverage of the standard itself is measured and small: the specification
states 314 absolute obligations, and the mapping from those to rules has only
begun (`tools/requirement_coverage.py` prints the honest number). "No
findings" is not "certified conformant" — nothing can certify that, and this
tool says so rather than implying otherwise.
