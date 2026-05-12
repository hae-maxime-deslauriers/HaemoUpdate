#!/bin/bash
TESTS_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
pytest --cov=src.haemo_update --cov-report=term-missing --cov-branch "${TESTS_DIR}/tests.py"
