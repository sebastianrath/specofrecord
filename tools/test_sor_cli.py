"""Tests for the command line as agents meet it: a pipe that closes early, `--as` on a command that does not take it,
`sor check` for some parts, the refusal of `sor new` for a name an item has, and what the edit guard does to the
skeleton `sor new` writes.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import cli, hook, views               # noqa: E402
from sorlib.markers import Scan                   # noqa: E402
from sorlib.model import Project                  # noqa: E402
from test_sor_flows import Flow, reason, replace_in   # noqa: E402

doc, write, read, tree = base.doc, base.write, base.read, base.tree


# --- a pipe that closes early ---------------------------------------------------------------------------------------

@unittest.skipIf(os.name == 'nt', 'Windows reports a closed pipe as another error')
class TestAPipeThatClosesEarly(unittest.TestCase):
    """`sor status | head -1`: the reader has what it wanted and goes. The program ends without a traceback."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.big = os.path.realpath(tmp.name)
        base.make_project(cls.big)
        for n in range(1300):   # unfilled skeletons: `sor parts`, `sor check` and `sor status` each print more than any pipe holds
            write(cls.big, f'sor/part-{n}.md', views.PART.format(title=f'Part {n}', limit=7, why='It is here for a reason ' * 4))

    def program(self, project, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', NO_COLOR='1')
        return subprocess.Popen([sys.executable, base.SOR, '-C', project, *args], cwd=base.REPO, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_a_reader_that_stops_after_one_line_ends_the_program_quietly(self):
        for command in ('status', 'parts', 'check'):
            with self.subTest(command=command):
                everything = base.run_process(self.big, command)[1]
                self.assertGreater(len(everything), 2 * 65536, 'the output must be more than a pipe holds, or nothing breaks')
                proc = self.program(self.big, command)
                first = proc.stdout.readline()
                proc.stdout.close()
                err = proc.stderr.read().decode('utf8')
                proc.stderr.close()
                self.assertEqual(first.decode('utf8'), everything.splitlines(True)[0])
                self.assertEqual(err, '')
                self.assertEqual(proc.wait(timeout=60), 141)   # 128 + SIGPIPE, what a shell reports for `ls | head -1`

    def test_text_still_in_the_buffer_when_the_reader_is_gone_is_dropped_quietly_too(self):
        # a short output is written when Python exits, which is where a closed pipe used to be reported
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base.make_project(tmp.name)
        proc = self.program(tmp.name, 'parts')
        proc.stdout.close()   # the child needs far longer than this to start
        err = proc.stderr.read().decode('utf8')
        proc.stderr.close()
        self.assertEqual(err, '')
        self.assertIn(proc.wait(timeout=60), (0, 141))   # 0 only if the child won the race and wrote before the close


# --- --as on a command that does not take it ------------------------------------------------------------------------

class TestAsOnTheWrongCommand(Flow):
    """`--as NAME` is for claim, lock and release. An agent that puts it on another command is told so."""

    HINT = '`--as NAME` is for claim, lock and release only'

    def test_a_command_that_does_not_take_it_says_which_commands_do(self):
        self.greet_project()
        for args in (('new', 'audio'), ('status',), ('check',), ('parts',), ('needs',), ('changes',), ('test',),
                     ('markers',), ('show', 'greet')):
            for flag in (['--as', 'a5'], ['--as=a5']):
                with self.subTest(command=args[0], flag=flag):
                    before = tree(self.dir)
                    code, out, err = self.sor(*args, *flag)
                    self.assertEqual((code, out), (2, ''))
                    self.assertIn('unrecognized arguments: ' + flag[0], err)   # a command with a positional takes the name as it
                    self.assertIn(self.HINT, err)
                    self.assertIn(f'`{args[0]}` does not take it', err)
                    self.assertEqual(tree(self.dir), before)

    def test_the_commands_are_found_in_the_parser_not_written_into_the_message(self):
        self.greet_project()
        real = cli.build_parser

        def with_as_on_status():
            ap = real()
            sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
            sub.choices['status'].add_argument('--as', dest='agent')
            return ap

        with mock.patch.object(cli, 'build_parser', with_as_on_status):
            code, _, err = self.sor('check', '--as', 'a5')
        self.assertEqual(code, 2)
        self.assertIn('`--as NAME` is for claim, lock, release and status only', err)

    def test_another_unknown_flag_gets_no_hint_about_as(self):
        self.greet_project()
        code, _, err = self.sor('status', '--bogus')
        self.assertEqual(code, 2)
        self.assertIn('unrecognized arguments: --bogus', err)
        self.assertNotIn('--as', err)

    def test_the_commands_that_take_it_still_do(self):
        self.greet_project()
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'a5')[0], 0)
        self.assertEqual(self.sor('lock', 'greet/hello', '--as', 'a5', '--allow-incomplete')[0], 0)
        self.assertEqual(self.sor('release', '--all', '--as', 'a5')[0], 0)


