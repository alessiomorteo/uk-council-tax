.PHONY: all fetch parse align join figures pages test clean help

PY ?= python3

all: fetch parse align join figures pages test

fetch:
	$(PY) src/fetch/download.py

parse:
	$(PY) src/build/parse.py

align:
	$(PY) src/build/align.py

join:
	$(PY) src/build/join.py

figures:
	$(PY) src/render/figures.py

pages:
	$(PY) src/render/pages.py

test:
	$(PY) src/validate.py

clean:
	rm -rf data/processed/* output/figures/* output/pages/*

help:
	@echo "make all      - full pipeline + validation"
	@echo "make test     - run validation only"
	@echo "make clean    - remove generated data and output"
