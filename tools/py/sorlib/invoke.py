"""How this tool is called in the messages it prints, and how it reads its environment variables.

`sor` is the command when it runs from the Claude Code plugin (whose bin/ is on the PATH), otherwise the
relative path of a checkout. Agents copy these commands. Variables are SOR_<NAME>."""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(_HERE)), '.claude-plugin', 'plugin.json'))
# A checkout of this repository keeps the tool in tools/py, with the JavaScript tool beside it in tools/js. A copy of the tool somewhere else (the plugin's,
# vendored into a project) sits directly in a tools folder, with no js beside it, even when a folder on the way is called py.
_TOOL = os.path.dirname(_HERE)
CHECKOUT = os.path.basename(_TOOL) == 'py' and os.path.isdir(os.path.join(os.path.dirname(_TOOL), 'js'))
CMD = 'sor' if PLUGIN else 'python3 tools/py/sor.py' if CHECKOUT else 'python3 tools/sor.py'


def getenv(name):
    """SOR_<name>, else ''."""
    return os.environ.get('SOR_' + name) or ''


def command_lines(command, in_body=None):
    """The lines of a shell command line as the shell reads them: a backslash that ends a line, and is not itself escaped by another before it (an odd run of them),
    joins the line with the next (`sor lock \\` and, below it, `--already-fits x` is one command), so a guard that reads line by line does not see two. `in_body()`
    says whether the caller is inside a here-document: its lines are data, are never joined and never join the line before them, so its terminator is still seen.
    A caller that tracks here-documents consumes this as it goes, so that `in_body` is asked when each line is read."""
    carry = ''
    for raw in command.split('\n'):
        if in_body is not None and in_body():
            yield raw
            continue
        text = raw[:-1] if raw.endswith('\r') else raw
        if (len(text) - len(text.rstrip('\\'))) % 2:
            carry += text[:-1]
            continue
        yield carry + raw
        carry = ''
    if carry:
        yield carry
