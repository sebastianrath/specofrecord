"""Tests for claims when several agents of one Claude Code session work at once (SPEC §16): what `sor release` frees
for a caller that names itself, what happens to a claim that ran out, and what a plain `sor lock` locks of a claimed
part.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no browser, no sleeps (a clock is moved by editing the `until` of a claim). Every
project lives in a temporary folder. Subagents share their parent's session id, so each call here passes the same one.
"""
import json
import os
import sys
import time
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import claims                          # noqa: E402
from sorlib.model import Project                   # noqa: E402
from test_sor_flows import Flow, accepted, lock_bytes, replace_in   # noqa: E402  (not the Test classes: they would run twice)

doc, write, read = base.doc, base.write, base.read

SESSION = 'session-of-the-parent'
GREET = doc('Greet', 'Says hello.', rules=['- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.'])
AUDIO = doc('Audio', 'Sound.', rules=['- **volume** - The volume is {max: 10}.'])
MIXER = doc('Mixer', 'Mixes.', rules=['- **gain** - The gain is {max: 3}.'])
EQUALISER = doc('Equaliser', 'Shapes.', rules=['- **bands** - There are {count: 5} bands.'])
OLD = doc('Old', 'Was here before.', rules=['- **kept** - Kept as it was.'])
OTHER = doc('Other', 'Something else.', rules=['- **thing** - A thing.'])


class Session(Flow):
    """Every call comes from the same Claude Code session, as the subagents of one parent do."""

    def greet_part(self):
        """Two independent clauses, greet/hello and greet/bye, locked."""
        self.project({'greet': GREET})
        accepted(self.dir)

    def run_sor(self, *args, **env):
        return self.sor(*args, **dict({'CLAUDE_CODE_SESSION_ID': SESSION}, **env))

    def live(self):
        """The agents whose claims are in force, from the file."""
        return sorted(c['agent'] for c in self.claims_file() if c['until'] > time.time())

    def expired_at(self, agent):
        """The clock time one agent's claim ran out, as the commands print it."""
        (c,) = [c for c in self.claims_file() if c['agent'] == agent and c['until'] <= time.time()]
        return claims.when(c['until'])

    def lapse(self, agent, ago=5):
        """Moves the claims of one agent to the past, the others' stay."""
        path = os.path.join(self.spec, '.sor-claims.json')
        data = json.loads(read(path))
        for c in data['claims']:
            if c['agent'] == agent:
                c['until'] = time.time() - ago
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))


# --- release: a name releases only its own claims -----------------------------------------------------------

