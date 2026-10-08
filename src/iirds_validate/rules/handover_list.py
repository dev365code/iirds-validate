"""Section 8.3.1.1: the human-readable content list in iiRDS/H.

The specification names data, not header strings or a column order. Read the
cells against the metadata; an English caption alone proves nothing about a
column. Appendix B supplies the element inventory and the bounded XML reader.
"""
from __future__ import annotations

import re

from rdflib import URIRef
from rdflib.namespace import RDFS

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
    b4_no_event_handlers,
    b5_link_rel,
    b7_data_role_values,
    b8_safety_alert_symbol,
    b9_signal_word_present,
    b11_no_scripting_urls,
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
      title="the content list uses only its five permitted XHTML sections",
      spec=_CONTENT_LIST_SECTION, covers=("x8-3-1-1-mandatory-content-list#4",),
      fix="Write index.html as iiRDS XHTML5 using only Main Root, Document Metadata, "
          "Sections, Text-Level Semantics and Tabular Data. Replace grouping, embedded "
          "content and edit elements with elements from those five sections.")
def r67_content_list_elements(ctx):
    if not ctx.package.has(CONTENT_LIST):
        return  # C11.2 owns the missing list for all three sentences.
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
            yield Violation("<%s> is outside the content list's permitted XHTML sections" % tag,
                            subject=CONTENT_LIST, detail=str(element.tag))
    # "Based on iiRDS XHTML5" includes its attribute and semantic MUSTs too.
    # Reuse B's implementations, without making ordinary renditions the
    # subject of this profile-specific rule. B6's extension requirement has
    # the explicit index.html exception in this section.
    for check in (b4_no_event_handlers, b5_link_rel, b7_data_role_values,
                  b8_safety_alert_symbol, b9_signal_word_present,
                  b11_no_scripting_urls):
        for violation in check(ctx):
            if violation.subject == CONTENT_LIST:
                yield violation


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


def _cell_values(cell):
    """Visible values and actual link targets, without guessing header meanings."""
    values = set()
    for element in _cell_elements(cell):
        text = " ".join(_cell_text(element).split())
        if text:
            values.add(text)
        if _list_tag(element) == "a" and element.get("href"):
            values.add(element.get("href").strip())
    return values


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
      title="the content list has one table row per information unit",
      spec=_CONTENT_LIST_SECTION, covers=("x8-3-1-1-mandatory-content-list#5",),
      fix="Provide a table in index.html with one row for each information unit. "
          "Identify each unit by its IRI, its complex identity (value and domain), "
          "or a hyperlink to its PDF/A rendition; remove duplicate unit rows.")
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


def _node_names(ctx, node):
    return {str(node)} | {str(v) for v in ctx.values(node, RDFS.label)} \
        | {str(v) for v in ctx.ontology.graph.objects(node, RDFS.label)}


def _data_columns(ctx, cells, unit):
    """Candidate positions for the five bullet points, using actual cell data."""
    slots = [set() for _ in range(5)]
    for position, cell in enumerate(cells):
        values = _cell_values(cell)
        if {str(v) for v in ctx.values(unit, T.title)} & values:
            slots[0].add(position)
        languages = {str(v).lower() for v in ctx.values(unit, T.language)}
        if languages and languages <= {v.lower() for v in values}:
            slots[1].add(position)
        if any(_node_names(ctx, v) & values or _identity_in(ctx, v, " ".join(values))
               for v in ctx.values(unit, T.relates_to_product_variant)):
            slots[2].add(position)
        categories = list(ctx.values(unit, T.hov_has_document_category)) \
            + list(ctx.values(unit, T.has_external_classification))
        if any(_node_names(ctx, c) & values
               or {str(v) for v in ctx.values(c, T.classificationIdentifier)} & values
               for c in categories):
            slots[3].add(position)
        if unit in _row_units(ctx, [cell], {unit}):
            slots[4].add(position)
    return slots


def _five_distinct_columns(slots, used=frozenset()):
    # Only the five data roles in this section, not a general table engine.
    if not slots:
        return True
    first, *rest = sorted(slots, key=len)
    return any(_five_distinct_columns(rest, used | {column}) for column in first - used)


@rule("R69", kind="content", prio="MUST", versions=("1.3",), variants=("H",),
      title="the content list provides all five required data columns",
      spec=_CONTENT_LIST_SECTION, covers=("x8-3-1-1-mandatory-content-list#6",),
      fix="Provide columns in index.html for the document title, languages, product "
          "instance reference or complex identity, document category or external "
          "classification, and unit IRI, complex identity or PDF/A hyperlink. Fill "
          "each row with the corresponding metadata; captions alone do not provide data.")
def r69_content_list_columns(ctx):
    if not ctx.package.has(CONTENT_LIST):
        return  # C11.2 owns the missing list.
    units = set(ctx.instances_of(T.InformationUnit))
    for rows in _list_tables(_list_root(ctx)):
        if not rows:
            continue
        common = None
        for cells in rows:
            targets = _row_units(ctx, cells, units)
            if len(targets) != 1:
                break
            slots = _data_columns(ctx, cells, next(iter(targets)))
            common = slots if common is None else [a & b for a, b in zip(common, slots)]
        else:
            if common is not None and _five_distinct_columns(common):
                return
    yield Violation("the content list must provide all five required data columns",
                    subject=CONTENT_LIST)
