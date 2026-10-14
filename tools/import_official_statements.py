"""Import a reviewed, local official-document extract; no network or model calls."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from investment.market_discovery import read_market_cache
from investment.official_statements import import_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    code = json.loads(args.packet.read_text(encoding='utf-8'))['company']['code']
    cache = read_market_cache(args.root, {'meta': {'data_mode': 'user_input'}})
    row = next((r for r in (cache or {}).get('universe', {}).get('companies', []) if r.get('code') == code), None)
    if row is None:
        raise ValueError('이 PC의 저장 기업 목록에 없는 종목')
    print(json.dumps(import_packet(args.root, args.packet, row), ensure_ascii=False))


if __name__ == '__main__':
    main()
