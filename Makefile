# Common tasks. `make help` lists them.
UV ?= uv
STORE ?= data/processed/store

.DEFAULT_GOAL := help
.PHONY: help setup test lint fmt synth api openapi openapi-check sample spike check

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup: ## Install Python dependencies (needs uv)
	$(UV) sync

test: ## Run all Python tests
	$(UV) run pytest

lint: ## Lint and check formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Auto-format and apply safe lint fixes
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

synth: ## Publish synthetic demo data for every source into $(STORE)
	$(UV) run pf-pipeline run --synthetic --run latest --storage $(STORE)

api: ## Serve the API on :8000 over $(STORE), with the dev data proxy on
	PF_API_STORAGE_URL=$(STORE) PF_API_SERVE_DATA=true \
	  $(UV) run uvicorn pf_api.app:create_app --factory --reload --port 8000

openapi: ## Regenerate packages/api-contract/openapi.json
	$(UV) run python scripts/export_openapi.py

openapi-check: ## Fail if packages/api-contract/openapi.json is stale
	$(UV) run python scripts/export_openapi.py --check

sample: ## Download a small real ECMWF sample and report its structure (needs network)
	$(UV) run pf-pipeline sample

spike: ## Measure tile encodings on synthetic data (add ARGS=--real after `make sample`)
	$(UV) run python scripts/spike_tile_format.py $(ARGS)

check: lint test openapi-check ## Everything CI runs
