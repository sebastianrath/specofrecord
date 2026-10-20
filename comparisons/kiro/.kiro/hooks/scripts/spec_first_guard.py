"""Pre Tool Use guard for Kiro: code under out/ may change only together with the spec.

Kiro runs this before a write tool and passes the event as JSON on stdin. Exit 0 lets the
write go ahead; any other exit blocks it and stderr is shown to the agent.

What it checks: if the target path is under out/, at least one file under .kiro/specs/ must
differ from HEAD (staged, unstaged or untracked). It cannot tell WHICH requirement changed or
whether the code change matches it.
"""
import json
import subprocess
import sys

GUARDED = ("out/",)
SPECS = ".kiro/specs/"


def target_path(event):
    tool_input = event.get("tool_input") or {}
    # Guess: the write tool's argument name is not documented; try the likely ones.
    for key in ("path", "file_path", "filePath", "target"):
        if isinstance(tool_input.get(key), str):
            return tool_input[key].replace("\\", "/")
    return ""


def changed_spec_files():
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", SPECS],
        capture_output=True, text=True, check=False,
    ).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0  # not a tool event we understand; do not block
    path = target_path(event)
    if not any(g in path for g in GUARDED):
        return 0
    if changed_spec_files():
        return 0
    sys.stderr.write(
        "Blocked: you are editing app code (%s) but no file under .kiro/specs/ has changed "
        "since the last commit. Change the acceptance criterion in requirements.md first "
        "(the bodies table is Requirement 1), or open a bugfix spec if the code is wrong and "
        "the requirement is right. See .kiro/steering/spec-first.md.\n" % path
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
