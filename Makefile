.PHONY: help install-backend install-frontend install dev-backend dev-frontend dev up down logs build test lint format

help:
	@echo "Available targets:"
	@echo "  install-backend  - create .venv and install Python deps"
	@echo "  install-frontend - install frontend npm deps"
	@echo "  install          - install backend + frontend deps"
	@echo "  dev-backend      - run FastAPI locally on :8000"
	@echo "  dev-frontend     - run React (Vite) locally on :3000"
	@echo "  dev              - run full stack with docker compose"
	@echo "  up               - run docker compose in detached mode"
	@echo "  down             - stop docker compose"
	@echo "  logs             - tail docker compose logs"
	@echo "  build            - build docker images"
	@echo "  test             - run pytest"
	@echo "  lint             - run ruff"
	@echo "  format           - run black + isort"

install-backend:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r backend/requirements.txt -r requirements-dev.txt

install-frontend:
	cd frontend && npm install

install: install-backend install-frontend

dev-backend:
	.venv/bin/uvicorn src.app.fastapi_main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 3000

dev:
	docker compose up --build

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check src tests

format:
	.venv/bin/black src tests
	.venv/bin/isort src tests
