"""单账号串行结账；缺货时查询同一门店，成功一单即返回。"""
import sys
import time
from copy import deepcopy
from pathlib import Path
from threading import Event
from urllib.parse import parse_qsl, urlsplit
from playwright.sync_api import expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apple_store import apple_order as base
from sms import verify

CONTACT = ("checkout", "pickupContact", "selfPickupContact", "selfContact", "address")
STORE = ("checkout", "fulfillment", "pickupTab", "pickup", "storeLocator")


class StoreSelection541(base.HTTP541Error):
    """仅选店动作的 541 允许从购物袋重新进入结账。"""


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


def guest_login(session, browser, page, model):
    """访客态入口：浏览器生成含 deviceID 的表单，再按模型声明的 POST+args 初始化结账。"""
    with base.timing("浏览器生成访客表单及 deviceID"):
        fields = guest_fields(session, browser, page, model)
    response = base.post_action(session, page.url, model, ("signIn", "guestLogin"), "guestLogin", fields)
    payload = base.parse_json(response.text)
    base.check_business_errors(payload)
    redirect = payload["head"]["data"]
    if payload["head"]["status"] not in (302, "302") or redirect["method"].lower() != "post":
        raise ValueError("访客响应未声明 POST 初始化")
    return base.follow_navigation(session, base.request(
        session, "POST", base.apple_url(response.url, redirect["url"]),
        headers={"Referer": page.url}, form=redirect["args"]))


def check_existing_bag(model, config, sku):
    """购物袋为空返回 False；刚好只有配置的同一件商品返回 True；其它情况停止。

    商品以 SKU 判定：本流程的 SKU 由选品阶段的机型、颜色、容量决定，SKU 相同即三者相同。
    """
    items = base.require(model, "shoppingCart", "items")
    if not any(key.startswith("item-") for key in items):
        return False
    try:
        base.check_bag(model, sku, config["数量"])
    except ValueError as error:
        raise ValueError(f"{error}；请先清空购物袋再重跑") from None
    return True


def bag_page_for_checkout(session, page, config, product):
    """读取购物袋并按需加购，返回结账要用的购物袋响应。

    空袋按原流程加购；袋里刚好只有配置的同一件商品时跳过加购直接结账；
    其它情况一律停止，既不自动清空购物袋，也不追加商品。
    """
    sku = base.require(product, "partNumber")
    bag_page = base.follow_navigation(session, base.request(
        session, "GET", base.apple_url(page.url, "/shop/bag")))
    if check_existing_bag(base.read_model(bag_page), config, sku):
        print("购物袋里只有本配置的同一件商品，跳过加购。", flush=True)
        return bag_page
    _, form = base.fetch_summary(session, page, product)
    return base.add_to_bag(session, page, form)


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
    # Review 对手机固定显示八个圆点及后四位；邮箱字段只在访客态 Review 出现。
    if contact["fullDaytimePhone"] != "•" * 8 + config["手机号"][-4:]:
        raise ValueError("Review 脱敏手机号不一致")
    if "emailAddress" in contact:
        local, domain = config["邮箱"].split("@")
        masked_email = local[0] + "•" * (len(local) - 2) + local[-1] + "@" + domain
        if contact["emailAddress"] != masked_email:
            raise ValueError("Review 脱敏邮箱不一致")
    if review["summary"]["d"]["total"] != total or review["billingReview"]["alipayReview"]["d"]["alipayReview"] is not True:
        raise ValueError("Review 金额或支付方式不一致")
    if review["placeOrder"]["d"]["enableContinue"] is not True:
        raise ValueError("Review 不允许提交")