class TestReleaseByAName(Session):
    def setUp(self):
        super().setUp()
        self.greet_part()
        self.assertEqual(self.run_sor('claim', 'greet/hello', '--as', 'a1')[0], 0)
        self.assertEqual(self.run_sor('claim', 'greet/bye', '--as', 'a2')[0], 0)

    def test_release_all_as_a_name_leaves_the_claims_of_the_other_agents_of_the_session(self):
        code, out, _ = self.run_sor('release', '--all', '--as', 'a2')
        self.assertEqual((code, out.strip()), (0, 'released greet/bye'))
        self.assertEqual(self.live(), ['a1'])

    def test_release_by_id_as_a_name_does_not_drop_a_siblings_claim(self):
        code, out, _ = self.run_sor('release', 'greet/hello', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertIn('NOT released (held by someone else; --force overrides): a1: greet/hello', out)
        self.assertNotIn('released greet/hello', out.replace('NOT released', ''))
        self.assertEqual(self.live(), ['a1', 'a2'])

    def test_a_name_in_the_environment_is_a_name_too(self):
        code, out, _ = self.run_sor('release', '--all', SOR_AGENT='a1')
        self.assertEqual((code, out.strip()), (0, 'released greet/hello'))
        self.assertEqual(self.live(), ['a2'])

    def test_a_caller_with_no_name_still_cleans_up_after_all_its_subagents(self):
        code, out, _ = self.run_sor('release', '--all')
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out.split('\n')[:2]), ['released greet/bye', 'released greet/hello'])
        self.assertEqual(self.claims_file(), [])

    def test_a_caller_with_no_name_does_not_touch_another_sessions_claims(self):
        self.assertEqual(self.sor('claim', 'greet', '--as', 'b1', CLAUDE_CODE_SESSION_ID='another-session')[0], 3)
        self.assertEqual(self.run_sor('release', '--all')[0], 0)
        self.assertEqual(self.sor('claim', 'greet', '--as', 'b1', CLAUDE_CODE_SESSION_ID='another-session')[0], 0)
        code, out, _ = self.run_sor('release', '--all')
        self.assertEqual((code, out.strip()), (0, 'nothing to release'))
        self.assertEqual(self.live(), ['b1'])

    def test_force_still_releases_a_siblings_claim(self):
        code, out, _ = self.run_sor('release', 'greet/hello', '--as', 'a2', '--force')
        self.assertEqual((code, out.strip()), (0, 'released greet/hello'))
        self.assertEqual(self.live(), ['a2'])

    def test_a_sibling_cannot_take_a_claimed_clause_either(self):
        """The same rule from the other side: `claim` already told agents of one session apart."""
        code, out, _ = self.run_sor('claim', 'greet/hello', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertIn('a1: greet/hello', out)


# --- a claim that ran out is not forgotten at once ----------------------------------------------------------

class TestExpiredClaims(Session):
    def setUp(self):
        super().setUp()
        self.greet_part()

    def test_claim_says_how_long_it_lasts(self):
        out = self.run_sor('claim', 'greet/hello', '--as', 'a1')[1]
        ends = claims.when(self.claims_file()[0]['until'])
        self.assertEqual(out.strip(), f'claimed greet/hello, held while you work: it ends at {ends} if you do nothing for 30 min')
        self.assertIn('if you do nothing for 2 h', self.run_sor('claim', 'greet/bye', '--as', 'a1', '--ttl', '2h')[1])
        self.assertIn('if you do nothing for 90 s', self.run_sor('claim', 'greet/bye', '--as', 'a1', '--ttl', '90s')[1])
        out = self.run_sor('claim', 'greet/bye', '--as', 'a1', '--ttl', 'never')[1]
        self.assertEqual(out.strip(), 'claimed greet/bye, held while you work: no idle limit')
        (never,) = [c for c in self.claims_file() if c['asked'] == ['greet/bye']]
        self.assertEqual((never['idle'], never['until']), (None, claims.NEVER))

    def test_a_lock_after_the_claims_expired_says_which_and_when(self):
        self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a1')
        self.lapse('a1')
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith('lock refused:\n'), out)
        self.assertIn(f'your claims on greet/bye, greet/hello expired at {self.expired_at("a1")}', out)
        self.assertIn('claims end after 30 min idle by default: claim again, `--ttl 2h` for a longer window', out)
        self.assertNotIn('locking what you claimed', out)

    def test_the_note_names_each_time_when_claims_ran_out_at_different_minutes(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.run_sor('claim', 'greet/bye', '--as', 'a1')
        path = os.path.join(self.spec, '.sor-claims.json')
        data = json.loads(read(path))
        for c, ago in zip(data['claims'], (600, 5)):
            c['until'] = time.time() - ago
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))
        out = self.run_sor('lock', '--as', 'a1')[1]
        first, second = (claims.when(c['until']) for c in data['claims'])
        self.assertIn(f'your claims on greet/hello expired at {first}, on greet/bye at {second}; claims end after', out)

    def test_an_agent_is_told_only_about_its_own_expired_claims(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        code, out, _ = self.run_sor('lock', '--as', 'a2')
        self.assertEqual(code, 2)
        self.assertIn('say which clauses', out)
        self.assertNotIn('expired', out)

    def test_a_lock_that_covers_live_claims_warns_about_the_expired_ones(self):
        self.run_sor('claim', 'greet/bye', '--as', 'a1')
        self.lapse('a1')
        expired = self.expired_at('a1')
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertIn('locking what you claimed: greet/hello', out)
        self.assertIn(f'warning: your claims on greet/bye expired at {expired}, so they are not part of this lock', out)

    def test_claiming_again_ends_the_notice_and_a_part_claim_covers_its_clauses(self):
        self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a1')
        self.lapse('a1')
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        out = self.run_sor('lock', '--as', 'a1')[1]
        self.assertIn('warning: your claims on greet/bye expired', out)
        self.assertNotIn('greet/hello expired', out)
        self.lapse('a1')
        self.run_sor('claim', 'greet', '--as', 'a1')    # the part holds both clauses again
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertNotIn('expired', out)
        self.assertEqual([c['asked'] for c in self.claims_file()], [['greet']])

    def test_an_expired_claim_is_kept_for_a_while_but_is_no_claim(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        self.assertEqual(self.run_sor('claim', 'greet/bye', '--as', 'a2')[0], 0)
        old, new = self.claims_file()
        self.assertEqual((old['agent'], new['agent']), ('a1', 'a2'))
        self.assertLess(old['until'], time.time())    # an older tool drops it as expired
        project = Project(self.dir)
        self.assertEqual([c['agent'] for c in claims.active(project)], ['a2'])
        self.assertEqual(claims.others_for_session(project, 'nobody', ['greet/hello']), [])
        self.assertEqual([c['agent'] for c in json.loads(self.run_sor('status', '--json')[1])['claims']], ['a2'])
        self.assertNotIn('a1', self.run_sor('status')[1])

    def test_a_claim_that_ran_out_long_ago_is_forgotten_by_the_next_write(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1', ago=claims.TOMBSTONE + 60)
        self.run_sor('claim', 'greet/bye', '--as', 'a2')
        self.assertEqual([c['agent'] for c in self.claims_file()], ['a2'])
        self.lapse('a1', ago=claims.TOMBSTONE - 60)
        self.assertEqual(self.claims_file()[0]['agent'], 'a2')

    def test_release_says_that_the_claims_had_run_out_and_forgets_them(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        expired = self.expired_at('a1')
        code, out, _ = self.run_sor('release', '--all', '--as', 'a1')
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f'nothing to release: your claims on greet/hello expired at {expired} '
                         '(claims end after 30 min idle by default: claim again, `--ttl 2h` for a longer window)')
        self.assertEqual(self.claims_file(), [])   # nothing is left in the project
        self.assertEqual(self.run_sor('release', '--all', '--as', 'a1')[1].strip(), 'nothing to release')

    def test_release_frees_the_live_claims_and_adds_the_expired_ones_as_a_note(self):
        self.run_sor('claim', 'greet/bye', '--as', 'a1')
        self.lapse('a1')
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        code, out, _ = self.run_sor('release', '--all', '--as', 'a1')
        self.assertEqual(code, 0)
        self.assertIn('released greet/hello\n', out)
        self.assertIn('note: your claims on greet/bye expired at', out)
        self.assertEqual(self.claims_file(), [])

    def test_another_agents_release_leaves_the_notice_for_the_agent_it_belongs_to(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        self.run_sor('claim', 'greet/bye', '--as', 'a2')
        code, out, _ = self.run_sor('release', '--all', '--as', 'a2')
        self.assertEqual((code, out.strip()), (0, 'released greet/bye'))
        self.assertIn('your claims on greet/hello expired', self.run_sor('lock', '--as', 'a1')[1])

    def test_an_expired_claim_is_nothing_to_refuse_a_release_by_id(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        code, out, _ = self.run_sor('release', 'greet/hello', '--as', 'a2')
        self.assertEqual((code, out.strip()), (0, 'nothing to release'))

    def test_a_new_claim_by_another_agent_does_not_erase_the_notice(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.lapse('a1')
        self.assertEqual(self.run_sor('claim', 'greet/hello', '--as', 'a2')[0], 0)
        self.assertIn('your claims on greet/hello expired', self.run_sor('lock', '--as', 'a1')[1])

    def test_lock_still_refuses_what_an_expired_claim_never_covered(self):
        """Nothing changes for an agent that never claimed: the old sentence, no talk of expiry."""
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 2)
        self.assertIn('say which clauses: sor lock <ids> (or claim them first: sor claim <ids>).', out)


# --- a claimed part is locked with its subtree --------------------------------------------------------------

class TestLockOfAClaimedPart(Session):
    def setUp(self):
        super().setUp()
        self.project({'audio': AUDIO, 'audio/old': OLD, 'other': OTHER})
        accepted(self.dir)
        self.assertEqual(self.run_sor('claim', 'audio', '--as', 'a1')[0], 0)

    def entries(self):
        return json.loads(lock_bytes(self.dir))

    def pending(self):
        code, out, _ = self.run_sor('status', '--json')
        return sorted(f['key'] for f in json.loads(out)['findings'])

    def test_the_child_parts_made_after_the_claim_are_locked_with_it(self):
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        write(self.dir, 'sor/audio/mixer/eq.md', EQUALISER)    # a grandchild
        self.assertEqual(self.pending(), ['audio/mixer', 'audio/mixer/eq', 'audio/mixer/eq/bands', 'audio/mixer/gain'])
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertIn('locking what you claimed: audio\n', out)
        self.assertIn('locking the parts under them too: audio/mixer, audio/mixer/eq\n', out)   # not audio/old: untouched
        self.assertNotIn('still pending outside what you locked', out)
        self.assertTrue({'audio/mixer', 'audio/mixer/gain', 'audio/mixer/eq', 'audio/mixer/eq/bands'} <= set(self.entries()))
        self.assertEqual(self.pending(), [])
        self.assertIn('clauses, code and lock agree', self.run_sor('status')[1])

    def code_of_old(self, number):
        write(self.dir, 'out/old.js', f'// @clause audio/old/kept\nconsole.log({number});\n// @clause end\n')

    def test_a_child_part_with_nothing_new_in_it_is_left_alone_with_its_drift(self):
        """Locking `audio` never needed the state of `audio/old`: a person's change there is not this lock's business."""
        self.code_of_old(1)
        accepted(self.dir)
        self.code_of_old(2)    # a person changed the code, not the clause: drift
        write(self.dir, 'sor/audio.md', AUDIO.replace('{max: 10}', '{max: 11}'))
        self.assertIn('drift', self.run_sor('status')[1])
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertNotIn('locking the parts under them', out)
        self.assertIn('drift', self.run_sor('status')[1])    # still there, for whoever changed the code

    def test_a_child_part_with_a_change_of_its_own_and_drift_blocks_the_lock_like_one_named_by_hand(self):
        self.code_of_old(1)
        accepted(self.dir)
        self.code_of_old(2)
        write(self.dir, 'sor/audio/old.md', OLD.replace('Kept as it was.', 'Kept as it was.\n- **added** - And one more.'))
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 2)
        self.assertIn('locking the parts under them too: audio/old', out)
        self.assertIn('drift  audio/old/kept', out)

    def test_a_child_part_whose_own_text_changed_is_locked_with_it(self):
        write(self.dir, 'sor/audio/old.md', OLD.replace('Was here before.', 'Was here, and still is.'))
        self.assertEqual(self.pending(), ['audio/old'])
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertIn('locking the parts under them too: audio/old\n', out)
        self.assertEqual(self.pending(), [])

    def test_a_part_that_only_starts_with_the_same_letters_is_no_child(self):
        write(self.dir, 'sor/audio2.md', OTHER)
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertIn('locking the parts under them too: audio/mixer\n', out)
        self.assertEqual(self.pending(), ['audio2', 'audio2/thing'])
        self.assertIn('still pending outside what you locked: 2', out)

    def test_a_child_part_with_a_problem_blocks_the_lock_like_one_named_by_hand(self):
        write(self.dir, 'sor/audio/mixer.md', doc('Mixer', 'Mixes.', rules=['- **gain** - The gain is {max: <fill in: n>}.']))
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 2)
        self.assertIn('lock refused:', out)
        self.assertIn('audio/mixer.md', out)
        self.assertNotIn('audio/mixer', self.entries())

    def test_a_child_part_another_agent_holds_is_left_out_and_named(self):
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        self.assertEqual(self.run_sor('claim', 'audio/mixer', '--as', 'a2')[0], 0)
        write(self.dir, 'sor/audio/mixer/eq.md', EQUALISER)
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertIn('not locking audio/mixer, which is claimed: a2: audio/mixer', out)
        self.assertIn('locking the parts under them too: audio/mixer/eq\n', out)
        self.assertNotIn('audio/mixer/gain', self.entries())
        self.assertIn('audio/mixer/eq/bands', self.entries())
        self.assertIn('still pending outside what you locked: 2', out)
        self.assertEqual(self.pending(), ['audio/mixer', 'audio/mixer/gain'])
        self.assertEqual(self.run_sor('release', '--all', '--as', 'a2')[0], 0)
        self.assertEqual(self.run_sor('lock', '--as', 'a1')[0], 0)    # a2 let go: now it goes with the part
        self.assertEqual(self.pending(), [])

    def test_the_claims_listing_stays_what_was_claimed(self):
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        self.assertEqual(self.run_sor('lock', '--as', 'a1')[0], 0)
        (held,) = claims.active(Project(self.dir))
        self.assertEqual(held['asked'], ['audio'])
        self.assertNotIn('audio/mixer', held['keys'])
        data = json.loads(self.run_sor('status', '--json')[1])
        self.assertEqual([(c['agent'], c['asked']) for c in data['claims']], [('a1', ['audio'])])
        self.assertIn('a1: audio (since', self.run_sor('status')[1])

    def test_another_agent_may_still_not_claim_an_item_of_a_claimed_part(self):
        code, out, _ = self.run_sor('claim', 'audio/volume', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertIn('a1: audio', out)

    def test_the_root_is_not_a_claim_on_every_part(self):
        self.run_sor('release', '--all', '--as', 'a1')
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        write(self.dir, 'sor/SPECOFRECORD.md', base.ROOT_DOC.replace('everything else', 'everything else, again'))
        self.assertEqual(self.run_sor('claim', 'ROOT', '--as', 'a1')[0], 0)
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertNotIn('locking the parts under them', out)
        self.assertNotIn('audio/mixer', self.entries())

    def test_locking_by_id_stays_exactly_what_was_named(self):
        write(self.dir, 'sor/audio/mixer.md', MIXER)
        code, out, _ = self.run_sor('lock', 'audio', '--as', 'a1')
        self.assertEqual(code, 0, out)
        self.assertNotIn('locking the parts under them', out)
        self.assertNotIn('audio/mixer', self.entries())
        self.assertIn('still pending outside what you locked: 2', out)

    def test_a_claimed_part_that_left_the_spec_is_locked_as_before(self):
        os.remove(os.path.join(self.spec, 'audio.md'))
        code, out, _ = self.run_sor('lock', '--as', 'a1')
        self.assertEqual(code, 0, out)    # locking it retires its entries
        self.assertNotIn('audio/volume', self.entries())


if __name__ == '__main__':
    unittest.main()


class TestRefusedBatchClaim(Session):
    """A claim of several ids takes all of them or none; the refusal names only the ids in the way and says that the free ones were not claimed either."""

    def setUp(self):
        super().setUp()
        self.greet_part()

    def test_the_refusal_names_the_id_in_the_way_and_says_the_free_one_was_not_claimed(self):
        self.assertEqual(self.run_sor('claim', 'greet/hello', '--as', 'a1')[0], 0)
        code, out, _ = self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith('REFUSED greet/hello: held by'), out)
        self.assertNotIn('REFUSED greet/hello, greet/bye', out)
        self.assertIn('nothing was claimed: greet/bye is free, but a claim takes all its ids or none', out)
        self.assertEqual(self.live(), ['a1'])   # a2 holds nothing

    def test_what_was_free_can_be_claimed_on_its_own_afterwards(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a2')
        self.assertEqual(self.run_sor('claim', 'greet/bye', '--as', 'a2')[0], 0)
        self.assertEqual(self.live(), ['a1', 'a2'])

    def test_when_every_id_is_in_the_way_there_is_nothing_to_add(self):
        self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a1')
        code, out, _ = self.run_sor('claim', 'greet/hello', 'greet/bye', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith('REFUSED greet/hello, greet/bye: held by'), out)
        self.assertNotIn('nothing was claimed', out)

    def test_an_id_that_is_in_the_way_only_through_a_shared_code_region_is_named_too(self):
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nrun();\n// @clause end\n')   # one region, two clauses
        write(self.dir, 'sor/audio.md', AUDIO)
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        code, out, _ = self.run_sor('claim', 'greet/bye', 'audio', '--as', 'a2')
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith('REFUSED greet/bye: held by'), out)   # not held by item, held through the region
        self.assertIn('nothing was claimed: audio is free', out)

    def test_several_free_ids_are_named_in_the_plural(self):
        self.run_sor('claim', 'greet/hello', '--as', 'a1')
        write(self.dir, 'sor/audio.md', AUDIO)
        out = self.run_sor('claim', 'greet/hello', 'greet/bye', 'audio', '--as', 'a2')[1]
        self.assertIn('nothing was claimed: greet/bye, audio are free', out)


# --- a scoped lock waits for the items it locks, not for a neighbour's ---------------------------------------

CORE = doc('Core', 'The core.', rules=['- **tick** - A tick lasts {ms: 16} ms.', '- **tock** - A tock follows a tick.'],
           tests=['- **tick** - ok', '  manual: by hand', '- **tock** - ok', '  manual: by hand'])
TOCK = '- **tock** - A tock follows a tick.'


class TestAScopedLockWaitsOnlyForItsOwnItems(Session):
    """Two agents work in one file: a1 on core/tick, a2 on core/tock. A problem in the text of a2's item does not keep a1
    from locking, as one in another file never did; what is not one item's own text, or is a person's draft, still does."""

    def setUp(self):
        super().setUp()
        self.project({'core': CORE})
        accepted(self.dir)
        self.core = os.path.join(self.spec, 'core.md')
        replace_in(self.core, '{ms: 16}', '{ms: 17}')
        self.assertEqual(self.run_sor('claim', 'core/tick', '--as', 'a1')[0], 0)
        self.assertEqual(self.run_sor('claim', 'core/tock', '--as', 'a2')[0], 0)

    def lock(self, agent):
        return self.run_sor('lock', '--as', agent, '--allow-incomplete')

    def lock_entries(self):
        return json.loads(lock_bytes(self.dir))

    def break_tock(self, text=TOCK + ' See {nothing-here}.'):
        replace_in(self.core, TOCK, text)

    def test_a_broken_reference_in_a_neighbours_item_does_not_stop_my_lock(self):
        before = self.lock_entries()
        self.break_tock()
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 0, out)
        self.assertIn('1 problem(s) in other items of these files do not block this lock', out)
        after = self.lock_entries()
        self.assertEqual(after['core/tick.ms']['text'], base.sha12('17'))
        self.assertEqual(after['core/tock'], before['core/tock'], "the neighbour's entry is left as it was")
        self.assertIn('{nothing-here}', self.run_sor('status')[1])
        self.assertIn('1 problem(s)', self.run_sor('check')[1])

    def test_the_item_with_the_problem_is_still_refused_and_so_is_lock_all(self):
        self.break_tock()
        code, out, _ = self.lock('a2')
        self.assertEqual(code, 2)
        self.assertIn('{nothing-here}', out)
        code, out, _ = self.run_sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('{nothing-here}', out)

    def test_a_broken_reference_in_a_table_row_belongs_to_its_item(self):
        self.break_tock(TOCK + '\n\n| Name | Cost |\n|------|------|\n| x | {nothing-here} |')
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 0, out)
        self.assertIn('in other items of these files', out)

    def test_a_problem_that_is_no_item_s_own_text_still_blocks(self):
        write(self.dir, 'sor/core.md', read(self.core) + '\n## Rules\n- **extra** - Another rules heading.\n')
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 2)
        self.assertIn('heading', out)

    def test_a_persons_draft_test_keeps_the_lock_waiting_wherever_it_is_in_the_file(self):
        write(self.dir, 'sor/core.md', read(self.core).rstrip('\n') + '\n- test that a tock follows a tick\n')
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 2)
        self.assertIn('unnamed test', out)

    def test_a_half_filled_skeleton_keeps_the_lock_waiting_and_the_refusal_says_whose_item_it_is(self):
        self.break_tock(TOCK + ' <fill in: what a tock does>')
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 2)
        self.assertIn('placeholder', out)
        self.assertIn('(in core/tock, claimed by a2)', out)

    def test_nothing_claimed_around_it_means_no_holder_in_the_line(self):
        self.run_sor('release', '--all', '--as', 'a2')
        self.break_tock(TOCK + ' <fill in: what a tock does>')
        code, out, _ = self.lock('a1')
        self.assertEqual(code, 2)
        self.assertNotIn('claimed by', out)
