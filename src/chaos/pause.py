"""Cooperative pause with an unwind signal, so resume never reuses stale input."""
import threading


class ResumeExploration(BaseException):
    """Internal control flow; bypass handler error catches until the facade."""


class ExplorationPause:
    def __init__(self):
        self.requested = threading.Event()
        self.acknowledged = threading.Event()

    def pause(self):
        self.requested.set()

    def resume(self):
        self.requested.clear()
