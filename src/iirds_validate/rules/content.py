"""Content rules (B*) — iiRDS XHTML5, Appendix B of the specification.

Twenty-five absolute requirements live in Appendix B, and until now nothing
checked any of them. Not this project, and not the reference tool, whose rules
all operate on `META-INF/metadata.rdf` and never open a content file. A package
can therefore pass every conformance check in existence while its content
carries scripts, forms and iframes that the standard forbids outright.

That gap matters most for the profile that made this project necessary. A
handover package is opened years later by whoever inherited the machine, in a
viewer nobody chose in advance. "The metadata is well-formed" says nothing
about whether the documents inside can be rendered.

Which files get checked is decided by the metadata rather than by extension: a
rendition whose `iirds:format` is `application/xhtml+xml` is content the
package itself claims is iiRDS XHTML5.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
import xml.parsers.expat as expat

from iirds import UnreadableMethod

from .. import terms as T
from ..model import Violation
from ..package import ContentBudgetExceeded, entry_named
from ..registry import rule
from .container import CONTENT_LIST

XHTML_FORMAT = "application/xhtml+xml"

#: Content arrives from a supplier just as metadata does, and the guard that
#: refuses entity declarations was only ever applied to metadata. A few hundred
#: bytes of nested entities in a content file expanded to gigabytes and the
#: report came back clean — a silent pass, which is the failure this project
#: exists to remove.
MAX_CONTENT_BYTES = 64 * 1024 * 1024
XHTML_NS = "{http://www.w3.org/1999/xhtml}"


class _Declared(Exception):
    """An entity declaration reached the parser."""


class _RootReached(Exception):
    """The prolog is over, and nothing after it can declare an entity."""


def _declares_entities(raw: bytes) -> bool:
    """Whether the parser will be handed declarations to expand.

    Asked of the parser, not of the bytes. A pattern over bytes has to decide
    the encoding for itself and then agree with the parser about it, and the
    two did not: a declaration written UTF-16 walked past a pattern that
    matches UTF-8. It also has to know where the grammar permits a
    declaration, and it did not: the token appearing in a CDATA section or in
    a comment was read as the thing itself, so a topic *about* XML syntax was
    refused -- which in a documentation standard is an ordinary file, and
    under iiRDS/A an error that fails the package.

    expat settles both, being the thing that would do the expanding. The
    handler fires when a declaration is read and before any reference to it
    is expanded, so raising there is early enough: the billion-laughs shape
    is refused in microseconds where an unguarded parse of the same bytes
    runs for seconds and grows with the nesting.

    Stopped at the root element. Declarations live in the DTD, the DTD
    precedes the root, and an external one is not fetched -- so the prolog
    answers the question and the body is never read here. An external DTD
    therefore passes: it declares nothing this parser will see, and if a
    parser ever did go and get one, that is the offline promise's business
    and has its own rule.
    """
    parser = expat.ParserCreate()
    parser.EntityDeclHandler = lambda *_args: _raise(_Declared)
    parser.StartElementHandler = lambda *_args: _raise(_RootReached)
    try:
        parser.Parse(raw, True)
    except _Declared:
        return True
    except _RootReached:
        return False
    except Exception:
        # Whatever else the parser refuses the prolog with is not this guard's
        # finding: B1 parses the document itself and reports what the parser
        # said about it. Named `ExpatError` alone until a document declaring
        # an encoding Python does not know raised `LookupError` from here --
        # outside every handler in `_walk`, so the rule that asked died and
        # the cache it was filling was left truncated for all the others. The
        # ways a prolog can fail are the parser's list, not ours.
        return False
    return False


def _raise(exception):
    raise exception()


#: B.5.1 to B.5.9. The complete set, transcribed from the specification rather
#: than from an HTML5 reference — iiRDS XHTML5 is a subset and the difference
#: is the point.
ALLOWED_ELEMENTS = frozenset((
    "html",                                                            # B.5.1
    "head", "title", "link",                                           # B.5.2
    "body", "h1", "h2", "h3", "h4", "h5", "h6", "section",             # B.5.3
    "dd", "div", "dl", "dt", "figcaption", "figure",                   # B.5.4
    "li", "ol", "p", "pre", "ul",
    "a", "abbr", "b", "bdi", "bdo", "br", "code", "em", "i", "kbd",    # B.5.5
    "q", "s", "samp", "small", "span", "strong", "sub", "sup", "u", "wbr",
    "area", "audio", "img", "map", "source", "track", "video",         # B.5.6
    "ins", "del",                                                      # B.5.8
    "caption", "col", "colgroup", "table", "tbody", "td",              # B.5.9
    "tfoot", "th", "thead", "tr",
))

#: B.5.7 and B.5.10. Named separately from "not in the allowed set" so the
#: finding can say which prohibition was broken.
FORBIDDEN = {
    "script": "B.5.7: scripting must not be used",
    "noscript": "B.5.7: scripting must not be used",
    "form": "B.5.10: forms must not be used",
    "input": "B.5.10: forms must not be used",
    "button": "B.5.10: forms must not be used",
    "select": "B.5.10: forms must not be used",
    "option": "B.5.10: forms must not be used",
    "textarea": "B.5.10: forms must not be used",
    "fieldset": "B.5.10: forms must not be used",
    "label": "B.5.10: forms must not be used",
    "svg": "B.5.11: svg, math and iframe must not be used",
    "math": "B.5.11: svg, math and iframe must not be used",
    "iframe": "B.5.11: svg, math and iframe must not be used",
}

#: B.6, the hazard statement table. Each value belongs on one element.
DATA_ROLE_ELEMENTS = {
    "caution": "div", "warning": "div", "danger": "div", "notice": "div",
    "signalword-panel": "div", "signalword": "p",
    "symbol-panel": "div", "message-panel": "div",
    "safety-alert-symbol": "img",
}

_EVENT_ATTRIBUTE = re.compile(r"^on[a-z]+$", re.I)


def _media_type(value) -> str:
    """The media type without its parameters.

    `application/xhtml+xml; charset=utf-8` is the same media type as
    `application/xhtml+xml`, and comparing the whole literal meant one legal
    parameter switched off every rule in this file.
    """
    return str(value).split(";")[0].strip().lower()


def _xhtml_renditions(ctx):
    """Files the package itself declares to be iiRDS XHTML5."""
    return _renditions_declared_as(ctx, XHTML_FORMAT)


def _renditions_declared_as(ctx, media_type=None):
    """Files the package itself declares to be of `media_type`, present in it;
    with no type, every file a rendition names.

    One walk for every format a rule asks about. The first two callers were
    B6 for XHTML and R41 for PDF, and the reason for keeping it one is the
    comment below: two readers of what a source names is how a file came to
    be present to one rule and absent to another.
    """
    seen = set()
    for rendition in ctx.instances_of(T.Rendition):
        declared = [_media_type(f) for f in ctx.values(rendition, T.fmt)]
        # A type ending in "/" names the whole family: "video/" is every video
        # subtype, which is what "video content" means -- `video/webm` is the
        # case the section's .mp4 sentence exists for.
        if media_type is None:
            pass
        elif media_type.endswith("/"):
            if not any(d.startswith(media_type) for d in declared):
                continue
        elif media_type not in declared:
            continue
        for source in ctx.values(rendition, T.source):
            # The container layer decides what a source names, for every rule
            # that asks. Deciding it here as well is how a file came to be
            # present to L2 and absent to these.
            name = entry_named(str(source))
            if name and name not in seen and ctx.package.has(name):
                seen.add(name)
                yield name


#: The shapes a defect in this project takes. A read that fails because the
#: archive is wrong is the package's business and is reported per file; a read
#: that fails because this code is wrong has to reach the runner, which reports
#: it as a rule that raised. Measured: with these swallowed, injecting one typo
#: into `Package.charge` turned two errors into two warnings and an answered
#: rule, and the suite's "no rule crashes" guard had nothing left to see.
_OUR_FAULT = (NameError, AttributeError, TypeError, IndexError, KeyError,
              ImportError, RecursionError)


def _unexamined(ctx, name, reason):
    """Record a file the package lists as content that no content rule parsed.

    S16 reports what is in here. Two refusals stay out because a rule of their
    own already names the fault at error severity: the run's total is S9's and
    a compression method no bounded read can be made of is S14's. That is the
    rule, and it is narrower than "whatever no other rule names" -- S9 names
    the one rendition the run stopped at and says the rest were not examined
    without naming them, and this stays silent about those too, because one
    ceiling reached is one fault with one remedy.

    B1 names these files too, where they are renditions, and is not one of
    those two: outside iiRDS/A it is a warning, which is the whole reason this
    record exists, and under iiRDS/A it is an error that this repeats.

    Not here: a document handed to a parser as a document and rejected by it.
    That is the document's own defect, B1 reports it, and what severity it
    carries is the profile's business.
    """
    ctx.__dict__.setdefault("content_unexamined", {})[name] = reason


def _bytes_of(ctx, name):
    """The rendition's bytes, and why they were not read if they were not.

    Measured before this existed: one rendition was decompressed four times
    in a run -- B1 read it to refuse or accept it and again to parse it, and
    the tree cache B2 draws from did the same pair over. The bytes are kept
    on the context after the first read, so every later question about a
    rendition is answered from memory already paid for.

    The second value used to be a flag meaning "over the per-file limit", and
    both refusals were reported with that one sentence. It is a reason now
    because two of them are not that: a run that has reached its total does
    not read this file at all, and saying it was too big is a claim about a
    file nobody looked at -- which sends the reader of B1 to shrink something
    that may be a few hundred bytes.
    """
    memo = ctx.__dict__.get("_content_bytes")
    if memo is None:
        memo = ctx.__dict__["_content_bytes"] = {}
    if name not in memo:
        spent = ctx.__dict__.get("content_budget")
        if spent is not None:
            # The ceiling has already been passed, and reading this one to
            # find out by how much is the amplification the ceiling exists to
            # refuse. What must not happen is the read, not the charge: the
            # old order read the file in full and charged for it afterwards,
            # so a package of no size on disk declaring forty megabytes made
            # a run decompress all forty against a two megabyte ceiling --
            # the refusal was per file and the reading went on.
            memo[name] = (b"", "not read: the run had already reached its "
                               "%d byte content budget" % spent[1])
            return memo[name]
        try:
            raw, oversize = ctx.package.read_bounded(name, MAX_CONTENT_BYTES)
            ctx.package.charge(len(raw))
            if oversize:
                reason = "over the %d byte limit uncompressed" % MAX_CONTENT_BYTES
                memo[name] = (raw, reason)
                # This ceiling is a number this project chose and the file
                # is legal, so nothing but B1 said anything and the package
                # passed outside iiRDS/A with a rendition nobody had parsed.
                # The number is still ours; that the file never reached a
                # parser is not a reading of anything.
                _unexamined(ctx, name, reason)
            else:
                memo[name] = (raw, None)
        except UnreadableMethod as exc:
            # S14 reports the entry and says why. B1 says the same thing in
            # its own place, because a reader looking at a rendition wants to
            # know there why it was not parsed.
            memo[name] = (b"", "not read: %s" % exc)
        except ContentBudgetExceeded as exc:
            # The one read allowed to cross the ceiling, and it cannot be
            # avoided: what a file costs is not knowable without reading it,
            # and that read is bounded by the per-file limit above. So what
            # the content rules read is the budget plus one per-file limit,
            # once -- a statement about reading, not about memory, and not
            # about the run: C1's damage check opens every entry and pays no
            # budget. Recorded where S9 reads it and where the branch above
            # sees it.
            ctx.__dict__["content_budget"] = (exc.read_so_far, exc.limit, name)
            memo[name] = (b"", "reading this took the run past its %d byte "
                               "content budget" % exc.limit)
        except _OUR_FAULT:
            # A name that is not defined, an attribute that is not there, an
            # argument of the wrong type: not ways an archive can be wrong,
            # ways this code can be. Turning one into "the rendition could not
            # be read" hides it twice -- the rule is recorded as answered, and
            # outside iiRDS/A the finding is demoted to a warning, so a run
            # that should have failed with `S3 rule B1 raised` comes back
            # clean. What a package can do to a read is not our list to keep;
            # what our own defects look like is.
            raise
        except Exception as exc:
            # Anything else, and that list is not ours: `zlib.error` for a
            # stream that will not decode, whatever a future `zipfile` raises
            # for an entry it cannot hand over. Before this, such a failure
            # left `_bytes_of`, killed the rule that asked, and left `_walk`'s
            # cache half filled, so every later content rule walked a
            # truncated file set and was recorded as having answered.
            reason = "not read: %s" % (exc if str(exc) else type(exc).__name__)
            memo[name] = (b"", reason)
            # Kept apart from the refusals above that a rule of their own
            # already names at error severity: the run's total is S9's, a
            # method no bounded read can be made of is S14's. What is left
            # here is the container failing to hand over a file it lists, and
            # in the unpacked form, where C1 does not run, nothing else
            # reports it at all.
            _unexamined(ctx, name, reason)
    return memo[name]


def _refusal(ctx, name):
    """Why this file will not be parsed, or None."""
    # The same reasoning as the metadata gate: the declared size belongs to
    # the sender, so the limit is on what is read rather than on what is
    # claimed, and one read answers both questions.
    raw, refused = _bytes_of(ctx, name)
    if refused:
        return refused
    if _declares_entities(raw):
        # Read whole and then not parsed, on what the document says rather
        # than on anything the container did -- so it is the one refusal here
        # that is not a read failure, and it lands in the same place for the
        # same reason: no rule that needs a parsed document gets one here.
        reason = "the document declares XML entities"
        _unexamined(ctx, name, reason)
        return reason
    return None


def _iirds_xhtml_files(ctx):
    """The files appendix B is about: what the metadata declares, and the
    content list.

    The second half is not a declaration and cannot be one. Section 8.3.1.1
    requires an iiRDS/H package to carry `index.html` in the root, says it
    MUST be based on iiRDS XHTML 5, and says it MUST NOT be referenced in the
    metadata file -- so it is never a declared rendition, and for as long as
    this population was "what the metadata declares" no rule here had ever
    read it. Measured: a content list carrying a script, a form and an iframe
    -- three things appendix B says MUST NOT be used -- drew eight findings
    and not one from a content rule.

    The prohibition made the blind spot, which is worth stating plainly: the
    sentence that keeps a package conformant was the reason the checker
    stopped looking at part of it.

    Only under the handover profile. Elsewhere `index.html` is an ordinary
    file with an ordinary name, and an ordinary file is content when the
    metadata says so -- which is the rule that was already here.
    """
    yield from _xhtml_renditions(ctx)
    if ctx.variant == "H" and ctx.package.has(CONTENT_LIST):
        yield CONTENT_LIST


def _walk(ctx):
    """Every iiRDS XHTML file, parsed — once per run, not once per rule.

    Eight B rules each iterated the same files, so every content document was
    read and parsed eight times; on large packages that was a third of the
    whole run. The parse result is cached on the Context, which lives exactly
    as long as one validation. Rules only read the tree, so sharing it is
    safe; if one ever mutates it, that rule must copy first.
    """
    cache = ctx.__dict__.get("_content_trees")
    if cache is None:
        # Built in a local and installed when it is complete. Installing it
        # first and filling it afterwards meant that anything escaping the loop
        # left a half-filled cache on the context: the rule that asked died,
        # and every rule after it found a non-empty cache, walked a truncated
        # file set, and was recorded as having answered for the package.
        # Repairing one escape route is not repairing that -- a rendition
        # declaring an encoding Python does not know raises `LookupError` out
        # of `fromstring`, no monkeypatching required, and the population was
        # truncated again.
        built = {}
        for name in sorted(set(_iirds_xhtml_files(ctx))):
            if _refusal(ctx, name):
                continue
            try:
                built[name] = ElementTree.fromstring(_bytes_of(ctx, name)[0])
            except Exception:
                # A document that will not parse is one this rule has nothing
                # to say about; B1 is where "it did not parse" is reported, and
                # it reads the same bytes. The exception type is not the point
                # and enumerating it is how this went wrong twice.
                continue
        cache = ctx.__dict__["_content_trees"] = built
    yield from cache.items()


def _local(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


@rule("B1", covers=("b-3-conformance-criteria#2",), kind="content", prio="MUST", versions=(), variants=(),
      title="iiRDS XHTML5 content must be a well-formed XML document",
       fix="Open the file in an XML parser and fix the syntax it rejects. iiRDS XHTML5 is XML, not HTML: every element needs a closing tag, `<br>` must be `<br/>`, and a bare `&` must be written `&amp;`.")
def b1_well_formed(ctx):
    """B.3: "It MUST be a well-formed XML document."

    First because nothing else here can run otherwise, and because a content
    file that does not parse is a delivery a consumer cannot open at all.
    """
    for name in sorted(_xhtml_renditions(ctx)):
        refused = _refusal(ctx, name)
        if refused:
            # Its own remedy: nothing here is a syntax error, so a reader sent
            # to an XML parser would find the file perfectly well-formed.
            yield Violation("content declared as iiRDS XHTML5 was refused rather than parsed",
                            subject=name, detail=refused,
                            fix="The reason is printed as this finding's detail, and it is "
                                "what to act on -- not the file's syntax, which nothing here "
                                "has looked at. A file turned away for what it declares -- XML "
                                "entities -- is fixed by removing the declarations and every "
                                "reference to them together: remove the declarations alone and "
                                "the references are left defined by nothing, which is a document "
                                "that still does not parse. One turned away for "
                                "its own size asks for a smaller rendition; one turned away "
                                "because the run had already spent what it will decompress in "
                                "total is answered by `IIRDS_CONTENT_BUDGET`, which sets that "
                                "total. One whose entry this tool cannot decompress at all is "
                                "reported beside this by S14 and is fixed by rebuilding the "
                                "entry with deflate. One the container will not give back at "
                                "all is named beside this by S16, and what repairs it depends "
                                "on which container: a damaged entry in an archive is what C1 "
                                "reports and a rebuild repairs, while an unpacked container "
                                "has no C1 and the usual cause is a mode bit on the file. "
                                "Those are the reasons seen so far rather than all there can be, which is "
                                "why the detail is the thing to read. Whichever it is, the "
                                "file was turned away before it was parsed, so there is no "
                                "syntax error in it to find: an XML parser would open it and a "
                                "consumer applying the same guard will not.")
            continue
        try:
            ElementTree.fromstring(_bytes_of(ctx, name)[0])
        except Exception as exc:
            # Every way the parser can decline the document, not the one this
            # named: a declaration naming an encoding Python does not know
            # raises `LookupError` here, which left B1 recorded as raised and
            # said nothing about the file. The message carries the type where
            # it is not a syntax error, because "not well-formed" would be a
            # claim about markup nobody parsed.
            # And the message says which, because the comment above is only
            # true if it does: a document whose declaration names a codec
            # nobody has is refused before a character of its markup is read,
            # and "not well-formed" sent the reader hunting a syntax error
            # that is not there. The rule's own remedy is about syntax, so
            # that case carries one of its own.
            if isinstance(exc, ElementTree.ParseError):
                yield Violation("content declared as iiRDS XHTML5 is not well-formed XML",
                                subject=name, detail=str(exc))
            else:
                yield Violation("content declared as iiRDS XHTML5 could not be parsed, "
                                "and not because of its markup",
                                subject=name,
                                detail="%s: %s" % (type(exc).__name__, exc),
                                fix="Read the error beside this; the markup was never "
                                    "reached. An encoding the declaration names and this "
                                    "reader does not have is the common one -- write the "
                                    "file as UTF-8 and say so in the declaration, which "
                                    "is what XML assumes when nothing is declared. There "
                                    "is no syntax error to look for: a parser given the "
                                    "same file stops in the same place.")


@rule("B2", covers=("b-3-conformance-criteria#4", "b-5-10-forms#1", "b-5-11-svg-mathml-and-iframes#1", "b-5-7-scripting#1",), kind="content", prio="MUST NOT", versions=(), variants=(),
      title="scripting, forms, svg, math and iframes must not be used",
       fix="Delete the element. These carry behaviour rather than content, so a consumer that strips them for safety renders a topic with a hole in it. Express the same thing as text, a table, or an image.")
def b2_forbidden_elements(ctx):
    for name, root in _walk(ctx):
        for element in root.iter():
            tag = _local(element.tag)
            if tag in FORBIDDEN:
                yield Violation("<%s> is forbidden in iiRDS XHTML5" % tag,
                                subject=name, detail=FORBIDDEN[tag])


@rule("B3", covers=("b-3-conformance-criteria#4",), kind="content", prio="MUST", versions=(), variants=(),
      title="only the elements iiRDS XHTML5 lists may be used",
       fix="Replace the element with one Appendix B lists. If it carries meaning no listed element expresses, put that meaning in the metadata graph instead, where a consumer can act on it.")
def b3_only_listed_elements(ctx):
    """B.3: "It MUST use only iiRDS-compliant HTML elements listed in this
    specification." Elements with their own prohibition are B2's."""
    for name, root in _walk(ctx):
        reported = set()
        for element in root.iter():
            tag = _local(element.tag)
            if not tag or tag in ALLOWED_ELEMENTS or tag in FORBIDDEN or tag in reported:
                continue
            reported.add(tag)
            yield Violation("<%s> is not part of iiRDS XHTML5" % tag, subject=name)


