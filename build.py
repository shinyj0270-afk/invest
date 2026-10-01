"""Rebuild the dependency-free HTML dashboard from local source files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def build() -> Path:
    source = ROOT / 'src'
    html = (source / 'shell.html').read_text(encoding='utf-8')
    for marker, filename in [('/*STYLE*/', 'style.css'), ('/*ENGINE*/', 'engine.js'), ('/*UI*/', 'ui.js'), ('/*PORTFOLIO_ENGINE*/', 'portfolio_engine.js'), ('/*PORTFOLIO_UI*/', 'portfolio_ui.js'), ('/*HOLDINGS_SYNC_ENGINE*/','holdings_sync.js'), ('/*HOLDINGS_SYNC_UI*/','holdings_sync_ui.js')]:
        if marker not in html:
            raise ValueError(f'Missing template marker: {marker}')
        html = html.replace(marker, (source / filename).read_text(encoding='utf-8'))
    target = ROOT / 'INVESTMENT_Dashboard.html'
    target.write_text(html, encoding='utf-8')
    return target

if __name__ == '__main__':
    print(build())
