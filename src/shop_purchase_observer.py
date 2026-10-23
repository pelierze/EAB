"""Observe one shop row and its quantity transition without fixed button colors."""
from dataclasses import dataclass
import logging
import re

import cv2
import numpy as np

from .image_matcher import ImageMatcher


logger = logging.getLogger(__name__)


@dataclass
class PurchaseBaseline:
    item_bounds: tuple
    button_bounds: tuple
    item_image: np.ndarray
    counter_mask: np.ndarray


class ShopPurchaseObserver:
    def __init__(self, active, disabled):
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

    def counter_state(self, button, allow_ocr=False):
        glyphs = self._glyphs(button)
        if glyphs is not None:
            scores = [min(self._glyph_score(a, b) for a, b in zip(glyphs, reference))
                      for reference in self.glyphs]
            winner = int(scores[1] > scores[0])
            if scores[winner] >= .80 and scores[winner] - scores[1-winner] >= .12:
                return ('available', 'sold')[winner]
        if not allow_ocr:
            return None
        try:
            if self.ocr is None:
                from rapidocr_onnxruntime import RapidOCR
                self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
            sample = cv2.resize(self.counter_image(button), None, fx=4, fy=4)
            rows, _ = self.ocr(sample, use_det=False, use_cls=False)
            if rows and len(rows) == 1:
                text, score = rows[0]
                text = re.sub(r'\s', '', text)
                if score >= .90 and text in ('1/1', '0/1'):
                    return {'1/1': 'available', '0/1': 'sold'}[text]
        except Exception:
            logger.warning('구입 수량 OCR 재확인 실패', exc_info=True)
        return None

    @staticmethod
    def _shape_scores(screen, template):
        return ImageMatcher.match_template(screen, template, shape_only=True)

    @classmethod
    def locate_item(cls, screen, template, expected, threshold=.95, tolerance=24):
        x, y, w, h = expected
        left, top = max(0, x-tolerance), max(0, y-tolerance)
        right, bottom = min(screen.shape[1], x+w+tolerance), min(screen.shape[0], y+h+tolerance)
        region = screen[top:bottom, left:right]
        th, tw = template.shape[:2]
        if min(left, top) < 0 or region.shape[0] < th or region.shape[1] < tw:
            return None
        _, score, _, point = cv2.minMaxLoc(cls._shape_scores(region, template))
        if score < threshold:
            return None
        return (left+point[0], top+point[1], tw, th)

    def find_button(self, screen, item_bounds, threshold=.92, y_tolerance=50):
        x, y, w, h = item_bounds
        center_y = y + h / 2
        left, top = x+w, max(0, int(center_y-y_tolerance-27))
        bottom = min(screen.shape[0], int(center_y+y_tolerance+27))
        region = screen[top:bottom, left:]
        candidates = []
        for template in self.templates:
            th, tw = template.shape[:2]
            if region.shape[0] < th or region.shape[1] < tw:
                continue
            scores = self._shape_scores(region, template)
            for _ in range(8):
                _, score, _, point = cv2.minMaxLoc(scores)
                if score < threshold:
                    break
                bx, by = point
                bounds = (left+bx, top+by, tw, th)
                distance = abs(bounds[1]+th/2-center_y)
                if distance <= y_tolerance:
                    candidates.append((distance, -score, bounds))
                scores[max(0, by-th//2):by+th//2+1, max(0, bx-tw//2):bx+tw//2+1] = -1
        seen = set()
        for _, _, bounds in sorted(candidates):
            if bounds in seen:
                continue
            seen.add(bounds)
            bx, by, bw, bh = bounds
            state = self.counter_state(screen[by:by+bh, bx:bx+bw], allow_ocr=True)
            if state is not None:
                return bounds, state
        return None

    def baseline(self, screen, item_bounds, button_bounds):
        x, y, w, h = item_bounds
        bx, by, bw, bh = button_bounds
        return PurchaseBaseline(item_bounds, button_bounds, screen[y:y+h, x:x+w].copy(),
                                self.counter_mask(screen[by:by+bh, bx:bx+bw]))

    def purchase_complete(self, screen, before):
        item = self.locate_item(screen, before.item_image, before.item_bounds)
        if item is None:
            return False
        bx, by, bw, bh = before.button_bounds
        bx += item[0] - before.item_bounds[0]
        by += item[1] - before.item_bounds[1]
        if min(bx, by) < 0 or bx+bw > screen.shape[1] or by+bh > screen.shape[0]:
            return False
        button = screen[by:by+bh, bx:bx+bw]
        # A different row or a popup must not supply the completion evidence.
        if max(float(self._shape_scores(button, t).max()) for t in self.templates) < .80:
            return False
        state = self.counter_state(button, allow_ocr=True)
        if state != 'sold':
            return False
        changed = np.count_nonzero(self.counter_mask(button) != before.counter_mask)
        return changed >= max(6, before.counter_mask.size * .015)
