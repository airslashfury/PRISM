.PHONY: help init up down logs install wfs-list mirror load graph resilience optimize report test lint fmt clean

WFS_URL ?= http://geoserver2.pr.gov/geoserver/pr_geodata/wfs

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

init: ## create local data directories
	mkdir -p data/raw data/interim data/derived catalog

up: ## start PostGIS
	docker compose up -d

down: ## stop services
	docker compose down

logs: ## tail PostGIS logs
	docker compose logs -f postgis

install: ## install the package + dev tools
	pip install -e ".[dev]"

wfs-list: ## Phase 0 - enumerate the OGP/PRITS WFS layers (keystone)
	python -m prism.sync.wfs list --url "$(WFS_URL)"

mirror: ## Phase 0 - mirror all sources into data/raw (versioned)
	python -m prism.mirror

load: ## Phase 1 - load layers into PostGIS at EPSG:32161
	python -m prism.load

graph: ## Phase 2 - build the infrastructure knowledge graph
	python -m prism.graph

resilience: ## Phase 3 - single-point-of-failure + criticality
	python -m prism.resilience

optimize: ## Phase 4/5 - corridor optimization
	python -m prism.optimize

report: ## Phase 7 - AI tradeoff narrative
	python -m prism.report

test: ## run tests
	pytest -q

lint: ## lint
	ruff check .

fmt: ## format
	ruff format .

clean: ## remove python caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