@rule("B4", covers=("b-5-7-scripting#1",), kind="content", prio="MUST NOT", versions=(), variants=(),
      title="event handler attributes are scripting",
       fix="Remove the attribute. Event handlers are scripting written as markup, so a consumer that blocks scripts keeps the attribute and drops the behaviour, leaving a control that looks live and is not.")
def b4_no_event_handlers(ctx):
    """B.5.7 again, by the other route. `onclick` is scripting without a
    `<script>` element, and a consumer that strips scripts would keep it.

    Deliberately the only attribute rule here. The specification lists six
    permitted global attributes, but tekom's own sample packages carry `type`
    on `<link>`, which appears in neither that list nor any element-specific
    table — so a strict attribute whitelist would fail the standard's own
    examples. The prohibition on scripting is not ambiguous in the same way.
    """
    for name, root in _walk(ctx):
        for element in root.iter():
            for attribute in element.attrib:
                if _EVENT_ATTRIBUTE.match(_local(attribute)):
                    yield Violation("event handler attribute %s is scripting" % attribute,
                                    subject=name, detail="<%s>" % _local(element.tag))


#: Attributes whose value a consumer resolves as a URL. Deliberately short:
#: these are the ones that navigate or load in XHTML content, and the point is
#: the scheme, not an inventory of attributes.
_URL_ATTRIBUTES = ("href", "src", "action", "formaction", "data", "poster",
                   "cite", "longdesc")

