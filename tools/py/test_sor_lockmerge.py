"""Tests for `sor merge-lock`, the merge driver for sor-lock.json (SPEC §11): the merge by entry, the command, and a real `git merge` through it.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser. The git test is skipped where git is not installed.
"""
import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                          # noqa: E402  (its helpers only)
from sorlib import cli                           # noqa: E402
from sorlib import lock as lockfile              # noqa: E402

SOR = os.path.join(HERE, 'sor.py')


def read_rel(root, rel):
    return base.read(os.path.join(root, *rel.split('/')))


# Nothing that says who runs the tool: a command run from a Claude Code session renews that session's claims, and these tests touch only temporary folders.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith(('SOR_', 'CLAUDE_'))}
CLEAN_ENV['PYTHONDONTWRITEBYTECODE'] = '1'


def glue(code):
    return {'kind': 'glue', 'code': code}


def item(text):
    return {'kind': 'item', 'text': text}


class TestMergeEntries(unittest.TestCase):
    def test_an_entry_inserted_next_to_a_changed_one_merges(self):
        """The case git reports as a conflict: this side added `glue:b` right before the entry `glue:c` that the other side changed."""
        merged, left_out = lockfile.merge_entries({'glue:a': glue('1'), 'glue:c': glue('3')},
                                                  {'glue:a': glue('1'), 'glue:b': glue('2'), 'glue:c': glue('3')},
                                                  {'glue:a': glue('1'), 'glue:c': glue('9')})
        self.assertEqual(merged, {'glue:a': glue('1'), 'glue:b': glue('2'), 'glue:c': glue('9')})
        self.assertEqual(left_out, [])

    def test_the_same_change_on_both_sides_is_kept(self):
        merged, left_out = lockfile.merge_entries({'k': item('a')}, {'k': item('b')}, {'k': item('b')})
        self.assertEqual((merged, left_out), ({'k': item('b')}, []))

    def test_an_entry_changed_in_different_ways_is_left_out_and_named_and_the_rest_merges(self):
        merged, left_out = lockfile.merge_entries({'k': item('a'), 'm': item('1')}, {'k': item('b'), 'm': item('2')}, {'k': item('c'), 'm': item('1')})
        self.assertEqual(merged, {'m': item('2')})
        self.assertEqual(left_out, ['k'])

    def test_a_removal_on_one_side_wins_over_no_change_and_loses_to_a_change(self):
        merged, left_out = lockfile.merge_entries({'k': item('a'), 'm': item('1')}, {'m': item('1')}, {'k': item('a'), 'm': item('1')})
        self.assertEqual((merged, left_out), ({'m': item('1')}, []))
        merged, left_out = lockfile.merge_entries({'k': item('a')}, {}, {'k': item('b')})
        self.assertEqual((merged, left_out), ({}, ['k']))

    def test_an_entry_added_on_both_sides_differently_is_left_out(self):
        merged, left_out = lockfile.merge_entries({}, {'k': item('a')}, {'k': item('b')})
        self.assertEqual((merged, left_out), ({}, ['k']))

    def test_a_clause_and_its_per_target_lines_come_from_one_side(self):
        line = lambda code: {'kind': 'code', 'of': 'greet/hello', 'target': 'py', 'code': code, 'built': 'x'}
        clause = lambda text: {'kind': 'item', 'text': text}
        was = {'greet/hello': clause('1'), 'greet/hello@py': line('a')}
        merged, left_out = lockfile.merge_entries(was, {'greet/hello': clause('2'), 'greet/hello@py': line('a')},
                                                  {'greet/hello': clause('1'), 'greet/hello@py': line('b')})
        self.assertEqual((merged, left_out), ({}, ['greet/hello']), 'text from one side and code from the other would be a state nobody locked')
        merged, left_out = lockfile.merge_entries(was, was, {'greet/hello': clause('1'), 'greet/hello@py': line('b')})
        self.assertEqual((merged, left_out), ({'greet/hello': clause('1'), 'greet/hello@py': line('b')}, []))


class TestParseText(unittest.TestCase):
    def test_conflict_markers_damage_and_a_newer_format_are_refused(self):
        for text in ('{\n<<<<<<< HEAD\n"a": {}\n=======\n"a": {"x": 1}\n>>>>>>> b\n}\n', '{"a": {}, "a": {}}', 'nope', '[]',
                     '{"*format": 99, "a": {}}', '{"*format": true, "a": {}}'):
            with self.subTest(text=text[:20]):
                with self.assertRaises(lockfile.LockFormatError):
                    lockfile.parse_text(text, 'the version')

    def test_the_marker_is_not_an_entry(self):
        self.assertEqual(lockfile.parse_text(lockfile.render({'glue:a': glue('1')}), 'v'), {'glue:a': glue('1')})


