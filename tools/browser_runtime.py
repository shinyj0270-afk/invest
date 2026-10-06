"""Browser selection for portable UI checks. Never installs a browser."""
import os
import shutil
from pathlib import Path


def chromium_options():
    explicit = os.environ.get('CHROMIUM_PATH')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ValueError('CHROMIUM_PATH must name an existing browser executable')
        return {'executable_path': str(path)}
    for name in ('chromium', 'chromium-browser', 'msedge', 'google-chrome'):
        found = shutil.which(name)
        if found:
            return {'executable_path': found}
    # Windows installations vary by architecture and installation scope.
    for variable, suffix in (
        ('PROGRAMFILES(X86)', 'Microsoft/Edge/Application/msedge.exe'),
        ('PROGRAMFILES', 'Microsoft/Edge/Application/msedge.exe'),
        ('LOCALAPPDATA', 'Microsoft/Edge/Application/msedge.exe'),
        ('PROGRAMFILES', 'Google/Chrome/Application/chrome.exe'),
        ('LOCALAPPDATA', 'Google/Chrome/Application/chrome.exe'),
    ):
        base = os.environ.get(variable)
        if base and (path := Path(base) / suffix).is_file():
            return {'executable_path': str(path)}
    # Let Playwright use its installed browser, or report its normal missing-browser error.
    return {}
