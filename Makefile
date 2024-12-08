# Makefile
.PHONY: lint test test-cov
lint:
	pre-commit

test:
	pytest tests

test-cov:
	pytest tests --cov=.  --cov-report term
