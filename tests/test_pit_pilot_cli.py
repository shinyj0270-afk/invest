import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from tools.pit_pilot import main


def sessions():
    out = [];d = date(2026, 1, 2)
    while d < date(2026, 12, 31):
        if d.weekday() < 5:out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def receipt(no='20260310000001', rcept='2026-03-10', revenue=100.0):
    return dict(company='298040', period_end='2025-12-31', basis='CFS', report_kind='annual', rcept_no=no, rcept_dt=rcept, values=dict(revenue=revenue))


class CliTests(unittest.TestCase):
    def write(self, data):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'in.json';path.write_text(json.dumps(data), encoding='utf-8');return path

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_project_and_verify_work_on_a_local_file_and_verify_fails_on_unresolved(self):
        path = self.write(dict(receipts=[receipt()], sessions=sessions()))
        code, out, _ = self.run_cli(['project', '--input', str(path)]);self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['298040|CFS']['rows'][0]['available_at'], '2026-03-11')
        code, out, _ = self.run_cli(['verify', '--input', str(path)]);self.assertEqual(code, 0);self.assertTrue(json.loads(out)['ok'])
        bad = self.write(dict(receipts=[receipt()], sessions=sessions(),
            inventory=[dict(rcept_no='20260520000002', rcept_dt='2026-05-20', title_period='2025-12', correction='기재정정', kind='annual')]))
        code, out, _ = self.run_cli(['verify', '--input', str(bad)]);self.assertEqual(code, 1);self.assertFalse(json.loads(out)['ok'])

    def test_live_is_refused_and_bad_input_returns_an_error_without_a_traceback(self):
        path = self.write(dict(receipts=[], sessions=sessions()))
        code, _, err = self.run_cli(['verify', '--input', str(path), '--live']);self.assertEqual(code, 2);self.assertIn('구현되지 않았습니다', err)
        for payload in ({}, dict(receipts='x', sessions=[]), dict(receipts=[1], sessions=[]), dict(receipts=[], sessions=[1]),
                        dict(receipts=[], sessions=sessions(), inventory=[None]), dict(receipts=[], sessions=sessions(), inventory=[dict(rcept_no=1)]), [1, 2],
                        dict(receipts=[], sessions=sessions(), inventory=[dict(rcept_no='20260310000001', rcept_dt='garbage')]),
                        dict(receipts=[], sessions=sessions(), inventory=[dict(rcept_no='123', rcept_dt='2026-03-10')]),
                        dict(receipts=[], sessions=sessions(), inventory=[dict(rcept_no='20260310000001', rcept_dt='2026-03-10', company='OTHER', title_period=[])])):
            code, _, err = self.run_cli(['verify', '--input', str(self.write(payload))]);self.assertEqual(code, 2);self.assertIn('오류', err)
        code, _, err = self.run_cli(['verify', '--input', 'Z:/definitely/not/here.json']);self.assertEqual(code, 2)


if __name__ == '__main__':unittest.main()
