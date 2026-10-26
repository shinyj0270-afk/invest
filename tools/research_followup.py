"""Freeze an explicit local research cohort, or read its forward observations."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.local_config import load_local, require_profile
from investment.research_library_view import view
from investment.research_followup import freeze, project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('freeze','status'))
    parser.add_argument('--id',required=True)
    parser.add_argument('--input')
    parser.add_argument('--project-root',default=str(ROOT))
    args=parser.parse_args()
    root=Path(args.project_root).resolve();profile=require_profile(load_local(root))
    record=next((r for r in view(root)['theses'] if r['id']==args.id),None)
    if record is None:raise ValueError('열람 가능한 현재 가설 필요')
    if args.action=='freeze':
        if not args.input:raise ValueError('--input 필요')
        path=(root/args.input).resolve()
        if not path.is_relative_to(root/'.local'):raise ValueError('Git 제외 .local 입력만 허용')
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if set(value)!={'candidates','selection_rule'}:raise ValueError('명시한 후보·선정규칙만 허용')
        result=freeze(root,profile,record,**value)
        print(json.dumps(dict(created=result['created'],thesis_id=args.id,digest=result['plan']['digest'],
                              candidates=len(result['plan']['candidates'])),ensure_ascii=False))
    else:print(json.dumps(project(root,profile,record),ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print('Research follow-up: '+str(exc),file=sys.stderr);sys.exit(1)
