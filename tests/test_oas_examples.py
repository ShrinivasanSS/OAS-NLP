from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from oas_service import extract_operations, load_oas


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def test_examples_have_operations():
    example_files = sorted(EXAMPLES_DIR.glob("*.yaml"))
    assert example_files, "No example OAS files found."
    for path in example_files:
        oas = load_oas(str(path))
        operations = extract_operations(oas)
        assert operations, f"Expected operations in {path.name}"
