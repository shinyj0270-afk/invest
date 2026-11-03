import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tools.trial_log import main


class TrialLogCliTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)

    def run_cli(self,*args):
        out=io.StringIO()
        with redirect_stdout(out):code=main(['--root',str(self.root),*args])
        return code,out.getvalue()

    def test_record_from_file_then_summary(self):
        entry=self.root/'entry.json'
        entry.write_text(json.dumps(dict(experiment_id='EXP-CLI',rule_version='r1',parameter_set=dict(z=1.5),decision='pending')),encoding='utf-8')
        code,text=self.run_cli('record','--profile','work','--entry-file',str(entry));self.assertEqual(code,0);self.assertIn('trial_index',text)
        code,text=self.run_cli('summary','--profile','work');data=json.loads(text)
        self.assertEqual((code,data['trials'],data['distinct_parameter_sets']),(0,1,1));self.assertTrue(data['head_digest'])

    def test_invalid_entry_returns_error_code_and_writes_nothing(self):
        entry=self.root/'bad.json';entry.write_text(json.dumps(dict(experiment_id='',rule_version='r1',parameter_set=dict(z=1),decision='pending')),encoding='utf-8')
        code,_=self.run_cli('record','--profile','work','--entry-file',str(entry));self.assertEqual(code,2)
        code,text=self.run_cli('summary','--profile','work');self.assertEqual(json.loads(text)['trials'],0)


if __name__=='__main__':unittest.main()
