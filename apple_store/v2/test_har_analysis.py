import base64
import json
import tempfile
import unittest
from pathlib import Path

from apple_store.v2.har_analysis import analyze, endpoint, fields, model_from, response_text


class HarAnalysisTests(unittest.TestCase):
    def test_missing_body_is_not_empty(self):
        self.assertEqual(fields({"request": {}})["state"], "not_exported_or_unknown")
        self.assertEqual(fields({"request": {"bodySize": 0}})["state"], "empty")

    def test_encoded_html_model(self):
        html = '<script id="init_data">{"spinner":{"a":{}}}</script>'
        entry = {"response": {"content": {"mimeType": "text/html", "encoding": "base64",
                    "text": base64.b64encode(html.encode()).decode()}}}
        self.assertIn("spinner", model_from(entry, response_text(entry)))
        entry["response"]["content"]["text"] = "%%%"
        with self.assertRaises(ValueError):
            response_text(entry)

    def test_sensitive_url_path_is_hidden(self):
        self.assertEqual(endpoint("https://example.com/shop/checkout/private-secret")['path'], '<路径已隐藏>')

    def test_evidence_and_redaction(self):
        secret = "PRIVATE-CREDENTIAL-123"
        source = {"_id": 10, "startedDateTime": "2026-01-01T00:00:00Z", "time": 100,
            "request": {"method": "POST", "url": "https://example.com/shop/checkoutx",
                        "headers": [{"name": "Cookie", "value": secret}],
                        "postData": {"mimeType": "application/x-www-form-urlencoded", "text": f"token={secret}&empty="}},
            "response": {"status": 200, "headers": [], "content": {"mimeType": "application/json", "text": json.dumps({
                "head": {"status": 302, "data": {"url": "/shop/checkout/status"}},
                "body": {"meta": {"h": {"x-aos-stk": secret}}}})}}}
        dest = {"_id": 11, "startedDateTime": "2026-01-01T00:00:01Z", "time": 100,
            "request": {"method": "GET", "url": "https://example.com/shop/checkout/status", "bodySize": 0,
                        "headers": [{"name": "x-aos-stk", "value": secret}]},
            "response": {"status": 200, "headers": [], "content": {"mimeType": "text/html"}}}
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "test.har"
            p.write_text(json.dumps({"log": {"entries": [source, dest]}}), encoding="utf-8")
            result = analyze(p, [10, 11], [secret])
            self.assertNotIn(secret, json.dumps(result))
            self.assertEqual(result['links'][0]['header_equal'], {'x-aos-stk': True})
            self.assertFalse(result['records'][1]['response_body_exported'])
            self.assertEqual(result['records'][0]['body']['fields'][1]['value'], '')
            with self.assertRaises(ValueError):
                analyze(p, [99], [])
            p.write_text(json.dumps({"log": {"entries": [source, source]}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze(p, [10], [])


if __name__ == '__main__':
    unittest.main()
