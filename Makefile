.DEFAULT_GOAL := help

.PHONY: help test repository-check check build

help:
	@echo "test             Run unit tests"
	@echo "repository-check Check for personal paths and credential values"
	@echo "check            Run all pull-request checks"
	@echo "build            Build the installable package"

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

repository-check:
	python3 scripts/check_repository.py

check: repository-check test
	python3 -m compileall -q src

build:
	python3 -m build
