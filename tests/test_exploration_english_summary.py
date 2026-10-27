import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class EnglishSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_summary_20261025.npz') as data:
            cls.screen = data['screen']

    def test_actual_english_summary_and_boss_count(self):
        self.assertEqual(self.observer.classify(self.screen), 'expedition_summary')
        self.assertEqual(self.observer.summary_boss_count(self.screen), 3)

    def test_title_and_localized_labels_are_not_recognition_inputs(self):
        screen = self.screen.copy()
        screen[20:100, 450:840] = 0
        screen[105:150, 480:1260] = 0
        screen[120:275, 45:265] = 0
        screen[685:715, 615:750] = 0  # preserve the separate X symbol
        self.assertEqual(self.observer.classify(screen), 'expedition_summary')
        self.assertEqual(self.observer.summary_boss_count(screen), 3)

    def test_each_statistics_icon_is_required(self):
        for name in ('expedition_summary', 'summary_nodes_icon', 'summary_fragments_icon', 'summary_loot_icon'):
            screen = self.screen.copy()
            x, y, w, h = self.observer.config['markers'][name]['crop']
            screen[y:y+h, x:x+w] = 0
            with self.subTest(icon=name):
                self.assertIsNone(self.observer.find(screen, 'expedition_summary'))
                self.assertNotEqual(self.observer.classify(screen), 'expedition_summary')

    def test_close_symbol_is_required(self):
        screen = self.screen.copy()
        screen[670:715, 570:740] = 0
        self.assertIsNone(self.observer.summary_controls(screen))
        self.assertNotEqual(self.observer.classify(screen), 'expedition_summary')

    def test_ordinary_victory_and_other_screens_are_not_summaries(self):
        for name in ('battle/victory_live.png', 'event_recruit_reward_live.png', 'loot_cards_live.png'):
            with self.subTest(name=name):
                self.assertIsNone(self.observer.summary_controls(read_image(str(RAW/name))))

    def test_final_boss_english_summary_exits_battle_closes_and_counts_clear(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, recognition_attempts=1, stable_frames=2,
                               poll_seconds=0, battle_timeout_seconds=2)
        frames = [self.screen, read_image(str(RAW/'entry_after_defeat_live.png'))]
        index = [0]
        taps = []
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer)
            bot._capture = lambda: frames[index[0]]
            def tap(bounds):
                taps.append(tuple(bounds))
                index[0] += 1
            bot._tap = tap
            bot._battle()
            self.assertEqual(bot.stats['outcome'], 'victory')
            result = bot.run()
            self.assertEqual(result['status'], 'round_cleared', result)
            self.assertEqual(result['summary_boss_count'], 3)
            self.assertEqual(taps, [observer.find(self.screen, 'summary_close')])
            bot.adb.tap.assert_not_called()
