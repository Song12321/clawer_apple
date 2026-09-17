"""Apple 商城请求流程；未确认的接口契约必须补齐后才能创单。"""

import json
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


# 用户配置集中在这里；不保存 Cookie、验证码或历史会话令牌。
# 机型、颜色、容量使用商品页面中的 familyType、dimensionColor、dimensionCapacity。
CONFIG = {
    "商品页面": "",
    "机型": "",
    "颜色": "",
    "容量": "",
    "数量": None,
    "自提门店": "",
    "姓": "",
    "名": "",
    "手机号": "",
    "邮箱": "",
    "发票类型": "",
    "支付方式": "",
}


def require(data, *path):
    """按完整键名读取必填数据，键名本身可以含有点号。"""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"响应缺少字段：{' / '.join(path)}")
        current = current[key]
    if current is None:
        raise ValueError(f"响应字段为空：{' / '.join(path)}")
    return current


def apple_url(base_url, target):
    if not isinstance(target, str) or not target.strip():
        raise ValueError("请求地址为空或格式错误")
    url = urljoin(base_url, target)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".apple.com.cn")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("请求地址不是 Apple 中国商城 HTTPS 地址")
    return url


def validate_config(config):
    for key in CONFIG:
        value = require(config, key)
        if key == "数量":
            if type(value) is not int or value < 1:
                raise ValueError("数量必须为正整数")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"请填写配置：{key}")
    apple_url("", config["商品页面"])


def request(session, method, url, *, headers=None, form=None):
    # 不自动重试或重定向：未知跳转不能被当作成功，创单也不能重复提交。
    url = apple_url("", url)
    try:
        response = session.request(
            method, url, headers=headers, data=form,
            timeout=30, allow_redirects=False,
        )
    except requests.RequestException:
        # requests 的原始异常可能包含带动态凭据的 URL，不直接打印。
        raise RuntimeError("请求失败或超时；未自动重试，需先确认服务端处理结果") from None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"收到未处理的 HTTP 状态：{response.status_code}")
    return response


def parse_json(text):
    try:
        result = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("响应不是有效 JSON") from None
    if not isinstance(result, dict):
        raise ValueError("响应 JSON 根节点必须是对象")
    return result


def check_business_errors(model):
    # 抓包中业务状态 200 仍可能携带模块 m 中的 ERROR。
    # 只报告字段位置，不回显服务端可能包含个人信息的错误文本。
    def visit(node, path):
        if isinstance(node, dict):
            if isinstance(node.get("m"), list):
                for message in node["m"]:
                    if isinstance(message, dict) and message.get("level") == "ERROR":
                        raise ValueError(f"业务字段校验失败：{path or '根节点'}")
            for key, value in node.items():
                visit(value, f"{path}/{key}")
        elif isinstance(node, list):
            for value in node:
                visit(value, path)
    visit(model, "")


def read_model(response):
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if content_type == "application/json":
        payload = parse_json(response.text)
        status = require(payload, "head", "status")
        if type(status) not in (str, int) or status not in (200, "200"):
            raise ValueError("JSON 响应不是成功模型；需单独处理跳转或错误")
        model = require(payload, "body")
    elif content_type == "text/html":
        soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")
        scripts = soup.select('script#init_data[type="application/json"]')
        if len(scripts) != 1:
            raise ValueError("页面缺少唯一的 init_data 模型，可能未进入预期页面")
        model = parse_json(scripts[0].get_text())
    else:
        raise ValueError("不支持的响应 Content-Type")
    if not isinstance(model, dict):
        raise ValueError("页面模型必须是对象")
    check_business_errors(model)
    return model


def select_product(html, config):
    # productSelectionData 是脚本中的 JSON 对象，不执行页面 JavaScript。
    soup = BeautifulSoup(html, "html.parser")
    marker = "productSelectionData:"
    scripts = [s.get_text() for s in soup.find_all("script") if marker in s.get_text()]
    if len(scripts) != 1 or scripts[0].count(marker) != 1:
        raise ValueError("没有找到唯一的 productSelectionData")
    source = scripts[0].split(marker, 1)[1].lstrip()
    try:
        selection, _ = json.JSONDecoder().raw_decode(source)
    except ValueError:
        raise ValueError("商品选配数据不是有效 JSON") from None
    products = require(selection, "products")
    if not isinstance(products, list):
        raise ValueError("商品列表格式错误")
    matches = [p for p in products if (
        require(p, "familyType") == config["机型"]
        and require(p, "dimensionColor") == config["颜色"]
        and require(p, "dimensionCapacity") == config["容量"]
    )]
    if len(matches) != 1:
        raise ValueError("指定机型、颜色和容量未唯一匹配到商品")
    require(matches[0], "partNumber")
    return matches[0]


