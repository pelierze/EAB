import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from build_support.release_assets import used_images
from src.chaos.bot import PartyRecruitmentBot
from src.chaos.debug import ExplorationDebugRecorder
from src.chaos.exploration import ExplorationBot, NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.chaos.observer import RecruitmentObserver

ROOT = Path(__file__).resolve().parents[1]


class EnglishBattleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/exploration/english_battle_20261024.npz') as data:
            cls.frames = {k: data[k] for k in data.files}
        cls.nodes = NodeObserver(ROOT)
        cls.recruitment = RecruitmentObserver(ROOT)

    def test_new_english_states_and_real_selected_attribute(self):
        for key, state in [('entry', 'exploration_entry'), ('battle_detail', 'battle_detail'),
                           ('battle_setup', 'battle_setup'), ('levelup', 'levelup'), ('victory', 'victory')]:
            with self.subTest(key=key):
                self.assertEqual(self.nodes.classify(self.frames[key]), state)
        bot = object.__new__(PartyRecruitmentBot)
        bot.observer = self.recruitment
        bot.active_hero = self.recruitment.heroes[0]
        self.assertEqual(bot._element_state(self.frames['selected_filter'])[0], 'selected')

    def test_actual_selected_hero_requires_portrait_and_gold_border(self):
        bot = object.__new__(PartyRecruitmentBot)
        bot.observer = self.recruitment
        bot.active_hero = self.recruitment.heroes[0]
        self.assertIsNotNone(bot._recruit(self.frames['selected_hero']))
        self.assertIsNone(bot._recruit(self.frames['selected_filter']))

    def test_shared_action_does_not_identify_unrelated_screens(self):
        for key in self.frames:
            if key != 'battle_setup':
                self.assertIsNone(self.nodes.find(self.frames[key], 'battle_start'), key)
            if key != 'entry':
                self.assertIsNone(self.recruitment.find(self.frames[key], 'start'), key)
        setup = self.frames['battle_setup'].copy()
        setup[640:692, 142:200] = 0
        self.assertIsNone(self.nodes.find(setup, 'battle_start'))
        victory = self.frames['victory'].copy()
        victory[0:110, 450:850] = 0
        self.assertIsNone(self.nodes.find(victory, 'continue'))

    def test_changed_start_and_continue_lettering_is_ignored(self):
        entry = self.frames['entry'].copy()
        entry[634:690, 948:1224] = 0
        self.assertIsNotNone(self.recruitment.find(entry, 'start'))
        victory = self.frames['victory'].copy()
        victory[634:686, 503:777] = 0
        self.assertEqual(self.nodes.classify(victory), 'victory')

    def test_new_references_are_packaged(self):
        assets = set(used_images(ROOT))
        for name in ('entry_action', 'entry_symbol', 'setup_symbol', 'detail_symbol',
                     'continue_frame', 'level_frame', 'rose_english', 'rose_portrait'):
            self.assertIn(f'images/chaos/hero_selection/templates/controls/{name}.png', assets)

    def test_real_frames_replay_node_entry_levelup_and_victory_without_game_input(self):
        with np.load(ROOT / 'tests/fixtures/exploration/english_entry_20261024.npz') as data:
            map_frame = data['map']
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=8, poll_seconds=0, stable_frames=2)
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer)
            # Combat itself is skipped in this offline replay; use the supplied
            # result frame immediately after Start, without inventing game inputs.
            screens = [map_frame, self.frames['battle_detail'], self.frames['battle_setup'],
                       self.frames['levelup'], self.frames['victory'], map_frame]
            index = [0]
            taps = []
            bot._capture = lambda: screens[index[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            self.assertTrue(bot._select_node())
            bot._guarded_tap('Start', 'battle_setup', 'battle_start')
            self.assertEqual(bot._dismiss_popup('Level up', 'levelup', 'level_close',
                                               {'victory'}), 'victory')
            bot._victory()
            self.assertEqual(len(taps), 5)
            self.assertEqual(bot.stats['nodes'], 1)
            bot.adb.tap.assert_not_called()

    def test_debug_default_creates_no_recorder_or_matching_work(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                'src.chaos.debug.ExplorationDebugRecorder') as recorder:
            bot = ExplorationBot(Mock(), ROOT, tmp)
            self.assertIsNone(bot.debug_recorder)
            recorder.assert_not_called()
            self.assertFalse(list(Path(tmp).rglob('recognition.jsonl')))

    def test_debug_records_phase_input_failure_scores_and_existing_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = ExplorationBot(Mock(), ROOT, tmp, debug_mode=True)
            trace = bot.debug_recorder
            bot.nodes.last_screen = self.frames['battle_setup']
            trace.event('observation', phase='start', result=None)
            trace.event('observation', phase='start', result=None)
            trace.event('input', point=[1088, 660])
            trace.failure(bot.nodes, 'timeout')
            trace.close()
            rows = [json.loads(line) for line in (trace.directory / 'recognition.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([r['event'] for r in rows], ['observation', 'input', 'failure'])
            metadata = json.loads((trace.directory / 'failure_01.json').read_text(encoding='utf-8'))
            self.assertIn('score', metadata['markers']['battle_start'])
            self.assertIsNotNone(metadata['markers']['battle_start']['accepted_bounds'])
            self.assertTrue((trace.directory / 'failure_01.png').exists())
            bot.nodes.adb.capture_frame.assert_not_called()

    def test_debug_disk_failure_does_not_interrupt_bot(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = ExplorationDebugRecorder(tmp)
            with patch.object(trace.handler, 'emit', side_effect=OSError('disk full')):
                trace.event('input', point=[10, 10])
            trace.close()


if __name__ == '__main__':
    unittest.main()
