#!/usr/bin/env python3
"""Runs the Spec of Record CLI: python sor.py <command>. See sorlib/cli.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run(fn, *args):
    """fn(*args) as an exit code. A reader that closes the pipe early (`sor status | head -1`) ends the program
    quietly instead of with a traceback, as `ls | head -1` does."""
    try:
        code = fn(*args)
        if sys.stdout is not None:
            sys.stdout.flush()   # what is still buffered fails here, where it can be caught, not when Python exits
        return code
    except BrokenPipeError:
        if sys.stdout is not None:   # Python flushes it once more at exit and would complain again: point it at devnull
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141   # 128 + SIGPIPE, what a shell reports for a program that a closed pipe ended


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'hook' and sys.argv[2] in ('pre-edit', 'post-read', 'session-start', 'pre-bash', 'session-end'):
        # A hook runs on every edit and read, in every project: skip the CLI (it pulls in the test
        # runner, about 150 ms) and load only the hook.
        for stream in (sys.stdout, sys.stderr):   # what sorlib.cli.main does for every other command
            try:
                stream.reconfigure(encoding='utf-8')
            except AttributeError:
                pass
        from sorlib import hook  # noqa: E402
        sys.exit(run(hook.run, sys.argv[2]))
    from sorlib.cli import main  # noqa: E402
    sys.exit(run(main))
