#!/bin/sh
# Keeps the plugin and the VS Code extension self-contained: copies the canonical tools (../tools) into both, and
# regenerates the skill's format cheat sheet from ../SPEC.md. `tools/` and SPEC.md stay the places to edit.
#   sh plugins/sync-tools.sh           copy
#   sh plugins/sync-tools.sh --check   fail (exit 1) when a copy is out of date
# The extension copy (editors/vscode/tools) is the JavaScript tool (tools/js: sor.js and sorlib/*.js, not its tests) that the extension
# always runs, so it needs no Python; it is left alone when this repository has no editors/vscode. The plugin carries the Python tool.
set -e
here=$(cd "$(dirname "$0")" && pwd)
src="$here/../tools"
spec="$here/../SPEC.md"
plugin="$here/specofrecord"
vscode="$here/../editors/vscode"
sheet_rel="skills/specofrecord/reference/format-cheatsheet.md"

copy_tools() {  # copy_tools <folder>: the tool as it is shipped, in <folder>/tools
  mkdir -p "$1/tools/sorlib"
  cp "$src/sor.py" "$1/tools/sor.py"
  for f in "$src"/sorlib/*.py; do cp "$f" "$1/tools/sorlib/"; done
}

copy_js_tool() {  # copy_js_tool <folder>: the JavaScript tool the editor extension runs, in <folder>/tools
  mkdir -p "$1/tools/sorlib"
  cp "$src/js/sor.js" "$1/tools/sor.js"
  for f in "$src"/js/sorlib/*.js; do cp "$f" "$1/tools/sorlib/"; done
}

build() {  # build <folder>: everything this script generates, laid out as inside the plugin
  copy_tools "$1"
  mkdir -p "$1/skills/specofrecord/reference"
  {
    printf '# Spec of Record: the format cheat sheet\n\n'
    printf 'Copied from SPEC.md of Spec of Record by Sebastian Rath (sebastianrath.io), licensed CC BY 4.0\n'
    printf '(https://creativecommons.org/licenses/by/4.0/). The full format is in SPEC.md of the project.\n\n'
    sed -n '/^## Cheat sheet/,/^---$/p' "$spec" | sed '1d;$d'
  } > "$1/$sheet_rel"
}

has_extension=0
[ -f "$vscode/package.json" ] && has_extension=1

if [ "$1" = "--check" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  build "$tmp"
  bad=0
  diff -r -q -x __pycache__ "$tmp/tools" "$plugin/tools" >&2 || bad=1
  diff -q "$tmp/$sheet_rel" "$plugin/$sheet_rel" >&2 || bad=1
  [ -x "$plugin/bin/sor" ] || { echo "plugins/specofrecord/bin/sor is not executable (the plugin puts bin/ on the PATH): chmod +x it" >&2; bad=1; }
  if [ "$bad" = 0 ]; then
    echo "plugin tools and cheat sheet are in sync"
  else
    echo "the plugin is out of date: run sh plugins/sync-tools.sh" >&2
  fi
  bad_extension=0
  if [ "$has_extension" = 1 ]; then
    copy_js_tool "$tmp/vscode"
    diff -r -q "$tmp/vscode/tools" "$vscode/tools" >&2 || bad_extension=1
    if [ "$bad_extension" = 0 ]; then
      echo "extension tools are in sync"
    else
      echo "the extension copy of tools/ is out of date: run sh plugins/sync-tools.sh" >&2
    fi
  fi
  [ "$bad" = 0 ] && [ "$bad_extension" = 0 ] && exit 0
  exit 1
fi

rm -rf "$plugin/tools"
build "$plugin"
echo "copied tools/ and the cheat sheet into plugins/specofrecord"
if [ "$has_extension" = 1 ]; then
  rm -rf "$vscode/tools"
  copy_js_tool "$vscode"
  echo "copied tools/js into editors/vscode"
fi
