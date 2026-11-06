import subprocess
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from scripts.session_check import summary


class SessionCheckTests(unittest.TestCase):
    def run_summary(self, *, fail=(), status=' M a\0R  new\0old\0?? b\0', **kwargs):
        calls = []

        def run(command, **options):
            args = tuple(command[3:])
            calls.append(args)
            outputs = {
                ('symbolic-ref', '--quiet', '--short', 'HEAD'): 'topic\n',
                ('rev-parse', '--short', 'HEAD'): 'abcdef1\n',
                ('rev-list', '--left-right', '--count', 'HEAD...origin/main'): '2\t3\n',
                ('status', '--porcelain=v1', '-z', '--untracked-files=all'): status,
            }
            return subprocess.CompletedProcess(command, int(args[0] in fail), outputs.get(args, ''), '')

        with patch('scripts.session_check.subprocess.run', side_effect=run), patch.object(
            Path, 'open', mock_open(read_data='마지막 갱신일: 2026-11-06\n')
        ) as opened:
            lines = summary(Path('synthetic'), **kwargs)
        self.assertEqual(opened.call_count, 1)
        self.assertLessEqual(len(lines), 15)
        return '\n'.join(lines), calls

    def test_offline_counts_rename_and_unknown_profile(self):
        output, calls = self.run_summary()
        self.assertIn('ahead/behind: 2/3', output)
        self.assertIn('uncommitted files: 3', output)
        self.assertIn('PC profile: 미확인', output)
        self.assertIn('STATE_DIGEST updated: 2026-11-06', output)
        self.assertFalse(any(c[0] == 'fetch' for c in calls))

    def test_only_fetch_mutates_git_metadata(self):
        output, calls = self.run_summary(fetch=True, profile='work')
        self.assertEqual(calls[0], ('fetch', 'origin', 'main'))
        self.assertIn('fetch 성공', output)
        self.assertIn('설정 대조 미확인', output)
        self.assertTrue(all(c[0] in {'fetch', 'symbolic-ref', 'rev-parse', 'rev-list', 'status'} for c in calls))

    def test_fetch_failure_is_not_fresh(self):
        output, _ = self.run_summary(fetch=True, fail=('fetch',))
        self.assertIn('fetch 실패; 아래 수치는 캐시', output)

    def test_git_errors_not_zero_or_clean(self):
        output, _ = self.run_summary(fail=('symbolic-ref', 'rev-parse', 'rev-list', 'status'))
        for field in ('branch', 'HEAD', 'ahead/behind', 'uncommitted files'):
            self.assertIn(field + ': 미확인', output)

    def test_missing_digest_and_git_executable(self):
        with patch('scripts.session_check.subprocess.run', side_effect=FileNotFoundError), patch.object(
            Path, 'open', side_effect=FileNotFoundError
        ):
            output = '\n'.join(summary())
        self.assertIn('STATE_DIGEST updated: 미확인', output)
        self.assertIn('ahead/behind: 미확인', output)


if __name__ == '__main__':
    unittest.main()
