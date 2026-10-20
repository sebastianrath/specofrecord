#!/bin/sh
# Keeps the plugin self-contained: copies the canonical tools (../tools) into it, and regenerates the
# skill's format cheat sheet from ../SPEC.md. `tools/` and SPEC.md stay the places to edit.
#   sh plugins/sync-tools.sh           copy
#   sh plugins/sync-tools.sh --check   fail (exit 1) when the plugin's copies are out of date
set -e
here=$(cd "$(dirname "$0")" && pwd)
src="$here/../tools"
spec="$here/../SPEC.md"
plugin="$here/specofrecord"
sheet_rel="skills/workflow/reference/format-cheatsheet.md"

build() {  # build <folder>: everything this script generates, laid out as inside the plugin
  mkdir -p "$1/tools/sorlib" "$1/skills/workflow/reference"
  cp "$src/sor.py" "$1/tools/sor.py"
  for f in "$src"/sorlib/*.py; do cp "$f" "$1/tools/sorlib/"; done
  {
    printf '# Spec of Record: the format cheat sheet\n\n'
    printf 'Copied from SPEC.md of Spec of Record by Sebastian Rath (sebastianrath.io), licensed CC BY 4.0\n'
    printf '(https://creativecommons.org/licenses/by/4.0/). The full format is in SPEC.md of the project.\n\n'
    sed -n '/^## Cheat sheet/,/^---$/p' "$spec" | sed '1d;$d'
  } > "$1/$sheet_rel"
}

if [ "$1" = "--check" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  build "$tmp"
  bad=0
  diff -r -q -x __pycache__ "$tmp/tools" "$plugin/tools" >&2 || bad=1
  diff -q "$tmp/$sheet_rel" "$plugin/$sheet_rel" >&2 || bad=1
  [ -x "$plugin/bin/sor" ] || { echo "plugins/specofrecord/bin/sor is not executable (the plugin puts bin/ on the PATH): chmod +x it" >&2; bad=1; }
  if [ "$bad" = 0 ]; then echo "plugin tools and cheat sheet are in sync"; exit 0; fi
  echo "the plugin is out of date: run sh plugins/sync-tools.sh" >&2
  exit 1
fi

rm -rf "$plugin/tools"
build "$plugin"
echo "copied tools/ and the cheat sheet into plugins/specofrecord"
