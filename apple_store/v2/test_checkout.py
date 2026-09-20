"""requests 结账链回归测试：合成响应，不读取历史凭据或发送网络请求。"""

import json
import unittest
from unittest.mock import patch

import requests

import apple_order as order
import test_order_review


BASE = "https://secure7.www.apple.com.cn"


def node(action, path):
    return {"a": {action: {"url": f"/shop/checkoutx?_a={action}&_m={path}", "submit": True}}}


def model(checkout, version):
    return {"meta": {"h": {"x-aos-model-page": "checkout", "modelVersion": str(version),
                           "syntax": "orbit", "x-aos-stk": "synthetic-test-value"}}, "checkout": checkout}


def response(body, path="/shop/checkoutx"):
    result = requests.Response()
    result.status_code = 200
    result.url = BASE + path
    result.headers["Content-Type"] = "application/json"
    result._content = json.dumps(body).encode("utf-8")
    return result


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        review_test = test_order_review.OrderReviewTests()
        review_test.setUp()
        self.config = {**review_test.config, "自提门店": "R448", "发票类型": "e_personal_fdf"}
        self.review = review_test.review
        self.review["placeOrder"].update(node("continueFromReviewToProcess", "checkout.review.placeOrder"))
        self.bag = {"shoppingCart": {"items": {"item-test": {
            "d": {"sku": "TEST/A"}, "itemQuantity": {"d": {"quantity": 1}}}},
            "summary": {"d": {"total": "RMB 100"}}}}
        self.signin = {"meta": model({}, 0)["meta"], "signIn": {"guestLogin": node("guestLogin", "signIn.guestLogin")}}
        fulfillment = node("continueFromFulfillmentToPickupContact", "checkout.fulfillment")
        fulfillment["fulfillmentOptions"] = node("selectFulfillmentLocationAction", "checkout.fulfillment.fulfillmentOptions")
        locator = node("select", ".".join(order.STORE_PATH))
        locator["d"] = {"showAllStores": False, "searchInput": "", "selectStore": "R448"}
        locator["searchResults"] = {"d": {"retailStores": [{"storeId": "R448", "storeDisabled": False, "storeName": "Test store"}]}}
        locator["address"] = {"stateCitySelectorForCheckout": {"d": {
            "city": "Test city", "state": "Test state", "provinceCityDistrict": "", "countryCode": "CN", "district": ""}}}
        fulfillment["pickupTab"] = {"pickup": {"storeLocator": locator}}
        self.fulfillment = fulfillment
        contact = node("contactVerify", ".".join(order.CONTACT_PATH))
        verification = node("submitVerificationToken", ".".join(order.CONTACT_PATH) + ".verificationModule")
        verification["d"] = {"verificationToken": "", "authRequired": True, "isVerified": False}
        contact["verificationModule"] = verification
        pickup = node("continueFromPickupContactToBilling", "checkout.pickupContact")
        pickup["selfPickupContact"] = {"selfContact": {"address": contact}}
        pickup["eFapiaoSelector"] = {"ePersonalFapiao": {"d": {"invoiceHeader": ""}}}
        self.pickup = pickup
        self.verify = verification
        self.billing = node("continueFromBillingToReview", "checkout.billing")
        self.billing["billingOptions"] = node("selectBillingOptionAction", "checkout.billing.billingOptions")
        self.billing["billingOptions"]["d"] = {"selectBillingOption": "ALIPAY"}
        self.session = unittest.mock.Mock()
        self.calls = []

    def verification_model(self, verified):
        module = {"d": {"isVerified": True, "authRequired": False}} if verified else self.verify
        return {"pickupContact": {"selfPickupContact": {"selfContact": {"address": {"verificationModule": module}}}}}

    def sequence(self, direct_review=False):
        sequence = [
            ("guestLogin", {"head": {"status": 302, "data": {"url": "/shop/checkout/start"}}}),
            ("GET", model({"d": {"page": "Fulfillment"}, "fulfillment": self.fulfillment}, 1)),
            ("selectFulfillmentLocationAction", model({"d": {"page": "Fulfillment"}, "fulfillment": self.fulfillment}, 2)),
            ("select", model({"d": {"page": "Fulfillment"}, "fulfillment": self.fulfillment}, 3)),
            ("continueFromFulfillmentToPickupContact", model({"d": {"page": "PickupContact"}, "pickupContact": self.pickup,
                "companionBar": {"orderDetails": {"fulfillmentCompanionBar": {"pickupSummary": {"d": {"store_name": "Test store"}}}}}}, 4)),
            ("contactVerify", model(self.verification_model(False), 5)),
            ("submitVerificationToken", model(self.verification_model(True), 6)),
            ("continueFromPickupContactToBilling", model({"d": {"page": "Billing"}, "billing": self.billing}, 7)),
        ]
        review = model({"d": {"page": "Review"}, "review": self.review}, 9)
        if direct_review:
            sequence.append(("selectBillingOptionAction", review))
        else:
            sequence.extend([
                ("selectBillingOptionAction", model({"d": {"page": "Billing"}, "billing": self.billing,
                    "locationConsent": {"d": {"locationConsent": False}}}, 8)),
                ("continueFromBillingToReview", review),
            ])
        sequence.extend([
            ("continueFromReviewToProcess", {"head": {"status": 302, "data": {"url": "/shop/checkout/status"}}}),
            ("GET", {"meta": model({}, 10)["meta"], "spinner": node("checkStatus", "spinner")}),
            ("checkStatus", {"head": {"status": 302, "data": {"url": "/shop/checkout/interstitial"}}}),
            ("GET", {"thankYouInterstitial": {"d": {"orderNumber": "TEST-ORDER-1", "orderStatusUrl": BASE + "/order/test"}}}),
        ])
        return sequence

    def run_checkout(self, sequence):
        from urllib.parse import parse_qs, urlsplit
        pending = list(sequence)
        def send(method, url, **kwargs):
            action = parse_qs(urlsplit(url).query).get("_a", [method])[0]
            self.calls.append((action, kwargs))
            expected, body = pending.pop(0)
            self.assertEqual(action, expected)
            self.assertEqual(method, "GET" if action == "GET" else "POST")
            if isinstance(body, Exception):
                raise body
            if "head" not in body:
                body = {"head": {"status": 200}, "body": body}
            result = response(body)
            result.url = url
            return result
        self.session.request.side_effect = send
        with patch("builtins.print"), \
             patch.object(order, "checkout_bag", return_value=response({"head": {"status": 200}, "body": self.signin})), \
             patch.object(order, "guest_form", return_value={"signIn.guestLogin.deviceID": "synthetic-device"}), \
             patch.object(order, "verification_token", return_value="synthetic-verification"):
            return order.checkout_order(self.session, response({}), self.bag, self.config, "TEST/A")

    def test_complete_chain_returns_order(self):
        self.assertEqual(self.run_checkout(self.sequence())["订单号"], "TEST-ORDER-1")
        calls = dict(self.calls)
        self.assertEqual(calls["continueFromPickupContactToBilling"]["headers"]["modelVersion"], "6")
        self.assertEqual(calls["submitVerificationToken"]["data"], {
            ".".join(order.CONTACT_PATH) + ".verificationModule.verificationToken": "synthetic-verification"})
        self.assertEqual(calls["continueFromReviewToProcess"]["data"], {})
        self.assertEqual(sum(name == "continueFromReviewToProcess" for name, _ in self.calls), 1)

    def test_payment_can_enter_review_directly(self):
        self.assertEqual(self.run_checkout(self.sequence(True))["订单号"], "TEST-ORDER-1")

    def test_unavailable_store_stops(self):
        self.fulfillment["pickupTab"]["pickup"]["storeLocator"]["searchResults"]["d"]["retailStores"][0]["storeDisabled"] = True
        with self.assertRaisesRegex(ValueError, "不可取货"):
            self.run_checkout(self.sequence())
        self.assertEqual(self.calls[-1][0], "selectFulfillmentLocationAction")

    def test_failed_verification_stops(self):
        sequence = self.sequence()
        sequence[6] = ("submitVerificationToken", model(self.verification_model(False), 6))
        with self.assertRaisesRegex(ValueError, "尚未确认"):
            self.run_checkout(sequence)
        self.assertEqual(self.calls[-1][0], "submitVerificationToken")

    def test_changed_total_prevents_order(self):
        self.review["summary"]["d"]["total"] = "RMB 101"
        with self.assertRaisesRegex(ValueError, "总额"):
            self.run_checkout(self.sequence())
        self.assertFalse(any(name == "continueFromReviewToProcess" for name, _ in self.calls))

    def test_unknown_submission_result_is_not_retried(self):
        sequence = self.sequence()
        sequence[-4] = ("continueFromReviewToProcess", {"head": {"status": 200}, "body": {}})
        with self.assertRaisesRegex(ValueError, "禁止重复提交"):
            self.run_checkout(sequence)
        self.assertEqual(sum(name == "continueFromReviewToProcess" for name, _ in self.calls), 1)

    def test_submission_timeout_is_not_retried(self):
        sequence = self.sequence()
        sequence[-4] = ("continueFromReviewToProcess", requests.exceptions.Timeout())
        with self.assertRaisesRegex(RuntimeError, "未自动重试"):
            self.run_checkout(sequence)
        self.assertEqual(sum(name == "continueFromReviewToProcess" for name, _ in self.calls), 1)

    def test_new_final_form_field_stops(self):
        self.review["placeOrder"]["b"] = {"newField": {"submit": True}}
        with self.assertRaisesRegex(ValueError, "新增表单字段"):
            self.run_checkout(self.sequence())
        self.assertFalse(any(name == "continueFromReviewToProcess" for name, _ in self.calls))

    def test_changed_submit_scope_stops(self):
        self.review["placeOrder"]["a"]["continueFromReviewToProcess"]["module"] = "/checkout"
        with self.assertRaisesRegex(ValueError, "表单范围"):
            self.run_checkout(self.sequence())
        self.assertFalse(any(name == "continueFromReviewToProcess" for name, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