#: The two schemes that are a script rather than a location. `data:` is
#: deliberately absent: a data URL is a document, and whether an embedded
#: document counts as scripting is a question B.5.7 does not answer, so
#: reporting it would be this project inventing a prohibition.
_SCRIPT_SCHEMES = ("javascript:", "vbscript:")


def _url_scheme_text(value: str) -> str:
    """The value as the URL parser sees it: ASCII whitespace and C0 controls
    removed, lowercased.

    HTML's URL parser strips tab, newline and carriage return from anywhere in
    a URL before resolving it, so `java&#9;script:` is a value that runs. A
    check on the literal text would pass exactly the values a prohibition
    exists to catch, which is worse than no check: it reports the careless and
    clears the deliberate.
    """
    return "".join(ch for ch in value if ord(ch) > 0x20).lower()


@rule("B11", covers=("b-5-7-scripting#1",), kind="content", prio="MUST NOT",
      versions=(), variants=(),
      title="a URL whose scheme is a script is scripting",
       fix="Replace the URL with a real location, or remove the link. B.5.7 forbids scripting, and a javascript: URL is a script that happens to be written where an address goes — a consumer that blocks scripts is left with a control that looks live and does nothing.")
def b11_no_scripting_urls(ctx):
    """B.5.7 by its third route.

    The element list (B2) sees `<script>`; the attribute names (B4) see
    `onclick`. Neither can see this one, because `<a href>` is as ordinary as
    markup gets and only the value says what happens. The sentence prohibits
    scripting, not a spelling of it.

    Scoped to the scheme, so the letters alone are not the test. Technical
    documentation writes *about* javascript: URLs, and a rule that reported the
    word would fire on the prose explaining why it is forbidden.
    """
    for name, root in _walk(ctx):
        for element in root.iter():
            for attribute, value in sorted(element.attrib.items()):
                if _local(attribute) not in _URL_ATTRIBUTES:
                    continue
                text = _url_scheme_text(value)
                if text.startswith(_SCRIPT_SCHEMES):
                    yield Violation(
                        "%s is a script, not a location, and B.5.7 forbids scripting"
                        % attribute, subject=name,
                        detail="<%s %s=\"%s\">" % (_local(element.tag), attribute,
                                                   value[:60]))