class TestTheCommand(base.Case):
    def files(self, base_entries, ours, theirs):
        paths = []
        for name, entries in (('base', base_entries), ('ours', ours), ('theirs', theirs)):
            paths.append(base.write(self.dir, name, lockfile.render(entries) if entries is not None else ''))
        return paths

    def run_sor(self, *paths):
        done = subprocess.run([sys.executable, SOR, 'merge-lock', *paths], capture_output=True, text=True, encoding='utf8', env=CLEAN_ENV)
        return done.returncode, done.stderr

    def test_it_writes_the_merge_over_ours_and_names_what_it_left_out_and_exits_1_so_git_shows_a_conflict(self):
        paths = self.files({'a': item('1'), 'b': item('1')}, {'a': item('2'), 'b': item('2')}, {'a': item('1'), 'b': item('3')})
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 1, err)
        self.assertEqual(lockfile.parse_text(read_rel(self.dir, 'ours'), 'ours'), {'a': item('2')})
        self.assertIn('left out, lock them again: b', err)

    def test_it_exits_0_when_nothing_is_left_out(self):
        paths = self.files({'a': item('1'), 'b': item('1')}, {'a': item('2'), 'b': item('1')}, {'a': item('1'), 'b': item('3')})
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 0, err)
        self.assertEqual(lockfile.parse_text(read_rel(self.dir, 'ours'), 'ours'), {'a': item('2'), 'b': item('3')})

    def test_entries_that_cannot_be_written_leave_ours_as_it_was(self):
        """`render` raises LockWriteError for entries it cannot write (a clause named like another clause's per-target line) and ValueError for a format
        they need that this tool lacks: the command says so and exits 1 before it opens OURS."""
        paths = self.files({'k': item('1')}, {'k': item('2')}, {'k': item('1')})
        before = read_rel(self.dir, 'ours')
        for error in (lockfile.LockWriteError('k@py is a clause of its own'), ValueError('these entries need lock format 5')):
            with self.subTest(error=type(error).__name__), mock.patch.object(lockfile, 'render', side_effect=error), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.cmd_merge_lock(argparse.Namespace(base=paths[0], ours=paths[1], theirs=paths[2])), 1)   # not main(): it renews session claims
            self.assertIn('cannot be written', err.getvalue())
            self.assertEqual(read_rel(self.dir, 'ours'), before)

    def test_the_legacy_root_key_is_the_root_on_every_side(self):
        paths = self.files({'CLAUSES': item('1')}, {'ROOT': item('2')}, {'CLAUSES': item('1')})
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 0, err)
        self.assertEqual(lockfile.parse_text(read_rel(self.dir, 'ours'), 'ours'), {'ROOT': item('2')})

    def test_an_empty_base_is_an_add_add_merge(self):
        paths = self.files(None, {'a': item('1')}, {'b': item('1')})
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(lockfile.parse_text(read_rel(self.dir,'ours'), 'ours')), ['a', 'b'])

    def test_it_refuses_what_it_cannot_read_and_leaves_ours_alone(self):
        paths = self.files({'a': item('1')}, {'a': item('2')}, {'a': item('1')})
        base.write(self.dir, 'theirs', '{\n<<<<<<< HEAD\n}\n')
        before = read_rel(self.dir,'ours')
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 1)
        self.assertIn('conflict markers', err)
        self.assertEqual(read_rel(self.dir,'ours'), before)

    def test_an_empty_side_is_refused(self):
        paths = self.files({'a': item('1')}, {'a': item('2')}, None)
        code, err = self.run_sor(*paths)
        self.assertEqual(code, 1)
        self.assertIn('theirs version is empty', err)


@unittest.skipUnless(shutil.which('git'), 'git is not installed')
class TestAGitMergeThroughTheDriver(base.Case):
    """The merge that stranded a claim in practice: one side inserted an entry next to an entry the other side changed."""

    def git(self, *args, check=True):
        env = dict(CLEAN_ENV, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t', GIT_CONFIG_NOSYSTEM='1')
        done = subprocess.run(['git', '-c', 'commit.gpgsign=false', '-c', f'core.hooksPath={os.devnull}', *args], cwd=self.dir, env=env,
                              capture_output=True, text=True, encoding='utf8')
        if check and done.returncode:
            self.fail(f'git {" ".join(args)}: {done.stdout}{done.stderr}')
        return done

    def set_up_repo(self):
        self.git('init', '-q')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')   # `init -b` needs git 2.28
        base.write(self.dir, '.gitattributes', 'sor/sor-lock.json merge=sor-lock\n')
        base.write(self.dir, 'sor/sor-lock.json', lockfile.render({'glue:a': glue('1'), 'glue:c': glue('3')}))
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'base')
        self.git('checkout', '-q', '-b', 'side')
        base.write(self.dir, 'sor/sor-lock.json', lockfile.render({'glue:a': glue('1'), 'glue:c': glue('9')}))
        self.git('commit', '-q', '-am', 'side changes c')
        self.git('checkout', '-q', 'main')
        base.write(self.dir, 'sor/sor-lock.json', lockfile.render({'glue:a': glue('1'), 'glue:b': glue('2'), 'glue:c': glue('3')}))
        self.git('commit', '-q', '-am', 'main inserts b')

    def test_git_alone_conflicts_and_the_driver_merges_it(self):
        self.set_up_repo()
        alone = self.git('merge', '--no-edit', 'side', check=False)   # the textual conflict this driver exists for; a git that merges it cleanly needs no driver here
        self.git('merge', '--abort') if alone.returncode else self.git('reset', '-q', '--hard', 'ORIG_HEAD')
        driver = f'"{sys.executable}" "{SOR}" merge-lock %O %A %B'.replace('\\', '/')
        self.git('config', 'merge.sor-lock.driver', driver)
        merged = self.git('merge', '--no-edit', 'side', check=False)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        entries = lockfile.parse_text(read_rel(self.dir,'sor/sor-lock.json'), 'merged')
        self.assertEqual(entries, {'glue:a': glue('1'), 'glue:b': glue('2'), 'glue:c': glue('9')})


if __name__ == '__main__':
    unittest.main()
