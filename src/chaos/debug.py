"""Opt-in, bounded exploration evidence from frames already captured by the bot."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

import cv2

from src.image_matcher import ImageMatcher
from .template_masks import color_error

logger = logging.getLogger(__name__)


class _DiagnosticHandler(RotatingFileHandler):
    def handleError(self, record):
        raise


class ExplorationDebugRecorder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.handler = _DiagnosticHandler(self.directory / 'recognition.jsonl',
                                          maxBytes=2_000_000, backupCount=2, encoding='utf-8')
        self.previous = None
        self.evidence_count = 0
        self.disabled = False

    def event(self, event, **fields):
        if self.disabled:
            return
        try:
            payload = dict(event=event, **fields)
            signature = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
            if signature == self.previous:
                return
            self.previous = signature
            payload['time'] = time.time()
            message = json.dumps(payload, ensure_ascii=False, default=str)
            self.handler.emit(logging.LogRecord('exploration.debug', logging.DEBUG, '', 0, message, (), None))
        except Exception:
            self.disabled = True
            logger.warning('탐사 디버그 로그 저장 실패', exc_info=True)

    def failure(self, bot, label):
        screen = getattr(bot, 'last_screen', None)
        if self.disabled or screen is None or self.evidence_count >= 12:
            return
        self.evidence_count += 1
        try:
            markers = {}
            for name, template in bot.observer.templates.items():
                definition = bot.observer.config['markers'][name]
                x, y, w, h = definition.get('region', [0, 0, 1280, 720])
                th, tw = template.shape[:2]
                if w < tw or h < th:
                    continue
                sample = screen[y:y+h, x:x+w]
                _, score, _, (mx, my) = cv2.minMaxLoc(ImageMatcher.match_template(sample, template))
                markers[name] = dict(score=score,
                    color_error=color_error(sample[my:my+th, mx:mx+tw], template),
                    threshold=definition.get('threshold', .9),
                    max_color_error=definition.get('max_color_error', .09),
                    best_bounds=[x+mx, y+my, tw, th],
                    reference='primary', masked=template.shape[2] == 4)
                try:
                    markers[name]['accepted_bounds'] = bot.observer.find(screen, name)
                except Exception as exc:
                    markers[name]['recognition_error'] = str(exc)
            path = self.directory / f'failure_{self.evidence_count:02d}'
            ok, encoded = cv2.imencode('.png', screen)
            if ok:
                encoded.tofile(str(path.with_suffix('.png')))
            metadata = dict(label=label, stage=type(bot).__name__, stats=bot.get_stats(), markers=markers,
                            hero=getattr(bot, 'active_hero', None),
                            selection_target=getattr(bot, '_selection_target', None),
                            node=getattr(bot, 'current_node_kind', None))
            path.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False,
                indent=2, default=str), encoding='utf-8')
            self.event('failure', path=str(path), **metadata['stats'])
        except Exception:
            logger.warning('탐사 디버그 화면 저장 실패', exc_info=True)

    def close(self):
        try:
            self.handler.close()
        except OSError:
            logger.warning('탐사 디버그 로그 닫기 실패', exc_info=True)
