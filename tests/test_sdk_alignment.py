"""One container layer, two projects, held together by `is`.

The validator wrote the metadata guards, the parser and the merge; they
moved to the iirds SDK so every tool shares them; the validator imports
them back. Equality tests would pass against a drifted fork -- these pin
object identity, so the seam cannot reopen without failing loudly.
"""
import iirds

from iirds_validate import context, model


def test_the_shared_constants_are_the_same_objects():
    assert context.MAX_METADATA_BYTES is iirds.MAX_METADATA_BYTES
    assert model.PACKAGE_BASE is iirds.PACKAGE_BASE
    assert model.METADATA_RDF is iirds.METADATA_RDF
    assert model.METADATA_JSONLD is iirds.METADATA_JSONLD


def test_the_shared_functions_are_the_same_objects():
    assert context.parse_metadata is iirds.parse_metadata
    assert context.merge_sources is iirds.merge_sources
    assert context.subclasses_of is iirds.subclasses_of


def test_the_error_string_contract_routes_findings():
    """The runner partitions each parse error on its first ": " to decide
    which per-file finding it becomes; the SDK documents the same shape as
    an interface. Whichever side moves first, this trips."""
    _, error = iirds.parse_metadata(model.METADATA_RDF, b"<broken",
                                    base=model.PACKAGE_BASE)
    name, sep, detail = error.partition(": ")
    assert (name, sep) == (model.METADATA_RDF, ": ")
    assert detail


def test_the_generated_shapes_speak_the_same_base():
    """emit_shacl embeds the base as literal TTL text (a generator emits
    text, not objects), so identity cannot hold there -- containment can."""
    import emit_shacl
    assert iirds.PACKAGE_BASE in emit_shacl.BASE_EXCLUSION
