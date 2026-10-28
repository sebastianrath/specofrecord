"""Tests for how the tool names its own command in the messages it prints (`invoke.CMD`): `sor` from the plugin, otherwise the path of the tool. A checkout of
this repository keeps it in tools/py, and a copy that sits directly in a tools folder (the plugin's, or one vendored into a project) in tools/.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. The copies live in temporary folders, and each answer comes from a fresh interpreter.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LIBRARY = os.path.join(HERE, 'sorlib')


def command_of(tool_folder):
    """`invoke.CMD` as a copy of the tool in `tool_folder` (the folder that holds sorlib/) works it out."""
    code = 'import sys; sys.path.insert(0, sys.argv[1]); from sorlib import invoke; print(invoke.CMD)'
    done = subprocess.run([sys.executable, '-c', code, tool_folder], capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class TestTheNameOfTheCommand(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)

    def copy_library(self, *parts):
        target = os.path.join(self.root, *parts, 'sorlib')
        shutil.copytree(LIBRARY, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        return os.path.dirname(target)

    def test_a_checkout_of_this_repository_names_the_tool_in_tools_py(self):
        self.assertEqual(command_of(HERE), 'python3 tools/py/sor.py')
        self.assertTrue(os.path.isfile(os.path.join(REPO, 'tools', 'py', 'sor.py')))   # and that is where the command points

    def test_a_copy_that_sits_directly_in_a_tools_folder_names_tools_sor_py(self):
        self.assertEqual(command_of(self.copy_library('project', 'tools')), 'python3 tools/sor.py')

    def test_a_folder_that_is_only_called_py_is_not_a_checkout(self):
        self.assertEqual(command_of(self.copy_library('vendor', 'py')), 'python3 tools/sor.py')   # no js beside it
        os.makedirs(os.path.join(self.root, 'vendor', 'js'))
        self.assertEqual(command_of(os.path.join(self.root, 'vendor', 'py')), 'python3 tools/py/sor.py')   # the same folder with js beside it is the layout

    def test_the_plugin_names_sor_whatever_the_folder_is_called(self):
        folder = self.copy_library('plugin', 'tools')
        os.makedirs(os.path.join(self.root, 'plugin', '.claude-plugin'))
        with open(os.path.join(self.root, 'plugin', '.claude-plugin', 'plugin.json'), 'w', encoding='utf8') as fh:
            fh.write('{}\n')
        self.assertEqual(command_of(folder), 'sor')


class TestReplacingAFileThatIsRead(unittest.TestCase):
    """Windows refuses to replace a file while another process has it open; the files the tool writes (claims, bindings, the lock) are read without any mutex,
    so a write has to wait for the reader for a moment instead of failing."""
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='sor-replace-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        sys.path.insert(0, HERE)
        self.addCleanup(sys.path.remove, HERE)
        from sorlib import invoke
        self.invoke = invoke
        self.path = os.path.join(self.root, 'claims.json')
        self.tmp = self.path + '.1.tmp'
        for name, text in ((self.path, 'old'), (self.tmp, 'new')):
            with open(name, 'w') as fh:
                fh.write(text)

    def test_a_reader_that_lets_go_after_a_moment_does_not_stop_the_write(self):
        import threading
        import time
        reader = open(self.path)
        timer = threading.Timer(0.15, reader.close)
        timer.start()
        self.addCleanup(reader.close)
        self.addCleanup(timer.cancel)
        self.invoke.replace_file(self.tmp, self.path)
        with open(self.path) as fh:
            self.assertEqual(fh.read(), 'new')
        self.assertFalse(os.path.exists(self.tmp))
        time.sleep(0.2)

    def test_an_ordinary_replace_is_one(self):
        self.invoke.replace_file(self.tmp, self.path)
        with open(self.path) as fh:
            self.assertEqual(fh.read(), 'new')

    def test_an_error_that_is_not_a_reader_is_raised(self):
        os.remove(self.tmp)
        with self.assertRaises(OSError):
            self.invoke.replace_file(self.tmp, self.path)


if __name__ == '__main__':
    unittest.main()
