"""Starts coverage in every Python process that tools/py/coverage.sh starts, the tests' own and the programs they run
(`sor` as a subprocess, the hooks): coverage reads COVERAGE_PROCESS_START, and does nothing when it is not set."""
try:
    import coverage
    coverage.process_startup()
except ImportError:
    pass
