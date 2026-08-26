# Everything CI's lint and test gates run, runnable before you push. (CI also
# builds the wheel and the .pyz and smoke-tests both in a clean venv; those
# need the network once and are not part of `check`.)
#
# This file exists because a commit went red twice on lint alone — the code was
# right and the import order was not, which CI can see and a local `pytest`
# cannot. A contributor should not have to read ci.yml to find out what it will
# object to, and the version below is pinned to the one CI installs so the two
# never disagree about what counts as tidy.

RUFF_VERSION := 0.16.3
PYTHON       ?= python3
# The suite imports `iirds`, and this line decides which copy it finds. Left
# to itself Python takes whatever happens to be installed, so a green run is a
# fact about the machine rather than about the commit -- and while the SDK and
# the validator are repaired together, it is a fact about the *unrepaired* SDK.
# IIRDS_SRC names a checkout to prefer, and tests/test_sdk_alignment.py checks
# that naming one meant it.
#
# Opt-in rather than reaching for ../iirds/src on sight: an implicit sibling
# would quietly change what `make check` means for anyone who happens to have
# one, which is the same accident this exists to remove.
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/tests$(if $(IIRDS_SRC),:$(IIRDS_SRC))

# The differential gate is an opt-in extra and silent when absent, so a run
# without it can report the tree good while the strongest cross-check here --
# two independent implementations of every rule, compared -- was switched off.
# Under make it is not optional. tests/test_ci_parity.py checks this line
# exists, because a gate whose switch nobody checks is a gate that is off.
export IIRDS_REQUIRE_SHACL := 1

.PHONY: help check test lint fix generated corpus exercised versions requirements shapes tools dev clean

help:
	@echo "make check   everything CI runs: lint, tests, the equivalence proof"
	@echo "make test    the test suite alone"
	@echo "make lint    ruff, pinned to the version CI uses"
	@echo "make generated  the generated rule table still matches its generator"
	@echo "make corpus  the vendored reference fixtures are still upstream's"
	@echo "make exercised  no rule has quietly stopped firing anywhere"
	@echo "make versions  no rule claims a version whose vocabulary it predates"
	@echo "make requirements  the specification index is internally consistent"
	@echo "make shapes  the emitted SHACL shapes still match their generator"
	@echo "make fix     ruff --fix, for the things it can correct itself"
	@echo "make tools   the checks that need a built container"
	@echo "make dev     install ruff and pytest for the above"
	@echo ""
	@echo "IIRDS_SRC=../iirds/src make check   run against that SDK checkout,"
	@echo "                                    not whatever is installed"

check: lint generated corpus versions requirements shapes test exercised tools

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

fix:
	$(PYTHON) -m ruff check --fix .

# src/iirds_validate/rules/schema_tables.py is written by this script from the
# bundled ontologies, and editing it by hand is how it silently stops matching
# them. --check regenerates into memory and compares; it caught exactly that
# within an hour of the Makefile being written.
generated:
	$(PYTHON) tools/propose_class_rules.py --check

# The vendored corpus is the only external check this project has, and it is
# only evidence for as long as it is upstream's bytes. Verified offline.
# Which rules the suite has ever seen produce a finding. A rule that fires
# nowhere is not known to work -- S8 sat in that state from day one while being
# exactly backwards. Depends on `test` having run, which writes the record.
exercised:
	$(PYTHON) tools/rule_coverage.py --check

# Every `versions` array came from the reference tool and none had been checked.
# A rule applicable to a version whose ontology lacked its class runs, matches
# nothing, and reports clean -- so the error is in the claim, not the output.
versions:
	$(PYTHON) tools/version_inventory.py

# The denominator: what the standard actually requires, derived rather than
# asserted. The README carried an unsourced 254 from day one, and deriving it
# showed the scope was wrong.
requirements:
	$(PYTHON) tools/extract_requirements.py
	$(PYTHON) tools/requirement_coverage.py

# The language-neutral encoding of the rules. Committed and byte-compared,
# like every other generated artefact here.
shapes:
	$(PYTHON) tools/emit_shacl.py --check

corpus:
	$(PYTHON) tools/vendor_corpus.py --check
	$(PYTHON) tools/crossvalidate.py --check

tools: fixtures/good.iirds fixtures/bad.iirds
	$(PYTHON) -m iirds_validate.ontology --verify
	$(PYTHON) tools/serialisation_equivalence.py fixtures/bad.iirds
	$(PYTHON) tools/serialisation_equivalence.py fixtures/good.iirds --allow-clean

fixtures/good.iirds:
	$(PYTHON) tools/make_fixture_package.py $@

fixtures/bad.iirds:
	$(PYTHON) tools/make_fixture_package.py $@ --broken missing-format

dev:
	$(PYTHON) -m pip install --quiet ruff==$(RUFF_VERSION) pytest "pyshacl==0.40.*"

clean:
	rm -rf fixtures dist build .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
