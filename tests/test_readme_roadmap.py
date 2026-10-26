"""The roadmap puts each entrance in the column the capabilities data puts it.

The picture under "Where it stands" is drawn from `docs/capabilities.json`
and held by `tests/test_capabilities_current.py`. The roadmap further down is a
hand-written timeline, and nothing held the two together: the GitHub Action
was marked done in the data, with a test of its own as the evidence, while the
timeline's Shipped column went on without it.

Each entrance is placed by the phrase the timeline uses for it -- named here
rather than matched loosely, so adding, renaming or moving an entrance is an
edit to this table as well as to the data.
"""
import json
import re

from conftest import ROOT

#: Entrance, as `docs/capabilities.json` words it -> the phrase the roadmap uses.
PLACED_BY = {
    "command line": "One package",
    "Python library": "reader + writer",
    "single file, nothing to install but Python": "single file",
    "GitHub Action": "GitHub Action",
    "browser, nothing installed": "Browser-local validation",
}


def roadmap_columns():
    """The timeline's columns and the lines under each, as README writes them."""
    readme = (ROOT / "README.md").read_text("utf-8")
    block = readme.split("title Where iirds is going", 1)[1].split("```", 1)[0]
    columns, current = {}, None
    for line in block.splitlines():
        heading = re.match(r"\s*(\w+) :(.*)$", line)
        if heading:
            current = heading.group(1)
            columns[current] = [heading.group(2).strip()]
        elif line.strip().startswith(":") and current:
            columns[current].append(line.strip()[1:].strip())
    return columns


def test_every_entrance_sits_in_the_column_the_data_gives_it():
    data = json.loads((ROOT / "docs" / "capabilities.json").read_text("utf-8"))
    entrances = next(axis for axis in data["axes"] if axis["key"] == "entrances")["items"]
    assert {item["text"] for item in entrances} == set(PLACED_BY), (
        "an entrance was added or renamed in the data; place it in PLACED_BY and the roadmap")
    columns = roadmap_columns()
    assert set(columns) == {"Shipped", "Building", "Planned"}, sorted(columns)
    for item in entrances:
        phrase = PLACED_BY[item["text"]]
        found = sorted(name for name, lines in columns.items()
                       if any(phrase in line for line in lines))
        wanted = [["Shipped"]] if item["done"] else [["Building"], ["Planned"]]
        assert found in wanted, "%s (done=%s) is under %s in the roadmap" % (
            item["text"], item["done"], found or "no column")
