PYTHON ?= python3

.PHONY: demo test eval video real-data

demo:
	$(PYTHON) run.py

test:
	$(PYTHON) -m unittest discover -s tests -v

eval:
	$(PYTHON) run.py --compare

real-data:
	$(PYTHON) -m pip install --user -r requirements-benchmark.txt
	$(PYTHON) scripts/prepare_ashland_benchmark.py --noncommercial-use

video:
	$(PYTHON) demo/build_demo.py
