# Everything CI runs, runnable before you push.
#
# This file exists because a commit went red twice on lint alone — the code was
# right and the import order was not, which CI can see and a local `pytest`
# cannot. A contributor should not have to read ci.yml to find out what it will
# object to, and the version below is pinned to the one CI installs so the two
# never disagree about what counts as tidy.

RUFF_VERSION := 0.16.3
PYTHON       ?= python3
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/tests

.PHONY: help check test lint fix tools dev clean

help:
	@echo "make check   everything CI runs: lint, tests, the equivalence proof"
	@echo "make test    the test suite alone"
	@echo "make lint    ruff, pinned to the version CI uses"
	@echo "make fix     ruff --fix, for the things it can correct itself"
	@echo "make tools   the checks that need a built container"
	@echo "make dev     install ruff and pytest for the above"

check: lint test tools

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

fix:
	$(PYTHON) -m ruff check --fix .

tools: fixtures/good.iirds fixtures/bad.iirds
	$(PYTHON) -m iirds_validate.ontology --verify
	$(PYTHON) tools/serialisation_equivalence.py fixtures/bad.iirds
	$(PYTHON) tools/serialisation_equivalence.py fixtures/good.iirds --allow-clean

fixtures/good.iirds:
	$(PYTHON) tools/make_fixture_package.py $@

fixtures/bad.iirds:
	$(PYTHON) tools/make_fixture_package.py $@ --broken missing-format

dev:
	$(PYTHON) -m pip install --quiet ruff==$(RUFF_VERSION) pytest

clean:
	rm -rf fixtures dist build .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