@rule("B5", covers=("b-5-2-document-metadata#1",), kind="content", prio="MUST", versions=(), variants=(),
      title="link must be used only with rel=\"stylesheet\"",
       fix="Use rel=\"stylesheet\", or delete the element. Other relations describe a document's place among others, and in iiRDS the metadata graph carries that; a consumer reads the graph and never sees this.")
def b5_link_rel(ctx):
    """B.5.2. Every other relation "MUST be expressed by means of RDF in
    iiRDS", so a `<link rel="next">` is metadata smuggled past the metadata."""
    for name, root in _walk(ctx):
        # By local name, like every other rule here. Matching the namespaced
        # tag meant a document missing its xmlns declaration got B2, B3, B4, B7
        # and B8 and silently lost B5.
        for element in (e for e in root.iter() if _local(e.tag) == "link"):
            rel = (element.get("rel") or "").strip().lower()   # ASCII case-insensitive
            if rel != "stylesheet":
                yield Violation("<link> must be used only with rel=\"stylesheet\"",
                                subject=name, detail="found rel=%r" % (element.get("rel") or ""))


@rule("B6", covers=("b-3-conformance-criteria#5",), kind="content", prio="MUST", versions=(), variants=(),
      title="iiRDS XHTML5 files must use the .xhtml extension",
       fix="Rename the file to end in .xhtml and update every iirds:source that points at it. Consumers select renditions by extension as well as by declared media type.")
