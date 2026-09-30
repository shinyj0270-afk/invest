"""Fetch explicitly selected public Npay company references once into a local cache."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.naver_reference import cache_path, fetch_references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codes', nargs='+', required=True, help='국내 6자리 코드 1~30개')
    parser.add_argument('--output', type=Path, help='기본값: PC 로컬 data/profile/references/naver_reference.json')
    args = parser.parse_args()
    result = fetch_references(args.codes)
    if not result['companies']:
        parser.exit(2, '네이버 공개 조회 실패: 기존 참고 캐시를 보존합니다.\n')
    target = args.output or cache_path(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='naver-reference-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, target)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    print(json.dumps(dict(companies=len(result['companies']), errors=result['errors'],
                         status='reference_only', output=str(target.resolve())), ensure_ascii=False))


if __name__ == '__main__':
    main()
