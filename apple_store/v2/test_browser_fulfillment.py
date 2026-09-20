"""浏览器履约失败必须在会话交接和加购前停止。"""

import json
import unittest
from unittest.mock import Mock

from apple_order import validate_browser_fulfillment


class BrowserFulfillmentTests(unittest.TestCase):
    def test_541_stops_without_parsing_error_page(self):
        response = Mock(status=541)
        with self.assertRaisesRegex(RuntimeError, "尚未交接 requests"):
            validate_browser_fulfillment(response)
        response.text.assert_not_called()

    def test_http_200_business_error_is_not_success(self):
        response = Mock(status=200)
        response.text.return_value = json.dumps({"head": {"status": 500}})
        with self.assertRaisesRegex(ValueError, "业务失败"):
            validate_browser_fulfillment(response)

    def test_success_status_with_error_message_stops(self):
        response = Mock(status=200)
        response.text.return_value = json.dumps({"head": {"status": 200}, "body": {"m": [{"level": "ERROR"}]}})
        with self.assertRaisesRegex(ValueError, "业务字段校验失败"):
            validate_browser_fulfillment(response)

    def test_successful_native_response(self):
        for status in (200, "200"):
            with self.subTest(status=status):
                response = Mock(status=200)
                response.text.return_value = json.dumps({"head": {"status": status}, "body": {}})
                validate_browser_fulfillment(response)


if __name__ == "__main__":
    unittest.main()
