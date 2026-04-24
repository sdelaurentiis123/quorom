.PHONY: help install install-backend install-frontend dev backend frontend sandbox-image test test-backend test-frontend clean

PY ?= $(shell command -v python3.11 2>/dev/null || command -v python3 2>/dev/null)

help:
	@echo "Quorum — make targets"
	@echo "  install          backend + frontend deps"
	@echo "  sandbox-image    build the Docker sandbox image (run once)"
	@echo "  dev              run backend + frontend side by side"
	@echo "  test             run all tests"

install: install-backend install-frontend

install-backend:
	@echo "Python: $(PY)"
	cd backend && $(PY) -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"

install-frontend:
	cd frontend && pnpm install

sandbox-image:
	docker build -t quorum-sandbox:latest backend/sandbox/

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

dev:
	@command -v npx >/dev/null || (echo "need npx (node) on PATH" && exit 1)
	npx -y concurrently -n backend,frontend -c blue,green \
	  "make backend" "make frontend"

test: test-backend test-frontend

test-backend:
	cd backend && . .venv/bin/activate && pytest -v

test-frontend:
	cd frontend && pnpm test

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/**/__pycache__
	rm -rf frontend/node_modules frontend/dist
