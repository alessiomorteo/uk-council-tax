.PHONY: all fetch parse align join discounts figures pages site test clean help

PY ?= python3

all: fetch parse align join discounts figures pages site test

fetch:
	$(PY) src/fetch/download.py

parse:
	$(PY) src/build/parse.py

align:
	$(PY) src/build/align.py

join:
	$(PY) src/build/join.py

discounts:
	$(PY) src/build/discounts.py
	$(PY) src/build/discount_values.py

figures:
	$(PY) src/render/figures.py

pages:
	$(PY) src/render/pages.py

site: pages
	$(PY) src/render/site.py

test:
	$(PY) src/validate.py

clean:
	rm -rf data/processed/* output/figures/* output/pages/* docs/index.html docs/map.html docs/table.html docs/figures docs/.nojekyll

help:
	@echo "make all      - full pipeline, site build and validation"
	@echo "make site     - copy built pages into docs/site for GitHub Pages"
	@echo "make test     - run validation only"
	@echo "make clean    - remove generated data, output and site"
