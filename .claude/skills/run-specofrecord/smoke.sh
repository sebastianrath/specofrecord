#!/bin/sh
# Drives the sor command on a temporary copy of examples/solar-system and checks each result.
# Usage, from the repository root:  sh .claude/skills/run-specofrecord/smoke.sh
# It never touches examples/ (CLAUDE.md forbids claim and lock there), and it removes its copy at the end.
set -u
root=$(cd "$(dirname "$0")/../../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -R "$root/examples/solar-system" "$tmp/p"
sor() { python3 "$root/tools/py/sor.py" -C "$tmp/p" "$@"; }
bad=0
expect() {  # expect <exit code wanted> <label> <command...>: runs the command, shows the first lines of its output
  want=$1; label=$2; shift 2
  out=$("$@" 2>&1); got=$?
  if [ "$got" = "$want" ]; then echo "ok    $label (exit $got)"; else echo "FAIL  $label (exit $got, wanted $want)"; bad=1; fi
  printf '%s\n' "$out" | head -${LINES_SHOWN:-3} | sed 's/^/        /'
}

expect 0 "parts --tree lists every part"       sor parts --tree
expect 0 "status says everything agrees"        sor status
expect 0 "check passes (notes do not count)"    sor check
expect 0 "show clock prints clauses and code"   sor show clock
expect 0 "markers finds the code of a line"     sor markers out/index.html:137
expect 0 "claim clock as smoke"                 sor claim clock --as smoke
expect 3 "a second agent is refused"            sor claim clock --as other
expect 3 "a clause that shares its code is refused" sor claim year --as other
expect 2 "lock is refused with no test results" sor lock --as smoke
expect 0 "release smoke's claims"               sor release --all --as smoke
expect 0 "test --list shows what a run would do" sor test --list

if [ "$bad" = 0 ]; then echo "smoke passed"; else echo "smoke FAILED"; exit 1; fi
