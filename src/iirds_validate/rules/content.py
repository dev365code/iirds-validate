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

import posixpath
import re
import xml.etree.ElementTree as ElementTree

from .. import terms as T
from ..model import Violation
from ..registry import rule

XHTML_FORMAT = "application/xhtml+xml"

#: Content arrives from a supplier just as metadata does, and the guard that
#: refuses entity declarations was only ever applied to metadata. A few hundred
#: bytes of nested entities in a content file expanded to gigabytes and the
#: report came back clean — a silent pass, which is the failure this project
#: exists to remove.
MAX_CONTENT_BYTES = 64 * 1024 * 1024
_ENTITY_DECL = re.compile(rb"<!ENTITY", re.IGNORECASE)
XHTML_NS = "{http://www.w3.org/1999/xhtml}"

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
    seen = set()
    for rendition in ctx.instances_of(T.Rendition):
        if XHTML_FORMAT not in [_media_type(f) for f in ctx.values(rendition, T.fmt)]:
            continue
        for source in ctx.values(rendition, T.source):
            name = posixpath.normpath(str(source).lstrip("/"))
            if name not in seen and ctx.package.has(name):
                seen.add(name)
                yield name


def _refusal(ctx, name):
    """Why this file will not be parsed, or None."""
    # The same reasoning as the metadata gate: the declared size belongs to
    # the sender, so the limit is on what is read rather than on what is
    # claimed, and one read answers both questions.
    raw, oversize = ctx.package.read_bounded(name, MAX_CONTENT_BYTES)
    if oversize:
        return "over the %d byte limit uncompressed" % MAX_CONTENT_BYTES
    if _ENTITY_DECL.search(raw):
        return "the document declares XML entities"
    return None


def _walk(ctx):
    """Every declared XHTML file, parsed — once per run, not once per rule.

    Eight B rules each iterated the same files, so every content document was
    read and parsed eight times; on large packages that was a third of the
    whole run. The parse result is cached on the Context, which lives exactly
    as long as one validation. Rules only read the tree, so sharing it is
    safe; if one ever mutates it, that rule must copy first.
    """
    cache = ctx.__dict__.get("_content_trees")
    if cache is None:
        cache = ctx.__dict__["_content_trees"] = {}
        for name in sorted(_xhtml_renditions(ctx)):
            if _refusal(ctx, name):
                continue
            try:
                cache[name] = ElementTree.fromstring(ctx.package.read(name))
            except ElementTree.ParseError:
                continue
    yield from cache.items()


def _local(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


@rule("B1", kind="content", prio="MUST", versions=(), variants=(),
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
            yield Violation("content declared as iiRDS XHTML5 was refused rather than parsed",
                            subject=name, detail=refused)
            continue
        try:
            ElementTree.fromstring(ctx.package.read(name))
        except ElementTree.ParseError as exc:
            yield Violation("content declared as iiRDS XHTML5 is not well-formed XML",
                            subject=name, detail=str(exc))


@rule("B2", kind="content", prio="MUST NOT", versions=(), variants=(),
      title="scripting, forms, svg, math and iframes must not be used",
       fix="Delete the element. These carry behaviour rather than content, so a consumer that strips them for safety renders a topic with a hole in it. Express the same thing as text, a table, or an image.")
def b2_forbidden_elements(ctx):
    for name, root in _walk(ctx):
        for element in root.iter():
            tag = _local(element.tag)
            if tag in FORBIDDEN:
                yield Violation("<%s> is forbidden in iiRDS XHTML5" % tag,
                                subject=name, detail=FORBIDDEN[tag])


@rule("B3", kind="content", prio="MUST", versions=(), variants=(),
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


@rule("B4", kind="content", prio="MUST NOT", versions=(), variants=(),
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


@rule("B5", kind="content", prio="MUST", versions=(), variants=(),
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


@rule("B6", kind="content", prio="MUST", versions=(), variants=(),
      title="iiRDS XHTML5 files must use the .xhtml extension",
       fix="Rename the file to end in .xhtml and update every iirds:source that points at it. Consumers select renditions by extension as well as by declared media type.")
def b6_file_extension(ctx):
    for name in sorted(_xhtml_renditions(ctx)):
        if not name.lower().endswith(".xhtml"):
            yield Violation("content declared as iiRDS XHTML5 does not use the .xhtml "
                            "file extension", subject=name)


@rule("B7", kind="content", prio="MUST", versions=(), variants=(),
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


@rule("B8", kind="content", prio="MUST", versions=(), variants=(),
      title="a safety alert symbol must sit in the signal word panel, and only one",
       fix="Move the img so it is a direct child of the signal word panel, and leave one per hazard statement. A symbol outside the panel renders as a picture with no warning attached to it.")
def b8_safety_alert_symbol(ctx):
    """B.6: "The img element MUST be a child of the signal word panel. Only one
    safety alert symbol MUST be included."

    A hazard statement whose symbol has drifted out of its panel renders as a
    picture with no warning attached to it.
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