def b6_file_extension(ctx):
    for name in sorted(_xhtml_renditions(ctx)):
        if not name.lower().endswith(".xhtml"):
            yield Violation("content declared as iiRDS XHTML5 does not use the .xhtml "
                            "file extension", subject=name)


PDF_FORMAT = "application/pdf"


@rule("R41", covers=(), kind="content", prio="MUST", versions=(),
      variants=("A",),
      title="a rendition declared as PDF in an iiRDS/A package must use the .pdf extension",
      fix="Rename the file to end in .pdf and update every iirds:source that points at it. "
          "Section 8.2.1.1 names the extension, and a consumer choosing a viewer by it opens "
          "anything else as a file it does not recognise.")
def r41_pdf_extension(ctx):
    """B6's twin for the other text format section 8.2.1.1 names, and like B6
    it reads the files a rendition declares.

    That is why it claims no sentence: "The file extension MUST be .pdf"
    binds a PDF a page points at as well, and this does not read those.
    Whether a file conforms to ISO 19005-3 is a PDF/A validator's question.
    The extension is compared case-blind, as B6 compares it: `.PDF` names the
    same extension.
    """
    for name in sorted(_renditions_declared_as(ctx, PDF_FORMAT)):
        if not name.lower().endswith(".pdf"):
            yield Violation("content declared as PDF does not use the .pdf file extension",
                            subject=name)


