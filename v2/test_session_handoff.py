"""结账准备与接续边界；全部使用本地模型和模拟对象，不联网。"""
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
import session as preparation
from test_accounts import account
from test_order import html_model_response, GUEST_ENTRY


class HandoffTests(unittest.TestCase):
    def test_browser_checkout_checks_bag_before_clicking(self):
        page = MagicMock()
        page.url = preparation.BAG_URL
        page.goto.return_value.status = 200
        model = {"shoppingCart": {"summary": {"d": {"total": "999"}},
                 "actions": {"a": {"checkout": {"url": "/shop/bagx/checkout_now"}}}}}
        response = page.expect_response.return_value.__enter__.return_value.value
        response.status = 200
        response.text.return_value = '{"head":{"status":302,"data":{}}}'
        def arrive(*args, **kwargs):
            page.url = "https://secure9.www.apple.com.cn/shop/signIn"
        page.wait_for_url.side_effect = arrive
        with patch.object(preparation, "browser_cookies") as cookies, \
             patch.object(preparation, "page_response"), \
             patch.object(preparation.base, "read_model", return_value=model), \
             patch.object(preparation.base, "check_bag") as check, \
             patch.object(preparation.base, "checkout_bag") as python_checkout:
            preparation.checkout_in_browser("session", page, "TEST/A", 1, "999")
        cookies.assert_called_once_with("session", page)
        check.assert_called_once_with(model, "TEST/A", 1)
        page.locator.return_value.click.assert_called_once()
        python_checkout.assert_not_called()

    def test_browser_checkout_rejects_changed_total_before_click(self):
        page = MagicMock()
        page.goto.return_value.status = 200
        with patch.object(preparation, "browser_cookies"), \
             patch.object(preparation, "page_response"), \
             patch.object(preparation.base, "read_model", return_value={
                 "shoppingCart": {"summary": {"d": {"total": "1000"}}}}), \
             patch.object(preparation.base, "check_bag"):
            with self.assertRaisesRegex(ValueError, "金额"):
                preparation.checkout_in_browser("session", page, "TEST/A", 1, "999")
        page.locator.assert_not_called()

    def test_browser_checkout_stops_on_412_without_navigation_retry(self):
        page = MagicMock()
        page.url = preparation.BAG_URL
        page.goto.return_value.status = 200
        page.expect_response.return_value.__enter__.return_value.value.status = 412
        model = {"shoppingCart": {"summary": {"d": {"total": "999"}},
                 "actions": {"a": {"checkout": {"url": "/shop/bagx/checkout_now"}}}}}
        with patch.object(preparation, "browser_cookies"), \
             patch.object(preparation, "page_response"), \
             patch.object(preparation.base, "read_model", return_value=model), \
             patch.object(preparation.base, "check_bag"):
            with self.assertRaisesRegex(RuntimeError, "HTTP 412"):
                preparation.checkout_in_browser("session", page, "TEST/A", 1, "999")
        page.locator.return_value.click.assert_called_once()
        page.wait_for_url.assert_not_called()

    def test_handoff_reads_secure_cookies_and_rejects_expired_response(self):
        page = MagicMock()
        page.url = "https://secure9.www.apple.com.cn/shop/checkout"
        expired = html_model_response("https://www.apple.com.cn/shop/sorry/session_expired", {})
        with patch.object(preparation, "sync_playwright"), \
             patch.object(preparation, "prepared_page", return_value=page), \
             patch.object(preparation.base, "read_page_cookies", return_value=[]) as cookies, \
             patch.object(preparation.base, "copy_browser_cookies"), \
             patch.object(preparation.base, "request", return_value=expired), \
             patch.object(preparation.base, "follow_navigation", return_value=expired):
            with self.assertRaisesRegex(ValueError, "尚未准备完成"):
                with preparation.prepared_session("http://127.0.0.1:9333"):
                    self.fail("expired checkout must not be handed off")
        cookies.assert_called_once_with(page, [page.url, preparation.BAG_URL])
        page.goto.assert_not_called()

    def test_handoff_yields_latest_http_response_instead_of_browser_snapshot(self):
        page = MagicMock()
        page.url = "https://secure9.www.apple.com.cn/shop/checkout"
        browser_entry = object()
        probe = html_model_response(
            page.url, {"checkout": {"d": {"page": "Fulfillment"}}})
        pw = MagicMock()

        with patch.object(preparation, "sync_playwright") as launch, \
             patch.object(preparation, "prepared_page", return_value=page), \
             patch.object(preparation, "page_response", return_value=browser_entry) as snapshot, \
             patch.object(preparation.base, "read_page_cookies", return_value=[]), \
             patch.object(preparation.base, "copy_browser_cookies"), \
             patch.object(preparation.base, "request", return_value=probe), \
             patch.object(preparation.base, "follow_navigation", return_value=probe):
            launch.return_value.__enter__.return_value = pw
            with preparation.prepared_session("http://127.0.0.1:9333") as (_, returned_page, entry):
                self.assertIs(returned_page, page)
                self.assertIs(entry, probe)
        snapshot.assert_not_called()

    def test_run_account_reuses_prepared_checkout_without_refreshing_it(self):
        page = MagicMock()
        entry = SimpleNamespace(url="https://secure9.www.apple.com.cn/shop/checkout")
        product = SimpleNamespace(content=b"product")
        bag = object()
        config = main.account_config(account("a", 9333))

        @contextmanager
        def prepared(*args):
            yield object(), page, entry

        with patch.object(main, "live_endpoint", return_value="http://127.0.0.1:9333"), \
             patch.object(main, "prepared_session", prepared), \
             patch.object(main.base, "request") as request, \
             patch.object(main.base, "follow_navigation", side_effect=[product, bag]), \
             patch.object(main.base, "select_product", return_value={"partNumber": "TEST/A"}), \
             patch.object(main.base, "read_model", return_value={}), \
             patch.object(main.base, "check_bag"), \
             patch.object(main, "checkout", return_value={"订单号": "TEST"}) as checkout:
            main.run_account(config)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[1:], ("GET", config["商品页面"]))
        self.assertEqual(request.call_args_list[1].args[1:], ("GET", "https://www.apple.com.cn/shop/bag"))
        self.assertIs(checkout.call_args.kwargs["prepared"], entry)
        page.goto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
