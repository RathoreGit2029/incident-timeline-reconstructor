.PHONY: test run clean

test:
	PYTHONPATH=. python3 -m unittest tests/test_suite.py

run:
	python3 -m src.cli --config config/ --input fixtures/alerts.jsonl fixtures/actions.jsonl --pretty

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete
	find . -type f -name "*~" -delete
