"""Create explicitly synthetic reader fixtures and a dashboard snapshot offline."""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

try:
    from .infomax_import import FIELDS, UNITS, convert, write_new
except ImportError:
    from infomax_import import FIELDS, UNITS, convert, write_new


def sample():
    sessions = [(date(2026, 1, 2) + timedelta(days=i)).isoformat() for i in range(28)
                if (date(2026, 1, 2) + timedelta(days=i)).weekday() < 5]
    codes = ['900001', '900002', '900003']
    config = dict(schema_version='infomax-import-0.1', mode='fixture', as_of='2026-01-30',
                  completed_through=sessions[-1], sessions_20d=sessions,
                  financial_period='2025-12-31', financial_basis='CFS',
                  balance_comp='누적', income_comp='순', units=UNITS,
                  price_venue='KRX', flow_venue='KRX', prices_final=True, flows_final=True,
                  market_cap_date=sessions[-1],
                  companies={c: dict(security_type='ordinary', analysis_profile='nonfinancial',
                                     financial_available_on='2026-01-15') for c in codes})
    names = ['가상테스트기업' + str(i+1) for i in range(3)]
    grids = {'info': [['종목명', '구분', '코드', '단축코드', '소속시장구분', '업종코드', '시가총액']] +
             [[name, 'STK', code, code, '1', '가상테스트산업', 10000000000] for code, name in zip(codes, names)]}
    for kind, fields in FIELDS.items():
        financial = kind in ('balance', 'income')
        dates = ['2025-12-31'] if financial else ['2026-01-30'] + list(reversed(sessions))
        conditions = ['시작', '2025-01-01', '종료', '2026-01-30', 'Data 개수', 60,
                      '주기', '분기' if financial else '일', '정렬', 'D', '영업일', 0, '시세산출', '종가']
        labels, headers = [], []
        for name in names:
            labels += [name] + [''] * len(fields)
            headers += ['일자'] + fields
        grid = [conditions, labels, headers]
        for d in dates:
            row = []
            for i in range(3):
                values = {'prices': [10000, 10000, 100000000], 'flows': [-500, 1000],
                          'balance': [300000, 200000, 100000], 'income': [100000, 10000, 7000]}[kind]
                if kind == 'flows' and d == '2026-01-30':
                    values = [None, None]
                row += [d] + values
            grid.append(row)
        grids[kind] = grid
    return grids, config


def create_demo(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    grids, config = sample()
    paths = {}
    for kind, grid in grids.items():
        paths[kind] = destination / (kind + '.csv')
        with paths[kind].open('w', encoding='utf-8-sig', newline='') as out:
            csv.writer(out).writerows(grid)
    config_path = destination / 'config.json'
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    result = convert(config_path, paths)
    write_new(destination / 'snapshot.json', result)
    return destination / 'snapshot.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(create_demo(args.output_dir))
    print('가상 테스트 전용입니다. 시장 관측이나 투자 판단 자료가 아닙니다.')
