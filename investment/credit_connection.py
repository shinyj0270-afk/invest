"""Read-only discovery of the existing loopback CREDIT dashboard; never builds it."""
from urllib.request import urlopen

URL = 'http://127.0.0.1:4580/index.html'
MARKER = 'http://127.0.0.1:4580/_dashboard/local_dashboard_server.txt'


def status(*, read_only=False):
    if read_only:
        return dict(available=False)
    try:
        with urlopen(MARKER, timeout=2) as response:
            if response.geturl() != MARKER or response.read(64).strip() != b'credit-dashboard-local-v1':
                return dict(available=False)
        return dict(available=True, url=URL)
    except (OSError, ValueError):
        return dict(available=False)
