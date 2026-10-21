"""Foreground home receiver; memory-only token, no scheduler or Library writes."""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .telegram_export import home, local_file
from .telegram_listen import poll_file, default_fetch


@contextmanager
def receiver_lock(root):
    path = local_file(root, '.local/telegram-research/receiver.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    # A previous interrupted process requires manual inspection, never auto-delete.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid()}, stream)
        yield
    finally:
        path.unlink()


def watch(root, profile, token, channel, *, interval=60, cycles=None,
          fetch=default_fetch, sleep=time.sleep, report=print):
    home(profile)  # Before file access or Telegram calls.
    if type(interval) is not int or not 15 <= interval <= 3600:
        raise ValueError('Polling interval must be 15..3600 seconds')
    if cycles is not None and (type(cycles) is not int or cycles < 1):
        raise ValueError('Positive cycle limit required')
    if not isinstance(channel, dict) or type(channel.get('expected_id')) is not int:
        raise ValueError('A previously confirmed numeric channel lock is required')
    key = channel.get('key')
    if not isinstance(key, str) or not key or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key):
        raise ValueError('Safe channel key required')
    completed = 0
    total = 0
    with receiver_lock(root):
        while True:
            receipt = poll_file(root, profile, token, channel,
                                f'.local/telegram-research/state/{key}.json',
                                f'.local/telegram-research/live/{key}', fetch=fetch)
            completed += 1
            total += receipt['counts']['accepted']
            report({'cycle': completed, **receipt['counts']})
            if cycles is not None and completed >= cycles:
                return {'cycles': completed, 'accepted': total}
            # A failed poll exits immediately. No automatic exception retry.
            sleep(interval)