SVG_FORMAT = "image/svg+xml"
GZIP_MAGIC = b"\x1f\x8b"


def _head(ctx, name, size, *, rendition):
    """The first `size` bytes of a file, and why they were not read where
    that is the caller's to say.

    Bytes `_bytes_of` already holds are used rather than read again, and a
    file it read and found empty is empty rather than unread. Nothing is read
    once the run's content budget is spent. A rendition's bytes are charged to
    that budget and may cross it, as `_bytes_of`'s may, which S9 reports; a
    file the package does not list is not charged -- C1's damage check reads
    every entry whole and pays nothing, and a stop charged to such a file
    would have S9 name something that is not a rendition. A method no bounded
    read can be made of is S14's to report, and this code's own faults reach
    the runner. Any other failure comes back as a reason, for the rule that
    asked to report: the first version caught everything and went on, and a
    file nobody could read passed as one nothing was wrong with.
    """
    memo = ctx.__dict__.get("_content_bytes") or {}
    if name in memo:
        raw, why = memo[name]
        return (None, None) if (why and not raw) else (raw[:size], None)
    if ctx.__dict__.get("content_budget") is not None:
        return None, None
    try:
        head, _more = ctx.package.read_bounded(name, size)
        if rendition:
            ctx.package.charge(len(head))
    except UnreadableMethod:
        return None, None
    except ContentBudgetExceeded as exc:
        ctx.__dict__["content_budget"] = (exc.read_so_far, exc.limit, name)
        return None, None
    except _OUR_FAULT:
        raise
    except Exception as exc:
        return None, "not read: %s" % (exc if str(exc) else type(exc).__name__)
    return head[:size], None


@rule("R42", covers=(), kind="content", prio="MUST", versions=(),
      variants=("A",),
      title="a rendition declared as SVG in an iiRDS/A package must be named .svg, or .svgz "
            "when gzip-compressed",
      fix="Name an uncompressed SVG .svg and a gzip-compressed one .svgz, and update every "
          "iirds:source that points at it. A consumer decides whether to decompress by the "
          "extension, so a gzip-compressed file named .svg arrives as bytes it cannot parse.")
def r42_svg_extension(ctx):
    """The extension depends on the bytes, so this reads the first of them.

    A gzip stream opens with 1f 8b, and two bytes answer the question; the
    read is three, since a bounded read hands back its limit plus one. It
    reads the SVGs a rendition declares, and an SVG a page
    points at with `<img>` -- the way section 8.2.1.2 says SVG is referenced
    -- is not read, so the sentence is not claimed. A file that is neither
    gzip nor named .svg is reported as not gzip-compressed, which is all two
    bytes say: zlib without the gzip wrapper is not gzip either.
    """
    for name in sorted(_renditions_declared_as(ctx, SVG_FORMAT)):
        head, unread = _head(ctx, name, 2, rendition=True)
        if unread:
            yield Violation("this SVG could not be read, so whether it is gzip-compressed "
                            "is not known", subject=name, detail=unread)
        if head is None:
            continue
        compressed = head == GZIP_MAGIC
        lowered = name.lower()
        if compressed and not lowered.endswith(".svgz"):
            yield Violation("a gzip-compressed SVG is not named .svgz", subject=name)
        elif not compressed and not lowered.endswith(".svg"):
            yield Violation("an SVG that is not gzip-compressed is not named .svg", subject=name)