# --- sor check for some parts ---------------------------------------------------------------------------------------

BROKEN = '- **loud** - Louder than {%s.nothing}.'
ASK = '  open: how loud?'
ROOT_BROKEN = doc('Demo', 'A project the tests use.', rules=['- **out-of-scope** - Nothing like {gone.away}.'])


def sound(title, name, ask=True, broken=True):
    """A part with a rule that points at nothing (a problem), a question (a note) and a test."""
    return doc(title, 'It sounds.', rules=[BROKEN % name if broken else '- **loud** - Loud.'] + ([ASK] if ask else []),
               tests=['- **loud** - is loud.', '  expect: ok', '  manual: by hand'])   # manual: so that no "never run" note adds to the count


class TestCheckForSomeParts(Flow):
    """`sor check audio ui`: the problems and notes of those parts and the parts inside them, and an exit code for those."""

    def setUp(self):
        super().setUp()
        self.project({'audio': sound('Audio', 'audio'), 'audio/mixer': sound('Mixer', 'mixer'),
                      'audio-fx': sound('Effects', 'fx'), 'ui': sound('Ui', 'ui', ask=False),
                      'calm': sound('Calm', 'calm', broken=False), 'ok': sound('Ok', 'ok', ask=False, broken=False)},
                     root_text=ROOT_BROKEN)
        write(self.dir, 'sor/audio.tests.md', '## Tests\n- **loud** - is loud twice.\n  expect: <fill in: how>\n')
        write(self.dir, 'out/app.js', '// @clause audio/ghost\nx();\n// @clause end\n// @clause audio/loud\ny();\n// @clause end\n'
              '// @clause ui/nothing\nx();\n// @clause end\nz();\n')
        write(self.dir, 'out/ok.js', '// @clause ok/loud\nx();\n// @clause end\n')

    def check(self, *args):
        return self.sor('check', *args)

    def test_without_parts_it_lists_everything_as_it_always_did(self):
        project = Project(self.dir)
        found = cli.problems(project, Scan(project))
        code, out, _ = self.check()
        self.assertEqual(code, 2)
        self.assertEqual(out.splitlines()[:len(found)], [str(p) for p in found])
        self.assertIn('7 parts, ', out)
        for where in ('SPECOFRECORD.md', 'audio.md', 'audio.tests.md', 'audio/mixer.md', 'audio-fx.md', 'ui.md', 'out/app.js'):
            self.assertIn(where, out)

    def test_a_part_brings_the_parts_inside_it_and_not_the_ones_that_only_start_alike(self):
        code, out, err = self.check('audio')
        self.assertEqual((code, err), (2, ''))
        for where in ('audio.md:', 'audio/mixer.md:', 'audio.tests.md:', 'out/app.js:1'):   # the tests file and a marker too
            self.assertIn(where, out)
        for other in ('audio-fx', 'ui.md', 'SPECOFRECORD.md', 'ui/nothing'):
            self.assertNotIn(other, out)
        self.assertIn('2 parts, ', out)
        self.assertIn('notes (2)', out)   # the questions of audio and audio/mixer; audio-fx has one too and is left out
        self.assertRegex(out, r'\n\d+ parts, \d+ references, \d+ code regions; \d+ problem\(s\)\n')

    def test_several_parts_are_added_up_and_the_root_is_the_root_alone(self):
        out = self.check('audio/mixer', 'ui')[1]
        self.assertIn('audio/mixer.md:', out)
        self.assertIn('ui.md:', out)
        self.assertNotIn('audio.md:', out)
        out = self.check('ROOT')[1]
        self.assertIn('SPECOFRECORD.md:', out)
        self.assertIn('1 parts, ', out)
        self.assertNotIn('audio', out)

    def test_the_exit_code_follows_only_the_parts_asked_for(self):
        for parts, code in ((['ok'], 0), (['calm'], 0), (['ui'], 2), (['ok', 'audio'], 2)):
            with self.subTest(parts=parts):
                self.assertEqual(self.check(*parts)[0], code)
        out = self.check('ok')[1]
        self.assertRegex(out, r'1 parts, \d+ references, 1 code regions; 0 problem\(s\)')
        self.assertEqual(self.check('calm', '--strict')[0], 2)   # its question is a note, and --strict makes notes count
        self.assertEqual(self.check('ok', '--strict')[0], 0)

    def test_a_problem_in_code_belongs_to_the_part_of_its_region_and_loose_code_to_the_parts_in_its_file(self):
        out = self.check('audio')[1]   # audio and ui have regions in out/app.js
        self.assertIn('audio/ghost is no item, row or part', out)
        self.assertNotIn('ui/nothing', out)
        self.assertIn('code outside any @clause region', out)   # in no region at all: it is for every part with code in that file
        out = self.check('ui')[1]
        self.assertIn('ui/nothing is no item, row or part', out)
        self.assertNotIn('audio/ghost', out)
        self.assertIn('code outside any @clause region', out)
        out = self.check('ok')[1]   # out/ok.js is the only file it has code in
        self.assertNotIn('out/app.js', out)

    def test_a_part_that_does_not_exist_is_an_error_that_lists_the_closest_and_prints_no_check(self):
        for names, close in ((['audoi'], 'audio'), (['audio/mix'], 'audio/mixer'), (['audio', 'audoi'], 'audio')):
            with self.subTest(names=names):
                code, out, err = self.check(*names)
                self.assertEqual((code, out), (2, ''))
                self.assertIn('no such part: audoi' if 'audoi' in names else 'no such part: audio/mix', err)
                self.assertIn('Closest part ids: ', err)
                self.assertIn(close, err.split('Closest part ids: ')[1].strip().split(', '))
        code, out, err = self.check('zzzz')
        self.assertEqual((code, out), (2, ''))
        self.assertIn('no such part: zzzz', err)
        self.assertIn('`sor parts` lists them', err)

    def test_an_item_is_not_a_part(self):
        code, out, err = self.check('audio/loud')
        self.assertEqual((code, out), (2, ''))
        self.assertIn('no such part: audio/loud', err)

    def test_a_scoped_lock_still_looks_at_the_whole_check(self):
        # `sor lock` keeps using every problem of the files it locks: the new argument is `check`'s alone
        code, out, _ = self.sor('lock', 'ok', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertIn('problem(s) in other files do not block this lock', out)
        code, out, _ = self.sor('lock', 'ui', '--allow-incomplete')
        self.assertEqual(code, 2, out)
        self.assertIn('ui.md', out)


# --- sor new for a name an item has -----------------------------------------------------------------------------------

class TestNewForTheNameOfAnItem(Flow):
    """Ids share one namespace, so `sor new audio/mixer` is refused while audio.md has an item `mixer`. The refusal says
    where it is and how to go on."""

    def refused(self, *args):
        before = tree(self.dir)
        code, out, err = self.sor('new', *args)
        self.assertEqual(code, 2, out + err)
        self.assertIn('Nothing was written.', out)
        self.assertEqual(tree(self.dir), before, 'something was written')
        return out

    def test_the_refusal_says_where_the_item_is_and_the_two_ways_out(self):
        self.project({'audio': doc('Audio', rules=['- **mixer** - Mixes.'])})
        out = self.refused('audio/mixer')
        self.assertIn('audio/mixer is already the id of an item: the rule **mixer** in audio.md', out)
        self.assertIn('choose another name for the part', out)
        self.assertIn('rename that item first', out)

    def test_both_ways_out_work(self):
        self.project({'audio': doc('Audio', rules=['- **mixer** - Mixes.'])})
        self.refused('audio/mixer')
        self.assertEqual(self.sor('new', 'audio/mixing-desk')[0], 0)
        replace_in(os.path.join(self.spec, 'audio.md'), '**mixer**', '**mix**')
        self.assertEqual(self.sor('new', 'audio/mixer')[0], 0)

    def test_it_says_what_kind_of_item_it_is_and_where_it_is_written(self):
        self.project({'audio': doc('Audio', approach=['- **mixer** - Mixes in software.'], contract=['- gives **bus** - A bus.']),
                      'bodies': doc('Bodies', rules=['- **planets** - The planets:', '', '| Planet | Size |', '|---|---|', '| mars | 5 |', '| a/b | 6 |'])},
                     root_text=doc('Demo', rules=['- **year** - Earth takes {days: 365 days}.']))
        self.assertIn('the approach item **mixer** in audio.md', self.refused('audio/mixer'))
        self.assertIn('the contract item **bus** in audio.md', self.refused('audio/bus'))
        self.assertIn('the rule **year** in SPECOFRECORD.md', self.refused('year'))
        self.assertIn('the row **mars** of **planets** in bodies.md', self.refused('bodies/planets/mars'))
        self.assertIn('the row **a/b** of **planets** in bodies.md', self.refused('bodies/planets/a/b'))

    def test_a_part_in_a_folder_is_named_by_its_own_file(self):
        self.project({'audio/mixer': doc('Mixer', rules=['- **bus** - A bus.'])})
        self.assertIn('the rule **bus** in audio/mixer.md', self.refused('audio/mixer/bus'))


# --- the edit guard and the skeleton -------------------------------------------------------------------------------

def put(path, text):
    """Replaces a file with exactly this text (no line-end changes)."""
    with open(path, 'w', encoding='utf8', newline='') as fh:
        fh.write(text)


def write_over(path, content='x', **extra):
    """The payload Claude Code sends a hook for a Write."""
    return dict({'tool_name': 'Write', 'tool_input': {'file_path': path, 'content': content}}, **extra)


class TestWriteOverASkeleton(Flow):
    """A skeleton `sor new` wrote and nobody touched may be written whole; the same file once anyone changed it may not."""

    REFUSAL = ('Do not rewrite sor/{rel} with Write: it erases changes others made since you read it. '
               'Change the clause with Edit (one clause at a time), or MultiEdit.')

    def new(self, *args):
        code, out, err = self.sor('new', *args)
        self.assertEqual(code, 0, out + err)
        return out

    def path(self, rel):
        return os.path.join(self.spec, *rel.split('/'))

    def test_the_root_and_every_part_sor_new_wrote_may_be_written_right_away(self):
        self.new('--root')
        self.new('audio')
        self.new('audio/mixer')
        for rel in ('SPECOFRECORD.md', 'audio.md', 'audio/mixer.md'):
            with self.subTest(file=rel):
                self.assertIsNone(hook.pre_edit(write_over(self.path(rel))))

    def test_what_sor_new_writes_is_what_the_guard_compares_with(self):
        self.new('--root')
        self.new('audio/mixer', '--why', 'Mixes.')
        self.assertEqual(read(self.path('SPECOFRECORD.md')), views.skeleton('', self.dir))
        self.assertEqual(read(self.path('audio/mixer.md')), views.skeleton('audio/mixer', self.dir, 'Mixes.'))
        self.assertEqual(read(self.path('SPECOFRECORD.md')).splitlines()[0], '# ' + views.title_of(os.path.basename(self.dir)))
        self.assertEqual(read(self.path('audio/mixer.md')).splitlines()[:2], ['# Mixer', 'Why: Mixes.'])

    def test_one_placeholder_filled_in_is_a_change_and_so_is_any_other_difference(self):
        self.new('--root')
        changes = {
            'a placeholder filled in': lambda p: replace_in(p, '<fill in: what must be true>', 'It must be loud.'),
            'the why written by hand': lambda p: replace_in(p, 'Why: <fill in: one sentence on why this part exists>', 'Why: It sounds.'),
            'a line added': lambda p: put(p, read(p) + '- **mine** - written by a person.\n'),
            'a hint removed': lambda p: replace_in(p, '<!-- How it is built', '<!-- how it is built'),
            'the last newline gone': lambda p: put(p, read(p).rstrip('\n')),
            'two spaces in the why': lambda p: replace_in(p, 'Why: <fill in: one', 'Why: <fill in:  one'),
            'a blank line gone': lambda p: replace_in(p, '\n\n## Approach', '\n## Approach'),
            'windows line ends': lambda p: put(p, read(p).replace('\n', '\r\n')),
        }
        for n, (what, change) in enumerate(changes.items()):
            name = f'p{n}'
            self.new(name)
            path = self.path(name + '.md')
            self.assertIsNone(hook.pre_edit(write_over(path)), 'the skeleton itself is free to write')
            change(path)
            with self.subTest(change=what):
                self.assertEqual(reason(hook.pre_edit(write_over(path))), self.REFUSAL.format(rel=name + '.md'))

    def test_a_skeleton_made_with_a_why_is_not_the_skeleton_the_guard_knows(self):
        self.new('--root', '--why', 'A tiny game engine.')
        self.new('ui', '--why', 'The screens.')
        for rel in ('SPECOFRECORD.md', 'ui.md'):
            with self.subTest(file=rel):
                self.assertIn('Do not rewrite', reason(hook.pre_edit(write_over(self.path(rel)))))

    def test_the_root_changed_after_sor_new_is_refused_and_so_is_a_file_that_is_nothing_like_one(self):
        self.new('--root')
        root = self.path('SPECOFRECORD.md')
        replace_in(root, '<fill in: what the project will not do>', 'Nothing about tax.')
        self.assertIn('Do not rewrite sor/SPECOFRECORD.md', reason(hook.pre_edit(write_over(root))))
        put(write(self.dir, 'sor/greet.md', ''), read(self.path('SPECOFRECORD.md')))   # the root's text under another name
        self.assertIn('Do not rewrite sor/greet.md', reason(hook.pre_edit(write_over(self.path('greet.md')))))
        write(self.dir, 'sor/empty.md', '')
        self.assertIn('Do not rewrite', reason(hook.pre_edit(write_over(self.path('empty.md')))))

    def test_the_skeleton_of_another_part_is_not_the_skeleton_of_this_one(self):
        self.new('--root')
        self.new('audio')
        skeleton = read(self.path('audio.md'))
        write(self.dir, 'sor/ui.md', skeleton)   # a file called ui that holds the text for audio
        self.assertIn('Do not rewrite sor/ui.md', reason(hook.pre_edit(write_over(self.path('ui.md')))))
        write(self.dir, 'sor/audio.md', read(self.path('SPECOFRECORD.md')))   # and the other way round
        self.assertIn('Do not rewrite sor/audio.md', reason(hook.pre_edit(write_over(self.path('audio.md')))))

    def test_only_the_files_sor_new_writes_count(self):
        self.new('--root')
        self.new('audio')
        # the text `sor new` would write if these were part ids: the folder form, the older name, a file of more tests, a name no part has
        for rel in ('audio/SPECOFRECORD.md', 'audio/CLAUSES.md', 'audio.tests.md', 'audio_x.md'):
            with self.subTest(file=rel):
                write(self.dir, 'sor/' + rel, views.skeleton(rel[:-3], self.dir))
                self.assertIn('Do not rewrite', reason(hook.pre_edit(write_over(self.path(rel)))))

    def test_a_new_file_is_free_and_so_are_files_that_are_not_specs(self):
        self.new('--root')
        self.assertIsNone(hook.pre_edit(write_over(self.path('fresh.md'))))
        self.assertIn('is written only by', reason(hook.pre_edit(write_over(self.path('sor-lock.json')))))

    def test_the_skeleton_is_free_once_and_the_file_it_became_is_not(self):
        self.new('--root')
        self.new('audio')
        path = self.path('audio.md')
        filled = doc('Audio', 'It sounds.', rules=['- **loud** - Loud.'], tests=['- **loud** - is loud.', '  expect: ok'])
        self.assertIsNone(hook.pre_edit(write_over(path, filled)))
        write(self.dir, 'sor/audio.md', filled)   # what the Write does
        self.assertIn('Do not rewrite sor/audio.md', reason(hook.pre_edit(write_over(path, filled + '- **more** - x.\n'))))
        self.assertEqual(self.sor('check', 'audio')[0], 0)

    def test_the_hook_program_answers_the_same_way(self):
        self.new('--root')
        self.new('audio')
        path = self.path('audio.md')
        code, out, _ = base.run_hook('pre-edit', write_over(path))
        self.assertEqual((code, out), (0, ''))
        put(path, read(path) + '- **mine** - written by a person.\n')
        code, out, _ = base.run_hook('pre-edit', write_over(path))
        self.assertEqual(code, 0)
        self.assertIn('Do not rewrite sor/audio.md', out)

    def test_a_claim_held_by_someone_else_still_stops_a_write_over_the_skeleton(self):
        self.new('--root')
        self.new('audio')
        path = self.path('audio.md')
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        self.assertTrue(self.claim(['audio'], 'alice', session='A')[0])
        self.assertIn('Someone else is working on this', reason(hook.pre_edit(write_over(path, session_id='B'))))
        self.assertIsNone(hook.pre_edit(write_over(path, session_id='A')))


if __name__ == '__main__':
    unittest.main()
