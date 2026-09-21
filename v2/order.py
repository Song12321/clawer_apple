"""本次 HAR 的单件、自提、个人发票、支付宝串行结账。"""
import sys
import time
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from playwright.sync_api import expect
from sms import verify

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apple_store import apple_order as base

CONTACT = ("checkout", "pickupContact", "selfPickupContact", "selfContact", "address")
STORE = ("checkout", "fulfillment", "pickupTab", "pickup", "storeLocator")


def browser_cookies(session, page):
    client = page.context.new_cdp_session(page)
    try:
        cookies = []
        for c in session.cookies:
            item = {"name": c.name, "value": c.value, "path": c.path, "secure": c.secure,
                    "httpOnly": c.has_nonstandard_attr("HttpOnly")}
            if c.domain_specified:
                item["domain"] = c.domain
            else:
                item["url"] = "https://" + c.domain + c.path
            if c.expires is not None:
                item["expires"] = c.expires
            cookies.append(item)
        client.send("Network.setCookies", {"cookies": cookies})
    finally:
        client.detach()


def guest_fields(session, page, response, model):
    browser_cookies(session, page)
    target = base.apple_url(response.url, model["signIn"]["guestLogin"]["a"]["guestLogin"]["url"])
    captured = []

    def intercept(route):
        req = route.request
        if req.url == target and req.method == "POST":
            captured.append(req.post_data)
            route.abort()
        elif req.is_navigation_request() and req.url == response.url:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=response.content)
        elif urlsplit(req.url).path.startswith("/shop/") and req.method == "POST":
            route.abort()
        else:
            route.continue_()

    page.route("**/*", intercept)
    try:
        page.goto(response.url, wait_until="domcontentloaded")
        page.locator('[id="signIn.guestLogin.guestLogin"]').click()
        accept = page.locator('#consent-overlay-accept-button')
        consent_done = False
        deadline = time.monotonic() + 30
        while not captured and time.monotonic() < deadline:
            if not consent_done and accept.is_visible():
                # 用户已授权同意访客隐私条款；policiesAccepted 由官网继续按钮设置。
                policies = model["signIn"]["guestLogin"]["consentOverlay"]["d"]["policies"]
                for policy in policies:
                    checkbox_id = "signIn.guestLogin.consentOverlay." + policy["name"]
                    checkbox = page.locator('[id="' + checkbox_id + '"]')
                    if not checkbox.is_checked():
                        page.locator('label[for="' + checkbox_id + '"] .form-checkbox-indicator').click()
                    expect(checkbox).to_be_checked()
                accept.click()
                consent_done = True
            page.wait_for_timeout(250)
        if not captured:
            raise ValueError("未取得当次访客表单")
        fields = dict(parse_qsl(captured[0], keep_blank_values=True))
        if not fields["signIn.guestLogin.deviceID"]:
            raise ValueError("当次 deviceID 为空")
        print("访客表单已生成，隐私同意自动处理，由 requests 提交。")
        base.copy_browser_cookies(session, base.read_page_cookies(page, [response.url, target]))
        return fields
    finally:
        page.unroute("**/*", intercept)


def check_review(model, config, sku, total):
    review = model["checkout"]["review"]
    rows = [row for key, group in review["fulfillmentReview"].items() if key.startswith("reviewGroup-")
            for name, row in group.items() if name.startswith("item-")]
    if len(rows) != 1 or rows[0]["d"]["sku"] != sku or rows[0]["itemQuantity"]["d"]["quantity"] != config["数量"]:
        raise ValueError("Review 商品或数量不一致")
    contact = review["pickupContactReview"]["pickupContactInfo"]["d"]
    for field, key in (("lastName", "姓"), ("firstName", "名")):
        if contact[field] != config[key]:
            raise ValueError("Review 联系人不一致")
    # 本次 Review 对手机固定显示八个圆点及后四位，邮箱隐藏本地部分中间字符。
    local, domain = config["邮箱"].split("@")
    masked_email = local[0] + "•" * (len(local) - 2) + local[-1] + "@" + domain
    if contact["fullDaytimePhone"] != "•" * 8 + config["手机号"][-4:] or contact["emailAddress"] != masked_email:
        raise ValueError("Review 脱敏联系方式不一致")
    if review["summary"]["d"]["total"] != total or review["billingReview"]["alipayReview"]["d"]["alipayReview"] is not True:
        raise ValueError("Review 金额或支付方式不一致")
    if review["placeOrder"]["d"]["enableContinue"] is not True:
        raise ValueError("Review 不允许提交")


