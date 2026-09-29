import unittest
from unittest.mock import patch

import requests
from sms import verify


class SmsTests(unittest.TestCase):
    def run_verification(self, status=200, token="test-token"):
        self.calls = []
        data = {"serviceURL": "https://id.apple.com/identity", "serviceKey": "test-key",
                "options": dict(frameId="frame", locale="zh_CN", token="identity-token",
                                context="context", nonce="nonce")}

        def request(session, method, url, **kwargs):
            self.calls.append((method, url, dict(session.headers), kwargs))
            response = requests.Response()
            response.status_code = status if len(self.calls) == 4 else 200
            response.headers["X-Apple-ID-Session-Id"] = f"session-{len(self.calls)}"
            if len(self.calls) == 4 and token:
                response.headers["X-Apple-Verification-Token"] = token
            return response

        with requests.Session() as store, patch("sms.requests.Session.request", request), \
                patch("builtins.input", return_value="123456"), \
                patch("apple_store.network._coordinate"):
            store.proxies = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
            return verify(store, "https://secure7.www.apple.com.cn/shop/checkout", data, "test-phone")

    def test_session_rotation_and_token(self):
        self.assertEqual(self.run_verification(), "test-token")
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.calls[2][2]["X-Apple-ID-Session-Id"], "session-2")
        self.assertEqual(self.calls[3][2]["X-Apple-ID-Session-Id"], "session-3")
        self.assertEqual(self.calls[3][3]["json"]["securityCode"], "123456")
        self.assertNotIn("securityCode", self.calls[2][3]["json"])

    def test_rejected_code_stops_without_retry(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
            self.run_verification(status=400)
        self.assertEqual(len(self.calls), 4)

    def test_missing_token_stops(self):
        with self.assertRaisesRegex(ValueError, "no verification token"):
            self.run_verification(token=None)


if __name__ == "__main__":
    unittest.main()
