import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class StreamlitTests(unittest.TestCase):
    def test_real_and_fixture_tabs_and_filters(self):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        mode=next(x for x in at.selectbox if x.label=='데이터 모드')
        mode.select('가상 테스트').run()
        self.assertEqual(len(at.exception),0)
        nav=next(x for x in at.radio if x.label=='화면')
        self.assertEqual(len(nav.options),10)
        self.assertEqual(nav.value,'오늘')
        nav.set_value('조건검색').run()
        control=next(x for x in at.selectbox if x.label=='판정')
        control.select('충족').run()
        self.assertEqual(len(at.exception),0)
        next(x for x in at.selectbox if x.label=='시장').select('KOSDAQ').run()
        next(x for x in at.button if x.label=='조건 저장').click().run()
        renewed=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        next(x for x in renewed.selectbox if x.label=='데이터 모드').select('가상 테스트').run()
        next(x for x in renewed.radio if x.label=='화면').set_value('조건검색').run()
        self.assertEqual(next(x for x in renewed.selectbox if x.label=='시장').value,'KOSDAQ')
        next(x for x in at.selectbox if x.label=='시장').select('전체').run()
        next(x for x in at.button if x.label=='조건 저장').click().run()
        next(x for x in at.radio if x.label=='화면').set_value('장기성장 연구').run()
        for label in ('기존 품질','다섯 경로','주간 목록','성장 단계·지속성','자료·가설'):
            next(x for x in at.radio if x.label=='연구 보기').set_value(label).run()
            self.assertEqual(len(at.exception),0)

if __name__=='__main__': unittest.main()
