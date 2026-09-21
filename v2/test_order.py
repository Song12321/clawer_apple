"""使用用户已提供的 HAR 离线回放；不访问商城，不输出抓包值。"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

import requests
from order import base, checkout

HAR = Path("D:/lqs/crawler/other/apple/url信息/所有_2026_09_20_09_21_37.har")


class CheckoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = {e["_id"]: e for e in json.loads(HAR.read_text(encoding="utf-8-sig"))["log"]["entries"]}

    def response(self, identity):
        entry = self.entries[identity]
        response = requests.Response()
        response.status_code = entry["response"]["status"]
        response.url = entry["request"]["url"]
        response.headers["Content-Type"] = entry["response"]["content"]["mimeType"]
        for h in entry["response"]["headers"]:
            if h["name"].lower() == "location":
                response.headers["Location"] = h["value"]
        response._content = entry["response"]["content"].get("text", "").encode()
        return response

    def form(self, identity):
        return dict(parse_qsl(self.entries[identity]["request"]["postData"]["text"], keep_blank_values=True))

    def run_chain(self, change_total=False):
        prefix = "checkout.pickupContact.selfPickupContact.selfContact.address."
        contact = {field: self.form(504)[prefix + field] for field in ("lastName", "firstName", "fullDaytimePhone", "emailAddress")}
        config = {key: contact[field] for field, key in (("lastName", "姓"), ("firstName", "名"), ("fullDaytimePhone", "手机号"), ("emailAddress", "邮箱"))}
        config.update({"数量": 1, "自提门店": "R645", "搜索地区": "北京 北京 朝阳区", "省": "北京", "市": "北京", "区": "朝阳区",
                       "证件后四位": self.form(504)["checkout.pickupContact.selfPickupContact.nationalIdSelf.nationalIdSelf"],
                       "发票类型": "e_personal_fdf", "支付方式": "ALIPAY"})
        config["自提门店名称"] = "Apple 朝阳大悦城"
        pending = iter([175, 189, 222, 266, 344, 490, 504, 514, 536])
        self.calls = []
        def post(session, url, model, path, name, fields):
            identity = next(pending)
            self.calls.append(identity)
            expected = self.form(identity) if identity != 536 else {}
            normalized = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in fields.items()}
            self.assertTrue(set(expected) == set(normalized), f"{identity} 表单字段集合不同")
            if identity in (266, 490, 504, 514, 536):
                self.assertTrue(expected == normalized, f"{identity} 表单值不一致（值不输出）")
            response = self.response(identity)
            if identity == 514 and change_total:
                data = json.loads(response.text)
                data["body"]["checkout"]["review"]["summary"]["d"]["total"] = "changed"
                response._content = json.dumps(data).encode()
            return response
        def request(session, method, url, **kwargs):
            self.assertEqual(next(pending), 189)
            self.assertEqual(method, "POST")
            self.assertTrue(kwargs["form"] == self.form(189))
            return self.response(189)
        def navigation(session, response):
            return self.response(202) if response.status_code == 302 else response
        token = next(iter(self.form(490).values()))
        result = {"订单号": "TEST-ORDER"}
        with patch("builtins.print"), patch.object(base, "checkout_bag", return_value=self.response(146)), \
             patch("order.guest_fields", return_value=self.form(175)), patch("order.verify", return_value=token), \
             patch.object(base, "post_action", side_effect=post), patch.object(base, "request", side_effect=request), \
             patch.object(base, "follow_navigation", side_effect=navigation), patch.object(base, "query_order", return_value=result):
            return checkout(object(), object(), self.response(116), config, "MG714CH/A")

    def test_serial_chain(self):
        self.assertEqual(self.run_chain()["订单号"], "TEST-ORDER")
        self.assertEqual(self.calls, [175, 222, 266, 344, 490, 504, 514, 536])

    def test_review_mismatch_stops_before_submission(self):
        with self.assertRaisesRegex(ValueError, "金额"):
            self.run_chain(change_total=True)
        self.assertNotIn(536, self.calls)


if __name__ == "__main__":
    unittest.main()
