"""Refresh public flow observations or export the saved interactive view."""
import argparse
import csv
from datetime import date, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment import market_flows as flows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--ici-table', type=Path, help='ICI official weekly table copied as UTF-8 TSV')
    parser.add_argument('--published', type=date.fromisoformat, help='publication date of the ICI release')
    parser.add_argument('--html', type=Path, help='export saved observations as interactive offline HTML')
    args = parser.parse_args()
    if bool(args.ici_table) != bool(args.published):
        parser.error('--ici-table and --published must be supplied together')
    errors = flows.refresh(ROOT) if args.refresh else {}
    if args.ici_table:
        with args.ici_table.open(encoding='utf-8-sig', newline='') as stream:
            flows.import_ici(ROOT, list(csv.reader(stream, delimiter='\t')), args.published, datetime.now(flows.KST))
    data = flows.view(ROOT)
    if args.html:
        args.html.write_text(flows.render_page(data), encoding='utf-8')
    print('KR', (data['kr'] or {}).get('as_of'), 'ICI', (data['us'] or {}).get('as_of'))
    for name, error in errors.items():
        print(name, error)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())

