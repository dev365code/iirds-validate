"""Section 8.3.1.1: the human-readable content list in iiRDS/H.

Delivered documents are identified by row references. The logical table grid
supplies a structural five-cell check; human-readable data roles and attribute
whitelists are outside these rules' coverage claims.
"""
from __future__ import annotations

import re

from rdflib import URIRef

from .. import terms as T
from ..model import Violation
from ..package import entry_named
from ..registry import rule
from .container import CONTENT_LIST
from .content import (
    ALLOWED_ELEMENTS,
    XHTML_NS,
    _local,
    _SCHEME,
    _walk,
)
from .handover import _CONTENT_LIST_SECTION

# 8.3.1.1 selects B.5.1/2/3/5/9 from B's inventory. The other permitted
# sections in that inventory are B.5.4 (grouping), B.5.6 (embedded content)
# and B.5.8 (edits). Subtract them rather than maintaining a second inventory.
LIST_ELEMENTS = ALLOWED_ELEMENTS.difference((
    "dd", "div", "dl", "dt", "figcaption", "figure", "li", "ol", "p", "pre", "ul",
    "area", "audio", "img", "map", "source", "track", "video", "ins", "del",
))


def _list_root(ctx):
    return dict(_walk(ctx)).get(CONTENT_LIST)


@rule("R67", kind="content", prio="MUST", versions=("1.3",), variants=("H",),
      title="the content list follows the XHTML element restrictions",
      spec=_CONTENT_LIST_SECTION, covers=(),
      fix="Use elements from Main Root, Document Metadata, Sections, Text-Level "
          "Semantics and Tabular Data. Replace the element named in this finding. "
          "For a parse error, correct the XML at the reported location.")
def r67_content_list_elements(ctx):
    if not ctx.package.has(CONTENT_LIST):
        return  # C11.2 owns the missing list.
    root = _list_root(ctx)
    if root is None:
        yield Violation("the content list could not be read as iiRDS XHTML5",
                        subject=CONTENT_LIST)
        return
    if _local(root.tag) != "html":
        yield Violation("the content list must have an html document element",
                        subject=CONTENT_LIST)
    reported = set()
    for element in root.iter():
        tag = _local(element.tag)
        foreign = isinstance(element.tag, str) and element.tag.startswith("{") \
            and not element.tag.startswith(XHTML_NS)
        if tag and (tag not in LIST_ELEMENTS or foreign) and element.tag not in reported:
            reported.add(element.tag)
            yield Violation("index.html contains <%s>, which section 8.3.1.1 excludes." % tag,
                            subject=CONTENT_LIST, detail=str(element.tag))


def _list_tag(element):
    if isinstance(element.tag, str) and element.tag.startswith("{") \
            and not element.tag.startswith(XHTML_NS):
        return ""
    return _local(element.tag)


def _span(cell, attribute, maximum):
    value = cell.get(attribute, "1")
    if not value.isdecimal():
        return 1
    number = int(value)
    if attribute == "rowspan" and number == 0:
        return maximum
    return min(max(number, 1), maximum)


def _list_tables(root):
    """Candidate rows in the logical grid; thead and tfoot are not data rows."""
    if root is None:
        return
    for table in (e for e in root.iter() if _list_tag(e) == "table"):
        candidates = []
        for child in table:
            tag = _list_tag(child)
            rows = [child] if tag == "tr" else list(child) if tag == "tbody" else []
            candidates.extend(row for row in rows if _list_tag(row) == "tr")
        active = {}
        grid_rows = []
        for index, row in enumerate(candidates):
            grid = {position: cell for position, (cell, remaining) in active.items()}
            following = {position: (cell, remaining - 1)
                         for position, (cell, remaining) in active.items() if remaining > 1}
            column = 0
            for cell in (e for e in row if _list_tag(e) in ("td", "th")):
                # HTML5 limits colspan to 1000; rowspan cannot outlive these rows.
                width = _span(cell, "colspan", 1000)
                height = _span(cell, "rowspan", len(candidates) - index)
                while any(column + offset in grid for offset in range(width)):
                    column += 1
                for offset in range(width):
                    position = column + offset
                    grid[position] = cell
                    if height > 1:
                        following[position] = (cell, height - 1)
                column += width
            grid_rows.append([grid[position] for position in sorted(grid)])
            active = following
        yield grid_rows


