.PHONY: install setup-voices run test demo clean

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
DOWNLOAD_STARTERS ?= 0

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

setup-voices: install
	DOWNLOAD_STARTERS=$(DOWNLOAD_STARTERS) bash scripts/setup_voices.sh

run: install
	@if [ -f .rvc/env.sh ]; then . .rvc/env.sh; fi; \
	$(BIN)/uvicorn lokalreader.main:app --app-dir backend --reload --host 127.0.0.1 --port 8787

test: install
	@# CI-friendly: Piper + RVC stub passthrough (not production timbre conversion)
	@mkdir -p data/piper_voices data/rvc_weights
	@$(BIN)/python -m piper.download_voices en_US-lessac-medium --download-dir data/piper_voices || true
	@# Flatten nested piper layout
	@find data/piper_voices -name '*.onnx' -exec cp -n {} data/piper_voices/ \; 2>/dev/null || true
	@find data/piper_voices -name '*.onnx.json' -exec cp -n {} data/piper_voices/ \; 2>/dev/null || true
	@test -f data/rvc_weights/narrator.pth || printf 'RVC-TEST-WEIGHT' > data/rvc_weights/narrator.pth
	@test -f data/rvc_weights/young_female.pth || printf 'RVC-TEST-WEIGHT' > data/rvc_weights/young_female.pth
	@echo '{"role":"narrator","gender":"male","description":"test"}' > data/rvc_weights/narrator.json
	@echo '{"role":"young_female","gender":"female","description":"test"}' > data/rvc_weights/young_female.json
	LOKALREADER_RVC_INFER_SCRIPT="$(CURDIR)/scripts/rvc_infer_stub.py" \
	LOKALREADER_RVC_PYTHON="$(BIN)/python" \
	LOKALREADER_PIPER_VOICES="$(CURDIR)/data/piper_voices" \
	LOKALREADER_RVC_WEIGHTS="$(CURDIR)/data/rvc_weights" \
	$(BIN)/pytest -q

demo: install
	@echo "Open http://127.0.0.1:8787 — requires make setup-voices for real RVC audio"
	@if [ -f .rvc/env.sh ]; then . .rvc/env.sh; fi; \
	$(BIN)/uvicorn lokalreader.main:app --app-dir backend --host 127.0.0.1 --port 8787

clean:
	rm -rf $(VENV) .venv-rvc data/books/* data/audio/* data/mappings/* data/piper_voices/* .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
