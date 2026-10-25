"""Read-only observations for verified exploration nodes; unknown screens fail closed."""

import json
import re
from pathlib import Path

import cv2
import numpy as np

from src.image_matcher import ImageMatcher, read_image
from .errors import RecognitionPending
from .template_masks import apply_exclusions, color_error, matches_fixed_mask
from .noncombat import menu_stack, active_menu


DETAIL_STATES = {
    'detail_battle': 'battle_detail',
    'rest_detail': 'rest_detail',
    'supply_detail': 'supply_detail',
    'elite_detail': 'elite_detail',
    'boss_detail': 'boss_detail',
    'event_detail': 'event_detail',
    'shop_detail': 'shop_detail',
}


class NodeObserver:
    def __init__(self, root, ocr=None):
        root = Path(root)
        self.config = json.loads((root / 'src/chaos/node_layout.json').read_text(encoding='utf-8'))
        self.templates = {}
        for name, definition in self.config['markers'].items():
            source = read_image(str(root / definition['file']))
            if source is None:
                raise ValueError(f'노드 이미지 누락: {definition["file"]}')
            if 'crop' in definition:
                x, y, w, h = definition['crop']
                source = source[y:y+h, x:x+w]
                if source.shape[:2] != (h, w):
                    raise ValueError(f'노드 이미지 영역 오류: {name}')
            self.templates[name] = apply_exclusions(source, definition.get('exclude'), name)
        self.blocked = []
        for path in sorted((root / 'images/chaos/node_progression/templates/blocked_choices').glob('*.png')):
            source = read_image(str(path))
            if source is None:
                raise ValueError(f'금지 이미지 읽기 실패: {path}')
            crop = self.config.get('blocked_choice_crops', {}).get(path.name)
            if crop:
                x, y, w, h = crop
                if min(x, y) < 0 or min(w, h) <= 0 or x+w > source.shape[1] or y+h > source.shape[0]:
                    raise ValueError(f'금지 아이템 아이콘 영역 오류: {path.name}')
                source = source[y:y+h, x:x+w]
            # Registry images added later should contain only the item icon.
            # Legacy files retain their original text but never match that text.
            self.blocked.append((path.stem, source))
        if not self.blocked:
            raise ValueError('금지 이미지 목록이 비어 있습니다.')
        self.ocr = ocr
        self.class_templates = {}
        class_dir = root / 'images/chaos/node_progression/templates/classes'
        if class_dir.is_dir():
            for path in sorted(class_dir.glob('class_*.png')):
                source = read_image(str(path))
                if source is not None:
                    c_name = path.stem.replace('class_', '')
                    self.class_templates[c_name] = source

        self.hero_to_class = {}
        rec_layout_path = root / 'src/chaos/recruitment_layout.json'
        if rec_layout_path.is_file():
            try:
                rec_data = json.loads(rec_layout_path.read_text(encoding='utf-8'))
                for h_id, h_info in rec_data.get('heroes', {}).items():
                    if 'class' in h_info:
                        self.hero_to_class[h_id] = h_info['class']
            except Exception:
                pass
        self.hero_to_class.update({
            'rhianna': 'thief',
            'rhianna_luciella': 'thief',
            'rose': 'knight',
            'shadow_rose': 'knight',
            'adin': 'thief',
            'savior_adin': 'thief',
            'wukong': 'warrior',
            'destina': 'soul_weaver',
            'lisette': 'soul_weaver',
            'jenua': 'thief',
        })

    def validate_screen(self, screen):
        if screen is None or screen.shape[:2] != (720, 1280):
            raise RuntimeError('새 1280×720 화면을 읽지 못했습니다.')

    @staticmethod
    def matches(screen, template, region, threshold=.9, max_error=.055):
        x, y, w, h = region
        th, tw = template.shape[:2]
        if x < 0 or y < 0 or x+w > screen.shape[1] or y+h > screen.shape[0] or w < tw or h < th:
            return []
        sample = screen[y:y+h, x:x+w]
        if template.shape[2] == 4 and (h, w) == (th, tw):
            return [(x, y, tw, th)] if matches_fixed_mask(sample, template, threshold, max_error) else []
        scores = ImageMatcher.match_template(sample, template)
        found = []
        for _ in range(100):
            _, score, _, (mx, my) = cv2.minMaxLoc(scores)
            if score < threshold:
                break
            error = color_error(sample[my:my+th, mx:mx+tw], template)
            if error <= max_error:
                found.append((x+mx, y+my, tw, th))
            scores[max(0,my-th//2):my+th//2+1, max(0,mx-tw//2):mx+tw//2+1] = -1
        return found

    def all(self, screen, name, region=None):
        d = self.config['markers'][name]
        return self.matches(screen, self.templates[name], region or d.get('region', [0,0,1280,720]), d['threshold'], d['max_color_error'])

    def _rank_menu_rows(self, screen):
        results = {}
        if not self.class_templates:
            return results
        row_y_starts = [75, 180, 285, 390]
        for row_idx, y_start in enumerate(row_y_starts):
            search_area = screen[y_start:y_start+80, 350:410]
            best_class = None
            best_score = 0
            best_loc = None
            for c_name, c_tmpl in self.class_templates.items():
                res = cv2.matchTemplate(search_area, c_tmpl, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, (mx, my) = cv2.minMaxLoc(res)
                if max_v > best_score:
                    best_score = max_v
                    best_class = c_name
                    best_loc = (350 + mx, y_start + my)

            if best_class and best_score >= 0.80:
                cx, cy = best_loc
                if best_class in results:
                    return {}
                results[best_class] = dict(row=row_idx, origin=(cx, cy), score=best_score)
        return results

    def scan_rank_menu_heroes(self, screen):
        results = {}
        for best_class, info in self._rank_menu_rows(screen).items():
            cx, cy = info['origin']
            y_digit_start = cy + 35
            y_digit_end = cy + 61
            x_digit_start = max(0, cx + 13)
            x_digit_end = cx + 30

            digit = self.read_rank_digit(screen[y_digit_start:y_digit_end, x_digit_start:x_digit_end])
            if digit is None:
                digit = self.read_rank_digit(screen[y_digit_start:y_digit_end, max(0, cx - 1):cx + 35], allow_max=True)

            results[best_class] = {
                'row': info['row'],
                'class': best_class,
                'score': info['score'],
                'rank': digit,
                'bounds': (397, cy, 140, 27)
            }
        return results

    def find(self, screen, name, region=None):
        if region is None:
            if name in ('rank_result_before_icon', 'rank_result_after_icon'):
                return (self.rank_result_controls(screen) or {}).get(name)
            if name in ('event_rank_reward_button', 'event_reward_continue'):
                return (self.rank_reward_controls(screen) or {}).get(name)
            if name == 'defeat':
                # Both upper crest patches exclude the localized result label.
                # A single purple decoration does not establish battle defeat.
                crest = self.all(screen, name)
                if len(crest) != 1:
                    return None
                ornaments = self.all(screen, 'defeat_ornament')
                if len(ornaments) != 1:
                    return None
                x, y, _, _ = crest[0]
                ox, oy, _, _ = ornaments[0]
                return crest[0] if abs(ox-x+72) <= 4 and abs(oy-y-98) <= 4 else None
            if name == 'expedition_summary':
                return (self.summary_controls(screen) or {}).get(name)
            if name == 'loot_button':
                # A shared purple frame alone never authorizes claiming loot.
                # Require the three-card scene and a single selected card too.
                if len(self.all(screen, 'loot_reroll')) != 3 or self.selected_loot(screen) is None:
                    return None
                matches = self.all(screen, name)
                if len(matches) != 1:
                    return None
                x, y, w, h = matches[0]
                sample = screen[y:y+h, x:x+w]
                active_score = float(ImageMatcher.match_template(sample, self.templates[name])[0, 0])
                dim_score = float(ImageMatcher.match_template(sample, self.templates['loot_button_dim'])[0, 0])
                # Compare both states at the same location. Similar shared
                # borders do not establish that the claim action is enabled.
                return matches[0] if active_score - dim_score >= .02 else None
            if name in ('loot_reward', 'reward_hero', 'battle_rank_reward'):
                return self.battle_reward_controls(screen).get(name)
            if name == 'battle_unresolved_reward':
                if not self.all(screen, 'victory'):
                    return None
                known = self.battle_reward_controls(screen).values()
                return next((b for b in self.all(screen, 'battle_reward_button') if b not in known), None)
            if name == 'battle_warning_cancel':
                return self.battle_unclaimed_cancel(screen)
            if name.startswith('ticket_class_') and name in self.templates:
                return self._ticket_icon(screen, name)
            if name in ('recruit_reward_title', 'recruit_continue'):
                return (self.recruit_reward_controls(screen) or {}).get(name)
            if name in ('rest_option_2', 'rest_option_3', 'rest_option_4', 'supply_menu_first'):
                return self._menu_option_bounds(screen, name)
            if name in ('supply_loot', 'supply_done'):
                return (self.supply_controls(screen) or {}).get(name)
            if name in ('detail_rest', 'rest_done'):
                return (self.rest_controls(screen) or {}).get(name)
            if name == 'leave':
                controls = self.rest_controls(screen)
                if controls:
                    return controls['leave']
                controls = self.supply_controls(screen)
                if controls:
                    return controls['leave']
            if name == 'rank_title':
                return tuple(self.config['markers'][name]['crop']) if self.is_rank_menu(screen) else None
            if name == 'rank_button':
                if self.is_rank_menu(screen) and sum(self._rank_row_selected(screen, i) for i in range(4)) == 1:
                    matches = self.all(screen, name)
                    return matches[0] if len(matches) == 1 else None
                return None
        if name == 'battle_rank_complete':
            # A completed battle reward has its class icon at the card's lower
            # right. Require the victory heading and the active continue control.
            if not self.find(screen, 'victory') or not self.find(screen, 'continue'):
                return None
            for role in ('knight', 'warrior', 'soul_weaver', 'thief'):
                bounds = self.find(screen, 'battle_rank_complete_' + role)
                if bounds:
                    return bounds
            return None
        if name in ('levelup', 'level_close') and region is None:
            controls = self.levelup_controls(screen)
            return controls.get(name) if controls else None
        if name == 'rank_close':
            return tuple(self.config['rank_result_close_bounds']) if self.is_rank_result(screen) else None
        if name in self.config['markers']:
            matches = self.all(screen, name, region)
            if len(matches) == 1:
                return matches[0]
            if not matches and region is None:
                if name == 'exploration_entry' and self.find(screen, 'entry_symbol'):
                    return self.find(screen, 'entry_action')
                if name == 'battle_start' and self.find(screen, 'setup_symbol'):
                    return self.find(screen, 'action_frame')
                if name == 'enter_node' and self.detail_state(screen):
                    return self.find(screen, 'action_frame')
                if name == 'continue' and self.find(screen, 'victory'):
                    return self.find(screen, 'continue_frame')
        target_class = self.hero_to_class.get(name, name)
        if target_class in self.class_templates and self.is_rank_menu(screen):
            scan = self.scan_rank_menu_heroes(screen)
            if target_class in scan:
                return scan[target_class]['bounds']
        return None

    def rest_controls(self, screen):
        # Both patches avoid the flag, fire, characters, and menu captions.
        for name in ('rest_static_left', 'rest_static_roof'):
            if not self.all(screen, name):
                return None
        active = self.all(screen, 'detail_rest')
        if not active and not self.all(screen, 'rest_option_disabled'):
            return None
        if not all(self._menu_option_bounds(screen, 'rest_option_' + str(i)) for i in (2, 3, 4)):
            return None
        leave = self.all(screen, 'action_frame')
        if len(leave) != 1:
            return None
        done = self.all(screen, 'rest_done')
        return dict(leave=leave[0], detail_rest=active[0] if len(active) == 1 and not done else None,
                    rest_done=done[0] if len(done) == 1 else None)

    def noncombat_kind(self, screen):
        """Recover one unambiguous node identity when entry history is unavailable."""
        if self.recruit_skip_buttons(screen):
            return None  # A generic dialog must not expose its underlying node.
        kinds = []
        if all(self.all(screen, name) for name in ('rest_static_left', 'rest_static_roof')):
            kinds.append('rest')
        if any(self.all(screen, 'supply_chest_'+state) for state in ('open', 'closed')):
            kinds.append('supply')
        if all(self.all(screen, name) for name in ('shop_frame', 'shop_display_base')):
            kinds.append('shop')
        if self.all(screen, 'event_card_left') and self.all(screen, 'event_card_right'):
            kinds.append('event')
        return kinds[0] if len(kinds) == 1 else None

    def noncombat_controls(self, screen, node_kind):
        """Node intent -> current scene symbols -> fresh control coordinates.

        The caller supplies verified entry history. History alone never permits
        a click, and these controls never override a separately recognized popup.
        """
        if node_kind not in ('rest', 'supply', 'shop', 'event'):
            return None
        symbols = []
        if node_kind == 'rest':
            for name in ('rest_static_left', 'rest_static_roof'):
                if not self.all(screen, name):
                    return None
                symbols.append(name)
            names = ['detail_rest', 'rest_option_2', 'rest_option_3', 'rest_option_4']
        elif node_kind == 'supply':
            symbols = [name for name in ('supply_chest_closed', 'supply_chest_open') if self.all(screen, name)]
            if not symbols:
                return None
            names = ['supply_menu_first', 'supply_loot']
        elif node_kind == 'shop':
            # Static display brackets avoid the vendor's animation and dialogue.
            if not self.all(screen, 'shop_display_base') or not self.all(screen, 'shop_frame'):
                return None
            leave = self.all(screen, 'action_frame')
            if len(leave) != 1:
                return None
            return dict(state='shop', symbols=['shop_display_base', 'shop_frame'], controls={'shop_exit': leave[0]})
        else:
            # Event art differs for each encounter. Paired choice-panel corner
            # ornaments identify the generic scene even for unregistered art.
            cards = self.event_cards(screen)
            if not cards or not self.all(screen, 'event_card_left') or not self.all(screen, 'event_card_right'):
                return None
            known = self.known_event_candidates(screen)
            return dict(state='event' if known else 'unknown_event',
                        symbols=known or ['event_card_left', 'event_card_right'],
                        controls={'event_cards': cards})
        rows = [self.config['markers'][name]['region'] for name in names]
        menus = menu_stack(screen, rows)
        leave = self.all(screen, 'action_frame')
        if not menus or len(leave) != 1:
            return None
        controls = {'leave': leave[0]}
        done_name = 'rest_done' if node_kind == 'rest' else 'supply_done'
        action_name = 'detail_rest' if node_kind == 'rest' else 'supply_loot'
        index = 0 if node_kind == 'rest' else 1
        done = self.all(screen, done_name, menus[index])
        if len(done) > 1:
            return None
        controls['leave'] = leave[0] if done else None
        controls[done_name] = done[0] if done else None
        inactive = 'rest_option_disabled' if node_kind == 'rest' else 'supply_option_disabled'
        enabled = active_menu(screen, menus[index], self.templates[action_name], self.templates[inactive])
        controls[action_name] = menus[index] if enabled and not done else None
        return dict(state=node_kind, symbols=symbols, menus=menus, exit_bounds=leave[0], controls=controls)

    def _menu_option_bounds(self, screen, name):
        # Unselected choices can be active or disabled independently.
        # Only their text-free geometry contributes to scene identification.
        definition = self.config['markers'][name]
        x, y, w, h = definition['region']
        sample = screen[y:y+h, x:x+w]
        templates = [self.templates[name], self.templates['detail_rest']]
        if name == 'supply_menu_first':
            templates.append(self.templates['supply_first_disabled'])
            templates.append(self.templates['supply_menu_first_variant'])
        if name == 'rest_option_4':
            templates.append(self.templates['rest_option_4_active'])
        for template in templates:
            score = ImageMatcher.match_template(sample, template, shape_only=True)
            if float(score[0, 0]) >= definition['threshold']:
                return (x, y, w, h)
        return None

    def supply_controls(self, screen):
        # The lower chest body remains visible with the lid open or closed.
        if not any(self.all(screen, 'supply_chest_' + state) for state in ('closed', 'open')):
            return None
        if not self._menu_option_bounds(screen, 'supply_menu_first'):
            return None
        active = self.all(screen, 'supply_loot') or self.all(screen, 'supply_loot_variant')
        if not active and not self.all(screen, 'supply_option_disabled'):
            return None
        leave = self.all(screen, 'action_frame')
        if len(leave) != 1:
            return None
        done = self.all(screen, 'supply_done')
        return dict(leave=leave[0], supply_loot=active[0] if len(active) == 1 and not done else None,
                    supply_done=done[0] if len(done) == 1 else None)

    def _ticket_icon(self, screen, name, region=None):
        definition = self.config['markers'][name]
        x, y, w, h = region or definition['region']
        sample = screen[y:y+h, x:x+w]
        best = None
        for scale in definition['match_scales']:
            template = cv2.resize(self.templates[name], None, fx=scale, fy=scale)
            th, tw = template.shape[:2]
            if th > h or tw > w:
                continue
            _, score, _, (mx, my) = cv2.minMaxLoc(ImageMatcher.match_template(sample, template, shape_only=True))
            if score >= definition['threshold'] and (best is None or score > best[0]):
                best = score, (x+mx, y+my, tw, th)
        return best[1] if best else None

    def battle_reward_controls(self, screen):
        """Pair a reward symbol with its own card and active, textless button."""
        if not self.all(screen, 'victory'):
            return {}
        controls = {}
        for button in self.all(screen, 'battle_reward_button'):
            x, y, w, h = button
            center = x + w / 2
            card_region = (int(center-135), 150, 270, 455)
            # Only the paired lower side notches belong to this mask. Long
            # translucent edges and card contents vary with the scene behind it.
            if not (self.all(screen, 'battle_reward_card', card_region)
                    or self.all(screen, 'battle_reward_card_legacy', card_region)):
                continue
            icon_region = (int(center-55), 205, 110, 95)
            if self.all(screen, 'battle_loot_icon', icon_region):
                controls['loot_reward'] = button
            elif self.all(screen, 'battle_rank_icon', icon_region):
                controls['battle_rank_reward'] = button
            elif any(self._ticket_icon(screen, 'ticket_class_'+role, icon_region)
                     for role in ('knight', 'warrior', 'thief', 'soul_weaver', 'ranger', 'mage', 'all')):
                controls['reward_hero'] = button
        return controls

    def battle_unclaimed_cancel(self, screen):
        buttons = self.recruit_skip_buttons(screen)
        if not buttons:
            return None
        # The dimmed VICTORY heading establishes battle context. Never approve
        # a generic warning: cancel it and re-scan the remaining reward cards.
        x, y, w, h = self.config['markers']['victory']['region']
        scores = ImageMatcher.match_template(screen[y:y+h, x:x+w],
                                            self.templates['victory'], shape_only=True)
        if cv2.minMaxLoc(scores)[1] >= .9:
            return buttons['cancel']
        return None

    def rank_reward_controls(self, screen):
        """Verify the rank emblem and card before exposing text-masked buttons."""
        controls = {}
        for name in ('event_rank_reward_icon', 'recruit_card_frame', 'event_reward_continue'):
            matches = self.all(screen, name)
            if len(matches) != 1:
                return None
            controls[name] = matches[0]
        ix, iy, iw, ih = controls['event_rank_reward_icon']
        cx, cy, cw, ch = controls['recruit_card_frame']
        bx, by, bw, bh = controls['event_reward_continue']
        if not (cx < ix and ix+iw < cx+cw and cy < iy and iy+ih < cy+ch
                and abs(cx+cw/2-bx-bw/2) <= 8 and 65 <= by-cy-ch <= 85):
            return None
        buttons = self.all(screen, 'event_rank_reward_button')
        if len(buttons) == 1:
            x, y, w, h = buttons[0]
            if cx < x and x+w < cx+cw and iy+ih < y and y+h < cy+ch:
                controls['event_rank_reward_button'] = buttons[0]
        return controls

    def recruit_reward_controls(self, screen):
        controls = {}
        for name in ('recruit_card_frame', 'recruit_reward_title', 'recruit_continue'):
            matches = self.all(screen, name)
            if len(matches) != 1:
                return None
            controls[name] = matches[0]
        roles = [role for role in ('knight', 'warrior', 'thief', 'soul_weaver', 'ranger', 'mage', 'all')
                 if self._ticket_icon(screen, 'ticket_class_' + role)]
        if len(roles) > 1:
            return None
        if not roles and not self.all(screen, 'recruit_title_legacy'):
            return None
        controls['role'] = roles[0] if roles else 'legacy'
        return controls

    def recruit_skip_buttons(self, screen, region=None):
        # Frames alone never authorize Confirm; callers must establish context.
        confirm = self.all(screen, 'recruit_skip_confirm_frame', region) if region else self.all(screen, 'recruit_skip_confirm_frame')
        cancel = self.all(screen, 'recruit_skip_cancel_frame', region) if region else self.all(screen, 'recruit_skip_cancel_frame')
        if len(confirm) == len(cancel) == 1:
            cx, cy, cw, ch = confirm[0]
            bx, by, bw, bh = cancel[0]
            if abs((cx+cw/2) - (bx+bw/2) - 215) <= 4 and abs(cy-by) <= 3:
                return dict(confirm=confirm[0], cancel=cancel[0])
        return None

    def event_warning_controls(self, screen):
        """Full-width modal borders plus a paired, text-masked button row.

        This only identifies a warning for cancellation, never permission to
        confirm it. Title/body text and the vertical button position may vary.
        """
        buttons = self.recruit_skip_buttons(screen, [375, 320, 550, 325])
        if not buttons:
            return None
        _, y, _, h = buttons['cancel']
        gray = cv2.cvtColor(screen[100:650, :, :3], cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 10, 30)
        coverage = (edges[:, 30:1250] > 0).mean(axis=1)
        rows = np.flatnonzero(coverage >= .8) + 100
        top = rows[(rows >= 100) & (rows <= y-80)]
        bottom = rows[(rows >= y+h+5) & (rows <= y+h+65)]
        if not len(top) or not len(bottom):
            return None
        top, bottom = int(top[-1]), int(bottom[0])
        if not 220 <= bottom-top <= 500:
            return None
        return dict(buttons, panel=(0, top, 1280, bottom-top+1))

    def is_rank_menu(self, screen):
        # Geometry + exploration footer + distinct party class icons; no OCR.
        # Departures can leave fewer than four heroes in the party.
        return bool(self.all(screen, 'rank_title') and self.all(screen, 'map_footer')
                    and self._rank_menu_rows(screen))

    @staticmethod
    def _rank_row_selected(screen, row):
        y = 80 + 105 * row
        regions = ((365, y-2, 630, y+12), (365, y+78, 630, y+94),
                   (337, y+15, 359, y+75))
        for i, (x1, y1, x2, y2) in enumerate(regions):
            hsv = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
            gold = cv2.inRange(hsv, np.array([10, 25, 150]), np.array([40, 255, 255]))
            if (gold > 0).any(axis=0 if i < 2 else 1).mean() < .75:
                return False
        return True

    def rank_hero_selected(self, screen, hero):
        role = self.hero_to_class.get(hero, hero)
        info = self._rank_menu_rows(screen).get(role)
        return bool(info and self._rank_row_selected(screen, info['row']))

    def detail_state(self, screen):
        """Require exactly one kind of icon in the right-hand detail header."""
        found = []
        for marker, state in DETAIL_STATES.items():
            matches = self.all(screen, marker)
            if len(matches) > 1:
                return None
            if matches:
                found.append(state)
        return found[0] if len(found) == 1 else None

    def levelup_controls(self, screen):
        """Pair the title with a moving down arrow; return a stable tap area."""
        frame = self.find(screen, 'level_frame')
        arrows = self.all(screen, 'level_close') if frame else []
        if frame and len(arrows) == 1:
            return {'levelup': frame, 'level_close_arrow': arrows[0],
                    'level_close': tuple(self.config['levelup_close_bounds'])}
        names = ('levelup', 'level_close')
        for scale in (1., .95, 1.05, .9, 1.1):
            controls = {}
            for name in names:
                definition = self.config['markers'][name]
                template = self.templates[name]
                if scale != 1:
                    template = cv2.resize(template, None, fx=scale, fy=scale)
                x, y, w, h = definition['region']
                margin = 20 if scale != 1 else 0
                bounds = self.matches(screen, template,
                    [x-margin, y-margin, w+2*margin, h+2*margin],
                    definition['threshold'], definition['max_color_error'])
                if len(bounds) != 1:
                    break
                controls[name] = bounds[0]
            if len(controls) == 2:
                tx, ty, tw, th = controls['levelup']
                cx, cy, cw, ch = controls['level_close']
                if abs(tx+tw/2-cx-cw/2) <= 40 and 490 <= cy+ch/2-ty-th/2 <= 565:
                    # Animation changes the arrow position every frame. The
                    # popup close area stays fixed, so stable-frame checks and
                    # the final pre-tap observation must use that area instead.
                    controls['level_close_arrow'] = controls['level_close']
                    controls['level_close'] = tuple(self.config['levelup_close_bounds'])
                    return controls
        return None

    def forbidden(self, screen):
        found = []
        # Shop icons are smaller than the loot-card references. Search that
        # footprint only inside a verified display, without widening all scans.
        shop_display = bool(self.all(screen, 'shop_frame') and self.all(screen, 'shop_display_base'))
        for name, template in self.blocked:
            searches = [(scale, [0, 0, 1280, 720]) for scale in (1., .85, .9, .8, 1.1)]
            if shop_display:
                searches.append((64/max(template.shape[:2]), [380, 80, 780, 520]))
            for scale, region in searches:
                scaled = template if scale == 1 else cv2.resize(template, None, fx=scale, fy=scale)
                for bounds in self.matches(screen, scaled, region, .88, .18):
                    x,y,w,h = bounds
                    if not any(old_name == name and abs(ox+ow/2-x-w/2)<max(w,ow)/2
                               and abs(oy+oh/2-y-h/2)<max(h,oh)/2 for old_name,(ox,oy,ow,oh) in found):
                        found.append((name,bounds))
        return found

    def arrows(self, screen):
        arrows = self.all(screen, 'arrow')
        for bounds in self.all(screen, 'arrow_boss'):
            if not any(abs(bounds[0]-old[0])<15 and abs(bounds[1]-old[1])<15 for old in arrows):
                arrows.append(bounds)
        return arrows

    def candidates(self, screen):
        arrows = self.arrows(screen)
        candidates = []
        for name in self.config['priority'] + ['boss']:
            for b in self.all(screen, 'node_'+name):
                x,y,w,h = b
                if any(abs(ax+aw/2-x-w/2)<22 and 0<y-ay<45 for ax,ay,aw,ah in arrows):
                    candidates.append((name, b))
        # Every reachable marker must resolve to exactly one type, otherwise stop.
        if any(sum(abs(ax+aw/2-b[0]-b[2]/2)<22 and 0<b[1]-ay<45 for _,b in candidates) != 1
               for ax,ay,aw,ah in arrows):
            raise RecognitionPending('진입 가능 표시와 노드 종류를 명확히 연결하지 못했습니다.')
        return candidates

    def choose_node(self, screen):
        blocked = self.forbidden(screen)
        candidates = self.candidates(screen)
        # Blocks inside a node remove that candidate; unassociated blocks stop.
        for _, (bx,by,bw,bh) in blocked:
            linked = [c for c in candidates if c[1][0]-25 <= bx+bw/2 <= c[1][0]+c[1][2]+25
                      and c[1][1]-25 <= by+bh/2 <= c[1][1]+c[1][3]+25]
            if not linked:
                raise RuntimeError('금지 항목이 있는 선택 화면입니다. 대응 규칙 확인이 필요합니다.')
            candidates = [c for c in candidates if c not in linked]
        if not candidates:
            raise RuntimeError('선택 가능한 노드가 없습니다.')
        order = self.config['priority'] + ['boss']
        return min(candidates, key=lambda c:(order.index(c[0]), c[1][1], c[1][0]))

    def loot_choices(self, screen):
        """Apply global forbidden scan before choosing any verified loot card."""
        forbidden = self.forbidden(screen)
        cards = [tuple(b) for b in self.config['loot_cards']]
        anchors = sorted(self.all(screen, 'loot_reroll'))
        if len(anchors) != len(cards) or any(not (cx <= x+w/2 <= cx+cw and cy+ch <= y <= cy+ch+60)
                for (x,y,w,h),(cx,cy,cw,ch) in zip(anchors,cards)):
            raise RecognitionPending('전리품 카드 배치를 확인하지 못했습니다.')
        blocked = set()
        for name, (x,y,w,h) in forbidden:
            owners = [i for i,(cx,cy,cw,ch) in enumerate(cards)
                      if cx <= x+w/2 <= cx+cw and cy <= y+h/2 <= cy+ch]
            if len(owners) != 1:
                raise RuntimeError('금지 이미지가 속한 전리품 카드를 확정하지 못했습니다.')
            blocked.add(owners[0])
        return [b for i,b in enumerate(cards) if i not in blocked]

    def selected_loot(self, screen):
        edges = self.all(screen, 'loot_selected_edge')
        if len(edges) != 1: return None
        x,y,w,h=edges[0]
        cards=[tuple(b) for b in self.config['loot_cards'] if abs(b[0]-x)<22]
        return cards[0] if len(cards)==1 else None

    def loot_consume_plus(self, screen):
        x, y, w, h = self.config['event_loot_consume_plus_region']
        sample = screen[y:y+h, x:x+w]
        if sample.shape[:2] != (h, w):
            return False
        hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 1] < 80) & (hsv[:, :, 2] >= 190)).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            cx, cy, cw, ch = cv2.boundingRect(contour)
            if not (24 <= cw <= 40 and 24 <= ch <= 40 and abs(cw-ch) <= 4):
                continue
            if abs(cx+cw/2-w/2) > 5 or abs(cy+ch/2-h/2) > 5:
                continue
            cross = mask[cy:cy+ch, cx:cx+cw]
            horizontal = cross[ch//2-2:ch//2+3].any(axis=0).mean()
            vertical = cross[:, cw//2-2:cw//2+3].any(axis=1).mean()
            if horizontal >= .85 and vertical >= .85 and cross.mean() <= .35:
                return True
        return False

    def is_loot_consume(self, screen):
        # A plus identifies the empty slot. Selection replaces it with an item
        # and its remove control; inventory geometry is required in both cases.
        slot = (self.loot_consume_plus(screen)
                or self.find(screen, 'event_loot_consume_selected_slot'))
        return bool(slot and self.loot_consume_choices(screen))

    def loot_consume_choices(self, screen):
        sub = screen[145:470, 650:1140]
        gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        centers = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if 55 <= w <= 110 and 55 <= h <= 110 and abs(w - h) < 15:
                cx, cy = 650 + x + w // 2, 145 + y + h // 2
                if 170 <= cy <= 435 and cx >= 675:
                    if not any(abs(cx - ox) < 20 and abs(cy - oy) < 20 for ox, oy in centers):
                        centers.append((cx, cy))
        centers.sort(key=lambda point: (point[1]//30, point[0]))
        return centers

    def loot_consume_target(self, screen):
        items = self.loot_consume_choices(screen)
        if not items:
            return None
        blocked = self.forbidden(screen)
        # Inventory thumbnails may be smaller than the acquisition cards.
        for name, template in self.blocked:
            for scale in (.5, .6, .7):
                sample = cv2.resize(template, None, fx=scale, fy=scale)
                blocked.extend((name, bounds) for bounds in self.matches(
                    screen, sample, [650,145,490,325], .88, .18))
        banned = [point for point in items if any(
            abs(point[0]-(x+w/2)) <= 42 and abs(point[1]-(y+h/2)) <= 42
            for _, (x,y,w,h) in blocked)]
        return (banned or items)[0]

    def loot_consume_selected(self, screen, item_icon):
        """Require the chosen icon in the sacrifice slot AND a 1/1 counter."""
        matched = False
        for scale in (.8, .9, 1., 1.1, 1.2):
            sample = cv2.resize(item_icon, None, fx=scale, fy=scale)
            if self.matches(screen, sample, [855,516,84,84], .80, .20):
                matched = True
                break
        if not matched:
            return False
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        rows, _ = self.ocr(cv2.resize(screen[650:686,575:718], None, fx=3, fy=3),
                           use_det=False, use_cls=False)
        return bool(rows and any(score >= .85 and re.search(r'(?<!\d)1\s*/\s*1(?!\d)', text)
                                 for text, score in rows))

    def classify(self, screen):
        if self.battle_unclaimed_cancel(screen): return 'battle_unclaimed_reward'
        if self.find(screen, 'shop_purchase_dialog'): return 'shop_purchase_confirm'
        if self.find(screen, 'defeat'): return 'defeat'
        if self.find(screen, 'hero_departure_title') and self.find(screen, 'hero_departure_button'): return 'hero_departure'
        if self.find(screen, 'expedition_summary') and self.find(screen, 'summary_close'): return 'expedition_summary'
        if self.find(screen, 'exploration_entry'): return 'exploration_entry'
        if self.find(screen, 'shop_exit_dialog') and self.find(screen, 'story_confirm'): return 'shop_exit_confirm'
        if self.find(screen, 'unclaimed_dialog'): return 'unclaimed_reward'
        if self.rank_reward_controls(screen): return 'rank_reward'
        if self.recruit_reward_controls(screen): return 'recruit_reward'
        if self.find(screen, 'story_dialog'): return 'story_confirm'
        if self.event_warning_controls(screen): return 'event_warning'
        if self.find(screen, 'story_confirm'): return 'event_warning'
        if self.levelup_controls(screen): return 'levelup'
        if self.is_rank_result(screen): return 'rank_result'
        # Rank and loot results share the close icon. Partial rank geometry
        # must not authorize a loot close during a transition.
        if self.find(screen, 'rank_result_arrow'): return None
        if self.find(screen, 'event_loot_close'): return 'event_loot_popup'
        if self.is_loot_consume(screen): return 'event_loot_consume'
        if len(self.all(screen,'loot_reroll')) == 3 and (self.find(screen,'loot_button') or self.find(screen,'loot_button_dim')): return 'loot'
        if self.find(screen, 'victory') and self.find(screen, 'continue'):
            if self.find(screen, 'battle_rank_complete'): return 'battle_rank_complete'
            return 'victory'
        if self.find(screen,'shop_frame') and self.find(screen,'shop_exit'): return 'shop'
        if self.rest_controls(screen): return 'rest'
        if self.supply_controls(screen): return 'supply'
        if self.find(screen, 'rank_title'): return 'rank_menu'
        if self.find(screen, 'skip'): return 'story'
        if self.event_result_marker(screen) and self.find(screen, 'event_advance') and not self.event_cards(screen): return 'event_result'
        if self.known_event_candidates(screen):
            # Event headings/backgrounds can survive on the outcome page. Only
            # a visible advance arrow with no choice cards authorizes continuing.
            if self.find(screen, 'event_advance') and not self.event_cards(screen):
                return 'unknown_event_result'
            return 'event'
        if self.find(screen, 'battle_start'): return 'battle_setup'
        if self.find(screen, 'enter_node'):
            return self.detail_state(screen) or 'node_detail'
        if self.detail_state(screen):
            return None
        # An unrecognized detail pane can retain the map footer and arrows.
        # Do not select another map node while that pane's action is visible.
        if self.find(screen, 'action_frame') and self.find(screen, 'map_footer'):
            return None
        if self.find(screen, 'map_footer') and self.arrows(screen): return 'map'
        if self.find(screen, 'battle_ui'): return 'battle'
        return None

    @staticmethod
    def hero_departure_highlight(screen, bounds):
        x, y, w, h = bounds
        regions = ((x+25, y-8, x+w-20, y+9),
                   (x+25, y+h-5, x+w-20, y+h+10),
                   (x-10, y+10, x+15, y+h-10))
        for index, (x1, y1, x2, y2) in enumerate(regions):
            if x1 < 0 or y1 < 0 or x2 > screen.shape[1] or y2 > screen.shape[0]:
                return False
            hsv = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
            gold = cv2.inRange(hsv, np.array([10, 25, 150]), np.array([40, 255, 255]))
            if (gold > 0).any(axis=0 if index < 2 else 1).mean() < .75:
                return False
        return True

    def hero_departure_candidates(self, screen):
        if not (self.find(screen, 'hero_departure_title')
                and self.find(screen, 'hero_departure_button')):
            return []
        corners = self.all(screen, 'hero_departure_card')
        cards = []
        for y in (85, 190, 295, 400):
            bounds = (350, y, 290, 80)
            # The same gold border replaces the blue corner on a selected row.
            if (any(abs(x-353) <= 3 and abs(cy-(y+1)) <= 3 for x, cy, _, _ in corners)
                    or self.hero_departure_highlight(screen, bounds)):
                cards.append(bounds)
        return cards

    def hero_departure_selected(self, screen, bounds, portrait):
        if not (self.find(screen, 'hero_departure_title')
                and self.hero_departure_highlight(screen, bounds)):
            return None
        button = self.find(screen, 'hero_departure_button')
        if not button:
            return None
        x, y, w, h = button
        label = cv2.cvtColor(screen[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
        if np.count_nonzero(label >= 200) < 40:
            return None
        _, cy, _, _ = bounds
        # A reordered party must not authorize departing the old row's hero.
        if not self.matches(screen, portrait, [510, cy+6, 120, 65], .90, .15):
            return None
        return button

    def event_intro_panel(self, screen):
        """Recognize the compact narration panel, never its words or artwork."""
        if not self.find(screen, 'event_intro_panel') or self.event_cards(screen):
            return False
        # The panel's pale violet text forms multiple centered lines beneath
        # the ornament. Background stars alone must not authorize an input.
        text = self.event_intro_text_mask(screen)
        rows = np.count_nonzero(text, axis=1) >= 45
        starts = np.count_nonzero(rows & ~np.r_[False, rows[:-1]])
        return bool(starts >= 2 and np.count_nonzero(text) >= 700)

    @staticmethod
    def event_intro_text_mask(screen):
        hsv = cv2.cvtColor(screen[460:526, 280:1000], cv2.COLOR_BGR2HSV)
        return ((hsv[:, :, 0] >= 105) & (hsv[:, :, 0] <= 135)
                & (hsv[:, :, 1] >= 15) & (hsv[:, :, 1] <= 100)
                & (hsv[:, :, 2] >= 150))

    @staticmethod
    def event_result_page_changed(before, after):
        """Compare visual caption strokes, without OCR or an exact pixel hash.

        The illustration and moving advance arrow are outside this region.
        Small isolated particles and a couple of pixels of rendering drift do
        not acknowledge a click as a new result page.
        """
        def strokes(screen):
            hsv = cv2.cvtColor(screen[455:550, 260:1020, :3], cv2.COLOR_BGR2HSV)
            mask = ((hsv[:, :, 1] < 100) & (hsv[:, :, 2] > 170)).astype(np.uint8)*255
            mask = (cv2.resize(mask, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA) >= 128).astype(np.uint8)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            keep = np.zeros(count, np.uint8)
            keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 3
            return keep[labels]
        a, b = strokes(before), strokes(after)
        kernel = np.ones((3, 3), np.uint8)
        different = int(np.count_nonzero(a & ~cv2.dilate(b, kernel))
                        + np.count_nonzero(b & ~cv2.dilate(a, kernel)))
        total = int(a.sum()+b.sum())
        return different >= 30 and different/max(1, total) >= .10

    def event_result_marker(self, screen):
        names = list(dict.fromkeys(self.config.get('event_result_markers', []) + [e['result_marker'] for e in self.config.get('events', []) if e.get('result_marker')]))
        found = [name for name in names if self.find(screen, name)]
        return found[0] if len(found) == 1 else None

    def event_choice(self, screen, excluded=()):
        # Only reviewed outcomes are allowed; absence of a forbidden image alone
        # does not establish that an unknown event preserves the party.
        blocked = self.forbidden(screen)
        ids = self.known_event_candidates(screen)
        events = [e for e in self.config.get('events', []) if e['id'] in ids]
        if len(events) != 1: return None
        event = events[0]
        priority = self.config['event_effect_priority']
        candidates = [c for c in event['choices'] if c['effect'] in priority
                      and tuple(c['bounds']) not in excluded and self.find(screen, c['choice_marker'])]
        if not candidates: return None
        for _,(bx,by,bw,bh) in blocked:
            owners = [r for r in event['choice_regions'] if r[0] <= bx+bw/2 <= r[0]+r[2]
                      and r[1] <= by+bh/2 <= r[1]+r[3]]
            if len(owners) != 1: raise RuntimeError('이벤트 금지 이미지의 선택지 연결 확인이 필요합니다.')
            candidates = [c for c in candidates if c['bounds'] != owners[0]]
        if not candidates: raise RuntimeError('금지 항목 제외 후 허용 이벤트 선택지가 없습니다.')
        choice = min(candidates, key=lambda c: priority.index(c['effect']))
        return tuple(choice['bounds'])

    def known_event(self, screen):
        found = self.known_event_candidates(screen)
        return found[0] if len(found) == 1 else None

    def known_event_candidates(self, screen):
        # A temporarily hidden heading must not turn a saved choice into random input.
        strict = [e['id'] for e in self.config['events'] if self.find(screen,e['state_marker'])]
        if strict:
            return strict
        return [e['id'] for e in self.config['events']
                if self.find(screen,e['state_marker']) or
                any(self.find(screen,c['choice_marker']) for c in e['choices'])]

    def event_cards(self, screen):
        # Bottom corners remain visible when a magnifier replaces the top icon.
        left = sorted((x,y-100,w,h) for x,y,w,h in self.all(screen,'event_card_left'))
        right = sorted(self.all(screen,'event_card_right'))
        if len(left) in (1, 2, 3) and len(right) == len(left):
            cards = []
            for (x,y,_,_),(rx,ry,_,_) in zip(left,right):
                if abs(y-ry)>3 or not 330 <= rx-x <= 345: break
                cards.append((x+5,y+4,362,131))
            if len(cards) == len(left) and max(c[1] for c in cards)-min(c[1] for c in cards)<=3:
                if not any(a[0]+a[2] >= b[0] for a,b in zip(cards,cards[1:])):
                    return cards
        # Fallback: if right corners are partially obscured by background effects,
        # verify left corners form standard card positions
        if len(left) in (1, 2, 3) and bool(right):
            if len(left) >= 2:
                dxs = [b[0] - a[0] for a, b in zip(left, left[1:])]
                dys = [abs(b[1] - a[1]) for a, b in zip(left, left[1:])]
                if all(378 <= dx <= 382 for dx in dxs) and all(dy <= 3 for dy in dys):
                    if any(any(abs((rx - x) - 337) <= 5 and abs(ry - y) <= 3 for rx, ry, _, _ in right) for x, y, _, _ in left):
                        cards = [(x+5, y+4, 362, 131) for x, y, _, _ in left]
                        if not any(a[0]+a[2] >= b[0] for a,b in zip(cards,cards[1:])):
                            return cards
            elif len(left) == 1:
                x, y, _, _ = left[0]
                if any(330 <= rx - x <= 345 and abs(ry - y) <= 3 for rx, ry, _, _ in right):
                    return [(x+5, y+4, 362, 131)]
        return []

    def available_event_cards(self, screen, cards):
        blocked = self.forbidden(screen)
        available = []
        excluded = set()
        for _,(x,y,w,h) in blocked:
            owners = [i for i,(cx,cy,cw,ch) in enumerate(cards)
                      if cx <= x+w/2 <= cx+cw and cy <= y+h/2 <= cy+ch]
            if len(owners) != 1: raise RuntimeError('금지 이미지가 속한 이벤트 선택지를 확인하지 못했습니다.')
            excluded.add(owners[0])
        for i,(x,y,w,h) in enumerate(cards):
            interior = cv2.cvtColor(screen[y+22:y+h-12,x+15:x+w-15],cv2.COLOR_BGR2GRAY)
            if i not in excluded and np.percentile(interior,99) >= 170:
                available.append((x,y,w,h))
        return available

    def rank(self, screen, name):
        if self.is_rank_menu(screen):
            target_class = self.hero_to_class.get(name, name)
            if target_class in self.class_templates:
                scan = self.scan_rank_menu_heroes(screen)
                if target_class in scan and scan[target_class]['rank'] is not None:
                    return scan[target_class]['rank']

        bounds = self.find(screen, name)
        if not bounds: return None
        x, y, _, _ = bounds
        digit = self.read_rank_digit(screen[y+35:y+61, max(0, x-16):x+1])
        if digit is not None:
            return digit
        digit_wide = self.read_rank_digit(screen[y+35:y+61, max(0, x-30):x+6], allow_max=True)
        if digit_wide is not None:
            return digit_wide
        return None

    def is_rank_result(self, screen):
        return self.rank_result_controls(screen) is not None

    def rank_result_controls(self, screen):
        """Find mark → arrow → mark across a shared horizontal band."""
        arrows = self.all(screen, 'rank_result_arrow')
        if len(arrows) != 1:
            return None
        marks = sorted(self.all(screen, 'rank_result_mark'))
        if len(marks) != 2:
            return None
        controls = dict(rank_result_before_icon=marks[0], rank_result_after_icon=marks[1],
                        rank_result_arrow=arrows[0])
        lx, ly, lw, lh = controls['rank_result_before_icon']
        rx, ry, rw, rh = controls['rank_result_after_icon']
        ax, ay, aw, ah = controls['rank_result_arrow']
        if not (lx+lw < ax and ax+aw < rx
                and abs(ly+lh/2-ry-rh/2) <= 4
                and abs(ly+lh/2-ay-ah/2) <= 5):
            return None
        controls['rank_close'] = tuple(self.config['rank_result_close_bounds'])
        return controls

    def shop_currency_mask(self, screen):
        """Extract bright neutral digit strokes without reading their value."""
        x, y, w, h = self.config['shop_purchase']['currency_region']
        sample = screen[y:y+h, x:x+w]
        if sample.shape[:2] != (h, w):
            return None
        hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 1] < 80) & (hsv[:, :, 2] >= 175)
        if not 15 <= np.count_nonzero(mask) <= mask.size * .5:
            return None
        return mask

    @staticmethod
    def shop_currency_changed(before, after):
        union = np.count_nonzero(before | after)
        return np.count_nonzero(before != after) >= max(12, union * .1)

    @staticmethod
    def shop_currency_stable(before, after):
        union = np.count_nonzero(before | after)
        return np.count_nonzero(before != after) <= max(3, union * .03)

    def shop_number(self, screen, region):
        x,y,w,h = region
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        rows, _ = self.ocr(cv2.resize(screen[y:y+h,x:x+w],None,fx=3,fy=3),use_det=False,use_cls=False)
        if rows and len(rows)==1:
            text, score = rows[0]
            text = text.strip().replace(',', '')
            if score >= .9 and re.fullmatch(r'[0-9]{1,5}',text): return int(text)
        raise RecognitionPending('상점 가격 또는 보유 파편 재확인')

    def shop_investment_offer(self, screen):
        if self.classify(screen) != 'shop' and not self.noncombat_controls(screen, 'shop'):
            return None
        if self.find(screen, 'shop_insufficient_notice'): return ('skip',)
        product = self.find(screen, 'shop_future_investment')
        if not product:
            # Unaffordable and purchased cards dim their icon; the name stays
            # readable. Recover the same card origin without matching its art.
            title = self.find(screen, 'shop_future_investment_title')
            if title: product = (title[0]-30,title[1]-14,164,174)
        if not product: return ('skip',)
        x,y,w,h = product
        card = (x,y,w,240)
        if self.find(screen, 'shop_purchase_done', region=card): return ('skip',)
        for _,(bx,by,bw,bh) in self.forbidden(screen):
            if x <= bx+bw/2 <= x+w and y <= by+bh/2 <= y+240:
                return ('skip',)
        cfg = self.config['shop_purchase']
        px,py,pw,ph = cfg['price_offset']
        if self.shop_price_unaffordable(screen,(x+px,y+py,pw,ph)): return ('skip',)
        price = self.shop_number(screen,(x+px,y+py,pw,ph))
        balance = self.shop_number(screen,cfg['currency_region'])
        if price <= 0 or price > balance: return ('skip',)
        bx,by,bw,bh = cfg['button_offset']
        return ('buy',price,balance,x,y,x+bx,y+by,bw,bh)

    @staticmethod
    def shop_price_unaffordable(screen, region):
        x,y,w,h = region
        sample = screen[y:y+h,x:x+w]
        if sample.shape[:2] != (h,w): return False
        hsv = cv2.cvtColor(sample,cv2.COLOR_BGR2HSV)
        red = ((hsv[:,:,0] <= 10) | (hsv[:,:,0] >= 170)) & (hsv[:,:,1] >= 150) & (hsv[:,:,2] >= 140)
        # Only inspect the target's price digits, never neighbouring products.
        return int(red.sum()) >= max(8, int(w*h*.015))

    def summary_controls(self, screen):
        """Recognize the statistics icon row and close symbol, never the title."""
        controls = {}
        for name in ('expedition_summary', 'summary_nodes_icon', 'summary_fragments_icon',
                     'summary_loot_icon', 'summary_close'):
            found = self.all(screen, name)
            if len(found) != 1:
                return None
            controls[name] = found[0]
        return controls

    def summary_boss_count(self, screen):
        if self.classify(screen) != 'expedition_summary':
            return None
        x, y, w, h = self.config['summary_boss_count_region']
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        rows, _ = self.ocr(cv2.resize(screen[y:y+h, x:x+w], None, fx=4, fy=4),
                           use_det=False, use_cls=False)
        if not rows or len(rows) != 1:
            return None
        text, confidence = rows[0]
        text = text.strip()
        if confidence >= .95 and text in ('0', '1', '2', '3'):
            return int(text)
        return None

    def read_rank_digit(self, sample, allow_max=True):
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        rows, _ = self.ocr(cv2.resize(sample, None, fx=4, fy=4), use_det=False, use_cls=False)
        if not rows or len(rows) != 1: return None
        text, confidence = rows[0]
        cleaned = text.strip()
        upper = cleaned.upper()
        if allow_max and (any(tok in upper for tok in ('MAX', 'MA', 'MX', '최대')) or 'MAX' in upper):
            return 5
        if confidence >= .65:
            for ch in cleaned:
                if ch in ('1', '2', '3', '4', '5'):
                    return int(ch)
                if ch in ('S', 's'):
                    return 5
        return None

    @staticmethod
    def progress_signature(screen):
        # Turn portraits and acting hero label; exclude animated battlefield and skills.
        return np.concatenate([screen[115:490, 0:72].flatten(), screen[628:663, 205:485].flatten()]).astype(float)
