"""账号注册表、运行开关与结果落盘的离线测试；不联网、不下单。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


def account(name, port, **overrides):
    config = {
        "账号": name, "资料目录": f"C:/tmp/{name}", "调试端口": port,
        "商品页面": "https://www.apple.com.cn/shop/buy-iphone/iphone-17e/mhu44ch/a",
        "机型": "iphone17e", "颜色": "black", "容量": "256gb", "数量": 1,
        "自提门店": "R448", "自提门店名称": "Apple 王府井", "搜索地区": "北京 北京 朝阳区",
        "省": "北京", "市": "北京", "区": "朝阳区",
        "姓": "xing", "名": "ming", "手机号": "13800000000", "邮箱": "a@example.com",
        "证件后四位": "1374", "发票类型": "e_personal_fdf", "支付方式": "ALIPAY",
    }
    config.update(overrides)
    return config


class AccountRegistryTests(unittest.TestCase):
    def test_multiple_accounts_pass(self):
        main.check_accounts([account("a", 9333), account("b", 9334)])

    def test_empty_registry_stops(self):
        with self.assertRaisesRegex(ValueError, "ACCOUNTS 为空"):
            main.check_accounts([])

    def test_duplicate_name_stops(self):
        with self.assertRaisesRegex(ValueError, "账号名重复"):
            main.check_accounts([account("a", 9333), account("a", 9334)])

    def test_duplicate_directory_stops(self):
        with self.assertRaisesRegex(ValueError, "资料目录与其他账号重复"):
            main.check_accounts([account("a", 9333), account("b", 9334, 资料目录="C:/tmp/a")])

    def test_duplicate_port_stops(self):
        with self.assertRaisesRegex(ValueError, "调试端口与其他账号重复"):
            main.check_accounts([account("a", 9333), account("b", 9333)])

    def test_missing_key_stops(self):
        broken = account("a", 9333)
        broken["手机号"] = "   "
        with self.assertRaisesRegex(ValueError, r"\[a\] 缺少配置：手机号"):
            main.check_accounts([broken])

    def test_non_single_quantity_stops(self):
        with self.assertRaisesRegex(ValueError, "仅支持单件商品"):
            main.check_accounts([account("a", 9333, 数量=2)])

    def test_illegal_port_stops(self):
        with self.assertRaisesRegex(ValueError, "调试端口非法"):
            main.check_accounts([account("a", 70000)])

    def test_account_config_merges_run_switches(self):
        config = main.account_config(account("a", 9333))
        self.assertEqual(config["账号"], "a")
        self.assertEqual(config["调试端口"], 9333)
        self.assertIs(config["允许访客结账"], main.RUN["允许访客结账"])
        self.assertIs(config["使用抓包代理"], main.RUN["使用抓包代理"])

    def test_run_switch_must_be_bool(self):
        with patch.dict(main.RUN, {"使用抓包代理": "False"}):
            with self.assertRaisesRegex(ValueError, "必须是 True 或 False"):
                main.check_runtime()

    def test_interval_must_be_non_negative(self):
        with patch.dict(main.RUN, {"账号间隔秒": -1}):
            with self.assertRaisesRegex(ValueError, "必须是非负数"):
                main.check_runtime()

    def test_require_sessions_reports_missing_accounts(self):
        with patch.object(main, "live_endpoint", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "没有检测到常驻会话：a、b"):
                main.require_sessions([account("a", 9333), account("b", 9334)])

    def test_require_sessions_passes_when_all_live(self):
        with patch.object(main, "live_endpoint", return_value="http://127.0.0.1:9333"), \
             patch.object(main, "login_state", return_value="结账准备完成"):
            main.require_sessions([account("a", 9333), account("b", 9334)])

    def test_append_result_writes_one_json_line_per_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "results.jsonl"
            main.append_result(path, {"账号": "a", "状态": "成功", "订单号": "X"})
            main.append_result(path, {"账号": "b", "状态": "失败", "失败原因": "测试"})
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual([json.loads(line)["账号"] for line in lines], ["a", "b"])
            self.assertEqual(json.loads(lines[0])["订单号"], "X")

    def test_describe_failure_keeps_local_messages_and_hides_others(self):
        self.assertEqual(main.describe_failure(ValueError("配置错误")), "配置错误")
        self.assertEqual(main.describe_failure(KeyError("secret-token")), "KeyError")

    def test_describe_failure_explains_closed_keepalive_browser(self):
        class TargetClosedError(main.base.BrowserError):
            pass

        message = main.describe_failure(TargetClosedError("Target page, context or browser has been closed"))
        self.assertIn("常驻浏览器已断开", message)
        self.assertIn("v2/session.py", message)

    def test_wait_ready_rejects_invalid_endpoint_immediately(self):
        import session

        class DummyProcess:
            def poll(self):
                return None

        with self.assertRaisesRegex(ValueError, "调试端点非法"):
            session.wait_ready(None, DummyProcess())

    def test_live_browser_without_checkout_stops(self):
        with patch.object(main, "live_endpoint", return_value="http://127.0.0.1:9333"), \
             patch.object(main, "login_state", return_value="结账未就绪"):
            with self.assertRaisesRegex(RuntimeError, "结账未就绪：a"):
                main.require_sessions([account("a", 9333)])

    def test_fulfillment_requires_model_not_just_url(self):
        from session import require_fulfillment
        from test_order import html_model_response, GUEST_ENTRY
        with self.assertRaisesRegex(ValueError, "不是已认证"):
            require_fulfillment(html_model_response("https://secure9.www.apple.com.cn/shop/checkout", GUEST_ENTRY))
        with self.assertRaisesRegex(ValueError, "尚未准备"):
            require_fulfillment(html_model_response("https://secure9.www.apple.com.cn/shop/sorry/session_expired", {}))


if __name__ == "__main__":
    unittest.main()