def _raster_other_than_jpeg_or_png(head: bytes):
    """The raster format these bytes open with, when it is one section 8.2.1.2
    does not allow; None when it is JPEG, PNG, or not a format known here.

    Only signatures strong enough not to be met by accident. BMP's is two
    letters, and a text file beginning "BM" would carry them, so BMP is only
    recognised with the four reserved header bytes that follow its size, which
    the format fixes at zero.
    """
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WebP"
    if head[:2] == b"BM" and head[6:10] == b"\x00\x00\x00\x00":
        return "BMP"
    return None


@rule("R43", covers=(), kind="content", prio="MUST", versions=(),
      variants=("A",),
      title="a file in an iiRDS/A package must not be a GIF, TIFF, WebP or BMP graphic",
      fix="Convert the graphic to PNG, or to JPEG for photographs, and update whatever "
          "points at it. Section 8.2.1.2 allows JPEG and PNG as raster formats in iiRDS/A, "
          "so that a consumer needs to render no other.")
def r43_raster_formats(ctx):
    """What each file is, rather than what its name or the metadata says: a
    GIF named .png is a GIF, whether a rendition declares it or a page points
    at it. It reads twelve bytes of a file.

    It recognises GIF, TIFF, WebP and BMP, and a raster format it has no
    signature for passes -- which is why it claims no sentence. "Raster
    graphics MUST be encoded as" JPEG or PNG would need every other raster
    format recognised, and "Only JPG and PNG graphics according to this
    section MUST be used" is one of section 8.2.1.2's restrictions on SVG,
    about the graphics an SVG uses; this does not open SVGs.
    """
    renditions = set(_renditions_declared_as(ctx))
    for name in sorted(ctx.package.files):
        if name == "mimetype" or name.startswith("META-INF/"):
            continue
        head, unread = _head(ctx, name, 12, rendition=name in renditions)
        if unread:
            yield Violation("this file could not be read, so whether it is a GIF, TIFF, "
                            "WebP or BMP graphic is not known", subject=name, detail=unread)
        if head is None:
            continue
        found = _raster_other_than_jpeg_or_png(head)
        if found:
            yield Violation("a %s graphic, where iiRDS/A allows JPEG and PNG" % found,
                            subject=name)


def _named_for_its_family(ctx, family, extension, what):
    """Every present file a rendition declares as `family`, not named `extension`."""
    for name in sorted(_renditions_declared_as(ctx, family)):
        if not name.lower().endswith(extension):
            yield Violation("%s content does not use the %s file extension" % (what, extension),
                            subject=name)


@rule("R44", covers=(), kind="content", prio="MUST", versions=(),
      variants=("A",),
      title="a rendition declared as video in an iiRDS/A package must use the .mp4 extension",
      fix="Name the video file .mp4 and update every iirds:source that points at it. Section "
          "8.2.1.3 fixes the extension, and a video in another container is the thing the "
          "section's encoding sentence also rules out.")
def r44_video_extension(ctx):
    """Video content is whatever a rendition declares with a video/ media type,
    any subtype. A video a page points at with `<video>` is not read, so the
    extension sentence is not claimed; nor is the encoding sentence beside
    it, which the index holds without the codecs that complete it."""
    yield from _named_for_its_family(ctx, "video/", ".mp4", "video")


@rule("R45", covers=(), kind="content", prio="MUST", versions=(),
      variants=("A",),
      title="a rendition declared as audio in an iiRDS/A package must use the .mp3 extension",
      fix="Name the audio file .mp3 and update every iirds:source that points at it. Section "
          "8.2.1.4 fixes the extension alongside the encoding.")
def r45_audio_extension(ctx):
    """As R44, for audio/, and for `<audio>` on a page. Whether the bytes are
    MP3 to ISO/IEC 11172-3 is a question for a decoder."""
    yield from _named_for_its_family(ctx, "audio/", ".mp3", "audio")


@rule("B7", covers=("b-6-additional-semantic-tagging-of-content#5",), kind="content", prio="MUST", versions=(), variants=(),
      title="data-role may only carry the values the hazard statement table defines",
       fix="Use one of the values from the hazard statement table, on the element that table names. data-role exists only to mark up hazard statements, so an invented value marks nothing a consumer can find.")
def b7_data_role_values(ctx):
    """B.6: "Tagging with data-role MUST only be used with hazard statements"
    and "The attribute values given in the following table MUST be used"."""
    for name, root in _walk(ctx):
        for element in root.iter():
            value = element.get("data-role")
            if value is None:
                continue
            expected = DATA_ROLE_ELEMENTS.get(value.strip())
            if expected is None:
                yield Violation("data-role=%r is not one of the values the specification "
                                "defines" % value, subject=name,
                                detail="allowed: " + ", ".join(sorted(DATA_ROLE_ELEMENTS)))
            elif _local(element.tag) != expected:
                yield Violation("data-role=%r belongs on <%s>, not <%s>"
                                % (value, expected, _local(element.tag)), subject=name)


@rule("B8", covers=("b-6-additional-semantic-tagging-of-content#6",
                    "b-6-additional-semantic-tagging-of-content#7"),
      kind="content", prio="MUST", versions=(), variants=(),
      title="a safety alert symbol must sit in the signal word panel, and only one",
       fix="Move the img so it is a direct child of the signal word panel, and leave one per hazard statement. A symbol outside the panel renders as a picture with no warning attached to it.")
