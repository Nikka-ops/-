.PHONY: install install-dev test demo web doctor clean

PYTHON ?= python3
VENV ?= .venv
BIN = $(VENV)/bin

install: $(VENV)/bin/python
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e .

install-dev: $(VENV)/bin/python
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)

test: install-dev
	$(BIN)/python -m pytest tests/ -v

demo: install-dev
	$(BIN)/interview-radar --role "AI 应用开发" --from-report \
		--raw-posts examples/sample_raw_posts.json --bank-only

web: install-dev
	$(BIN)/interview-radar-web --port 8765

doctor: install-dev
	$(BIN)/interview-radar-doctor

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__
