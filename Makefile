.PHONY: test coverage reproduce clean
PY = PYTHONPATH=src python

test:
	pytest -q

# Coverage report + static, secret-free badge (step 26). Runs the suite
# under coverage.py, prints the per-file report, enforces the floor from
# .coveragerc ([report] fail_under) — the SAME floor CI enforces — then
# regenerates report/coverage.svg + report/coverage_summary.json from the
# measured total. The badge is a committed SVG, not a third-party service,
# so it needs no upload token and stays verifiable from the repo alone.
coverage:
	coverage erase
	coverage run --source=sketchflow -m pytest -q
	coverage report -m
	coverage json -o report/coverage.json
	$(PY) -m sketchflow.covbadge

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
