.PHONY: test reproduce clean
test:
	pytest -q
reproduce:
	@echo "reproduce target grows as phases P4-P6 land (steps 13-24). Today: smoke only."
	python -c "import sketchflow; print('sketchflow', sketchflow.__version__, 'ok')"
clean:
	rm -rf report/*.png report/*.csv __pycache__ .pytest_cache
