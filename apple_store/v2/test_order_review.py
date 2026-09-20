"""订单提交前核验；使用合成数据，不访问商城。"""

import copy
import unittest

from apple_order import check_review, read_order


class OrderReviewTests(unittest.TestCase):
    def setUp(self):
        self.config = {"数量": 1, "姓": "Test", "名": "Buyer",
                       "手机号": "13800000000", "邮箱": "buyer@example.com", "支付方式": "ALIPAY"}
        self.review = {
            "placeOrder": {"d": {"enableContinue": True}},
            "fulfillmentReview": {"reviewGroup-1": {
                "item-test": {"d": {"sku": "TEST/A"}, "itemQuantity": {"d": {"quantity": 1}}}}},
            "pickupContactReview": {"pickupContactInfo": {"d": {
                "lastName": "Test", "firstName": "Buyer", "fullDaytimePhone": "13800000000",
                "emailAddress": "buyer@example.com"}}},
            "billingReview": {"alipayReview": {"d": {"alipayReview": True}}},
            "summary": {"d": {"total": "RMB 100"}},
        }

    def check(self):
        return check_review({"checkout": {"review": self.review}}, self.config, "TEST/A", "RMB 100")

    def test_matching_review(self):
        self.assertEqual(self.check(), "RMB 100")

    def test_reject_changed_order(self):
        cases = [
            (("placeOrder", "d", "enableContinue"), False),
            (("summary", "d", "total"), "RMB 101"),
            (("billingReview", "alipayReview", "d", "alipayReview"), False),
            (("pickupContactReview", "pickupContactInfo", "d", "emailAddress"), "other@example.com"),
            (("fulfillmentReview", "reviewGroup-1", "item-test", "d", "sku"), "OTHER/A"),
            (("fulfillmentReview", "reviewGroup-1", "item-test", "itemQuantity", "d", "quantity"), True),
        ]
        original = copy.deepcopy(self.review)
        for path, value in cases:
            with self.subTest(path=path):
                self.review = copy.deepcopy(original)
                node = self.review
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                with self.assertRaises(ValueError):
                    self.check()

    def test_reject_extra_item(self):
        group = self.review["fulfillmentReview"]["reviewGroup-1"]
        group["item-extra"] = copy.deepcopy(group["item-test"])
        with self.assertRaises(ValueError):
            self.check()

    def test_reject_missing_contact(self):
        del self.review["pickupContactReview"]["pickupContactInfo"]["d"]["lastName"]
        with self.assertRaises(ValueError):
            self.check()

    def test_no_order_number_is_not_success(self):
        with self.assertRaises(ValueError):
            read_order({"thankYouInterstitial": {"d": {"orderNumber": ""}}})


if __name__ == "__main__":
    unittest.main()
