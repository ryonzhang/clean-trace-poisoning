PYTHON = py
SCRIPTS = scripts

.PHONY: all fetch normalize validate mine provenance params clean

all: fetch normalize validate

fetch:
	$(PYTHON) $(SCRIPTS)/fetch.py --output-dir data/raw

normalize:
	$(PYTHON) $(SCRIPTS)/normalize.py --input-dir data/raw --output-dir data/normalized

validate:
	$(PYTHON) $(SCRIPTS)/validate.py

mine:
	$(PYTHON) $(SCRIPTS)/mine_baseline.py --all-corpora

provenance:
	$(PYTHON) $(SCRIPTS)/tag_provenance.py --all-corpora

params:
	$(PYTHON) $(SCRIPTS)/gen_params_grid.py

clean:
	if exist data\normalized rmdir /S /Q data\normalized
	if exist data\baseline rmdir /S /Q data\baseline
	if exist data\provenance rmdir /S /Q data\provenance
	if exist data\poison_pool rmdir /S /Q data\poison_pool
	if exist data\manifest.json del data\manifest.json
	if exist data\params_grid.csv del data\params_grid.csv
