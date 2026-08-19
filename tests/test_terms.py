"""Guard against the two ways a rule can silently check nothing."""
from __future__ import annotations

import pytest
from iirds_validate import terms as T
from iirds_validate.model import IIRDS
from iirds_validate.ontology import load


@pytest.mark.parametrize("name,iri", sorted(T.CLASSES.items()))
def test_every_class_exists_in_the_ontology(name, iri):
    assert load().is_defined(iri), "%s (%s) is not defined in the bundled ontology" % (name, iri)


@pytest.mark.parametrize("name,iri", sorted(T.PROPERTIES.items()))
def test_every_property_exists_in_the_ontology(name, iri):
    if name in T.NOT_IN_ONTOLOGY:
        pytest.skip("used by the specification but not declared in the ontology files")
    assert load().is_defined(iri), "%s (%s) is not defined in the bundled ontology" % (name, iri)


def test_namespace_attribute_access_is_a_trap():
    """Why terms.py exists at all.

    rdflib.Namespace subclasses str, so attribute access can hand back a string
    method instead of a term. rdflib patches a few well-known names, so the
    breakage is inconsistent rather than total — which is precisely what makes
    it dangerous to rely on.
    """
    shadowed = [n for n in ("format", "index", "count", "strip", "join", "split")
                if callable(getattr(IIRDS, n))]
    assert "format" in shadowed, "IIRDS.format no longer resolves to str.format"
    assert str(T.fmt) == "http://iirds.tekom.de/iirds#format"
    assert str(T.title) == "http://iirds.tekom.de/iirds#title"

    for name, iri in list(T.CLASSES.items()) + list(T.PROPERTIES.items()):
        assert str(iri).startswith("http://iirds.tekom.de/"), \
            "%s is not an iiRDS IRI: %r" % (name, iri)
