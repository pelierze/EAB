"""Opt-in, session-local shop measurements; never request a device capture."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .version import APP_VERSION


logger = logging.getLogger(__name__)


class _DiagnosticHandler(RotatingFileHandler):
    def handleError(self, record):
        # Let the recorder disable itself once instead of repeatedly printing errors.
        raise


def debug_timed(category):
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            trace = getattr(self, '_shop_debug', None)
            if trace is None:
                return function(self, *args, **kwargs)
            if category == 'capture':
                trace.count('captures')
            elif category == 'ocr':
                trace.count('ocr_calls')
            elif category == 'ocr_load':
                trace.count('ocr_loads')
            try:
                with trace.span(category):
                    result = function(self, *args, **kwargs)
            except Exception as exc:
                if category == 'capture':
                    trace.count('capture_failures')
                trace.record('operation_error', operation=function.__name__, error_type=type(exc).__name__)
                raise
            if category == 'capture':
                trace.count('capture_failures', int(not result))
                trace.record('capture', context=args[0] if args else kwargs.get('context'), success=bool(result))
            return result
        return wrapped
    return decorate


def debug_run(mode):
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            trace = getattr(self, '_shop_debug', None)
            if trace is None:
                return function(self, *args, **kwargs)
            trace.begin_run(mode, backend=type(self.adb).__name__,
                            screen_size=[self.screen_width, self.screen_height],
                            thresholds=self.thresholds, timings=self.timings,
                            arguments=list(args), options=kwargs)
            status = 'error'
            try:
                result = function(self, *args, **kwargs)
                status = ('stopped' if self.user_action == 'stop' else result.get('status', 'completed'))
                return result
            finally:
                trace.finish_run(status)
        return wrapped
    return decorate


def debug_purchase(function):
    @wraps(function)
    def wrapped(self, item_name, *args, **kwargs):
        trace = getattr(self, '_shop_debug', None)
        if trace is None:
            return function(self, item_name, *args, **kwargs)
        trace.begin_purchase(item_name)
        status = 'error'
        try:
            result = function(self, item_name, *args, **kwargs)
            status = 'confirmed' if result else ('stopped' if self.user_action == 'stop' else 'failed')
            return result
        finally:
            trace.end_purchase(status)
    return wrapped


class ShopDebugRecorder:
    MAX_LOG_BYTES = 2 * 1024 * 1024
    LOG_BACKUPS = 3
    MAX_EVIDENCE = 20

    def __init__(self, runtime_dir):
        self.directory = Path(runtime_dir) / 'shop_debug'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'events.jsonl'
        self.handler = _DiagnosticHandler(self.path, maxBytes=self.MAX_LOG_BYTES,
                                         backupCount=self.LOG_BACKUPS, encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.run_id = uuid4().hex
        self.sequence = 0
        self.cycle = None
        self.purchase = None
        self.purchase_sequence = 0
        self.mode = None
        self.phase = None
        keys = ('captures', 'capture_failures', 'purchases', 'skipped_items',
                'verification_attempts', 'verification_retries', 'ocr_calls', 'ocr_loads',
                'capture_ms', 'recognition_ms', 'ocr_ms', 'ocr_load_ms', 'input_ms',
                'wait_ms', 'pause_ms', 'verification_ms', 'natural_idle_ms', 'diagnostic_ms')
        self.totals = defaultdict(float, dict.fromkeys(keys, 0))
        self.stack = []
        self.failed = False
        self.started = None

    def _warn(self):
        if not self.failed:
            self.failed = True
            logger.warning('비밀상점 디버그 기록을 저장하지 못했습니다. 봇 동작은 계속합니다.', exc_info=True)

    def record(self, event, **fields):
        if self.failed:
            return
        with self.span('diagnostic'):
            self._write(event, fields)

    def _write(self, event, fields):
        try:
            self.sequence += 1
            data = dict(schema=1, method='shop_quantity_transition_v2',
                        timestamp=datetime.now(timezone.utc).isoformat(), run_id=self.run_id,
                        sequence=self.sequence, mode=self.mode,
                        cycle_id=self.cycle['index'] if self.cycle else None,
                        purchase_id=self.purchase['index'] if self.purchase else None,
                        phase=self.phase, event=event, **fields)
            message = json.dumps(data, ensure_ascii=False, allow_nan=False)
            self.handler.emit(logging.LogRecord('shop.debug', logging.DEBUG, '', 0, message, (), None))
        except Exception:
            self._warn()

    def count(self, key, amount=1):
        self.totals[key] += amount

    @contextmanager
    def span(self, category):
        if category == 'wait' and any(frame[0] == 'natural_idle' for frame in self.stack):
            category = 'natural_idle'
        frame = [category, perf_counter(), 0.0]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = perf_counter() - frame[1]
            self.stack.pop()
            self.totals[category + '_ms'] += max(0, elapsed - frame[2]) * 1000
            if self.stack:
                self.stack[-1][2] += elapsed

    def _delta(self, before):
        return {key: round(value - before.get(key, 0), 3) if key.endswith('_ms')
                else int(value-before.get(key, 0)) for key, value in self.totals.items()}

    def begin_run(self, mode, **metadata):
        self.mode = mode
        self.started = perf_counter()
        self.record('run_start', version=APP_VERSION, **metadata)
        logger.info('비밀상점 디버그 진단 기록: %s', self.path)

    def begin_cycle(self, index, refresh_planned=False):
        self.cycle = dict(index=index, started=perf_counter(), totals=dict(self.totals))
        self.record('cycle_start', refresh_planned=refresh_planned)

    def end_cycle(self, status):
        if self.cycle is None:
            return
        elapsed = (perf_counter() - self.cycle['started']) * 1000
        metrics = self._delta(self.cycle['totals'])
        self.record('cycle_end', status=status, elapsed_ms=round(elapsed, 3),
                    active_ms=round(max(0, elapsed-metrics.get('pause_ms', 0)), 3), metrics=metrics)
        self.cycle = None

    def begin_purchase(self, item):
        self.purchase_sequence += 1
        self.purchase = dict(index=self.purchase_sequence, started=perf_counter(), totals=dict(self.totals))
        self.phase = 'before_purchase'
        self.record('purchase_start', item=item)

    def end_purchase(self, status):
        metrics = self._delta(self.purchase['totals'])
        if metrics.get('skipped_items', 0):
            status = 'already_sold'
        self.record('purchase_end', status=status,
                    elapsed_ms=round((perf_counter()-self.purchase['started'])*1000, 3), metrics=metrics)
        self.purchase = None
        self.phase = None

    def evidence(self, reason, *images):
        if self.failed:
            return
        with self.span('diagnostic'):
            self._save_evidence(reason, images)

    def _save_evidence(self, reason, images):
        try:
            import cv2
            paths = []
            directory = self.directory / 'evidence'
            for image in images:
                if image is None or image.size == 0 or image.nbytes > 512 * 1024:
                    continue
                directory.mkdir(exist_ok=True)
                files = sorted(directory.glob('*.png'), key=lambda p: p.stat().st_mtime_ns)
                while len(files) >= self.MAX_EVIDENCE:
                    files.pop(0).unlink()
                path = directory / f'{self.run_id}_{self.sequence}_{len(paths)}.png'
                success, encoded = cv2.imencode('.png', image)
                if success and encoded.nbytes <= 512 * 1024:
                    encoded.tofile(str(path))
                    paths.append(path.relative_to(self.directory).as_posix())
            if paths:
                self.record('evidence', reason=reason, paths=paths)
        except Exception:
            self._warn()

    def finish_run(self, status):
        self.end_cycle(status)
        self.record('run_end', status=status,
                    elapsed_ms=round((perf_counter()-self.started)*1000, 3),
                    metrics=self._delta({}))
        self.close()

    def close(self):
        try:
            self.handler.close()
        except Exception:
            self._warn()
