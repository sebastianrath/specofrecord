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
