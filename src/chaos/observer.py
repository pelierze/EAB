"""Data-driven observations for exploration hero recruitment."""

import json
from pathlib import Path

import cv2
import numpy as np

from src.image_matcher import ImageMatcher, read_image
from .theme_selection import ThemeSelectionDetector
from .template_masks import apply_exclusions, color_error, matches_fixed_mask


class RecruitmentObserver:
    @staticmethod
    def load_config(resource_root):
        return json.loads((Path(resource_root) / "src/chaos/recruitment_layout.json").read_text(encoding="utf-8"))

    def __init__(self, resource_root: Path, hero_ids=None):
        root = Path(resource_root)
        self.config = self.load_config(root)
        if hero_ids is None:
            hero_ids = [self.config["classes"][key]["default_hero"] for key in self.config["class_order"]]
        if not hero_ids or any(key not in self.config["heroes"] for key in hero_ids):
            raise ValueError("지원하지 않는 영웅 구성입니다.")
        self.heroes = [dict(self.config["heroes"][key], id=key) for key in hero_ids]
        if len({hero["class"] for hero in self.heroes}) != len(self.heroes):
            raise ValueError("직업마다 영웅 한 명만 선택할 수 있습니다.")
        self.heroes.sort(key=lambda hero: self.config["class_order"].index(hero["class"]))
        self.assets = root / "images/chaos/hero_selection"
        self.theme = ThemeSelectionDetector(self.assets / "templates/themes")
        self.templates = {}
        self.template_variants = {}
        self.role_icon_markers = {role['header'] for role in self.config['classes'].values()}
        self.portrait_markers = {hero["portrait"] for hero in self.config["heroes"].values()}
        sources = {}
        needed = {"start", "unlock", "confirm_theme", "recruit_card", "filter", "filter_panel", "recruit_active", "completed"}
        for element in ("dark", "fire", "ice", "forest", "light"):
            needed.add(element + "_2")
            if element + '_1' in self.config['markers']:
                needed.add(element + '_1')
        for hero in self.heroes:
            role = self.config["classes"][hero["class"]]
            needed.update((role["anchor"], role["header"], role["completed_icon"], hero["portrait"], hero["selected"], hero["completed_name"], hero["element"] + "_1"))
            fallback_id = hero.get("fallback") or role.get("default_hero")
            if fallback_id and fallback_id in self.config["heroes"]:
                fb = self.config["heroes"][fallback_id]
                needed.update((fb["portrait"], fb["selected"], fb["completed_name"], fb["element"] + "_1"))
        for name in sorted(needed):
            definition = self.config["markers"][name]
            path = self.assets / definition["file"]
            if path not in sources:
                sources[path] = read_image(str(path))
            source = sources[path]
            if source is None:
                raise ValueError(f"자동 탐사 이미지 누락: {path}")
            if "crop" in definition:
                x, y, w, h = definition["crop"]
                if min(x, y) < 0 or min(w, h) <= 0 or x + w > source.shape[1] or y + h > source.shape[0]:
                    raise ValueError(f"잘못된 원본 이미지 영역: {name}")
                source = source[y:y + h, x:x + w]
            self.templates[name] = apply_exclusions(source, definition.get('exclude'), name)
            if name in self.portrait_markers:
                variants = [self.templates[name]]
                for filename in definition.get("alternate_files", []):
                    path = self.assets / filename
                    if path not in sources:
                        sources[path] = read_image(str(path))
                    alternate = sources[path]
                    if alternate is None:
                        raise ValueError(f"자동 탐사 이미지 누락: {path}")
                    if alternate.shape != source.shape:
                        raise ValueError(f"영웅 대체 이미지 크기 불일치: {name}: {path}")
                    variants.append(alternate.copy())
                self.template_variants[name] = tuple(variants)

    def validate_screen(self, screen):
        if screen is None:
            raise RuntimeError("ADB 화면 이미지를 읽지 못했습니다.")
        if (screen.shape[1], screen.shape[0]) != tuple(self.config["reference_size"]):
            raise RuntimeError("자동 탐사는 1280×720 화면에서 실행해 주세요.")

    def find(self, screen, name, region=None):
        bounds = self._find_template(screen, name, region)
        if name != 'filter_panel' or bounds is None:
            return bounds
        # The border alone could belong to another dialog. Require distinct
        # element symbols in the panel's element row as an independent anchor.
        row = self.config['filter_element_row']
        seen = 0
        for element in ('fire', 'forest', 'light', 'dark'):
            if any(self._find_template(screen, element + suffix, row) is not None
                   for suffix in ('_1', '_2')):
                seen += 1
        return bounds if seen >= 3 else None

    def _find_template(self, screen, name, region=None):
        if name not in self.templates:
            return None
        definition = self.config["markers"][name]
        region = region if region is not None else definition.get("region", [0, 0, 1280, 720])
        x, y, w, h = map(int, region)
        if x < 0 or y < 0 or x + w > screen.shape[1] or y + h > screen.shape[0]:
            return None
        template = self.templates[name]
        th, tw = template.shape[:2]
        if h < th or w < tw:
            return None
        sample = screen[y:y + h, x:x + w]
        threshold = definition.get("threshold", 0.90)
        if template.shape[2] == 4 and (h, w) == (th, tw):
            return ((x, y, tw, th) if matches_fixed_mask(
                sample, template, threshold, definition.get('max_color_error', .09)) else None)
        result = ImageMatcher.match_template(sample, template)
        if name in self.role_icon_markers:
            # List icons identify the role, not a click target. Repeated icons
            # are expected; background colors must not reject the same symbol.
            if self.find(screen, 'filter_panel') is not None:
                # The popup itself contains every role's icon. Only the visible
                # hero list outside the popup may identify the current role.
                px, py, pw, ph = self.config['filter_panel_bounds']
                left, top = max(0, px-x-tw+1), max(0, py-y-th+1)
                right, bottom = min(result.shape[1], px+pw-x), min(result.shape[0], py+ph-y)
                if right > left and bottom > top:
                    result[top:bottom, left:right] = -1
            _, score, _, (mx, my) = cv2.minMaxLoc(result)
            return (x + mx, y + my, tw, th) if score >= threshold else None
        if name in self.portrait_markers:
            # Multiple owned copies of the requested hero are interchangeable.
            # Use screen order so minor score changes do not move the target.
            candidates = []
            for index, variant in enumerate(self.template_variants[name]):
                if index:
                    result = cv2.matchTemplate(sample, variant, cv2.TM_CCOEFF_NORMED)
                while True:
                    _, score, _, (mx, my) = cv2.minMaxLoc(result)
                    if score < threshold:
                        break
                    matched = sample[my:my + th, mx:mx + tw]
                    error = float(np.abs(matched.astype(np.float32) - variant).mean() / 255)
                    if error <= definition.get("max_color_error", 0.09):
                        candidates.append((x + mx, y + my, tw, th))
                    result[max(0, my - th // 2):my + th // 2 + 1,
                           max(0, mx - tw // 2):mx + tw // 2 + 1] = -1
            return min(candidates, key=lambda bounds: (bounds[1], bounds[0])) if candidates else None
        _, score, _, (mx, my) = cv2.minMaxLoc(result)
        if score < threshold:
            return None
        matched = sample[my:my + th, mx:mx + tw]
        error = color_error(matched, template)
        if error > definition.get("max_color_error", 0.09):
            return None
        # Another independent hit makes the click target ambiguous.
        result[max(0, my - th // 2):my + th // 2 + 1,
               max(0, mx - tw // 2):mx + tw // 2 + 1] = -1
        if float(result.max()) >= threshold:
            return None
        return (x + mx, y + my, tw, th)

    def hero_completed(self, screen, hero):
        # Each completed card has a small class symbol at its lower right.
        # Its fixed slot separates it from list icons and unrecruited tickets.
        role = self.config["classes"][hero["class"]]
        return (self.find(screen, role["completed_icon"]) is not None
                and self.class_button(screen, hero) is None)

    def hero_selected(self, screen, portrait):
        """Verify the gold outline on this card, independent of hero name/art.

        Portrait crops end near the right edge of the shared 300x90 card.
        Check three separate edges so gold stars or artwork cannot authorize
        recruitment. Geometry uses the validated 1280x720 reference screen.
        """
        x, y, w, _ = map(int, portrait)
        right = x + w + 8
        left = right - 300
        regions = ((left + 25, y - 16, right - 25, y + 2),
                   (left + 25, y + 70, right - 25, y + 92),
                   (left - 8, y + 8, left + 20, y + 65))
        for index, (x1, y1, x2, y2) in enumerate(regions):
            if x1 < 0 or y1 < 0 or x2 > screen.shape[1] or y2 > screen.shape[0]:
                return False
            hsv = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
            gold = cv2.inRange(hsv, np.array([10, 25, 150]), np.array([40, 255, 255]))
            coverage = (gold > 0).any(axis=0 if index < 2 else 1).mean()
            if coverage < 0.75:
                return False
        return True

    def completed(self, screen):
        return all(self.hero_completed(screen, hero) for hero in self.heroes)

    def class_button(self, screen, hero):
        role = self.config["classes"][hero["class"]]
        anchor = self.find(screen, role["anchor"])
        if not anchor:
            return None
        x, y, w, h = anchor
        dx, dy, rw, rh = self.config["button_offset"]
        return self.find(screen, "recruit_card", (x + w // 2 + dx, y + h // 2 + dy, rw, rh))

    def header(self, screen, hero):
        return self.find(screen, self.config["classes"][hero["class"]]["header"])

    def get_fallback_hero(self, hero):
        fallback_id = hero.get("fallback") or self.config["classes"][hero["class"]].get("default_hero")
        if fallback_id and fallback_id in self.config["heroes"] and fallback_id != hero.get("id"):
            return dict(self.config["heroes"][fallback_id], id=fallback_id)
        return None

    def replace_hero(self, old_hero_id, new_hero):
        for i, h in enumerate(self.heroes):
            if h.get("id") == old_hero_id or h.get("class") == new_hero.get("class"):
                self.heroes[i] = new_hero
                return True
        return False


class KnightObserver(RecruitmentObserver):
    """Keep the independently testable knight milestone available."""
    def __init__(self, resource_root):
        super().__init__(resource_root, ["shadow_rose"])

    def knight_button(self, screen):
        return self.class_button(screen, self.heroes[0])