def _cell_elements(cell):
    yield cell
    for child in cell:
        if _list_tag(child) != "table":
            yield from _cell_elements(child)


def _cell_text(cell):
    parts = [cell.text or ""]
    for child in cell:
        if _list_tag(child) != "table":
            parts.append(_cell_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _contains(text, value):
    return bool(value) and re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", text) is not None


def _row_text(cells):
    return " ".join(" ".join(_cell_text(cell).split()) for cell in cells)


def _identity_in(ctx, subject, text):
    return any(_contains(text, identifier) and _contains(text, domain)
               for identity in ctx.values(subject, T.has_identity)
               for identifier in ctx.values(identity, T.identifier)
               for domain in ctx.values(identity, T.has_identity_domain))


def _row_units(ctx, cells, units):
    text = _row_text(cells)
    named = {u for u in units if isinstance(u, URIRef) and _contains(text, u)}
    identified = {u for u in units if _identity_in(ctx, u, text)}
    # Resolve index.html links as _pointed_at does: the list is at the root.
    links = set()
    for cell in cells:
        for element in _cell_elements(cell):
            value = (element.get("href") or "").strip()
            if _list_tag(element) == "a" and value and not value.startswith(("#", "//")) \
                    and not _SCHEME.match(value):
                name = entry_named(value[1:] if value.startswith("/") else value)
                if name and name != CONTENT_LIST and ctx.package.has(name):
                    links.add(name)
    referenced = {u for u in units for r in ctx.values(u, T.has_rendition)
                  if "application/pdf" in {str(f) for f in ctx.values(r, T.fmt)}
                  and any(entry_named(str(s)) in links for s in ctx.values(r, T.source))}
    if len(referenced) > 1:
        referenced = {u for u in referenced
                      if any(_contains(text, t) for t in ctx.values(u, T.title))}
        if len(referenced) > 1:
            referenced = set()
    return named | identified | referenced


@rule("R68", kind="content", prio="MUST", versions=("1.3",), variants=("H",),
      title="the content list identifies each delivered document in a table row",
      spec=_CONTENT_LIST_SECTION, covers=("x8-3-1-1-mandatory-content-list#5",),
      fix="Add a row for the named document, or correct its reference. Use its IRI, "
          "a complex identity with its domain, or a link to its PDF/A rendition. "
          "Keep summary rows separate from document rows.")
def r68_content_list_rows(ctx):
    if not ctx.package.has(CONTENT_LIST):
        return  # C11.2 owns the missing list.
    documents = set(ctx.instances_of(T.Document))
    occurrences = {document: [] for document in documents}
    for number, cells, targets in _document_rows(ctx, documents):
        if len(targets) > 1:
            yield Violation("a row refers to more than one document", subject=CONTENT_LIST,
                            detail="row %d" % number)
        elif targets:
            occurrences[next(iter(targets))].append(number)
    for document in sorted(documents, key=str):
        rows = occurrences[document]
        if not rows:
            yield Violation("index.html has no row identifying document %s" % document,
                            subject=CONTENT_LIST)
        elif len(rows) > 1:
            yield Violation("index.html lists document %s more than once" % document,
                            subject=CONTENT_LIST, detail="rows " + ", ".join(map(str, rows)))


def _document_rows(ctx, documents):
    number = 0
    for rows in _list_tables(_list_root(ctx)):
        for cells in rows:
            number += 1
            yield number, cells, _row_units(ctx, cells, documents)


@rule("R69", kind="content", prio="MUST", versions=("1.3",), variants=("H",),
      title="the content list gives each document row five data cells",
      spec=_CONTENT_LIST_SECTION, covers=(),
      fix="Provide document-title, language, product-reference, category or classification, "
          "and unit-reference data for the named document. Keep these data roles in "
          "consistent table columns.")
def r69_content_list_columns(ctx):
    if not ctx.package.has(CONTENT_LIST):
        return  # C11.2 owns the missing list.
    documents = set(ctx.instances_of(T.Document))
    for number, cells, targets in _document_rows(ctx, documents):
        if len(targets) == 1:
            nonempty = sum(bool(_cell_text(cell).strip())
                           or any(e.get("href") for e in _cell_elements(cell)) for cell in cells)
            if nonempty < 5:
                document = next(iter(targets))
                yield Violation("the row for document %s provides fewer than five data cells" % document,
                                subject=CONTENT_LIST, detail="row %d" % number)
