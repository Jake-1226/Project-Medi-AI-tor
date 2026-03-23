# Medi-AI-tor Makefile
# Provides convenient commands for development, testing, and deployment

.PHONY: help install install-dev test test-unit test-integration test-all test-coverage lint format clean run build docker-build docker-run docs

# Default target
help:
	@echo "Medi-AI-tor - Available commands:"
	@echo ""
	@echo "  install      - Install production dependencies"
	@echo "  install-dev  - Install development dependencies"
	@echo "  test         - Run all tests"
	@echo "  test-unit    - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-coverage - Run tests with coverage report"
	@echo "  lint         - Run code linting"
	@echo "  format       - Format code with black and isort"
	@echo "  clean        - Clean temporary files"
	@echo "  run          - Run the application"
	@echo "  build        - Build for production"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-run   - Run with Docker"
	@echo "  docs         - Generate documentation"
	@echo ""

# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-test.txt
	pip install -e .

# Testing
test:
	pytest

test-unit:
	pytest -m "unit"

test-integration:
	pytest -m "integration" -v

test-all:
	pytest -m "unit or integration" -v

test-coverage:
	pytest --cov=core --cov=integrations --cov=models --cov=main --cov-report=html --cov-report=term

test-slow:
	pytest -m "slow" -v

test-health:
	pytest -m "health" -v

test-cache:
	pytest -m "cache" -v

test-predictive:
	pytest -m "predictive" -v

# Code quality
lint:
	flake8 core integrations models main tests
	mypy core integrations models main
	pylint core integrations models main --disable=C0114,C0115,C0116

format:
	black core integrations models main tests
	isort core integrations models main tests

format-check:
	black --check core integrations models main tests
	isort --check-only core integrations models main tests

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .pytest_cache
	rm -rf dist
	rm -rf build

# Development
run:
	python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

run-prod:
	python -m uvicorn main:app --host 0.0.0.0 --port 8000

run-debug:
	python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

# Build
build:
	python -m build

# Docker
docker-build:
	docker build -t medi-ai-tor:latest .

docker-run:
	docker run -p 8000:8000 medi-ai-tor:latest

docker-dev:
	docker-compose up --build

# Documentation
docs:
	cd docs && make html

docs-serve:
	cd docs/_build/html && python -m http.server 8001

# Development helpers
check-all: format-check lint test
	@echo "All checks passed!"

pre-commit: format lint test-unit
	@echo "Pre-commit checks completed!"

# Performance profiling
profile-memory:
	python -m memory_profiler main.py

profile-cpu:
	python -c "import cProfile; cProfile.run('import main')" > profile.stats

# Security scan
security:
	bandit -r core integrations models main
	safety check

# Dependencies
deps-update:
	pip-compile requirements.in
	pip-compile requirements-test.in

deps-check:
	pip-audit

# Database (if using)
db-migrate:
	alembic upgrade head

db-reset:
	alembic downgrade base
	alembic upgrade head

# Monitoring
monitor:
	python -m pytest tests/test_monitoring.py -v -s

# Load testing
load-test:
	locust -f tests/load_test.py --host=http://localhost:8000

# Backup/Restore
backup-data:
	@echo "Backing up configuration and data..."
	tar -czf backup-$(shell date +%Y%m%d-%H%M%S).tar.gz data/ config/

# Deployment
deploy-staging:
	@echo "Deploying to staging..."
	# Add staging deployment commands here

deploy-prod:
	@echo "Deploying to production..."
	# Add production deployment commands here

# Version management
version:
	@python -c "import main; print(f'Medi-AI-tor v{main.__version__}')"
