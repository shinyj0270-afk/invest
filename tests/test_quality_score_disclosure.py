import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from investment import research
from investment.report import onepager
from investment.fixture import make_fixture

NOTE='순위·후보 자격·추천에 쓰이지 않는 참고 표시'
UNCOMPUTED='시점별 연간 재무가 없으면 계산되지 않습니다'


class QualityScoreDisclosureTests(unittest.TestCase):
    def test_one_pager_states_the_score_is_not_a_ranking_basis_with_and_without_a_score(self):
        s=make_fixture();row=s['companies'][0];scored=research.analyze(s)[0]
        self.assertIsNotNone(scored['quality_score'])
        self.assertIn(NOTE,onepager(s,row,scored))
        self.assertIn(NOTE,onepager(s,row,dict(scored,quality_score=None)))

    def test_quality_view_caption_states_the_same_limits(self):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        next(x for x in at.selectbox if x.label=='데이터 모드').select('가상 테스트').run()
        next(x for x in at.radio if x.label=='화면').set_value('장기성장 연구').run()
        next(x for x in at.radio if x.label=='연구 보기').set_value('기존 품질').run()
        self.assertEqual(len(at.exception),0)
        text=' '.join(c.value for c in at.caption)
        self.assertIn(NOTE,text);self.assertIn(UNCOMPUTED,text)
        self.assertIn('결측 기업 가중치 재배분 없음',text)                      # the original caption is kept


if __name__=='__main__':unittest.main()
