"""Observe one shop row and its quantity transition without fixed button colors."""
from dataclasses import dataclass
import logging
import re

import cv2
import numpy as np

from .image_matcher import ImageMatcher
from .shop_debug import debug_timed


logger = logging.getLogger(__name__)


@dataclass
class PurchaseBaseline:
    item_bounds: tuple
    button_bounds: tuple
    item_image: np.ndarray
    counter_mask: np.ndarray
    button_image: np.ndarray = None


class ShopPurchaseObserver:
    def __init__(self, active, disabled, diagnostics=None):
        self._shop_debug = diagnostics
        if active.shape[:2] != disabled.shape[:2]:
            raise ValueError('활성·비활성 구입 버튼 이미지 크기가 다릅니다.')
        self.templates = (active, disabled)
        self.ocr = None
        self.glyphs = [self._glyphs(image[:, :, :3]) for image in self.templates]
        if any(glyphs is None for glyphs in self.glyphs):
            raise ValueError('구입 버튼 수량 영역을 읽을 수 없습니다.')

    @staticmethod
    def counter_image(button):
        # The existing button assets are 183x53; the counter is left of the label.
        normalized = cv2.resize(button[:, :, :3], (183, 53))
        return normalized[10:40, 23:76]

    @classmethod
    def counter_mask(cls, button):
        gray = cv2.cvtColor(cls.counter_image(button), cv2.COLOR_BGR2GRAY)
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    @classmethod
    def _glyphs(cls, button):
        mask = cls.counter_mask(button)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        components = sorted((tuple(stat) for stat in stats[1:] if stat[4] >= 5), key=lambda s: s[0])
        if len(components) != 3:
            return None
        glyphs = []
        for index, (x, y, w, h, area) in enumerate(components):
            if not (2 <= w <= 15 and 10 <= h <= 24 and 3 <= y <= 12):
                return None
            left, right = ((8, 24), (20, 33), (29, 45))[index]
            if not left <= x <= right:
                return None
            glyphs.append(cv2.resize(mask[y:y+h, x:x+w], (20, 28), interpolation=cv2.INTER_NEAREST) > 0)
        return glyphs

    @staticmethod
    def _glyph_score(left, right):
        return 2 * np.count_nonzero(left & right) / max(1, np.count_nonzero(left) + np.count_nonzero(right))

    @debug_timed('recognition')
    def counter_state(self, button, allow_ocr=False):
        glyphs = self._glyphs(button)
        if glyphs is not None:
            scores = [min(self._glyph_score(a, b) for a, b in zip(glyphs, reference))
                      for reference in self.glyphs]
            winner = int(scores[1] > scores[0])
            if self._shop_debug is not None:
                self._shop_debug.record('counter_scores', active_score=float(scores[0]),
                                        sold_score=float(scores[1]), margin=float(abs(scores[0]-scores[1])))
            if scores[winner] >= .80 and scores[winner] - scores[1-winner] >= .12:
                state = ('available', 'sold')[winner]
                if self._shop_debug is not None:
                    self._shop_debug.record('counter_read', method_used='glyph', state=state)
                return state
        if self._shop_debug is not None:
            self._shop_debug.record('counter_read', method_used='glyph', state='unknown')
            self._shop_debug.evidence('ambiguous_counter', button)
        if not allow_ocr:
            return None
        try:
            if self.ocr is None:
                self.ocr = self._create_ocr()
            sample = cv2.resize(self.counter_image(button), None, fx=4, fy=4)
            rows, _ = self._read_ocr(sample)
            if rows and len(rows) == 1:
                text, score = rows[0]
                text = re.sub(r'\s', '', text)
                if self._shop_debug is not None:
                    self._shop_debug.record('ocr_result', text=text[:80], confidence=float(score))
                if score >= .90 and text in ('1/1', '0/1'):
                    return {'1/1': 'available', '0/1': 'sold'}[text]
        except Exception:
            logger.warning('구입 수량 OCR 재확인 실패', exc_info=True)
        return None

    @debug_timed('ocr_load')
    def _create_ocr(self):
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)

    @debug_timed('ocr')
    def _read_ocr(self, sample):
        return self.ocr(sample, use_det=False, use_cls=False)

    @staticmethod
    def _shape_scores(screen, template):
        return ImageMatcher.match_template(screen, template, shape_only=True)

    @classmethod
    def locate_item(cls, screen, template, expected, threshold=.95, tolerance=24,
                    stable_inner=False, diagnostics=None):
        x, y, w, h = expected
        left, top = max(0, x-tolerance), max(0, y-tolerance)
        right, bottom = min(screen.shape[1], x+w+tolerance), min(screen.shape[0], y+h+tolerance)
        region = screen[top:bottom, left:right]
        th, tw = template.shape[:2]
        if min(left, top) < 0 or region.shape[0] < th or region.shape[1] < tw:
            return None
        _, score, _, point = cv2.minMaxLoc(cls._shape_scores(region, template))
        full_score = score
        match_region = 'full'
        inner_score = None
        if score < threshold:
            _, color_score, _, color_point = cv2.minMaxLoc(
                ImageMatcher.match_template(region, template, shape_only=False)
            )
            if color_score > score:
                score, point = color_score, color_point
                full_score = color_score
                match_region = 'full_color'
        if score < threshold and stable_inner:
            # Purchase overlays change the frame, count label and outer glow.
            # Keep a substantial part of the artwork and the original row bounds.
            cx, cy = max(1, round(tw*.12)), max(1, round(th*.12))
            right_edge, bottom_edge = round(tw*.88), round(th*.80)
            core = template[cy:bottom_edge, cx:right_edge]
            if min(core.shape[:2]) >= 12 and core.shape[0]*core.shape[1] >= tw*th*.40:
                # Restrict candidate SLOT origins to the same +/-24px search as
                # full matching. The cropped template must not widen that search.
                search = region[cy:region.shape[0]-(th-bottom_edge),
                                cx:region.shape[1]-(tw-right_edge)]
                _, inner_score, _, inner_point = cv2.minMaxLoc(cls._shape_scores(search, core))
                if inner_score >= threshold:
                    score, point, match_region = inner_score, inner_point, 'inner'
        bounds = (left+point[0], top+point[1], tw, th) if score >= threshold else None
        if diagnostics is not None:
            diagnostics.record('item_anchor', expected=list(expected), bounds=list(bounds) if bounds else None,
                               match_region=match_region if bounds else None, threshold=threshold,
                               full_score=float(full_score), inner_score=float(inner_score) if inner_score is not None else None)
        return bounds

    def _button_near(self, screen, expected, radius=3):
        x, y, w, h = expected
        left, top = max(0, x-radius), max(0, y-radius)
        region = screen[top:min(screen.shape[0], y+h+radius), left:min(screen.shape[1], x+w+radius)]
        best = None
        for template in self.templates:
            th, tw = template.shape[:2]
            if region.shape[0] < th or region.shape[1] < tw:
                continue
            _, score, _, point = cv2.minMaxLoc(self._shape_scores(region, template))
            if best is None or score > best[0]:
                best = (score, (left+point[0], top+point[1], tw, th))
        return best

    @debug_timed('recognition')
    def find_button(self, screen, item_bounds, threshold=.82, y_tolerance=50):
        x, y, w, h = item_bounds
        center_y = y + h / 2
        left, top = x+w, max(0, int(center_y-y_tolerance-27))
        bottom = min(screen.shape[0], int(center_y+y_tolerance+27))
        region = screen[top:bottom, left:]
        candidates = []
        cand_threshold = min(threshold, 0.82)
        for template in self.templates:
            th, tw = template.shape[:2]
            if region.shape[0] < th or region.shape[1] < tw:
                continue
            scores = self._shape_scores(region, template)
            for _ in range(8):
                _, score, _, point = cv2.minMaxLoc(scores)
                if score < cand_threshold:
                    break
                bx, by = point
                bounds = (left+bx, top+by, tw, th)
                distance = abs(bounds[1]+th/2-center_y)
                if distance <= y_tolerance:
                    candidates.append((distance, -score, bounds))
                scores[max(0, by-th//2):by+th//2+1, max(0, bx-tw//2):bx+tw//2+1] = -1
        seen = set()
        for distance, negative_score, bounds in sorted(candidates):
            if bounds in seen:
                continue
            seen.add(bounds)
            bx, by, bw, bh = bounds
            if self._shop_debug is not None:
                self._shop_debug.record('button_candidate', bounds=list(bounds), shape_score=float(-negative_score))
            state = self.counter_state(screen[by:by+bh, bx:bx+bw], allow_ocr=True)
            if state is not None:
                return bounds, state
        return None

    def baseline(self, screen, item_bounds, button_bounds):
        x, y, w, h = item_bounds
        bx, by, bw, bh = button_bounds
        return PurchaseBaseline(item_bounds, button_bounds, screen[y:y+h, x:x+w].copy(),
                                self.counter_mask(screen[by:by+bh, bx:bx+bw]),
                                screen[by:by+bh, bx:bx+bw].copy() if self._shop_debug is not None else None)

    @debug_timed('recognition')
    def purchase_complete(self, screen, before, threshold=.92):
        item = self.locate_item(screen, before.item_image, before.item_bounds,
                                threshold=threshold, stable_inner=True,
                                diagnostics=self._shop_debug)
        if item is None:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='same_item_not_found', same_item=False)
                x, y, w, h = before.item_bounds
                self._shop_debug.evidence('same_item_not_found', before.item_image,
                                          screen[max(0, y):y+h, max(0, x):x+w])
            return False
        bx, by, bw, bh = before.button_bounds
        bx += item[0] - before.item_bounds[0]
        by += item[1] - before.item_bounds[1]
        if min(bx, by) < 0 or bx+bw > screen.shape[1] or by+bh > screen.shape[0]:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='button_out_of_bounds')
            return False
        # An interior icon peak may differ by one pixel from the full-slot peak.
        # Refine only within this button, never search other rows for a sold one.
        nearby = self._button_near(screen, (bx, by, bw, bh))
        shape_score = nearby[0] if nearby is not None else -1.0
        if shape_score < .80:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='button_shape_unconfirmed', shape_score=shape_score)
                self._shop_debug.evidence('button_shape_unconfirmed', before.button_image, screen[by:by+bh, bx:bx+bw])
            return False
        refined = nearby[1]
        button_offset = [refined[0]-bx, refined[1]-by]
        bx, by, bw, bh = refined
        button = screen[by:by+bh, bx:bx+bw]
        state = self.counter_state(button, allow_ocr=True)
        if state != 'sold':
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='counter_not_sold', state=state,
                                        same_item=True, shape_score=shape_score)
                self._shop_debug.evidence('counter_not_sold', before.button_image, button)
            return False
        changed = np.count_nonzero(self.counter_mask(button) != before.counter_mask)
        complete = changed >= max(6, before.counter_mask.size * .015)
        if self._shop_debug is not None:
            self._shop_debug.record('purchase_check', result=bool(complete), reason='quantity_transition' if complete else 'counter_unchanged',
                                    same_item=True, before='1/1', after='0/1',
                                    changed_pixels=int(changed), shape_score=shape_score,
                                    button_refinement=button_offset,
                                    item_offset=[item[0]-before.item_bounds[0], item[1]-before.item_bounds[1]])
            if not complete:
                self._shop_debug.evidence('counter_unchanged', before.button_image, button)
        return complete
