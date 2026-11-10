"""Opt-in, bounded exploration evidence from frames already captured by the bot."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from collections import deque

import cv2

from src.image_matcher import ImageMatcher
from .template_masks import color_error

logger = logging.getLogger(__name__)


class ExplorationEvidence:
    """Keep existing frames in RAM; encode only when an error report is saved."""

    def __init__(self):
        self.recent = deque(maxlen=12)
        self.transitions = deque(maxlen=8)
        self.last_sample = float('-inf')
        self.last_state = None
        self.sequence = 0

    def remember(self, screen, *, phase=None, state=None, pending=False, label=None):
        now = time.monotonic()
        important = label is not None or (state is not None and state != self.last_state)
        if state is not None:
            self.last_state = state
        if not important and now - self.last_sample < 1:
            return
        self.sequence += 1
        record = dict(sequence=self.sequence, time=time.time(), monotonic=now,
                      phase=phase, state=state, skip_confirmation_pending=bool(pending),
                      label=label, frame=screen.copy())
        if important:
            self.transitions.append(record)
        else:
            self.recent.append(record)
            self.last_sample = now

    def export(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        records = sorted([*self.recent, *self.transitions], key=lambda r: r['sequence'])
        manifest = []
        for index, record in enumerate(records, 1):
            entry = {k: v for k, v in record.items() if k != 'frame'}
            try:
                ok, encoded = cv2.imencode('.png', record['frame'])
                if not ok:
                    raise OSError('PNG encoding failed')
                filename = f'{index:02d}.png'
                encoded.tofile(str(directory / filename))
                entry['file'] = filename
            except Exception as exc:
                entry['error'] = str(exc)
            manifest.append(entry)
        (directory / 'frames.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return dict(directory=directory.name, frames=len(manifest), manifest='frames.json')


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
