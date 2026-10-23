#!/bin/sh
# Line and branch coverage of the tool over its own tests, per file, with the lines no test reaches.
#   sh tools/coverage.sh              run the tests under coverage and print the report
#   sh tools/coverage.sh --skip-covered      any option of `coverage report` is passed on
# `coverage` is a development tool only (the tool itself uses the standard library): it is installed once into
# .venv-coverage, which git ignores. Subprocesses (`sor` run as a program, the hooks) are measured too.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
cd "$root"
venv="$root/.venv-coverage"
if [ ! -x "$venv/bin/python" ]; then
  python3 -m venv "$venv"
  "$venv/bin/python" -m pip install --quiet coverage
fi
py="$venv/bin/python"
rm -f .coverage .coverage.*
COVERAGE_PROCESS_START="$root/.coveragerc" PYTHONPATH="$here/coverage_site${PYTHONPATH:+:$PYTHONPATH}" \
  "$py" -m unittest discover -s tools/py -p 'test_*.py'
"$py" -m coverage combine --quiet
"$py" -m coverage report "$@"