def b8_safety_alert_symbol(ctx):
    """B.6: "The img element MUST be a child of the signal word panel. Only one
    safety alert symbol MUST be included."

    A hazard statement whose symbol has drifted out of its panel renders as a
    picture with no warning attached to it.

    Two obligations in one sentence, and the index makes a row of each with
    the whole sentence written into both, so the two rows are identical.
    This rule enforces both -- a symbol outside the panel and a second symbol
    inside one are separate findings, and there is a case for each -- and it
    claimed one of them, so an obligation the tool does enforce was published
    as one it does not. C6 covers the same shape one section over and claims
    both halves.
    """
    for name, root in _walk(ctx):
        parents = {child: parent for parent in root.iter() for child in parent}
        symbols = [e for e in root.iter() if (e.get("data-role") or "").strip()
                   == "safety-alert-symbol"]
        per_panel = {}
        for symbol in symbols:
            parent = parents.get(symbol)
            role = (parent.get("data-role") or "").strip() if parent is not None else ""
            if role != "signalword-panel":
                yield Violation("a safety alert symbol must be a child of the signal word "
                                "panel", subject=name,
                                detail="parent is <%s data-role=%r>"
                                       % (_local(parent.tag) if parent is not None else "?", role))
            else:
                per_panel[id(parent)] = per_panel.get(id(parent), 0) + 1

        # Per hazard statement, not per file. "Only one safety alert symbol
        # MUST be included" sits inside the table describing one hazard
        # statement, and a topic carrying a Warning and a Danger notice, each
        # correctly formed, is ordinary safety documentation.
        for count in per_panel.values():
            if count > 1:
                yield Violation("a hazard statement may include only one safety alert symbol",
                                subject=name, detail="%d in one signal word panel" % count)


#: The hazard statement itself is tagged with its level -- there is no
#: "hazardstatement" role in the table -- so the level is read off the markup
#: and never off the signal word's text, which is written in the content's own
#: language.
HAZARD_ROLES = ("caution", "warning", "danger", "notice")

#: The three that alert to a hazard. NOTICE does not, by iiRDS's own bundled
#: definition of the level -- "information considered important but not related
#: to personal injury", where the other three are each defined by injury -- so
#: no safety alert symbol is "applicable" to it in the requirement's own word.
ALERTING_ROLES = ("caution", "warning", "danger")


def _role(element) -> str:
    return (element.get("data-role") or "").strip()


def _hazard_statements(root, roles):
    return [e for e in root.iter() if _role(e) in roles]


def _carries(statement, role) -> bool:
    return any(_role(e) == role for e in statement.iter())


@rule("B9", kind="content", prio="MUST", versions=(), variants=(),
      title="a hazard statement must carry its signal word",
       fix="Add a <p data-role=\"signalword\"> inside the signal word panel, holding the word for this hazard level. A hazard statement with a message and no signal word tells a reader something is dangerous without saying how dangerous.")  # noqa: E501
def b9_signal_word_present(ctx):
    """B.6: "If an iiRDS package contains content with hazard statements, then
    the iiRDS package MUST always provide the applicable safety alert symbols
    and signal words."

    About presence, and in the standard's own words. B8 governs where the
    symbol sits and how many there are; nothing asked whether either was there
    at all, so a hazard statement reduced to a paragraph of text passed.
    """
    for name, root in _walk(ctx):
        for statement in _hazard_statements(root, HAZARD_ROLES):
            if not _carries(statement, "signalword"):
                yield Violation("a hazard statement must provide its signal word",
                                subject=name, detail='data-role=%r' % _role(statement))


@rule("B10", kind="content", prio="RECOMMENDED", versions=(), variants=(),
      title="the safety alert symbol of a hazard statement should be tagged",
       fix="Add data-role=\"safety-alert-symbol\" to the img that carries the alert symbol, and place it in the signal word panel, as the tagging example in Appendix B shows. The picture is usually already there, in the symbol panel; what is missing is the attribute that says which picture it is.")
def b10_safety_alert_symbol_present(ctx):
    """The other half of the same sentence, and the half that is not checkable
    as written.

    "the iiRDS package MUST always provide the applicable safety alert symbols
    and signal words." The subject is the package and the verb is provide, and
    both Consortium packages do provide it: the yellow triangle with the
    exclamation mark sits in the symbol panel of every hazard statement this
    rule reports. What is absent is the data-role that would let a consumer
    tell that picture from the flammable-materials sign beside it.

    Turning "provide" into "tag it as a child of the signal word panel" takes
    the note above the table and the tagging example below it, and the
    specification's conformance section puts notes and examples outside the
    normative text -- the same rule tools/extract_requirements.py applies when
    it counts obligations. So this reports what is true and useful, at the
    severity a reading of ours is entitled to, and no more.

    Notices are left alone. The requirement says *applicable* symbols, and
    iiRDS's own definition of the level, bundled in iirds-core.rdf, is a
    "message that contains information considered important but not related to
    personal injury" -- while caution, warning and danger are all defined by
    injury. tekom's authors drew the same line: a triangle on the eleven, a
    blue circle on the four.
    """
    for name, root in _walk(ctx):
        for statement in _hazard_statements(root, ALERTING_ROLES):
            if not _carries(statement, "safety-alert-symbol"):
                yield Violation("no img in this hazard statement is tagged as the safety "
                                "alert symbol, so a consumer cannot tell which picture it is",
                                subject=name,
                                detail='data-role=%r' % _role(statement))
