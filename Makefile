.PHONY: test reproduce clean
PY = PYTHONPATH=src python

test:
	pytest -q

# One-command reproducibility (step 24): regenerates EVERY CSV and figure in
# report/ from the seeded sources. Generators run before plotters (plot.py
# reads sweep.csv). CI runs this clean-from-scratch and re-validates the
# regenerated data with the full test suite.
reproduce:
	$(PY) -m sketchflow.bench
	$(PY) -m sketchflow.sweep
	$(PY) -m sketchflow.plot
	$(PY) -m sketchflow.adversarial_study
	$(PY) -m sketchflow.real_plot

clean:
	rm -rf report/*.png report/*.csv __pycache__ .pytest_cache