def check_prepared_checkout(model, sku, total):
    """校验当前结账商品与刚读取并验证数量的购物袋一致。"""
    fulfillment = base.require(model, "checkout", "fulfillment")
    location = base.require(fulfillment, "fulfillmentOptions", "d", "selectFulfillmentLocation")
    if location == "RETAIL":
        items = base.require(fulfillment, "pickupTab", "pickup", "items")
        rows = [value for key, value in items.items() if key.startswith("item-")]
    elif location == "HOME":
        groups = base.require(fulfillment, "deliveryTab", "delivery", "shipmentGroups")
        rows = []
        for key, group in groups.items():
            if key.startswith("shipmentGroup-"):
                for key, options in base.require(group, "shipmentOptionsGroups").items():
                    if key.startswith("shipmentOptionsGroup-"):
                        rows.extend(value for key, value in base.require(options, "items").items()
                                    if key.startswith("item-"))
    else:
        raise ValueError("已准备结账的履约方式未知")
    if len(rows) != 1 or base.require(rows[0], "d", "sku") != sku:
        raise ValueError("已准备结账的商品与配置不一致")
    # 当前 HAR 的 Fulfillment 项没有 quantity；单件通过已验证购物袋及单价/总价一致校验。
    if base.require(rows[0], "d", "unitPrice") != base.require(rows[0], "d", "totalPrice"):
        raise ValueError("已准备结账的商品不是单件金额")
    if base.require(model, "checkout", "companionBar", "orderSummary", "d", "total") != total:
        raise ValueError("已准备结账的金额与购物袋不一致")


