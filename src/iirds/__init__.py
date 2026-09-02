"""Read and write iiRDS packages.

This is deliberately a small library: open a package, get its metadata as an
RDF graph, read its files, and write a conformant container back. It does not
validate. The checker ships in the same distribution, as `iirds_validate`, and
imports this package; nothing here imports it back, so a tool built on this
package inherits one dependency (rdflib and the standard library, nothing
else) and no verdicts.

Held in stewardship: the `iirds` name on PyPI belongs to the standard's
community more than to any one project. Should the iiRDS Consortium want the
name for an official SDK, it will be transferred on request. Until then it
does real work rather than squatting.

The API is 0.x: it will grow, and what is published here is intended not to
break. `open()` returns a `Package`; `pack()` writes one.
"""
from __future__ import annotations

from ._metadata import (
    MAX_METADATA_BYTES,
    NOT_RDFXML,
    is_absolute_name,
    is_rdfxml_document_element,
    merge_sources,
    parse_metadata,
    write_metadata,
)
from ._pack import PackError, pack
from ._package import (
    IIRDS,
    METADATA_JSONLD,
    METADATA_RDF,
    PACKAGE_BASE,
    IirdsError,
    Package,
    instances_of,
    label_of,
    source_of,
    subclasses_of,
)
from ._package import open_package as open  # noqa: A001 - deliberate, like gzip.open

__version__ = "0.4.2"
__all__ = ["IIRDS", "IirdsError", "MAX_METADATA_BYTES", "METADATA_JSONLD",
           "METADATA_RDF", "NOT_RDFXML", "PACKAGE_BASE", "PackError", "Package",
           "__version__", "instances_of", "is_absolute_name",
           "is_rdfxml_document_element", "label_of", "merge_sources", "open", "pack",
           "parse_metadata", "source_of", "subclasses_of", "write_metadata"]
