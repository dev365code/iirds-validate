"""Drift gate for the capabilities picture (copied into tests/ of each repository).

What it holds:
  1. docs/capabilities.svg and docs/capabilities.md are byte-identical to what the generator
     produces from docs/capabilities.json (edit the data, run the generator, commit both). Loading
     the data also refuses comparison words, dates, markup, and done items without evidence.
  2. every piece of evidence is a file inside the repository that says the words it is cited for.
  3. the data's `as_of` equals the package version, so the picture cannot describe a stale version.
  4. README embeds the picture from the repository's raw URL, stamped with the committed picture's
     hash, inside a link to the detail page, and the image alt text equals the one-line summary the
     generator derives from the data (readers without the picture get the same six facts).
  5. every 1.0 condition the picture shows is stated in the README's own words, so the picture
     cannot promise what the page does not.
  6. the detail page docs/what-it-catches.md has one section per axis, in the drawn order, and each
     section names that axis's checklist items.
  7. the detail page and the README paragraph under the picture use no comparison words.

Per-repo settings: PACKAGE (import name) and, if the repo keeps the generator elsewhere, GENERATOR.
"""
import hashlib
import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = "iirds_validate"                      # per repo
GENERATOR = ROOT / "tools" / "capabilities_svg.py"
DATA = ROOT / "docs" / "capabilities.json"
SVG = ROOT / "docs" / "capabilities.svg"
MD = ROOT / "docs" / "capabilities.md"
DETAIL = ROOT / "docs" / "what-it-catches.md"
README = ROOT / "README.md"


def _gen():
    if str(GENERATOR.parent) not in sys.path:
        sys.path.insert(0, str(GENERATOR.parent))
    return importlib.import_module(GENERATOR.stem)


def _data():
    return _gen().load(str(DATA))


def _squash(text):
    return re.sub(r"\s+", " ", text)


def _home():
    m = re.search(r'(?m)^Homepage = "https://github\.com/([^/"]+)/([^/"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"))
    assert m, "pyproject.toml must name the GitHub Homepage"
    return m.group(1), m.group(2)


def _sections(text):
    """{heading: body} for every H2 of the detail page, in order."""
    parts = re.split(r"(?m)^## (.+)$", text)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def test_rendered_files_match_the_data():
    gen = _gen()
    data = gen.load(str(DATA))
    assert SVG.read_text(encoding="utf-8") == gen.render_svg(data), "docs/capabilities.svg is stale: rerun the generator"
    assert MD.read_text(encoding="utf-8") == gen.render_md(data), "docs/capabilities.md is stale: rerun the generator"


def test_every_piece_of_evidence_says_what_it_is_cited_for():
    gen = _gen()
    for ax in _data()["axes"]:
        for ev in ax["evidence"]:
            assert gen.evidence_holds(str(ROOT), ev), f"axis {ax['key']}: {ev['file']} does not say {ev['says']!r}"


def test_as_of_is_the_package_version():
    pkg = importlib.import_module(PACKAGE)
    assert _data()["as_of"] == pkg.__version__


def test_readme_links_the_committed_picture_to_the_detail_page():
    readme = README.read_text(encoding="utf-8")
    data = _data()
    owner, repo = _home()
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/main/"
    blob = f"https://github.com/{owner}/{repo}/blob/main/"
    m = re.search(r'<a href="([^"]+)">\s*<img src="' + re.escape(raw) + r'docs/capabilities\.svg\?v=([0-9a-f]{8})" alt="([^"]*)"',
                  readme)
    assert m, "README must embed the raw docs/capabilities.svg?v=<hash> inside a link to the detail page"
    assert m.group(1) == blob + data["detail"], "the picture must link to the detail page on GitHub"
    assert m.group(2) == hashlib.sha256(SVG.read_bytes()).hexdigest()[:8], "?v= is not the committed picture's hash"
    assert m.group(3) == _gen().summary_line(data), "alt text must be the generator's one-line summary"


def test_every_condition_on_the_picture_is_in_the_readme():
    readme = _squash(README.read_text(encoding="utf-8"))
    for ax in _data()["axes"]:
        assert _squash(ax["target_text"]) in readme, (
            f"axis {ax['key']}: the 1.0 condition {ax['target_text']!r} is on the picture but not on the page")


def test_detail_page_has_one_section_per_axis_in_order_naming_its_items():
    sections = _sections(DETAIL.read_text(encoding="utf-8"))
    positions = []
    for ax in _data()["axes"]:
        label = ax["label"]
        hit = next((i for i, (h, _) in enumerate(sections) if re.fullmatch(re.escape(label) + r"(\s*[—:(].*)?", h)), None)
        assert hit is not None, f"detail page lacks a section headed {label!r}"
        positions.append(hit)
        body = sections[hit][1]
        for it in ax.get("items", []):
            assert it["text"] in body, f"the {label} section does not mention its item {it['text']!r}"
    assert positions == sorted(positions), "detail page sections must follow the drawn order"


def test_the_prose_around_the_picture_compares_with_nobody():
    gen = _gen()
    detail = DETAIL.read_text(encoding="utf-8")
    m = gen.FORBIDDEN_PROSE.search(detail)
    assert not m, f"detail page: {m.group(0)!r} turns a self-description into a comparison"
    readme = README.read_text(encoding="utf-8")
    block = re.search(r"## Where it stands\n(.*?)(?=\n## |\Z)", readme, flags=re.S)
    assert block, "README lacks the '## Where it stands' section"
    m = gen.FORBIDDEN_PROSE.search(block.group(1))
    assert not m, f"README 'Where it stands': {m.group(0)!r} turns a self-description into a comparison"
