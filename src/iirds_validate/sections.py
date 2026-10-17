"""Where each rule's words are in the standard, for the rules that do not
say so themselves. Written by tools/rule_sections.py; edit that, not this.

A rule carrying its own link keeps it. SECTIONS gives the rest a section of
the specification; NO_SECTION says why a rule has none.
"""

SECTIONS = {
    'B1': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-3-conformance-criteria',
    'B2': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-3-conformance-criteria',
    'B3': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-3-conformance-criteria',
    'B4': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-5-7-scripting',
    'B5': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-5-2-document-metadata',
    'B6': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-3-conformance-criteria',
    'B7': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-6-additional-semantic-tagging-of-content',
    'B8': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-6-additional-semantic-tagging-of-content',
    'B9': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-6-additional-semantic-tagging-of-content',
    'B10': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-6-additional-semantic-tagging-of-content',
    'B11': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#b-5-7-scripting',
    'C1': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-iirds-package-and-container',
    'C2': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-iirds-package-and-container',
    'L2': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-3-content-references-of-information-units',
    'L3': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-9-1-directory-nodes',
    'L4': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-9-1-directory-nodes',
    'L5': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x7-3-proprietary-iirds-extensions',
    'L6': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x7-3-1-adding-a-proprietary-instance',
    'L7': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#a-1-1-class-definitions',
    'L9': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-1-1-metadata-location-and-rdf-serializations',
    'L10': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#a-1-1-class-definitions',
    'L12': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-1-3-names-of-files-and-directories',
    'L13': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x7-3-proprietary-iirds-extensions',
    'L14': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-1-the-iirds-rdf-schema-and-identifiers',
    'L16': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#a-1-3-relations',
    'L17': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-12-rdf-serialization',
    'M97.1': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#a-1-1-class-definitions',
    'R41': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-2-1-1-text-formats',
    'R42': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-2-1-2-graphics-formats',
    'R43': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-2-1-2-graphics-formats',
    'R44': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-2-1-3-video-formats',
    'R45': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-2-1-4-audio-formats',
    'S4': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#a-1-2-property-definitions',
    'S5': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x8-1-1-unrestricted-iirds-vs-restricted-iirds',
    'S6': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-1-iirds-container',
    'S7': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-2-2-content-encoding',
    'S8': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-2-2-content-encoding',
    'S10': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-2-iirds-zip-archive',
    'S11': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x6-2-information-units',
    'S13': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-iirds-package-and-container',
    'S14': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-2-2-content-encoding',
    'S15': 'https://www.iirds.org/fileadmin/iiRDS_specification/20251103-1.3-release/index.html#x5-2-iirds-zip-archive',
}

NO_SECTION = {
    'L1': "this project's advice about what a consumer can resolve, not a reading of a sentence of the standard",
    'L8': "this project's note on what a consumer without network access cannot resolve, not a reading of a sentence of the standard",
    'L11': 'about this run: where the iiRDS XHTML5 rules did not read a file through its rendition',
    'L15': "this project's advice about the vocabulary of the declared edition, not a reading of a sentence of the standard",
    'S1': 'about this run: the path could not be read',
    'S2': 'about this run: no metadata was read, so no rule about the graph ran',
    'S3': 'about this run: a rule raised instead of answering',
    'S9': 'about this run: the content it decompressed reached its stated ceiling',
    'S12': "about this run: the search for the package's own ontology reached its ceiling",
    'S16': 'about this run: no content rule got a parsed document for the file',
}