def checkout(session, browser, bag_page, config, sku, *, prepared=None, stop_event=None):
    stop_event = stop_event if stop_event is not None else Event()
    name = config["账号"]

    def check_stopped():
        if stop_event.is_set():
            raise RuntimeError("用户已停止执行；未提交新的订单")

    model = base.read_model(bag_page)
    item = base.check_bag(model, sku, config["数量"])
    total = model["shoppingCart"]["summary"]["d"]["total"]
    page = prepared if prepared is not None else base.checkout_bag(session, bag_page, model, item)
    model = base.read_model(page, allow_pickup_unavailable=True)
    if "guestLogin" in model.get("signIn", {}):
        if prepared is not None or not config["允许访客结账"]:
            # 无人值守流程：登录态缺失直接停止，不等待人工登录、也不回退访客表单。
            raise ValueError(
                "结账入口被送到登录页：商城要求结账前重新验证一次 Apple ID 登录"
                "（页面标题为“登录 — 安全结账”）。请在 v2/session.py 的那个窗口里完成这次登录，"
                "登录后页面会回到结账流程，再重新运行 main.py")
        else:
            page = guest_login(session, browser, page, model)
            model = base.read_model(page)
    elif base.require(model, "checkout", "d", "page") != "Fulfillment":
        raise ValueError("结账入口既不是访客登录页，也不是履约页")

    sticky_headers = {}
    def action(path, name, form):
        nonlocal page, model
        check_stopped()
        try:
            response = base.post_action(
                session, page.url, model, path, name, form, extra_headers=sticky_headers)
        except base.HTTP541Error:
            if path == STORE and name == "select":
                raise StoreSelection541("选店 HTTP 541") from None
            raise
        # 跳转及解析错误不重发原动作，尤其不把后续页面的 541 算成 select 失败。
        page = base.follow_navigation(session, response)
        fulfillment_action = name in ("selectFulfillmentLocationAction", "search", "select",
                                      "continueFromFulfillmentToPickupContact")
        path_now = urlsplit(page.url).path
        if fulfillment_action and path_now == "/shop/sorry/session_expired":
            raise base.CheckoutExpired("库存等待期间结账过期")
        if path_now == "/shop/signIn":
            browser_cookies(session, browser)
            browser.goto(page.url, wait_until="domcontentloaded", timeout=30000)
            browser.bring_to_front()
            raise RuntimeError("[需要人工认证] Apple 要求重新登录或双重认证；请在该账号窗口完成后重新运行 main.py")
        model = base.read_model(page, allow_pickup_unavailable=fulfillment_action)
        # 登录态 Billing/Review 模型下发 x-as-actk；下发过一次后浏览器后续动作仍继续携带。
        action_key = model.get("meta", {}).get("h", {}).get("x-as-actk")
        if isinstance(action_key, str) and action_key:
            sticky_headers["x-as-actk"] = action_key
        print(f"[{config['账号']}] requests：{name}", flush=True)

    fulfillment = "checkout.fulfillment.fulfillmentOptions.selectFulfillmentLocation"
    action(("checkout", "fulfillment", "fulfillmentOptions"), "selectFulfillmentLocationAction", {fulfillment: "RETAIL"})
    prefix = ".".join(STORE)
    address = {"city": config["市"], "state": config["省"], "district": config["区"],
               "provinceCityDistrict": " ".join(
                   [config["市"], config["区"]] if config["省"] == config["市"]
                   else [config["省"], config["市"], config["区"]]), "countryCode": "CN"}
    attempt = 0

    def wait_stock(reason):
        interval = config["缺货轮询间隔秒"]
        print(f"[{name}] 第 {attempt} 次选店：{config['自提门店']} {reason}，{interval} 秒后重查。", flush=True)
        if stop_event.wait(interval):
            raise RuntimeError("用户已停止缺货轮询；未提交订单")

    if base.pickup_unavailable(model):
        print(f"[{name}] 当前默认地区无货；直接尝试配置门店。", flush=True)
    while True:
        check_stopped()
        attempt += 1
        locator = base.require(model, *STORE)
        fields = {prefix + ".showAllStores": locator["d"]["showAllStores"],
                  prefix + ".selectStore": config["自提门店"], prefix + ".searchInput": config["搜索地区"]}
        fields.update({prefix + ".address.stateCitySelectorForCheckout." + k: v for k, v in address.items()})
        action(STORE, "select", fields)
        if base.pickup_unavailable(model):
            wait_stock("直接选店返回缺货")
            continue
        stores = base.require(model, *STORE, "searchResults", "d", "retailStores")
        selected = next((s for s in stores if s["storeId"] == config["自提门店"]), None)
        if selected is None:
            raise ValueError(f"选店响应未包含目标门店：{config['自提门店']}；不按缺货重试")
        disabled = base.require(selected, "storeDisabled")
        if type(disabled) is not bool:
            raise ValueError("门店库存状态不是布尔值；停止")
        if disabled:
            wait_stock("当前不可取货")
            continue
        store_name = base.require(selected, "storeName")
        print(f"[{name}] 第 {attempt} 次选店：{store_name} 可取货，继续结账。", flush=True)
        if base.require(model, *STORE, "d", "selectStore") != config["自提门店"]:
            raise ValueError("服务端选中的自提门店与配置不一致")
        # 缺货时商品节点可能尚未生成；选店成功后、进入联系人之前严格核对。
        if prepared is not None:
            check_prepared_checkout(model, sku, total)
        action(("checkout", "fulfillment"), "continueFromFulfillmentToPickupContact", {fulfillment: "RETAIL", **fields})
        if base.pickup_unavailable(model):
            wait_stock("进入联系人前已无货")
            continue
        break
    base.require(model, "checkout", "pickupContact")
    if model["checkout"]["companionBar"]["orderDetails"]["fulfillmentCompanionBar"]["pickupSummary"]["d"]["store_name"] != store_name:
        raise ValueError("自提摘要门店不一致")
    prefix = ".".join(CONTACT)
    fields = {prefix + "." + field: config[key] for field, key in (
        ("lastName", "姓"), ("firstName", "名"), ("fullDaytimePhone", "手机号"))}
    token_key = prefix + ".verificationModule.verificationToken"
    if "contactVerify" in base.require(model, *CONTACT).get("a", {}):
        # 访客态：提交联系人触发验证；服务端要求时再由 sms 提供验证令牌。
        contact_model = deepcopy(model)
        contact_url = page.url
        fields[prefix + ".emailAddress"] = config["邮箱"]
        fields[token_key] = base.require(model, *CONTACT, "verificationModule", "d", "verificationToken")
        action(CONTACT, "contactVerify", fields)
        data = base.require(model, *CONTACT, "verificationModule", "d")
        if data["authRequired"]:
            if prepared is not None or not config["允许访客结账"]:
                raise ValueError("无人值守结账要求额外短信验证，流程停止；未发送短信")
            fields[token_key] = verify(session, contact_url, data, config["手机号"])
            action(CONTACT + ("verificationModule",), "submitVerificationToken", {token_key: fields[token_key]})
            data = base.require(model, *CONTACT, "verificationModule", "d")
        if not data["isVerified"] or data["authRequired"]:
            raise ValueError("服务端未确认联系人验证成功")
        contact_model["meta"]["h"] = model["meta"]["h"]
        model = contact_model  # 验证响应只含局部模块；继续动作取原模型，头取最新响应。
    else:
        # 登录态：模型不下发 contactVerify，也不提供 isVerified，令牌为空即可进入 Billing。
        verification = base.require(model, *CONTACT, "verificationModule", "d")
        if verification["authRequired"] is not False:
            raise ValueError("模型要求联系人验证，但未提供 contactVerify 动作")
        fields[token_key] = base.require(model, *CONTACT, "verificationModule", "d", "verificationToken")
    fields.update({"checkout.pickupContact.selfPickupContact.nationalIdSelf.nationalIdSelf": config["证件后四位"],
        "checkout.pickupContact.eFapiaoSelector.selectFapiao": config["发票类型"],
        "checkout.pickupContact.eFapiaoSelector.ePersonalFapiao.invoiceHeader": model["checkout"]["pickupContact"]["eFapiaoSelector"]["ePersonalFapiao"]["d"]["invoiceHeader"]})
    action(("checkout", "pickupContact"), "continueFromPickupContactToBilling", fields)
    payment = "checkout.billing.billingOptions."
    fields = {payment + "selectBillingOption": config["支付方式"], payment + "bankLookUp.selectBank":
              model["checkout"]["billing"]["billingOptions"]["bankLookUp"]["d"]["selectBank"]}
    consent = model["checkout"]["locationConsent"]["d"]["locationConsent"]
    # continueFromBillingToReview 绑定整个 billing 模块，请求体已含 selectBillingOption，
    # 正常一次即可选中支付方式并进入确认页；未生效时才补发单选动作重试。
    action(("checkout", "billing"), "continueFromBillingToReview", fields)
    if model["checkout"]["d"]["page"] != "Review":
        action(("checkout", "billing", "billingOptions"), "selectBillingOptionAction", {
            **fields, "checkout.locationConsent.locationConsent": consent})
        action(("checkout", "billing"), "continueFromBillingToReview", fields)
        if model["checkout"]["d"]["page"] != "Review":
            raise ValueError("支付方式未生效，仍停留在支付页")
    check_review(model, config, sku, total)
    check_stopped()
    print(f"[{name}] 即将提交一次创单请求；之后无论成功或结果不明，均不重新下单。", flush=True)
    response = base.post_action(session, page.url, model, ("checkout", "review", "placeOrder"),
                                "continueFromReviewToProcess", {}, extra_headers=sticky_headers)
    payload = base.parse_json(response.text)
    base.check_business_errors(payload)
    if payload["head"]["status"] not in (302, "302"):
        raise ValueError("提交结果未知，不可重复提交")
    target = base.apple_url(response.url, payload["head"]["data"]["url"])
    if urlsplit(target).path != "/shop/checkout/status":
        raise ValueError("未返回已知订单处理页，不可重复提交")
    result = base.query_order(session, target)
    # 供 main.py 记录每个账号的结果；不改动 query_order 的返回契约。
    result.update({"SKU": sku, "数量": config["数量"], "金额": total, "门店": store_name})
    return result
