import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot, ExplorationBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class NoncombatCoordinatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_supply_geometry_20261025.npz') as data:
            cls.supply = data['screen']

    def bot(self, kind=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, self.observer)
        bot._verified_noncombat_node = kind
        return bot

    def frame(self, name):
        return read_image(str(RAW / name))

    def test_latest_failure_needs_verified_entry_before_geometry_fallback(self):
        self.assertIsNone(self.observer.classify(self.supply))
        bot = self.bot()
        self.assertIsNone(bot._classify(self.supply))
        bot._verified_noncombat_node = 'supply'
        self.assertEqual(bot._classify(self.supply), 'supply')
        self.assertEqual(bot._find_control(self.supply, 'supply_loot'), (905, 368, 330, 94))
        self.assertIsNone(bot._find_control(self.supply, 'supply_done'))
        self.assertIsNone(bot._find_control(self.supply, 'leave'))

    def test_verified_node_detail_then_symbol_then_menu_search(self):
        bot = self.bot()
        bot.observer = NodeObserver(ROOT)
        bot.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        frames = [self.frame('map_after_rest_live.png'), self.frame('supply_detail_live.png'), self.supply]
        index = [0]
        bot._capture = lambda: frames[index[0]]
        bot._tap = lambda bounds: index.__setitem__(0, index[0]+1)
        with patch.object(bot.observer, 'choose_node', return_value=('supply', (500, 130, 40, 40))):
            self.assertTrue(bot._select_node())
        self.assertEqual(index[0], 2)
        self.assertEqual(bot._verified_noncombat_node, 'supply')
        self.assertEqual(bot._classify(frames[-1]), 'supply')

    def test_wrong_kind_or_missing_symbol_rejects_menu_coordinates(self):
        self.assertIsNone(self.observer.noncombat_controls(self.supply, 'rest'))
        screen = self.supply.copy()
        screen[505:570, 570:750] = 0
        self.assertIsNone(self.observer.noncombat_controls(screen, 'supply'))

    def test_competing_node_scene_cannot_override_verified_entry(self):
        bot = self.bot('rest')
        supply = self.frame('supply_menu_local_live.png')
        self.assertEqual(self.observer.classify(supply), 'supply')
        self.assertIsNone(bot._classify(supply))

    def test_restart_stabilizes_unique_node_symbols_before_resuming(self):
        with tempfile.TemporaryDirectory() as tmp:
            facade = ExplorationBot(Mock(), ROOT, tmp)
            facade.nodes.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
            facade.nodes._capture = Mock(return_value=self.supply)
            facade.nodes.run = Mock(return_value={'status': 'completed'})
            facade.recruitment._entry = Mock(return_value=None)
            facade.recruitment.run = Mock()
            self.assertEqual(facade._run_stages()['status'], 'completed')
            self.assertEqual(facade.nodes._verified_noncombat_node, 'supply')
            facade.recruitment.run.assert_not_called()

    def test_both_menu_outlines_are_required(self):
        for y in (258, 368):
            screen = self.supply.copy()
            screen[y:y+94, 905:1235] = 0
            with self.subTest(y=y):
                self.assertIsNone(self.observer.noncombat_controls(screen, 'supply'))

    def test_search_returns_shifted_buttons_not_expected_fixed_positions(self):
        screen = self.supply.copy()
        for y in (258, 368):
            screen[y-16:y+110, 889:1251] = 0
        for y in (258, 368):
            screen[y+6:y+100, 913:1243] = self.supply[y:y+94, 905:1235]
        controls = self.observer.noncombat_controls(screen, 'supply')
        self.assertIsNotNone(controls)
        x, y, w, h = controls['controls']['supply_loot']
        # The rounded outline model and dilated edge support may differ from
        # the outermost painted border by a few pixels; the tap stays central.
        self.assertLessEqual(abs(x-913), 6)
        self.assertLessEqual(abs(y-374), 6)
        self.assertTrue(913+40 < x+w/2 < 1243-40)
        self.assertTrue(374+20 < y+h/2 < 468-20)
        self.assertNotEqual((x, y), (905, 368))

    def test_menu_text_and_sparkle_do_not_contribute_to_geometry(self):
        screen = self.supply.copy()
        rng = np.random.default_rng(25)
        for y in (258, 368):
            for x0, y0, w, h in self.observer.config['markers']['supply_loot']['exclude']:
                screen[y+y0:y+y0+h, 905+x0:905+x0+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        scene = self.observer.noncombat_controls(screen, 'supply')
        self.assertEqual(scene['controls']['supply_loot'], (905, 368, 330, 94))

    def test_disabled_action_never_becomes_clickable_from_geometry(self):
        screen = self.supply.copy()
        screen[368:462, 905:1235] //= 2
        scene = self.observer.noncombat_controls(screen, 'supply')
        self.assertTrue(scene is None or scene['controls']['supply_loot'] is None)

    def test_completion_still_requires_the_existing_check_icon(self):
        for kind, filename, marker in (('supply', 'supply_done_live.png', 'supply_done'),
                                      ('rest', 'rest_completed_live.png', 'rest_done')):
            scene = self.observer.noncombat_controls(self.frame(filename), kind)
            with self.subTest(kind=kind):
                self.assertIsNotNone(scene['controls'][marker])
                action = 'supply_loot' if kind == 'supply' else 'detail_rest'
                self.assertIsNone(scene['controls'][action])

    def test_rest_symbol_then_four_rows_and_only_top_action(self):
        scene = self.observer.noncombat_controls(self.frame('rest_menu_local_live.png'), 'rest')
        self.assertEqual(len(scene['menus']), 4)
        self.assertEqual(scene['controls']['detail_rest'], (905, 148, 330, 94))
        self.assertNotIn('rest_option_4', scene['controls'])

    def test_shop_static_display_authorizes_textless_exit_despite_vendor_animation(self):
        screen = self.frame('shop/shop_full.png')
        screen[634:686, 956:1220] = 0
        bot = self.bot('shop')
        self.assertEqual(bot._classify(screen), 'shop')
        self.assertEqual(bot._find_control(screen, 'shop_exit'), (938, 628, 300, 64))
        screen[194:327, 70:250] = 0
        self.assertIsNotNone(self.observer.noncombat_controls(screen, 'shop'))
        screen[560:615, 375:415] = 0
        self.assertIsNone(self.observer.noncombat_controls(screen, 'shop'))

    def test_generic_confirmation_requires_our_own_verified_shop_exit(self):
        dialog = self.frame('shop_exit_confirm_live.png')
        dialog[440:480, 449:617] = 0
        dialog[440:480, 664:832] = 0
        bot = self.bot('shop')
        self.assertNotEqual(bot._classify(dialog), 'shop_exit_confirm')
        self.assertIsNone(bot._find_control(dialog, 'story_confirm'))
        bot._shop_exit_confirmation_pending = True
        self.assertEqual(bot._classify(dialog), 'shop_exit_confirm')
        bot._wait = lambda phase, ready: ready(dialog)
        bot._capture = Mock(return_value=dialog)
        bot._tap = Mock()
        bot._guarded_tap('test', 'shop_exit_confirm', 'story_confirm', exiting=True)
        bot._tap.assert_called_once_with((649, 430, 198, 60))

    def test_shop_exit_replay_uses_scene_and_textless_confirmation(self):
        shop = self.frame('shop/shop_full.png')
        shop[634:686, 956:1220] = 0
        dialog = self.frame('shop_exit_confirm_live.png')
        dialog[440:480, 449:617] = 0
        dialog[440:480, 664:832] = 0
        bot = self.bot('shop')
        bot.buy_future_investment = False
        bot.observer = NodeObserver(ROOT)
        bot.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        frames = [shop, dialog, self.frame('map_after_rest_live.png')]
        index = [0]
        taps = []
        bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        bot._tap = tap
        bot._shop()
        self.assertEqual(taps, [(938, 628, 300, 64), (649, 430, 198, 60)])
        self.assertFalse(bot._shop_exit_confirmation_pending)
        self.assertEqual(bot.stats['nodes'], 1)

    def test_event_result_taps_detected_arrow_after_it_moves(self):
        screen = self.frame('event_magic_result_live.png')
        x, y, w, h = self.observer.find(screen, 'event_advance')
        arrow = screen[y:y+h, x:x+w].copy()
        screen[y:y+h, x:x+w] = 0
        screen[y-4:y-4+h, x+6:x+6+w] = arrow
        detected = self.observer.find(screen, 'event_advance')
        self.assertEqual(detected, (x+6, y-4, w, h))
        bot = self.bot('event')
        state = ['unknown_event_result']
        bot._classify = lambda frame: state[0]
        bot._capture = lambda: screen
        bot._wait = lambda phase, predicate: predicate(screen)
        bot._start_report = Mock()
        bot._report = Mock()
        bot._event_signature = Mock(return_value='page')
        taps = []
        def tap(bounds):
            taps.append(tuple(bounds))
            state[0] = 'map'
        bot._tap = tap
        self.assertEqual(bot._event_result(), 'map')
        self.assertEqual(taps, [detected])

    def test_event_ornaments_authorize_coordinate_search_for_unknown_art(self):
        screen = self.frame('event_magic_circle_live.png')
        with patch.object(self.observer, 'known_event_candidates', return_value=[]):
            scene = self.observer.noncombat_controls(screen, 'event')
        self.assertEqual(scene['state'], 'unknown_event')
        self.assertEqual(len(scene['controls']['event_cards']), 3)
        screen[640:705, 35:1245] = 0
        self.assertIsNone(self.observer.noncombat_controls(screen, 'event'))

    def test_map_return_discards_the_previous_verified_entry(self):
        bot = self.bot('supply')
        self.assertEqual(bot._classify(self.frame('map_after_rest_live.png')), 'map')
        self.assertEqual(bot._verified_noncombat_node, 'supply')
        bot._wait = Mock(return_value=('map',))
        self.assertEqual(bot._state('confirmed return', {'map'}), 'map')
        self.assertIsNone(bot._verified_noncombat_node)
        self.assertIsNone(bot._classify(self.supply))

    def test_scene_change_before_input_never_uses_previous_coordinates(self):
        bot = self.bot('supply')
        screen = self.supply.copy()
        screen[505:570, 570:750] = 0
        bot._wait = lambda phase, ready: ready(self.supply)
        bot._capture = Mock(return_value=screen)
        bot._check_stop = Mock()
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._guarded_tap('test', 'supply', 'supply_loot')
        bot._tap.assert_not_called()

    def test_coordinate_trace_is_opt_in_and_deduplicated(self):
        bot = self.bot('supply')
        bot.debug_recorder = Mock()
        bot._noncombat_scene(self.supply)
        bot._noncombat_scene(self.supply)
        bot.debug_recorder.event.assert_called_once()
        self.assertEqual(bot.debug_recorder.event.call_args.args[0], 'noncombat_coordinates')

    def test_latest_supply_replay_collects_before_leaving(self):
        bot = self.bot('supply')
        bot.observer = NodeObserver(ROOT)
        bot.observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        frames = [self.supply, self.frame('loot_cards_live.png'), self.frame('supply_done_live.png'),
                  self.frame('map_after_rest_live.png')]
        index = [0]
        taps = []
        bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        bot._tap = tap
        def loot():
            self.assertEqual(index[0], 1)
            index[0] = 2
            return 'supply'
        bot._loot = Mock(side_effect=loot)
        bot._supply()
        self.assertEqual(taps, [(905, 368, 330, 94), (938, 628, 300, 64)])
        self.assertEqual(bot.stats['nodes'], 1)
        self.assertFalse(bot._supply_exit_confirmation_pending)
        bot.adb.tap.assert_not_called()
