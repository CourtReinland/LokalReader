.PHONY: install run test demo clean

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

run: install
	$(BIN)/uvicorn lokalreader.main:app --app-dir backend --reload --host 127.0.0.1 --port 8787

test: install
	$(BIN)/pytest -q

demo: install
	@echo "Open http://127.0.0.1:8787 and drop samples/the_quiet_carriage.txt"
	$(BIN)/uvicorn lokalreader.main:app --app-dir backend --host 127.0.0.1 --port 8787

clean:
	rm -rf $(VENV) data/books/* data/audio/* data/mappings/* .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
