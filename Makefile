.PHONY: help install dev test lint fmt check run demo demo-assets docker-up docker-down docker-logs backup clean

help:
	@echo "install   Install runtime package in the active virtualenv"
	@echo "dev       Install package with test/lint tools"
	@echo "test      Run the offline test suite"
	@echo "lint      Ruff check + format check"
	@echo "fmt       Format and auto-fix"
	@echo "check     Validate configuration without starting"
	@echo "run       Start the bot"
	@echo "demo      Serve the static website/demo at http://127.0.0.1:8000"
	@echo "demo-assets Regenerate demo GIF/poster/OG image (needs .[demo])"
	@echo "docker-up Start Ollama + bot with Compose"
	@echo "backup    Back up data/community.db to backups/"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .
	ruff check --fix .

check:
	python -m github_community_bot --check

run:
	python -m github_community_bot

demo:
	@echo "Serving docs/ at http://127.0.0.1:8000/ (Ctrl+C to stop)"
	python3 -m http.server 8000 -d docs

demo-assets:
	python scripts/render_demo_assets.py

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f bot

backup:
	./scripts/backup.sh data/community.db backups

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
