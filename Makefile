.DEFAULT_GOAL := help

.PHONY: help test repository-check check build

help:
	@echo "test             Run unit tests"
	@echo "repository-check Check for personal paths and credential values"
	@echo "check            Run all pull-request checks"
	@echo "build            Build the installable package"

test:
	uv run --locked python -m unittest discover -s tests -v

repository-check:
	python3 scripts/check_repository.py

check: repository-check test
	uv run --locked python -m compileall -q src

build:
	uv build
