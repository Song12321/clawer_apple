"""Console timing without request credentials or payloads."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from time import perf_counter
from urllib.parse import parse_qsl, urlsplit

account_name = ContextVar("account_name", default="")


ACTIONS = {
    "checkout": "购物袋结账", "guestLogin": "访客登录",
    "selectFulfillmentLocationAction": "选择自提方式", "search": "搜索自提门店",
    "select": "选择自提门店", "continueFromFulfillmentToPickupContact": "进入联系人页面",
    "contactVerify": "检查联系人验证要求", "submitVerificationToken": "提交联系人验证令牌",
    "continueFromPickupContactToBilling": "提交联系人并进入支付页面",
    "selectBillingOptionAction": "选择支付方式", "continueFromBillingToReview": "进入订单确认页",
    "continueFromReviewToProcess": "创建订单", "checkStatus": "查询订单处理状态",
}
PATHS = {
    "/shop/fulfillment-messages": "验证履约会话", "/shop/bag": "读取购物袋",
    "/shop/updateSummary": "读取商品购买摘要", "/shop/signIn": "读取访客登录页",
    "/shop/checkout/start": "初始化结账", "/shop/checkout": "读取结账页面",
    "/shop/checkout/status": "读取订单处理页", "/shop/checkout/interstitial": "读取订单号",
    "/identity/verification": "初始化身份验证", "/identity/verification/load": "加载身份会话",
    "/identity/verification/generate/phone": "发送短信验证码",
    "/identity/verification/validate/phone": "提交并校验短信验证码",
}


def request_label(method, url):
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query))
    purpose = ACTIONS.get(query.get("_a"), PATHS.get(parsed.path, "读取页面"))
    if "add-to-cart" in query:
        purpose = "加购商品"
    elif query.get("step") == "attach":
        purpose = "处理配件页"
    return f"{purpose} | {method} {parsed.hostname}{parsed.path}"


@contextmanager
def timing(label):
    if account_name.get():
        label = f"[{account_name.get()}] {label}"
    start = perf_counter()
    print(f"[{datetime.now():%H:%M:%S.%f}] 开始 | {label}", flush=True)
    result = {"started": start}
    try:
        yield result
    except BaseException as error:
        print(f"[{datetime.now():%H:%M:%S.%f}] 失败 | {label} | {type(error).__name__} | 耗时 {perf_counter()-start:.3f}s", flush=True)
        raise
    else:
        status = f" | HTTP {result['status']}" if "status" in result else ""
        if "headers_seconds" in result:
            status += (f" | 响应头 {result['headers_seconds']:.3f}s"
                       f" | 后续接收 {result['remaining_seconds']:.3f}s")
        print(f"[{datetime.now():%H:%M:%S.%f}] 完成 | {label}{status} | 耗时 {perf_counter()-start:.3f}s", flush=True)


def response_timing(log, response):
    received = perf_counter() - log["started"]
    headers = response.elapsed.total_seconds()
    log.update(status=response.status_code, headers_seconds=headers,
               remaining_seconds=received - headers)