def checkout(session, browser, bag_page, config, sku):
    model = base.read_model(bag_page)
    item = base.check_bag(model, sku, config["数量"])
    total = model["shoppingCart"]["summary"]["d"]["total"]
    page = base.checkout_bag(session, bag_page, model, item)
    model = base.read_model(page)
    fields = guest_fields(session, browser, page, model)
    response = base.post_action(session, page.url, model, ("signIn", "guestLogin"), "guestLogin", fields)
    payload = base.parse_json(response.text)
    base.check_business_errors(payload)
    redirect = payload["head"]["data"]
    if payload["head"]["status"] not in (302, "302") or redirect["method"].lower() != "post":
        raise ValueError("访客响应未声明 POST 初始化")
    page = base.follow_navigation(session, base.request(session, "POST", base.apple_url(response.url, redirect["url"]),
        headers={"Referer": page.url}, form=redirect["args"]))
    model = base.read_model(page)

    def action(path, name, form):
        nonlocal page, model
        page = base.follow_navigation(session, base.post_action(session, page.url, model, path, name, form))
        model = base.read_model(page)
        print("requests：" + name)

    fulfillment = "checkout.fulfillment.fulfillmentOptions.selectFulfillmentLocation"
    action(("checkout", "fulfillment", "fulfillmentOptions"), "selectFulfillmentLocationAction", {fulfillment: "RETAIL"})
    locator = base.require(model, *STORE)
    prefix = ".".join(STORE)
    fields = {prefix + ".showAllStores": locator["d"]["showAllStores"],
              prefix + ".selectStore": locator["d"]["selectStore"], prefix + ".searchInput": config["搜索地区"]}
    address = {"city": config["市"], "state": config["省"], "district": config["区"],
               "provinceCityDistrict": config["市"] + " " + config["区"], "countryCode": "CN"}
    fields.update({prefix + ".address.stateCitySelectorForCheckout." + k: v for k, v in address.items()})
    action(STORE, "search", fields)
    stores = base.require(model, *STORE, "searchResults", "d", "retailStores")
    selected = next(s for s in stores if s["storeId"] == config["自提门店"])
    if selected["storeDisabled"]:
        raise ValueError("目标门店不可取货")
    store_name = selected["storeName"]
    fields[prefix + ".selectStore"] = config["自提门店"]
    action(STORE, "select", fields)
    if base.require(model, *STORE, "d", "selectStore") != config["自提门店"]:
        raise ValueError("门店选择未生效")
    action(("checkout", "fulfillment"), "continueFromFulfillmentToPickupContact", {fulfillment: "RETAIL", **fields})
    if model["checkout"]["companionBar"]["orderDetails"]["fulfillmentCompanionBar"]["pickupSummary"]["d"]["store_name"] != store_name:
        raise ValueError("自提摘要门店不一致")
    contact_model = deepcopy(model)
    contact_url = page.url
    prefix = ".".join(CONTACT)
    fields = {prefix + "." + field: config[key] for field, key in (
        ("lastName", "姓"), ("firstName", "名"), ("fullDaytimePhone", "手机号"), ("emailAddress", "邮箱"))}
    token_key = prefix + ".verificationModule.verificationToken"
    fields[token_key] = base.require(model, *CONTACT, "verificationModule", "d", "verificationToken")
    action(CONTACT, "contactVerify", fields)
    data = base.require(model, *CONTACT, "verificationModule", "d")
    if data["authRequired"]:
        fields[token_key] = verify(session, contact_url, data, config["手机号"])
        action(CONTACT + ("verificationModule",), "submitVerificationToken", {token_key: fields[token_key]})
        data = base.require(model, *CONTACT, "verificationModule", "d")
    if not data["isVerified"] or data["authRequired"]:
        raise ValueError("服务端未确认联系人验证成功")
    contact_model["meta"]["h"] = model["meta"]["h"]
    model = contact_model  # 验证响应只含局部模块；继续动作取原模型，头取最新响应。
    fields.update({"checkout.pickupContact.selfPickupContact.nationalIdSelf.nationalIdSelf": config["证件后四位"],
        "checkout.pickupContact.eFapiaoSelector.selectFapiao": config["发票类型"],
        "checkout.pickupContact.eFapiaoSelector.ePersonalFapiao.invoiceHeader": model["checkout"]["pickupContact"]["eFapiaoSelector"]["ePersonalFapiao"]["d"]["invoiceHeader"]})
    action(("checkout", "pickupContact"), "continueFromPickupContactToBilling", fields)
    payment = "checkout.billing.billingOptions."
    fields = {payment + "selectBillingOption": config["支付方式"], payment + "bankLookUp.selectBank":
              model["checkout"]["billing"]["billingOptions"]["bankLookUp"]["d"]["selectBank"]}
    action(("checkout", "billing", "billingOptions"), "selectBillingOptionAction", {
        **fields, "checkout.locationConsent.locationConsent": model["checkout"]["locationConsent"]["d"]["locationConsent"]})
    if model["checkout"]["d"]["page"] == "Billing":
        action(("checkout", "billing"), "continueFromBillingToReview", fields)
    check_review(model, config, sku, total)
    response = base.post_action(session, page.url, model, ("checkout", "review", "placeOrder"), "continueFromReviewToProcess", {})
    payload = base.parse_json(response.text)
    base.check_business_errors(payload)
    if payload["head"]["status"] not in (302, "302"):
        raise ValueError("提交结果未知，不可重复提交")
    target = base.apple_url(response.url, payload["head"]["data"]["url"])
    if urlsplit(target).path != "/shop/checkout/status":
        raise ValueError("未返回已知订单处理页，不可重复提交")
    return base.query_order(session, target)
