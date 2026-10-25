import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.exploration import ExplorationBot, NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class NodeTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_shop_live_20261025.npz') as data:
            cls.shop = data['screen']
        with np.load(ROOT / 'tests/fixtures/exploration/english_shop_detail_20261025.npz') as data:
            cls.detail = data['screen']
        cls.map = read_image(str(RAW / 'map_after_rest_live.png'))

    def test_transient_map_during_entry_does_not_discard_verified_shop(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer)
            bot._verified_noncombat_node = 'shop'
            frames = iter([self.map, self.map, self.shop])
            bot._capture = lambda: next(frames, self.shop)
            self.assertEqual(bot._state('entry', {'shop'}), 'shop')
            self.assertEqual(bot._verified_noncombat_node, 'shop')

    def test_shop_detail_resume_survives_transition_then_exits_with_book_displayed(self):
        self.replay(start_on_map=False)

    def test_shop_map_selection_survives_transition_then_exits_with_book_displayed(self):
        self.replay(start_on_map=True)

    def test_current_english_shop_body_resumes_without_recruitment_or_reentry(self):
        frames = [self.shop, read_image(str(RAW / 'shop_exit_confirm_live.png')), self.map]
        index = [0]
        taps = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = ExplorationBot(Mock(), ROOT, tmp, max_nodes=1)
            bot = facade.nodes
            bot.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
            bot._capture = lambda: frames[index[0]]
            def tap(bounds):
                taps.append(tuple(bounds))
                index[0] += 1
            bot._tap = tap
            facade.recruitment._entry = Mock(return_value=None)
            facade.recruitment.run = Mock()
            result = facade._run_stages()
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(len(taps), 2)
            self.assertEqual(taps[0], (938, 628, 300, 64))
            self.assertIsNone(bot._verified_noncombat_node)
            facade.recruitment.run.assert_not_called()
            bot.adb.tap.assert_not_called()

    def replay(self, start_on_map):
        dialog = read_image(str(RAW / 'shop_exit_confirm_live.png'))
        dialog[440:480, 449:617] = 0
        dialog[440:480, 664:832] = 0
        frames = ([self.map] if start_on_map else []) + [self.detail, self.shop, dialog, self.map]
        shop_stage = 2 if start_on_map else 1
        stage = [0]
        transient = [2]
        contexts = []
        taps = []
        with tempfile.TemporaryDirectory() as tmp:
            facade = ExplorationBot(Mock(), ROOT, tmp, max_nodes=1, buy_future_investment=False)
            bot = facade.nodes
            bot.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
            def capture():
                if stage[0] == shop_stage and transient[0]:
                    transient[0] -= 1
                    contexts.append(bot._verified_noncombat_node)
                    return self.map
                return frames[stage[0]]
            bot._capture = capture
            def tap(bounds):
                taps.append(tuple(bounds))
                stage[0] += 1
            bot._tap = tap
            facade.recruitment.run = Mock()
            with patch.object(bot.observer, 'choose_node', return_value=('shop', (920, 115, 40, 40))):
                result = facade._run_stages()
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(contexts, ['shop', 'shop'])
            self.assertEqual(result['nodes'], 1)
            self.assertEqual(taps[-3:], [(939, 629, 300, 64), (938, 628, 300, 64), (649, 430, 198, 60)])
            self.assertIsNone(bot._verified_noncombat_node)
            facade.recruitment.run.assert_not_called()
            bot.adb.tap.assert_not_called()

    def test_actual_shop_book_is_detected_as_existing_forbidden_item(self):
        blocked = self.observer.forbidden(self.shop)
        self.assertEqual(len(blocked), 1)
        name, (x, y, w, h) = blocked[0]
        self.assertEqual(name, 'dont_select_2')
        self.assertTrue(1020 <= x+w/2 <= 1100 and 190 <= y+h/2 <= 270)

    def test_book_detection_ignores_english_caption_and_rejects_missing_icon(self):
        screen = self.shop.copy()
        screen[105:150, 970:1138] = 0
        self.assertEqual(self.observer.forbidden(screen)[0][0], 'dont_select_2')
        screen[175:275, 1005:1120] = 0
        self.assertEqual(self.observer.forbidden(screen), [])

    def test_detected_book_is_rejected_before_purchase_price_reading(self):
        observer = NodeObserver(ROOT)
        blocked_bounds = observer.forbidden(self.shop)[0][1]
        original_find = observer.find
        # Exercise the product guard with the actual detected forbidden book.
        # The production bot only targets Future Investment, never arbitrary goods.
        def product(screen, name, **kwargs):
            return blocked_bounds if name == 'shop_future_investment' else original_find(screen, name, **kwargs)
        with patch.object(observer, 'find', side_effect=product), patch.object(observer, 'shop_number') as number:
            self.assertEqual(observer.shop_investment_offer(self.shop), ('skip',))
            number.assert_not_called()
