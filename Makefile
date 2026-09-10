.PHONY: help install install-dev test test-cov run refresh-logs clean

help:
	@echo "Multi-Agent-Crypto — available targets:"
	@echo "  make install       pip install -e ."
	@echo "  make install-dev   pip install -e .[dev]"
	@echo "  make test          pytest -q"
	@echo "  make test-cov      pytest --cov --cov-report=term-missing"
	@echo "  make run           python main.py"
	@echo "  make refresh-logs  python scripts/refresh_logs.py"
	@echo "  make clean         rm -rf .pytest_cache outputs/cache/*.json"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	python3 -m pytest -q

test-cov:
	python3 -m pytest --cov --cov-report=term-missing

run:
	python3 main.py

refresh-logs:
	python3 scripts/refresh_logs.py

clean:
	rm -rf .pytest_cache outputs/cache/*.json
