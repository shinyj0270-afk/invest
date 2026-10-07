import copy
import unittest

from investment.dart_statements import parse_viewer,valid_report,quarter_records


def table(title, rows):
    header='<table><tr><td>'+title+'</td></tr><tr><td>2026.06.30 단위 : 원</td></tr></table>'
    return header+'<table>'+''.join('<tr><td>'+k+'</td><td>'+str(v)+'</td></tr>' for k,v in rows)+'</table>'


BALANCE=[('자산총계',20000000),('부채총계',8000000),('자본총계',12000000)]
INCOME=[('매출액',100),('영업이익',20),('반기순이익',15)]
CASH=[('영업활동현금흐름',80),('영업활동으로 인한 현금흐름',100),
      ('이자수취액',5),('이자지급액',-10),('법인세납부액',-15),
      ('투자활동현금흐름',-40),('재무활동현금흐름',-20),
      ('기초현금및현금성자산',200),('외화표시 현금및현금성자산의 환율변동효과',3),
      ('반기말현금및현금성자산',223)]


def parse(income=INCOME, cash=CASH):
    payload=table('연결 재무상태표',BALANCE)+table('연결 손익계산서',income)+table('연결 현금흐름표',cash)
    return parse_viewer(payload,code='900000',name='합성 검산',market='KOSPI',basis='CFS',
                        year=2026,quarter=2,receipt='20260813001554',
                        url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260813001554')


class FinancialAccountRecoveryTests(unittest.TestCase):
    def test_operating_cash_total_requires_adjustments_and_full_cash_balance(self):
        report=parse()
        self.assertTrue(valid_report(report))
        self.assertEqual(report['values']['ocf'],80)
        self.assertEqual(report['values']['cash_generated'],100)
        self.assertIn('독립 검산',quarter_records([report],'2026-09-01')[0]['cell_notes']['ocf'])
        for changed in (
            [(k,221 if k=='반기말현금및현금성자산' else v) for k,v in CASH],
            [(k,-12 if k=='법인세납부액' else v) for k,v in CASH],
            [(k,v) for k,v in CASH if k!='이자수취액'],
            CASH+[('이자수취액',5)],
            CASH+[('영업에서 창출된 현금',101)],
            [(k,v) for k,v in CASH if k!='외화표시 현금및현금성자산의 환율변동효과'],
            [CASH[1],CASH[0]]+CASH[2:],
        ):
            with self.assertRaises(ValueError):parse(cash=changed)
        forged=copy.deepcopy(report);forged['account_reconciliation']['ocf']['cash_balance_residual_krw']=1
        self.assertFalse(valid_report(forged))
        forged=copy.deepcopy(report);forged['values']['ocf']=100
        self.assertFalse(valid_report(forged))
        forged=copy.deepcopy(report);forged.pop('account_reconciliation')
        self.assertFalse(valid_report(forged))
        forged=copy.deepcopy(report);forged['units']['cash']=1000000000
        self.assertFalse(valid_report(forged))

    def test_mislabeled_total_needs_discontinued_and_independent_total_attribution(self):
        income=[('매출액 및 지분법손익',100),('영업이익',20),
                ('법인세비용차감전계속영업이익',25),('법인세비용',5),
                ('계속영업이익(손실)',20),('중단영업이익(손실)',-3),('계속영업이익(손실)',17),
                ('지배기업지분순이익(손실)',18),('비지배지분순이익',-1)]
        report=parse(income=income)
        self.assertTrue(valid_report(report))
        self.assertEqual(report['values']['net_income'],17)
        self.assertEqual(report['values']['parent_net'],18)
        self.assertIn('지분법',quarter_records([report],'2026-09-01')[0]['cell_notes']['revenue'])
        for changed in (
            [(k,v) for k,v in income if k!='중단영업이익(손실)'],
            [(k,v) for k,v in income if k!='비지배지분순이익'],
            [(k,20 if k=='지배기업지분순이익(손실)' else v) for k,v in income],
            [(k,8 if k=='법인세비용' else v) for k,v in income],
            income+[('비지배지분순이익',-1)],
        ):
            with self.assertRaises(ValueError):parse(income=changed)
        forged=copy.deepcopy(report);forged['values']['net_income']=20
        self.assertFalse(valid_report(forged))


if __name__=='__main__':unittest.main()
