"""Fails on purpose: the Python tests moved from tools/ to tools/py.

`python3 -m unittest discover -s tools -p 'test_*.py'`, the old command, used to run them. Since the move it finds no test and reports `Ran 0 tests ... OK`
with exit code 0 (Python 3.9, which CI uses), a green run that checked nothing. This file is what the old command finds instead, with `-p 'test_*.py'`
and with `-p 'test_sor*.py'`, and it fails with the new command. `discover -s tools/py` does not look in this folder, so the real run is not affected.
"""
import unittest


class TestTheTestsMoved(unittest.TestCase):
    def test_run_the_tests_from_tools_py(self):
        self.fail("The Python tests are in tools/py now, and this command found none of them. "
                  "Run: python3 -m unittest discover -s tools/py -p 'test_*.py'")


if __name__ == '__main__':
    unittest.main()