def read_add_form(model, sku):
    summary = require(model, "response", "summarySection", "summary")
    if require(summary, "isBuyable") is not True or require(summary, "disabled") is not False:
        raise ValueError("当前商品不可购买")
    soup = BeautifulSoup(require(summary, "buyNowButton"), "html.parser")
    forms = soup.find_all("form")
    if len(forms) != 1:
        raise ValueError("购买摘要没有唯一表单")
    fields = {}
    for field in forms[0].select('input[type="hidden"][name]:not([disabled])'):
        name = field["name"]
        if name in fields or "value" not in field.attrs:
            raise ValueError("加购隐藏字段重复或缺少值")
        fields[name] = field["value"]
    if require(fields, "product") != sku:
        raise ValueError("加购摘要与选配 SKU 不一致")
    require(fields, "purchaseOption")
    require(fields, "step")
    # 仅返回已观察到的有效隐藏字段；异步端点与按钮序列化尚未确认。
    return fields


def check_bag(model, sku, quantity):
    items = require(model, "shoppingCart", "items")
    rows = [(key, value) for key, value in items.items() if key.startswith("item-")]
    if len(rows) != 1:
        raise ValueError("购物袋不是指定的单一商品，请核对已有商品")
    key, row = rows[0]
    if require(row, "d", "sku") != sku:
        raise ValueError("购物袋 SKU 与选配不一致")
    actual = require(row, "itemQuantity", "d", "quantity")
    if type(actual) is not int or actual != quantity:
        raise ValueError("购物袋数量与配置不一致；数量更新契约尚未确认")
    require(model, "shoppingCart", "summary", "d", "total")
    return key


def model_headers(model):
    source = require(model, "meta", "h")
    headers = {}
    for name in ("x-aos-model-page", "modelVersion", "syntax", "x-aos-stk"):
        value = require(source, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"模型请求头无效：{name}")
        headers[name] = value
    return headers


def read_order(model):
    data = require(model, "thankYouInterstitial", "d")
    number = require(data, "orderNumber")
    if not isinstance(number, str) or not number.strip():
        raise ValueError("结果页没有有效订单号")
    return {
        "订单号": number,
        "订单链接": apple_url("", require(data, "orderStatusUrl")),
    }


def query_order(session, status_url):
    """使用当前结账会话查询结果；不负责创建订单或恢复历史 Cookie。"""
    page = request(session, "GET", status_url)
    model = read_model(page)
    action_url = apple_url(page.url, require(model, "spinner", "a", "checkStatus", "url"))
    headers = model_headers(model)
    parsed = urlsplit(page.url)
    headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "Fetch",
        "Origin": f"{parsed.scheme}://{parsed.netloc}",
        "Referer": page.url,
    })
    # 本样本只确认一次空体 POST 后返回结果页，不添加猜测性的轮询。
    response = request(session, "POST", action_url, headers=headers)
    payload = parse_json(response.text)
    check_business_errors(payload)
    status = require(payload, "head", "status")
    if type(status) not in (str, int) or status not in (302, "302"):
        raise ValueError("状态检查未返回已确认的结果页跳转；停止，不重复提交订单")
    result_url = apple_url(response.url, require(payload, "head", "data", "url"))
    if urlsplit(result_url).path != "/shop/checkout/interstitial":
        raise ValueError("状态检查跳转到其他页面，尚未取得订单结果")
    return read_order(read_model(request(session, "GET", result_url)))


def main():
    validate_config(CONFIG)
    with requests.Session() as session:
        page = request(session, "GET", CONFIG["商品页面"])
        product = select_product(page.content, CONFIG)
        require(product, "partNumber")
        # 下一步应请求 updateSummary；实际方法与完整参数尚未确认。
        # 不把页面声明或历史样本字段猜成请求契约，也不提前执行加购。
        raise NotImplementedError(
            "已匹配商品，但 updateSummary 的实际方法与完整入参尚未确认。"
            "主商品加购、访客初始化、联系人验证及最终创单契约也需补齐；"
            "当前程序未加入购物袋、未创建订单。"
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        raise SystemExit(str(exc)) from None
