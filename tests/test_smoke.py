"""Step 0 smoke test: the package imports and advertises its version.
Real correctness tests (never-undercount, error<=eN, top-k exactness) arrive
with each structure per plan.json."""
import sketchflow


def test_package_imports():
    assert sketchflow.__version__
    assert sketchflow.__author__ == "neil-cipher"
