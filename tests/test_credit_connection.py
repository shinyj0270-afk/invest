"""Only the identified loopback CREDIT service can become an embedded dashboard."""
import unittest
from unittest.mock import patch
from investment.credit_connection import status, URL, MARKER


class CreditConnectionTests(unittest.TestCase):
    @patch('investment.credit_connection.urlopen')
    def test_identified_service_and_wrong_service(self, open_url):
        response = open_url.return_value.__enter__.return_value
        response.geturl.return_value = MARKER
        response.read.return_value = b'credit-dashboard-local-v1\n'
        self.assertEqual(status(), dict(available=True, url=URL))
        response.read.return_value = b'other-server'
        self.assertEqual(status(), dict(available=False))
        response.read.return_value = b'credit-dashboard-local-v1'
        response.geturl.return_value = 'https://example.invalid/redirect'
        self.assertEqual(status(), dict(available=False))

    @patch('investment.credit_connection.urlopen')
    def test_read_only_and_disconnected_service(self, open_url):
        self.assertEqual(status(read_only=True), dict(available=False))
        open_url.assert_not_called()
        open_url.side_effect = OSError('offline')
        self.assertEqual(status(), dict(available=False))


if __name__ == '__main__':
    unittest.main()
